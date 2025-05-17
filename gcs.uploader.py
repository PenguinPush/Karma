import os
from flask import Flask, request, redirect, url_for, render_template_string, flash
from werkzeug.utils import secure_filename  # Still useful for getting a safe original filename
from google.cloud import storage
from dotenv import load_dotenv
import uuid  # To generate unique filenames


load_dotenv()

ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'webm'}  # Define allowed video extensions

# Your Google Cloud Storage bucket name
GCS_BUCKET_NAME = "karma-videos"  # IMPORTANT: Replace with your bucket name

app = Flask(__name__)
app.secret_key = 'super secret key'  # Needed for flash messages; change in production


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def upload_to_gcs_from_stream(file_stream, bucket_name: str, gcs_object_name: str) -> str | None:
    """
    Uploads a file from a stream to the specified Google Cloud Storage bucket.

    Args:
        file_stream: A file-like object (stream) to upload.
        bucket_name: The name of the GCS bucket.
        gcs_object_name: The desired name of the object in GCS.

    Returns:
        The GCS URI (gs://bucket_name/object_name) of the uploaded file, or None if upload failed.
    """
    # Check if GOOGLE_APPLICATION_CREDENTIALS is set
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        print("CRITICAL: GOOGLE_APPLICATION_CREDENTIALS environment variable not set.")
        flash("Server configuration error: GCS credentials not set.", "danger")
        return None

    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(gcs_object_name)

        print(f"Streaming upload to gs://{bucket_name}/{gcs_object_name}...")
        # Reset stream position to the beginning, just in case it was read before
        file_stream.seek(0)
        blob.upload_from_file(file_stream)  # Use upload_from_file for streams

        gcs_uri = f"gs://{bucket_name}/{gcs_object_name}"
        print(f"File streamed and uploaded successfully to {gcs_uri}")
        return gcs_uri
    except Exception as e:
        print(f"An error occurred during GCS stream upload: {e}")
        flash(f"Error uploading to Cloud Storage: {e}", "danger")
        return None


@app.route('/', methods=['GET', 'POST'])
def upload_video():
    if GCS_BUCKET_NAME == "karma-videos":
        flash("IMPORTANT: GCS_BUCKET_NAME is not configured in flask_app.py!", "danger")
        return "Server not configured. Please set GCS_BUCKET_NAME in the script.", 500

    if request.method == 'POST':
        if 'video_file' not in request.files:
            flash('No video file part in the request.', 'warning')
            return redirect(request.url)
        file = request.files['video_file']  # This is a FileStorage object (a stream)

        if file.filename == '':
            flash('No video selected for uploading.', 'warning')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            original_filename = secure_filename(file.filename)
            # Create a unique filename for GCS to avoid collisions
            unique_suffix = uuid.uuid4().hex[:8]
            extension = original_filename.rsplit('.', 1)[1].lower()
            gcs_filename = f"{original_filename.rsplit('.', 1)[0]}_{unique_suffix}.{extension}"

            # Define the object name in GCS (e.g., store in a 'raw_videos' folder)
            gcs_object_name = f"raw_videos/{gcs_filename}"

            try:
                # Directly stream the file to GCS
                gcs_uri = upload_to_gcs_from_stream(file, GCS_BUCKET_NAME, gcs_object_name)

                if gcs_uri:
                    flash(f'Video "{original_filename}" streamed successfully to GCS!', 'success')
                    flash(f'GCS URI: {gcs_uri}', 'info')
                    print(f"Next step: Process this GCS URI with VideoRecog.py: {gcs_uri}")
                    # Here you would trigger your video recognition process
                else:
                    flash('Video upload to GCS failed.', 'danger')

            except Exception as e:
                print(f"Error during GCS upload initiation: {e}")
                flash(f"An error occurred: {e}", "danger")

            return redirect(url_for('upload_video'))

    return render_template_string('''
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
        <title>Upload Video (Stream to GCS)</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background-color: #f4f4f4; color: #333; }
            .container { background-color: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 0 15px rgba(0,0,0,0.1); max-width: 600px; margin: auto; }
            h1 { color: #333; text-align: center; margin-bottom: 20px; }
            .flash-messages { list-style: none; padding: 0; margin-bottom: 20px; }
            .flash-messages li { padding: 10px 15px; margin-bottom: 10px; border-radius: 4px; }
            .flash-success { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .flash-danger { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
            .flash-warning { background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
            .flash-info { background-color: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
            label { display: block; margin-bottom: 8px; font-weight: bold; }
            input[type="file"] { display: block; margin-bottom: 20px; padding: 10px; border: 1px solid #ddd; border-radius: 4px; width: calc(100% - 22px); }
            input[type="submit"] { background-color: #007bff; color: white; padding: 12px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; width: 100%; }
            input[type="submit"]:hover { background-color: #0056b3; }
        </style>
      </head>
      <body>
        <div class="container">
            <h1>Upload New Video (Stream to GCS)</h1>
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% if messages %}
                <ul class="flash-messages">
                {% for category, message in messages %}
                  <li class="flash-{{ category }}">{{ message }}</li>
                {% endfor %}
                </ul>
              {% endif %}
            {% endwith %}
            <form method="post" enctype="multipart/form-data">
              <label for="video_file">Select video file (mp4, mov, avi, mkv, webm):</label>
              <input type="file" id="video_file" name="video_file" accept=".mp4,.mov,.avi,.mkv,.webm" required>
              <input type="submit" value="Upload Video">
            </form>
        </div>
      </body>
    </html>
    ''')


if __name__ == '__main__':
    if GCS_BUCKET_NAME == "your-actual-gcs-bucket-name":
        print("-" * 70)
        print("ERROR: Please update the GCS_BUCKET_NAME variable in flask_app.py")
        print("       with your actual Google Cloud Storage bucket name before running.")
        print("-" * 70)
    else:
        print(f"Flask app attempting to use GCS Bucket: {GCS_BUCKET_NAME} for streaming uploads.")
        # UPLOAD_FOLDER is no longer directly managed for saving the whole file.
        # print(f"Temporary upload folder (managed by Werkzeug for large files): {os.path.abspath(app.config.get('UPLOAD_FOLDER', 'Not Set'))}")
        app.run(debug=True, host='0.0.0.0', port=5001)
