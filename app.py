# app.py (Formerly flask_gcs_image_webhook.py)
import os
import uuid
from flask import Flask, request, jsonify, redirect, make_response, render_template
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from pymongo import MongoClient
import re
from bson.objectid import ObjectId

# --- User and Web Scraper Imports (from user's provided app.py) ---
from user import User  # Assuming user.py is in the same directory
from web_scraper import get_jamhacks_data  # Assuming web_scraper.py is in the same directory

# --- GCS Uploader Import ---
try:
    from gcs_uploader import upload_image_stream_to_gcs_for_user, \
        ALLOWED_IMAGE_EXTENSIONS  # Keep allowed_file defined locally or import it too


    # Define allowed_file locally if not imported from gcs_uploader
    def allowed_file(filename):
        """Checks if the file's extension is allowed."""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in {ext.lstrip('.') for ext in ALLOWED_IMAGE_EXTENSIONS}
except ImportError:
    print("CRITICAL ERROR: Could not import from 'gcs_uploader.py'.")


    def upload_image_stream_to_gcs_for_user(file_stream, original_filename: str, user_id_folder: str,
                                            bucket_name: str = "karma-videos",
                                            content_type: str | None = None) -> str | None:
        raise RuntimeError("GCS uploader function not found.")


    ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg'}


    def allowed_file(filename):
        return False  # Fallback

# --- Image Recognizer, Classifier, and Semantic Search Imports ---
try:
    from Image_recognizer import get_image_labels_and_entities
except ImportError:
    print("CRITICAL ERROR: Could not import 'get_image_labels_and_entities' from 'Image_recognizer.py'.")


    def get_image_labels_and_entities(gcs_image_uri: str) -> dict[str, float]:
        raise RuntimeError("Image recognizer function not found.")

try:
    from classifier import get_description, classify
except ImportError:
    print("CRITICAL ERROR: Could not import 'get_description' or 'classify' from 'classifier.py'.")


    def get_description(detected_labels: list[str], model_name: str = "gpt-4o") -> str | None:
        raise RuntimeError("Classifier get_description function not found.")


    def classify(activity_description: str, detected_labels: list[str], model_name: str = "gpt-4o") -> str | None:
        raise RuntimeError("Classifier classify function not found.")

try:
    from semantic_search import process_activity_and_get_points
except ImportError:
    print("CRITICAL ERROR: Could not import 'process_activity_and_get_points' from 'semantic_search.py'.")


    def process_activity_and_get_points(activity_category: str, activity_description: str,
                                        detected_labels: list[str] | None = None) -> int:
        raise RuntimeError("Semantic search/scoring function not found.")

load_dotenv()

app = Flask(__name__)

# MongoDB Connection (from user's provided app.py)
MONGO_URI_APP = os.getenv("MONGO_CONNECTION_STRING")
if not MONGO_URI_APP:
    raise ValueError("MONGO_CONNECTION_STRING not found in environment for Flask app.")
client = MongoClient(MONGO_URI_APP)  # Assuming certifi is handled by MONGO_URI if it's Atlas
db = client["karma"]  # Using "karma" as per user's app.py
users_collection = db["users"]
# Note: semantic_search.py also connects to MongoDB. Ensure configurations are consistent if they share DB/collections.


# UPLOAD_FOLDER is for temporary local storage before GCS upload if not streaming directly.
# If upload_image_stream_to_gcs_for_user streams directly, this might only be used by Werkzeug for large files.
UPLOAD_FOLDER = 'temp_flask_uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    try:
        os.makedirs(UPLOAD_FOLDER)
    except OSError as e:
        print(f"Error creating temporary upload folder {UPLOAD_FOLDER}: {e}")


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json
        if not data or "user_id" not in data:
            return jsonify({"error": "user_id is required"}), 400
        user_id = data["user_id"]
        response = make_response(
            jsonify({"message": "Login successful, redirecting...", "user_id": user_id}))  # Return JSON
        response.set_cookie('user_session', user_id, httponly=True, samesite='Lax')  # Add security flags
        return response
    return render_template('login.html')


@app.route('/logout')
def logout():
    response = make_response(redirect('/login'))
    response.delete_cookie('user_session')
    return response


@app.before_request
def redirect_to_https():
    if 'DYNO' in os.environ and request.headers.get('X-Forwarded-Proto', 'http') != 'https':
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)


@app.before_request
def check_user_session():
    # Added 'upload_endpoint' to public endpoints as it's an API
    public_endpoints = ["login", "static", "redirect_to_https", "url_to_user", "scan_qr", "get_dynamsoft_license",
                        "upload_endpoint", "home"]
    if request.endpoint not in public_endpoints:
        user_session = request.cookies.get('user_session')
        if not user_session:
            if request.endpoint:
                print(f"Redirecting, user not logged in for endpoint: {request.endpoint}")
            return redirect('/login')


