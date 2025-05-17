# gcs_uploader.py
import os
import uuid  # For generating unique filenames
from dotenv import load_dotenv
import mimetypes  # For guessing content type from filename
import json  # For parsing JSON string from environment variable

# Import Google Cloud Storage client library
# and google.auth components separately for better error handling
storage = None
google_auth = None  # For google.auth.exceptions
google_oauth2_service_account = None  # For explicit loading
google_auth_exceptions = None

try:
    from google.cloud import storage
except ImportError:
    print("Error: google-cloud-storage library not found. Please install it: pip install google-cloud-storage")

try:
    import google.auth

    google_auth = google.auth
    from google.oauth2 import service_account as oauth2_service_account

    google_oauth2_service_account = oauth2_service_account
except ImportError:
    print(
        "Error: google-auth or google.oauth2.service_account library not found. Please install it: pip install google-auth")

try:
    if google_auth:
        import google.auth.exceptions

        google_auth_exceptions = google.auth.exceptions
except ImportError:
    print(
        "Error: google.auth.exceptions module not found. This might indicate an issue with the google-auth installation.")

load_dotenv()

ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.heic', '.heif'}


def _get_gcs_credentials_and_project():
    """
    Helper function to load GCS credentials and project ID from a JSON string
    stored in the GOOGLE_APPLICATION_CREDENTIALS environment variable.
    Returns a tuple (credentials, project_id) or (None, None) on failure.
    """
    if not google_oauth2_service_account:
        print("google.oauth2.service_account module not available. Cannot load credentials.")
        return None, None

    google_app_creds_json_string = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not google_app_creds_json_string:
        print("Error: GOOGLE_APPLICATION_CREDENTIALS environment variable not set or is empty.")
        return None, None

    try:
        # Parse the JSON string from the environment variable
        creds_info = json.loads(google_app_creds_json_string)

        # Load credentials from the parsed dictionary
        credentials = google_oauth2_service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=['https://www.googleapis.com/auth/devstorage.read_write']
        )
        project_id_from_creds = credentials.project_id  # Should be available from creds_info or inferred

        # Manually setting universe_domain if needed.
        # With from_service_account_info, it should pick up 'universe_domain' if present in creds_info.
        if not hasattr(credentials, 'universe_domain') or not credentials.universe_domain:
            # Check if it's in the loaded info and try to set it
            if 'universe_domain' in creds_info:
                credentials.universe_domain = creds_info['universe_domain']
            else:  # Default if not in JSON and not on object
                # print("Attempting to manually set universe_domain on credentials object as a fallback.") # Debugging
                credentials.universe_domain = "googleapis.com"

        return credentials, project_id_from_creds

    except json.JSONDecodeError as e:
        print(f"Error: GOOGLE_APPLICATION_CREDENTIALS is not a valid JSON string: {e}")
        return None, None
    except Exception as e:
        print(f"Error loading credentials from service account info: {e}")
        return None, None


def upload_image_stream_to_gcs_for_user(
        file_stream,
        original_filename: str,
        user_id_folder: str,
        bucket_name: str = "karma-videos",
        content_type: str | None = None
) -> str | None:
    """
    Uploads an image from a file stream to a user-specific folder in GCS.

    Args:
        file_stream: The file stream object (e.g., from Flask request.files['image_file']).
        original_filename: The original name of the file, used for extension and base name.
        user_id_folder: The name of the folder (derived from user ID) in GCS.
        bucket_name: The name of the GCS bucket.
        content_type: The content type (MIME type) of the file. If None, it will be
                      guessed from original_filename if possible.

    Returns:
        The GCS URI of the uploaded image, or None if upload failed.
    """
    if not storage:
        print("Google Cloud Storage library not available. Cannot upload.")
        return None

    # Validate file extension from original_filename
    _, file_extension = os.path.splitext(original_filename)
    if file_extension.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        print(
            f"Error: Invalid file type based on original filename. '{file_extension}' is not an allowed image extension.")
        print(f"Allowed extensions are: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}")
        return None

    credentials, project_id_from_creds = _get_gcs_credentials_and_project()
    if not credentials:
        # Error message already printed by helper
        return None

    try:
        storage_client = storage.Client(credentials=credentials, project=project_id_from_creds)
        bucket = storage_client.bucket(bucket_name)

        sane_folder_name = "".join(c if c.isalnum() or c in ['-', '_', '.'] else '_' for c in str(user_id_folder))
        if not sane_folder_name:
            sane_folder_name = "default_user_folder"
            print(f"Warning: Provided user_id_folder was empty or invalid, using '{sane_folder_name}'.")

        name_part, ext_part = os.path.splitext(original_filename)
        unique_suffix = uuid.uuid4().hex[:8]
        gcs_object_name = f"{sane_folder_name}/{name_part}_{unique_suffix}{ext_part}"

        blob = bucket.blob(gcs_object_name)

        # Guess content type if not provided
        if content_type is None:
            content_type, _ = mimetypes.guess_type(original_filename)
            if content_type:
                print(f"Guessed content type: {content_type}")

        print(f"Uploading stream for '{original_filename}' to gs://{bucket_name}/{gcs_object_name}...")
        file_stream.seek(0)  # Ensure the stream is at the beginning before upload
        blob.upload_from_file(file_stream, content_type=content_type)

        gcs_uri = f"gs://{bucket_name}/{gcs_object_name}"
        print(f"Image uploaded successfully from stream to {gcs_uri}")
        return gcs_uri

    except (google_auth_exceptions.GoogleAuthError if google_auth_exceptions else Exception) as e:
        print(f"Google Auth/Credentials Error during stream upload: {e}")
        import traceback
        traceback.print_exc()
        return None
    except Exception as e:
        print(f"An error occurred during GCS stream upload: {e}")
        import traceback
        traceback.print_exc()
        return None


