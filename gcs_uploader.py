import os
import uuid  
from dotenv import load_dotenv



from google.cloud import storage

import google.auth

google_auth = google.auth
from google.oauth2 import service_account as oauth2_service_account

google_oauth2_service_account = oauth2_service_account

import google.auth.exceptions

google_auth_exceptions = google.auth.exceptions

load_dotenv()

ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.heic', '.heif'}


def _get_gcs_credentials_and_project():


    google_app_creds_json_string = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")


    try:
        creds_info = json.loads(google_app_creds_json_string)

        credentials = google_oauth2_service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=['https://www.googleapis.com/auth/devstorage.read_write']
        )
        project_id_from_creds = credentials.project_id  

        if not hasattr(credentials, 'universe_domain') or not credentials.universe_domain:
            if 'universe_domain' in creds_info:
                credentials.universe_domain = creds_info['universe_domain']
            else:  
                credentials.universe_domain = "googleapis.com"

        return credentials, project_id_from_creds

    except Exception as e:
        print(f"Error {e}")
        return None, None


def upload_image_stream_to_gcs_for_user(
        file_stream,
        original_filename: str,
        user_id_folder: str,
        bucket_name: str = "karma-videos",
        content_type: str | None = None
) -> str | None:


    _, file_extension = os.path.splitext(original_filename)
    if file_extension.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        print(
            f"Error: Invalid file type based on original filename. '{file_extension}' is not an allowed image extension.")
        print(f"Allowed extensions are: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}")
        return None

    credentials, project_id_from_creds = _get_gcs_credentials_and_project()
    if not credentials:
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

        if content_type is None:
            content_type, _ = mimetypes.guess_type(original_filename)
            if content_type:
                print(f"guessed content type: {content_type}")

        print(f"uploading stream for '{original_filename}' to gs://{bucket_name}/{gcs_object_name}...")
        file_stream.seek(0)  
        blob.upload_from_file(file_stream, content_type=content_type)

        gcs_uri = f"gs://{bucket_name}/{gcs_object_name}"
        print(f"image uploaded successfully from stream to {gcs_uri}")
        return gcs_uri

    except (google_auth_exceptions.GoogleAuthError if google_auth_exceptions else Exception) as e:
        print(f"Google Auth/Credentials Error during stream upload: {e}")
        import traceback
        traceback.print_exc()
        return None
    except Exception as e:
        print(f"An error occurred during gcs stream upload: {e}")
        import traceback
        traceback.print_exc()
        return None


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {ext.lstrip('.') for ext in ALLOWED_IMAGE_EXTENSIONS}


if __name__ == "__main__":
    

    dummy_image_filename_for_stream_test = "/Users/edwardwang/Downloads/recycle.png"
    user_id_for_stream_test = "sample_user_json_creds_test"

    if not os.path.exists(dummy_image_filename_for_stream_test):
        try:
            with open(dummy_image_filename_for_stream_test, "wb") as f:   
                f.write(b"dummy png content for stream test")  
            print(f"Created dummy image for stream testing: {dummy_image_filename_for_stream_test}")
        except IOError as e:
            print(f"Could not create dummy image '{dummy_image_filename_for_stream_test}': {e}")
            dummy_image_filename_for_stream_test = None

    if dummy_image_filename_for_stream_test and os.path.exists(dummy_image_filename_for_stream_test):
        print(f"\n--- Testing upload_image_stream_to_gcs_for_user (direct stream with JSON string credentials) ---")
        try:
            with open(dummy_image_filename_for_stream_test, 'rb') as stream_obj:  
                uploaded_gcs_uri_from_stream = upload_image_stream_to_gcs_for_user(
                    file_stream=stream_obj,
                    original_filename=os.path.basename(dummy_image_filename_for_stream_test),
                    user_id_folder=user_id_for_stream_test,
                    content_type='image/png'  
                )
                if uploaded_gcs_uri_from_stream:
                    print(f"Upload from stream successful. GCS URI: {uploaded_gcs_uri_from_stream}")
                else:
                    print("Upload from stream failed.")
        except IOError as e:
            print(f"Error opening file for stream test: {e}")

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

