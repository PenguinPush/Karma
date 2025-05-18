import os
from dotenv import load_dotenv
import io
import json

storage = None
google_auth = None
google_oauth2_service_account = None
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
    print("Error: google-auth or google.oauth2.service_account library not found. Please install it: pip install google-auth")

try:
    if google_auth:
        import google.auth.exceptions
        google_auth_exceptions = google.auth.exceptions
except ImportError:
    print("Error: google.auth.exceptions module not found. This might indicate an issue with the google-auth installation.")

load_dotenv()


def _get_gcs_credentials_and_project_for_fetch():
    """
    Helper function to load GCS credentials and project ID from a JSON string
    stored in the GOOGLE_APPLICATION_CREDENTIALS environment variable.
    This is similar to the one in gcs_uploader.py.
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
        creds_info = json.loads(google_app_creds_json_string)
        credentials = google_oauth2_service_account.Credentials.from_service_account_info(
            creds_info,

            scopes=['https://www.googleapis.com/auth/devstorage.read_only']
        )
        project_id_from_creds = credentials.project_id

        if not hasattr(credentials, 'universe_domain') or not credentials.universe_domain:
            if 'universe_domain' in creds_info:
                credentials.universe_domain = creds_info['universe_domain']
            else:
                credentials.universe_domain = "googleapis.com"

        return credentials, project_id_from_creds

    except json.JSONDecodeError as e:
        print(f"Error: GOOGLE_APPLICATION_CREDENTIALS is not a valid JSON string: {e}")
        return None, None
    except Exception as e:
        print(f"Error loading credentials from service account info: {e}")
        return None, None


def fetch_image(gcs_uri: str) -> io.BytesIO | None:
    """
    Fetches an image from Google Cloud Storage and returns it as an in-memory binary stream.

    Args:
        gcs_uri: The Google Cloud Storage URI of the image (e.g., "gs://bucket_name/path/to/image.png").

    Returns:
        An io.BytesIO object containing the image data, or None if fetching failed.
    """
    if not storage:
        print("Google Cloud Storage library not available. Cannot fetch image.")
        return None

    if not gcs_uri or not gcs_uri.startswith("gs://"):
        print(f"Error: Invalid GCS URI provided: {gcs_uri}")
        return None

    credentials, project_id_from_creds = _get_gcs_credentials_and_project_for_fetch()
    if not credentials:
        return None

    try:
        storage_client = storage.Client(credentials=credentials, project=project_id_from_creds)

        try:
            bucket_name, blob_name = gcs_uri.replace("gs://", "").split("/", 1)
        except ValueError:
            print(f"Error: Could not parse bucket and blob name from GCS URI: {gcs_uri}")
            return None

        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        print(f"Fetching image from gs://{bucket_name}/{blob_name}...")

        if not blob.exists():
            print(f"Error: Image not found at GCS URI: {gcs_uri}")
            return None

        image_bytes = blob.download_as_bytes()
        image_stream = io.BytesIO(image_bytes)
        image_stream.seek(0)  

        print(f"Image fetched successfully from {gcs_uri} ({len(image_bytes)} bytes).")
        return image_stream

    except (google_auth_exceptions.GoogleAuthError if google_auth_exceptions else Exception) as e:
        print(f"Google Auth/Credentials Error during image fetch: {e}")
        import traceback
        traceback.print_exc()
        return None
    except Exception as e:
        print(f"An error occurred during image fetch from GCS: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
   
    test_gcs_image_uri = "gs://karma-videos/sample_user_json_creds_test/recycle_cc6bde8e.png"

    print(f"Current test URI: {test_gcs_image_uri}")

    print(f"\n--- Testing fetch_image_from_gcs ---")
    fetched_image_stream = fetch_image(test_gcs_image_uri)

    if fetched_image_stream:
        print(f"\nSuccessfully fetched image into an in-memory stream.")
        
        try:
            output_filename = "fetched_image_test.png"  
            with open(output_filename, "wb") as f_out:
                f_out.write(fetched_image_stream.read())
            print(f"Test: Image stream saved to local file: {output_filename}")
            
        except Exception as e_save:
            print(f"Test: Error saving fetched image stream locally: {e_save}")
    else:
        print("\nFailed to fetch image from GCS. Check error messages above.")