# --- Example Usage ---
if __name__ == "__main__":
    # --- Configuration for Testing ---
    # To test this, your .env file should have GOOGLE_APPLICATION_CREDENTIALS
    # set to the *actual JSON string content*, not a file path.
    # Example .env entry:
    # GOOGLE_APPLICATION_CREDENTIALS='{"type": "service_account", "project_id": "your-project-id", ...rest of JSON...}'

    dummy_image_filename_for_stream_test = "/Users/edwardwang/Downloads/recycle.png"
    user_id_for_stream_test = "sample_user_json_creds_test"
    # --- End Configuration ---

    # Create a dummy image file for testing the stream upload
    if not os.path.exists(dummy_image_filename_for_stream_test):
        try:
            with open(dummy_image_filename_for_stream_test, "wb") as f:  # Open in binary write mode for dummy content
                f.write(b"dummy png content for stream test")  # Write some bytes
            print(f"Created dummy image for stream testing: {dummy_image_filename_for_stream_test}")
        except IOError as e:
            print(f"Could not create dummy image '{dummy_image_filename_for_stream_test}': {e}")
            dummy_image_filename_for_stream_test = None

    if dummy_image_filename_for_stream_test and os.path.exists(dummy_image_filename_for_stream_test):
        print(f"\n--- Testing upload_image_stream_to_gcs_for_user (direct stream with JSON string credentials) ---")
        try:
            with open(dummy_image_filename_for_stream_test, 'rb') as stream_obj:  # Open in binary read mode
                uploaded_gcs_uri_from_stream = upload_image_stream_to_gcs_for_user(
                    file_stream=stream_obj,
                    original_filename=os.path.basename(dummy_image_filename_for_stream_test),
                    user_id_folder=user_id_for_stream_test,
                    content_type='image/png'  # Example, or let it guess
                )
                if uploaded_gcs_uri_from_stream:
                    print(f"Upload from stream successful. GCS URI: {uploaded_gcs_uri_from_stream}")
                else:
                    print("Upload from stream failed.")
        except IOError as e:
            print(f"Error opening file for stream test: {e}")

        # Clean up the dummy image if it was the one created for testing
        if os.path.exists(dummy_image_filename_for_stream_test):
            is_dummy_content = False
            try:
                with open(dummy_image_filename_for_stream_test, 'rb') as f_check:
                    if b"dummy png content for stream test" in f_check.read():
                        is_dummy_content = True
            except:
                pass

            if is_dummy_content:
                try:
                    os.remove(dummy_image_filename_for_stream_test)
                    print(f"\nCleaned up dummy image: {dummy_image_filename_for_stream_test}")
                except OSError as e_remove:
                    print(f"Error cleaning up dummy image '{dummy_image_filename_for_stream_test}': {e_remove}")
    elif dummy_image_filename_for_stream_test:
        print(f"Test image specified ('{dummy_image_filename_for_stream_test}') but not found. Skipping upload test.")
    else:
        print("Could not proceed with example usage as the test image was not available.")

    print("\nReminder: For this script to work, the GOOGLE_APPLICATION_CREDENTIALS environment variable")
    print("must contain the *actual JSON string* of your service account key, not a path to the file.")

