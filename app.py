import certifi
import os
import random

from flask import Flask, request, jsonify, redirect, make_response, render_template
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from pymongo import MongoClient
import re
from bson.objectid import ObjectId

from web_scraper import Scraper  # Assuming web_scraper.py is in the same directory

from image_recognizer import get_image_labels_and_entities
from gcs_uploader import upload_image_stream_to_gcs_for_user, \
    ALLOWED_IMAGE_EXTENSIONS  # Keep allowed_file defined locally or import it too
from classifier import get_description, classify
from semantic_search import process_activity_and_get_points
from user import User
from photo import Photo
from quest import Quest, POSSIBLE_QUEST_CATEGORIES

load_dotenv()

app = Flask(__name__)
scraper = Scraper()

MONGO_URI = os.getenv("MONGO_CONNECTION_STRING")

client = MongoClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
db = client["karma"]
users_collection = db["users"]
quests_collection = db["quests"]
photos_collection = db["photos"]


def get_user_session():
    return request.cookies.get('user_session')


def allowed_file(filename):
    """Checks if the file's extension is allowed."""
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in {ext.lstrip('.') for ext in ALLOWED_IMAGE_EXTENSIONS}


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json
        if not data or "user_id" not in data:
            return jsonify({"error": "user_id is required"}), 400

        user_id = data["user_id"]
        new_user = data["new_user"]

        if not new_user:
            response = make_response(redirect('/'))
        else:
            response = make_response(redirect('/onboarding_pg0'))

        response.set_cookie('user_session', user_id)
        return response

    return render_template('login.html')


@app.route('/logout')
def logout():
    response = make_response(redirect('/login'))
    response.delete_cookie('user_session')
    return response


@app.before_request
def redirect_to_https():  # redirecting to https is needed for camera functionality
    if 'DYNO' in os.environ and request.headers.get('X-Forwarded-Proto', 'http') != 'https':
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)


@app.before_request
def check_user_session():
    if request.endpoint not in [
        "login",
        "static",
        "redirect_to_https",
        "url_to_user",
        "scan_qr",
        "get_dynamsoft_license"
    ]:
        user_session = get_user_session()
        if not user_session:
            if request.endpoint:
                print("redirecting, user not logged in!!" + request.endpoint)
            return redirect('/login')


@app.route("/")
def index():
    return render_template("index.html")