@app.route("/")
def home():  # Renamed from index to home to match public_endpoints
    return render_template("index.html")


@app.route("/friends")
def friends():
    return render_template("friends.html")


@app.route("/profile")
def profile():
    return render_template("profile.html")


@app.route("/quests")
def quests():
    return render_template("quests.html")


@app.route("/capture")
def capture():
    return render_template("capture.html")


@app.route("/url_to_user", methods=["POST"])
def url_to_user():
    try:
        data = request.json
        if not data or "url" not in data:
            return jsonify({"error": "url payload required"}), 400

        url = data["url"]
        match = re.search(r"https://app\.jamhacks\.ca/social/\s*(\d+)", url)
        if not match:
            return jsonify({"error": "invalid url format"}), 400

        jamhacks_code = match.group(1)
        user = User.get_user(users_collection, jamhacks_code)

        if user:
            return jsonify({
                "user_id": str(user.id()),  # Assuming user.id() returns ObjectId
                "new_user": False
            })
        else:
            name, socials = get_jamhacks_data(jamhacks_code)
            user = User(jamhacks_code, name, socials)
            user.save_to_db(users_collection)  # This will assign user._id
            return jsonify({
                "user_id": str(user.id()),
                "new_user": True
            })
    except Exception as e:
        print(f"Error in /url_to_user: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/scan_qr")
def scan_qr():
    return render_template("scan_qr.html")


@app.route('/get_dynamsoft_license', methods=["GET"])
def get_dynamsoft_license():
    # Consider more robust referer validation if this is sensitive
    allowed_referers = [
        "http://karmasarelaxingthought.tech", "https://karmasarelaxingthought.tech",
        "http://127.0.0.1", "https://127.0.0.1",
        "http://localhost", "https://localhost"  # Added localhost for local dev
    ]
    referer = request.headers.get("Referer")

    # A simple check; for production, ensure this logic is secure enough
    is_allowed = False
    if referer:
        for allowed_prefix in allowed_referers:
            if referer.startswith(allowed_prefix):
                is_allowed = True
                break

    if not is_allowed and not app.debug:  # Allow if debug mode for easier local testing
        print(f"Unauthorized referer for Dynamsoft license: {referer}")
        return jsonify({"error": "Unauthorized access"}), 403

    return jsonify({"license": os.getenv("DYNAMSOFT_LICENSE")})


@app.route('/upload_endpoint', methods=['POST'])
def upload_endpoint():
    if 'image_file' not in request.files:
        return jsonify({"error": "No image file part in the request."}), 400

    file = request.files['image_file']
    user_id_str = request.form.get('user_id')  # This is the uploader's user_id string

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

            # --- Start of new integration ---
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
            if not good_samaritan_category:
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

            # --- Directly update user data in MongoDB ---
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
                    # Fetch the updated karma to return (optional, adds a read)
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
            # --- End of direct MongoDB update ---

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

        user_id = data["user_id"]

        response = make_response(redirect('/'))
        response.set_cookie('user_session', user_id)

        return response

    return render_template('add_friend.html')


@app.route('/get_user_json', methods=['POST'])
def get_user_json():
    try:
        data = request.json
        if not data or "user_id" not in data:
            return jsonify({"error": "user_id is required"}), 400

        try:
            user_id_str = data["user_id"]
            user = users_collection.find_one({"_id": ObjectId(user_id_str)})
            if not user:
                # If user_id is potentially a jamhacks_code, your User class handles this.
                # For direct DB query, if _id fails, you might have a fallback or specific error.
                # This example assumes user_id is always the MongoDB _id string for this endpoint.
                return jsonify({"error": "User not found by ObjectId"}), 404

        except Exception as e_oid:
            print(f"Error finding user with ID '{data['user_id']}': {e_oid}")
            return jsonify({"error": "Invalid user_id format or user not found"}), 400

        user_data_response = {
            "_id": str(user.get("_id")),
            "jamhacks_code": user.get("jamhacks_code"),
            "name": user.get("name"),
            "socials": user.get("socials", []),
            "karma": user.get("karma"),
            "phone": user.get("phone"),
            "friends": [str(friend_id) for friend_id in user.get("friends", [])],
            "quests": user.get("quests", []),
            "photos": user.get("photos", []),
        }
        return jsonify(user_data_response)

    except Exception as e:
        print(f"Error in /get_user_json: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
