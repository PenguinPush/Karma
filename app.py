import os

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect, make_response
from pymongo import MongoClient
import re
from user import User
from web_scraper import get_jamhacks_data
from gcs_uploader import upload_image_stream_to_gcs_for_user, ALLOWED_IMAGE_EXTENSIONS, allowed_file
from werkzeug.utils import secure_filename


load_dotenv()

app = Flask(__name__)

client = MongoClient(os.getenv("MONGO_CONNECTION_STRING"))
db = client["karma"]
users_collection = db["users"]


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == 'admin' and password == 'password':
            response = make_response(redirect('/'))
            response.set_cookie('user_session', 'unique_session_token')
            return response
        return "Invalid credentials", 401
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
    if request.endpoint not in ['login', 'static', 'scan_qr']:
        user_session = request.cookies.get('user_session')
        if not user_session:
            return redirect('/login')


@app.route("/")
def index():
    return render_template("index.html")


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
        fetched_user = User.get_user(users_collection, jamhacks_code)

        name, socials = get_jamhacks_data(jamhacks_code)
        if fetched_user:
            user = User(
                jamhacks_code,
                name,
                socials,
                fetched_user.karma,
                fetched_user.phone,
                fetched_user.friends,
                fetched_user.quests,
                fetched_user.photos,
                fetched_user.id()
            )
        else:
            user = User(
                jamhacks_code,
                name,
                socials
            )

        user.save_to_db(users_collection)

        return jsonify({
            "user_id": str(user.id())
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/scan_qr")
def scan_qr():
    return render_template("scan_qr.html")


@app.route('/upload_endpoint', methods=['POST'])
def upload_endpoint():
    if 'image_file' not in request.files:
        return jsonify({"error": "No image file part in the request."}), 400

    file = request.files['image_file']  # This is a FileStorage object (stream-like)
    user_id = request.form.get('user_id')

    if not user_id:
        return jsonify({"error": "User ID is required."}), 400

    if file.filename == '':
        return jsonify({"error": "No image selected for uploading."}), 400

    if file and allowed_file(file.filename):
        original_filename = secure_filename(file.filename)

        gcs_uri = None
        try:
            # No local save: pass the file stream (file object from request.files) directly
            # Also pass the original filename for extension checking and naming in GCS
            # The content_type can be obtained from the FileStorage object
            print(f"Calling GCS stream uploader for user_id_folder: {user_id}, original filename: {original_filename}")
            gcs_uri = upload_image_stream_to_gcs_for_user(
                file_stream=file,  # Pass the stream directly
                original_filename=original_filename,
                user_id_folder=user_id,
                content_type=file.content_type  # Pass content type from Flask's FileStorage
            )

            if gcs_uri:
                print(f"Successfully uploaded to GCS: {gcs_uri}")
                return jsonify({
                    "message": f"Image '{original_filename}' streamed and uploaded successfully for user '{user_id}'.",
                    "gcs_uri": gcs_uri
                }), 200
            else:
                # upload_image_stream_to_gcs_for_user should print its own errors
                print("GCS stream upload function returned None.")
                return jsonify({
                                   "error": "Image upload to Google Cloud Storage failed. Check server logs for details from uploader."}), 500

        except Exception as e:
            print(f"An error occurred in the /upload route: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500
        # No 'finally' block to remove a local temp file, as we are not creating one here.
    else:
        allowed_ext_str = ", ".join(sorted([ext.lstrip('.') for ext in ALLOWED_IMAGE_EXTENSIONS]))
        return jsonify({"error": f"Invalid file type. Allowed types are: {allowed_ext_str}"}), 400


@app.route("/upload_photo")
def upload_photo():
    return render_template("upload_photo.html")


if __name__ == "__main__":
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