# --- Updated /quests route ---
@app.route("/quests")
def quests():
    user_session_id_str = get_user_session()
    if not user_session_id_str:
        return redirect('/login')

    try:
        user_object_id = ObjectId(user_session_id_str)
        current_user = User.get_user_by_id(users_collection, user_object_id)
        user_name_for_template = current_user.name if current_user else "User"

        if not current_user:
            print(f"User {user_session_id_str} not found in DB. Redirecting to login.")
            return redirect('/login')

        # --- Handle existing expired pending quests for the user ---
        print(f"Checking for existing pending quests for user {user_session_id_str}...")
        # Fetch as a list to iterate and potentially modify the collection during iteration
        pending_quests_docs = list(quests_collection.find({"user_to_id": user_session_id_str, "status": "pending"}))

        for quest_doc in pending_quests_docs:
            quest_obj = Quest.from_mongo(quest_doc)
            if quest_obj.is_expired():  # is_expired() should use quest_doc's expiry_time
                print(f"Found expired pending quest: {quest_obj.quest_id_str} for user {user_session_id_str}")
                # handle_expiry_and_regenerate_data deletes the old quest and returns data for a new one.
                new_system_quest_data = quest_obj.handle_expiry_and_regenerate_data(
                    quests_collection,
                    POSSIBLE_QUEST_CATEGORIES
                )
                if new_system_quest_data:
                    # Save the new system quest that replaces the expired one
                    quests_collection.insert_one(new_system_quest_data)
                    new_regenerated_quest_id_str = new_system_quest_data["quest_id_str"]
                    print(
                        f"Replaced expired quest {quest_obj.quest_id_str} with new system quest {new_regenerated_quest_id_str} for user {user_session_id_str}.")

                    # Update user's quest list in DB: remove old, add new
                    users_collection.update_one(
                        {"_id": user_object_id},
                        {"$pull": {"quests": quest_obj.quest_id_str}}
                    )
                    users_collection.update_one(
                        {"_id": user_object_id},
                        {"$push": {"quests": new_regenerated_quest_id_str}}
                    )
                else:
                    # This case implies handle_expiry_and_regenerate_data decided not to regenerate
                    # or failed, which might mean the quest wasn't truly expired or pending from its perspective.
                    print(
                        f"Quest {quest_obj.quest_id_str} was not regenerated after expiry check (possibly already handled or not expired).")

        # Re-fetch active quests after handling expiries
        user_active_quests = Quest.get_quests_for_user(quests_collection, user_session_id_str, status="pending")

        # If no pending quests exist after expiry handling, generate a new one
        if not user_active_quests:
            print(
                f"No pending quests for user {user_session_id_str} after expiry check. Generating a new system quest.")
            target_category = random.choice(POSSIBLE_QUEST_CATEGORIES)
            duration_seconds = 24 * 60 * 60  # Default 24 hours

            # Use Quest.generate_new_system_quest_data from quest.py
            new_quest_data = Quest.generate_new_system_quest_data(
                user_to_id=user_session_id_str,  # Pass user_id as string
                target_category=target_category,
                duration_seconds=duration_seconds
            )
            # Save the new quest data to the quests_collection
            quests_collection.insert_one(new_quest_data)
            new_quest_id_str = new_quest_data["quest_id_str"]
            print(f"New system quest {new_quest_id_str} generated and saved for user {user_session_id_str}.")

            # Add the quest_id_str to the user's 'quests' list in their document
            users_collection.update_one(
                {"_id": user_object_id},
                {"$push": {"quests": new_quest_id_str}}
            )
            # Fetch this new quest to display it
            # Quest.from_mongo expects a dict that includes _id if it's from DB.
            # Here, new_quest_data doesn't have _id yet, but Quest constructor can handle it.
            newly_generated_quest_object = Quest(
                user_to_id=new_quest_data["user_to_id"],
                target_category=new_quest_data["target_category"],
                expiry_time=new_quest_data["expiry_time"],
                quest_id_str=new_quest_data["quest_id_str"]
                # mongo_id will be assigned when/if this object is saved via its own save_to_db
            )
            user_active_quests = [newly_generated_quest_object]

        print(f"Displaying {len(user_active_quests)} pending quests for user {user_session_id_str}.")

        return render_template("quests.html",
                               user_quests=user_active_quests,
                               user_name=user_name_for_template)
    except Exception as e:
        print(f"Error fetching quests for user {user_session_id_str}: {e}")
        import traceback
        traceback.print_exc()
        return render_template("quests.html", user_quests=[], user_name=get_user_session(),
                               error_message="Could not load quests.")


@app.route("/capture")
def capture():
    return render_template("capture.html")


@app.route("/onboarding_pg0")
def onboarding_pg0():
    return render_template("onboarding_pg0.html")


@app.route('/onboarding_pg1', methods=['GET', 'POST'])
def onboarding_pg1():
    if request.method == 'POST':
        data = request.json
        if not data or "user_id" not in data:
            return jsonify({"error": "user_id is required"}), 400

        friend_id = data["user_id"]
        current_user = ObjectId(get_user_session())
        friend_user = ObjectId(friend_id)

        response = make_response(redirect('/onboarding_pg2'))
        users_collection.update_one(
            {"_id": current_user},
            {"$addToSet": {"friends": friend_user}}
        )
        users_collection.update_one(
            {"_id": friend_user},
            {"$addToSet": {"friends": current_user}}
        )

        return response

    return render_template('onboarding_pg1.html')


@app.route('/onboarding_pg2')
def onboarding_pg2():
    redirect('/quests')

    return render_template("onboarding_pg2.html")


