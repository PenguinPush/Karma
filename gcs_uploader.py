# gcs_image_uploader.py
import os
import uuid  # For generating unique filenames
from dotenv import load_dotenv

# Import Google Cloud Storage client library
# and google.auth components separately for better error handling
storage = None
google_auth = None  # For google.auth.exceptions
google_oauth2_service_account = None  # For explicit loading

try:
    from google.cloud import storage
except ImportError:
    print("Error: google-cloud-storage library not found. Please install it: pip install google-cloud-storage")

try:
    # We need google.auth for exceptions and potentially version checking
    import google.auth

    google_auth = google.auth
    # Import the specific credentials type we'll use for explicit loading
    from google.oauth2 import service_account as oauth2_service_account

    google_oauth2_service_account = oauth2_service_account
except ImportError:
    print(
        "Error: google-auth or google.oauth2.service_account library not found. Please install it: pip install google-auth")

try:
    # Import exceptions separately to ensure it's available if google.auth was imported
    if google_auth:  # Only try to import exceptions if google.auth itself was imported
        import google.auth.exceptions

        google_auth_exceptions = google.auth.exceptions
except ImportError:
    print(
        "Error: google.auth.exceptions module not found. This might indicate an issue with the google-auth installation.")

# Load environment variables from .env file
# Ensure your .env file has GOOGLE_APPLICATION_CREDENTIALS defined
load_dotenv()

# Define allowed image file extensions
ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.heic', '.heif'}


def upload_image_to_gcs_for_user(local_image_path: str, user_id_folder: str,
                                 bucket_name: str = "karma-videos") -> str | None:
    """
    Uploads an image to a user-specific folder in a Google Cloud Storage bucket,
    after validating the file type.

    Args:
        local_image_path: The local path to the image file.
        user_id_folder: The name of the folder (derived from user ID) in GCS.
        bucket_name: The name of the GCS bucket.

    Returns:
        The GCS URI of the uploaded image (e.g., gs://bucket_name/user_id_folder/filename.ext),
        or None if upload failed or file type is invalid.
    """
    if not storage:
        print("Google Cloud Storage library not available. Cannot upload.")
        return None
    if not google_oauth2_service_account:  # Check for the specific credentials loader
        print(
            "google.oauth2.service_account module not available (part of google-auth). Cannot load credentials or upload.")
        return None

    if not os.path.exists(local_image_path):
        print(f"Error: Local image file not found at {local_image_path}")
        return None

    # Validate file extension
    file_name_part, file_extension = os.path.splitext(local_image_path)
    if file_extension.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        print(f"Error: Invalid file type. '{file_extension}' is not an allowed image extension.")
        print(f"Allowed extensions are: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}")
        return None

    google_app_creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not google_app_creds_path:
        print("Error: GOOGLE_APPLICATION_CREDENTIALS environment variable not set.")
        return None

    if not os.path.exists(google_app_creds_path):
        print(f"Error: Credentials file not found at: {google_app_creds_path}")
        return None

    try:
        # Explicitly load credentials from the service account file
        credentials = google_oauth2_service_account.Credentials.from_service_account_file(
            google_app_creds_path,
            scopes=['https://www.googleapis.com/auth/devstorage.read_write']  # Scope for GCS read/write
        )

        project_id_from_creds = credentials.project_id

        # Manually setting universe_domain if needed as a workaround for specific environment/library version issues.
        # Ideally, with up-to-date libraries, this shouldn't be necessary if the JSON key contains it.
        if not hasattr(credentials, 'universe_domain') or not credentials.universe_domain:
            print("Attempting to manually set universe_domain on credentials object.")
            credentials.universe_domain = "googleapis.com"

        storage_client = storage.Client(credentials=credentials, project=project_id_from_creds)
        bucket = storage_client.bucket(bucket_name)

        # Sanitize user_id_folder to be a valid GCS folder name
        sane_folder_name = "".join(c if c.isalnum() or c in ['-', '_', '.'] else '_' for c in str(user_id_folder))
        if not sane_folder_name:
            sane_folder_name = "default_user_folder"  # Fallback if user_id_folder is empty or all invalid chars
            print(f"Warning: Provided user_id_folder was empty or invalid, using '{sane_folder_name}'.")

        original_filename = os.path.basename(local_image_path)
        name_part, ext_part = os.path.splitext(original_filename)
        unique_suffix = uuid.uuid4().hex[:8]
        gcs_object_name = f"{sane_folder_name}/{name_part}_{unique_suffix}{ext_part}"

        blob = bucket.blob(gcs_object_name)

        print(f"Uploading {local_image_path} to gs://{bucket_name}/{gcs_object_name}...")
        blob.upload_from_filename(local_image_path)

        gcs_uri = f"gs://{bucket_name}/{gcs_object_name}"
        print(f"Image uploaded successfully to {gcs_uri}")
        return gcs_uri

    except (google_auth.exceptions.DefaultCredentialsError if google_auth_exceptions else Exception) as e:
        # Handle DefaultCredentialsError specifically if the module was imported
        print(f"Google Auth/Credentials Error: {e}")
        if isinstance(e,
                      google_auth_exceptions.DefaultCredentialsError if google_auth_exceptions else RuntimeError):  # Check type if module exists
            print(
                "This usually means GOOGLE_APPLICATION_CREDENTIALS is not set correctly or the file is invalid/inaccessible.")
        import traceback
        traceback.print_exc()
        return None
    except AttributeError as e_attr:
        print(f"AttributeError encountered: {e_attr}")
        print(
            "This might be related to library versions or the specific credentials type loaded if 'universe_domain' is mentioned.")
        import traceback
        traceback.print_exc()
        return None
    except Exception as e:
        print(f"An error occurred during GCS upload: {e}")
        import traceback
        traceback.print_exc()
        return None


# --- Example Usage ---
if __name__ == "__main__":

    local_image_to_upload_test = "/Users/edwardwang/Downloads/litter.png"
    user_id_test = "sample_user_123"
    if local_image_to_upload_test and os.path.exists(local_image_to_upload_test):
        print(f"\nAttempting to upload '{local_image_to_upload_test}' to folder '{user_id_test}'...")
        uploaded_gcs_uri = upload_image_to_gcs_for_user(
            local_image_path=local_image_to_upload_test,
            user_id_folder=user_id_test
            # bucket_name="your_custom_bucket_name" # Optionally override default bucket
        )

        if uploaded_gcs_uri:
            print(f"\nUpload successful. GCS URI: {uploaded_gcs_uri}")
        else:
            print("\nUpload failed. Please check the error messages above.")

        # Clean up the dummy image if it was the one created for testing
        if local_image_to_upload_test == "test_image_for_gcs.png" and os.path.exists(
                local_image_to_upload_test) and "dummy png content" in open(local_image_to_upload_test).read():
            try:
                os.remove(local_image_to_upload_test)
                print(f"\nCleaned up dummy image: {local_image_to_upload_test}")
            except OSError as e_remove:
                print(f"Error cleaning up dummy image '{local_image_to_upload_test}': {e_remove}")
    elif local_image_to_upload_test:  # Path was specified but file doesn't exist
        print(f"Test image specified ('{local_image_to_upload_test}') but not found. Skipping upload test.")
