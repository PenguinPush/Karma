import certifi
import os
import uuid
from flask import Flask, request, jsonify, redirect, make_response, render_template
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from pymongo import MongoClient
import re
from bson.objectid import ObjectId

from user import User  # Assuming user.py is in the same directory
from web_scraper import Scraper  # Assuming web_scraper.py is in the same directory

from image_recognizer import get_image_labels_and_entities
from gcs_uploader import upload_image_stream_to_gcs_for_user, \
    ALLOWED_IMAGE_EXTENSIONS  # Keep allowed_file defined locally or import it too
from classifier import get_description, classify
from semantic_search import process_activity_and_get_points
from user import User
load_dotenv()

app = Flask(__name__)
scraper = Scraper()

MONGO_URI = os.getenv("MONGO_CONNECTION_STRING")

client = MongoClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
db = client["karma"]
users_collection = db["users"]


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

        response = make_response(redirect('/'))
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


@app.route("/profile")
def profile():
    return render_template("profile.html")


@app.route("/quests")
def quests():
    return render_template("quests.html")


@app.route("/capture")
def capture():
    return render_template("capture.html")


@app.route('/friends')
def friends():
    try:
        print(get_user_session())
        current_user = User.get_user_by_id(users_collection, get_user_session())
        all_users_from_db = current_user.friends
        print([User.get_user_by_id(users_collection, user_objectid) for user_objectid in all_users_from_db])
        # Sort users by karma in descending order
        # The User objects themselves will be sorted
        sorted_leaderboard_users = sorted(all_users_from_db, key=lambda u: User.get_user_by_id(users_collection, u).karma, reverse=True)
        sorted_leaderboard_users = [User.get_user_by_id(users_collection, user_objectid) for user_objectid in sorted_leaderboard_users]
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
    user_id_str = request.form.get('user_id')

    if not user_id_str:
        return jsonify({"error": "User ID (uploader_user_id) is required."}), 400

    if file.filename == '':
        return jsonify({"error": "No image selected for uploading."}), 400

    if file and allowed_file(file.filename):
        original_filename = secure_filename(file.filename)
        gcs_uri = None

        try:
            print(
                f"Calling GCS stream uploader for user_id_folder: {user_id_str}, original filename: {original_filename}")
            gcs_uri = upload_image_stream_to_gcs_for_user(
                file_stream=file,
                original_filename=original_filename,
                user_id_folder=user_id_str,
                content_type=file.content_type
            )

            if not gcs_uri:
                print("GCS stream upload function returned None.")
                return jsonify({"error": "Image upload to Google Cloud Storage failed."}), 500

            print(f"Successfully uploaded to GCS: {gcs_uri}")

            print("\nStep 1 (Flask): Getting image labels from Image_recognizer...")
            image_labels_dict = get_image_labels_and_entities(gcs_uri)

            if not image_labels_dict or "error" in image_labels_dict:
                error_msg = image_labels_dict.get("error", "Failed to get image labels.") if isinstance(
                    image_labels_dict, dict) else "Failed to get image labels."
                print(f"Error from Image Recognizer: {error_msg}")
                return jsonify({"error": f"Label extraction failed: {error_msg}", "gcs_uri": gcs_uri}), 500

            formatted_labels = [f"{desc.capitalize()} (Score: {score:.2f})" for desc, score in
                                image_labels_dict.items()]
            print(f"Image Labels from Recognizer: {formatted_labels if formatted_labels else 'None'}")

            print("\nStep 2 (Flask): Getting activity description from classifier...")
            img_activity_description = get_description(formatted_labels)
            if not img_activity_description:
                print("Warning: get_description returned None. Using a default description.")
                img_activity_description = "Activity could not be automatically described from labels."
            print(f"Generated Activity Description: {img_activity_description}")

            print("\nStep 3 (Flask): Classifying Good Samaritan category from classifier...")
            good_samaritan_category = classify(img_activity_description, formatted_labels)
            if good_samaritan_category is None:
                print("Warning: classify returned None. Using a default category.")
                good_samaritan_category = "No Specific Good Samaritan Activity Detected"
            print(f"Classified Category: {good_samaritan_category}")

            print("\nStep 4 (Flask): Processing activity for karma points from semantic_search...")
            karma_points_info = process_activity_and_get_points(
                activity_category=good_samaritan_category,
                activity_description=img_activity_description,
                detected_labels=formatted_labels
            )

            print(f"Karma Points Calculated: {karma_points_info}")

            current_user_karma = "User not found or karma not updated"
            try:
                user_object_id = ObjectId(user_id_str)  # Convert user_id string to ObjectId
                update_result = users_collection.update_one(
                    {"_id": user_object_id},
                    {
                        "$inc": {"karma": karma_points_info},
                        "$push": {"photos": gcs_uri}
                    }
                )
                if update_result.matched_count > 0:
                    print(f"User {user_id_str}'s karma and photos updated in MongoDB.")
                    updated_user_doc = users_collection.find_one({"_id": user_object_id}, {"karma": 1})
                    if updated_user_doc:
                        current_user_karma = updated_user_doc.get("karma", "Could not fetch updated karma")
                else:
                    print(
                        f"Warning: User with ID {user_id_str} (ObjectId: {user_object_id}) not found in DB for update.")
                    current_user_karma = "User not found for update"
            except Exception as e_db_update:
                print(f"Error updating user {user_id_str} in MongoDB: {e_db_update}")
                current_user_karma = "Error during karma update"

            return jsonify({
                "message": f"Image '{original_filename}' processed successfully for user '{user_id_str}'.",
                "gcs_uri": gcs_uri,
                "image_labels": formatted_labels,
                "activity_description": img_activity_description,
                "classified_category": good_samaritan_category,
                "karma_points_awarded": karma_points_info,
                "user_current_karma": current_user_karma
            }), 200

        except RuntimeError as e:
            print(f"A critical imported function is missing: {e}")
            return jsonify({"error": f"Server configuration error: {e}"}), 500
        except Exception as e:
            print(f"An error occurred in the /upload_endpoint route: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500
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