@app.route('/onboarding_pg3', methods=['GET'])
def onboarding_pg3():
    try:

        current_user = get_user_session()

        # Generate quest data using the method from Quest class
        # This assumes Quest.generate_new_system_quest_data is available and works as expected
        # It returns a dictionary, not a Quest object directly, which is suitable for DB insertion.
        target_category = random.choice(POSSIBLE_QUEST_CATEGORIES)
        duration_seconds = 60 * 60  # Default 1 hours for an onboarding quest

        new_quest_data = Quest.generate_new_system_quest_data(
            user_to_id=current_user,  # Quest class expects user_to_id as string
            target_category=target_category,
            duration_seconds=duration_seconds
        )

        # Save the new quest to the quests_collection
        result = quests_collection.insert_one(new_quest_data)
        new_quest_mongo_id = result.inserted_id
        new_quest_id_str = new_quest_data["quest_id_str"]  # Get the app-level quest ID

        print(
            f"New onboarding quest {new_quest_id_str} created for user {current_user} with MongoDB ID {new_quest_mongo_id}.")

        # Add the quest_id_str to the user's 'quests' list in their document
        update_user_result = users_collection.update_one(
            {"_id": current_user},
            {"$push": {"quests": new_quest_id_str}}
        )

        if update_user_result.modified_count > 0:
            print(f"Quest {new_quest_id_str} added to user {current_user}'s quest list.")
        else:
            # This might happen if the user doc was found but update failed, or if $push didn't modify (e.g., already there, though unlikely for new quest)
            print(
                f"Warning: User {current_user}'s quest list might not have been updated, or quest ID already present.")

        return jsonify({
            "message": "Onboarding quest generated successfully.",
            "user_id": current_user,
            "quest_id_str": new_quest_id_str,
            "target_category": target_category,
            "expiry_time": new_quest_data["expiry_time"].isoformat()  # Return expiry time
        }), 201  # 201 Created

    except RuntimeError as e:  # Catch if placeholder Quest functions are called
        print(f"A critical imported function for Quest generation is missing: {e}")
        return jsonify({"error": f"Server configuration error for quest generation: {e}"}), 500
    except Exception as e:
        print(f"Error in /generate_onboarding_quest: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500


@app.route('/friends')
def friends():
    try:
        print(get_user_session())
        current_user = User.get_user_by_id(users_collection, get_user_session())
        all_users_from_db = current_user.friends + [ObjectId(get_user_session())]
        user_objects = [User.get_user_by_id(users_collection, user_objectid) for user_objectid in all_users_from_db if
                        User.get_user_by_id(users_collection, user_objectid) is not None]
        # Sort users by karma in descending order
        # The User objects themselves will be sorted
        sorted_leaderboard_users = sorted(user_objects, key=lambda u: u.karma, reverse=True)
        sorted_leaderboard_users = [user for user in sorted_leaderboard_users]
        print(sorted_leaderboard_users[0].name)
        return render_template('friends.html', leaderboard_users=sorted_leaderboard_users)
    except Exception as e:
        print(f"Error fetching leaderboard data: {e}")
        import traceback
        traceback.print_exc()
        # You might want to render an error page or return a JSON error
        return e, 500


@app.route("/url_to_user", methods=["POST"])
def url_to_user():
    # loads a user from a qr code, creates a new user if user doesn't exist in db
    try:
        data = request.json
        if not data or "url" not in data:
            return jsonify({"error": "url payload required"}), 400

        url = data["url"]
        match = re.search(r"https://app\.jamhacks\.ca/social/\s*(\d+)", url)
        if not match:
            return jsonify({"error": "invalid url format"}), 400

        print(match.group(1))
        jamhacks_code = match.group(1)
        user = User.get_user(users_collection, jamhacks_code)
        print(user)

        if user:  # skip creating a new user
            return jsonify({
                "user_id": str(user.id()),
                "new_user": False
            })
        else:
            name, socials = scraper.get_jamhacks_data(jamhacks_code)
            user = User(
                jamhacks_code,
                name,
                socials
            )

            user.save_to_db(users_collection)
            return jsonify({
                "user_id": str(user.id()),
                "new_user": True
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/scan_qr")
def scan_qr():
    return render_template("scan_qr.html")


@app.route('/get_dynamsoft_license', methods=["GET"])
def get_dynamsoft_license():
    allowed_referers = [
        "http://karmasarelaxingthought.tech",
        "https://karmasarelaxingthought.tech",
        "http://127.0.0.1",
        "https://127.0.0.1",
    ]
    referer = request.headers.get("Referer")
    print("referer: " + referer)

    if not referer or not any(referer.startswith(allowed) for allowed in allowed_referers):
        return jsonify({"error": "Unauthorized access"}), 403

    return jsonify({"license": os.getenv("DYNAMSOFT_LICENSE")})


@app.route('/upload_endpoint', methods=['POST'])
def upload_endpoint():
    if 'image_file' not in request.files:
        return jsonify({"error": "No image file part in the request."}), 400

    file = request.files['image_file']
    user_id_str = get_user_session()
    quest_id_str = request.form.get('quest_id')

    if not user_id_str:
        return jsonify({"error": "User ID is required."}), 400

    if not quest_id_str:
        return jsonify({"error": "Quest ID is required."}), 400

    if file.filename == '':
        return jsonify({"error": "No image selected for uploading."}), 400

    if file and allowed_file(file.filename):
        original_filename = secure_filename(file.filename)
        try:
            gcs_uri = upload_image_stream_to_gcs_for_user(
                file_stream=file,
                original_filename=original_filename,
                user_id_folder=user_id_str,
                content_type=file.content_type
            )
            if not gcs_uri:
                return jsonify({"error": "Image upload to Google Cloud Storage failed."}), 500

            image_labels_dict = get_image_labels_and_entities(gcs_uri)
            if not image_labels_dict or "error" in image_labels_dict:
                error_msg = image_labels_dict.get("error", "Failed to get image labels.")
                return jsonify({"error": f"Label extraction failed: {error_msg}", "gcs_uri": gcs_uri}), 500

            formatted_labels = [f"{desc.capitalize()} (Score: {score:.2f})" for desc, score in
                                image_labels_dict.items()]
            img_activity_description = get_description(formatted_labels) or "No activity description."
            good_samaritan_category = classify(img_activity_description, formatted_labels) or "Unclassified"
            karma_points_info = process_activity_and_get_points(
                activity_category=good_samaritan_category,
                activity_description=img_activity_description,
                detected_labels=formatted_labels
            )

            try:
                user_object_id = ObjectId(user_id_str)
                update_result = users_collection.update_one(
                    {"_id": user_object_id},
                    {
                        "$inc": {"karma": karma_points_info},
                    }
                )
                current_user_karma = "User not found" if update_result.matched_count == 0 else users_collection.find_one(
                    {"_id": user_object_id}, {"karma": 1}
                ).get("karma", "Karma not found")
            except Exception as e_db_update:
                current_user_karma = "Error during karma update"
                print(f"DB error: {e_db_update}")

            # Save photo referencing user and quest
            new_photo = Photo(user_id=ObjectId(user_id_str), quest_id=ObjectId(quest_id_str), url=gcs_uri)
            new_photo.save_to_db(photos_collection)

            users_collection.update_one(
                {"_id": ObjectId(user_id_str)},
                {"$push": {"photos": new_photo.id()}}
            )

            # Insert reference into quest, mark as complete
            quests_collection.update_one(
                {"_id": ObjectId(quest_id_str)},
                {"$set": {
                    "completion_image_uri": new_photo.id(),
                    "status": "complete"
                }}
            )

            return jsonify({
                "message": f"Image '{original_filename}' processed successfully for user '{user_id_str}'.",
                "quest_id": quest_id_str,
                "gcs_uri": gcs_uri,
                "image_labels": formatted_labels,
                "activity_description": img_activity_description,
                "classified_category": good_samaritan_category,
                "karma_points_awarded": karma_points_info,
                "user_current_karma": current_user_karma
            }), 200

        except Exception as e:
            print(f"Error in /upload_endpoint route: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Server error: {str(e)}"}), 500
    else:
        allowed_ext_str = ", ".join(sorted([ext.lstrip('.') for ext in ALLOWED_IMAGE_EXTENSIONS]))
        return jsonify({"error": f"Invalid file type. Allowed types are: {allowed_ext_str}"}), 400


@app.route("/upload_photo")
def upload_photo():
    return render_template("upload_photo.html")


@app.route('/add_friend', methods=['GET', 'POST'])
def add_friend():
    if request.method == 'POST':
        data = request.json
        if not data or "user_id" not in data:
            return jsonify({"error": "user_id is required"}), 400

        friend_id = data["user_id"]
        current_user = ObjectId(get_user_session())
        friend_user = ObjectId(friend_id)

        response = make_response(redirect('/friends'))
        users_collection.update_one(
            {"_id": current_user},
            {"$addToSet": {"friends": friend_user}}
        )
        users_collection.update_one(
            {"_id": friend_user},
            {"$addToSet": {"friends": current_user}}
        )

        return response

    return render_template('add_friend.html')


@app.route('/get_user_json', methods=['POST'])
def get_user_json():
    try:
        data = request.json
        if not data or "user_id" not in data:
            return jsonify({"error": "user_id is required"}), 400

        try:
            user_id = ObjectId(data["user_id"])  # Convert to ObjectId
        except Exception:
            return jsonify({"error": "Invalid user_id format"}), 400

        user = users_collection.find_one({"_id": user_id})
        if not user:
            return jsonify({"error": "User not found"}), 404

        print(user)

        friends = [str(friend) for friend in user.get("friends", [])]
        quests = [str(quest) for quest in user.get("quests", [])]
        photos = [str(photo) for photo in user.get("photos", [])]

        return jsonify({
            "jamhacks_code": user.get("jamhacks_code"),
            "name": user.get("name"),
            "socials": user.get("socials", []),
            "karma": user.get("karma"),
            "phone": user.get("phone"),
            "friends": friends,
            "quests": quests,
            "photos": photos,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv('PORT', 5002))
    app.run(host='0.0.0.0', port=port, debug=True)