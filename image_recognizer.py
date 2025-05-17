# Image_recognizer.py (Updated to handle GOOGLE_APPLICATION_CREDENTIALS as JSON string)
import os
import json  # For parsing JSON string from environment variable
from dotenv import load_dotenv

# Import Google Cloud Vision client library and specific modules for credentials
try:
    from google.cloud import vision
    from google.oauth2 import service_account  # For from_service_account_info
    import google.auth.exceptions  # For specific exception handling
except ImportError:
    print("Error: google-cloud-vision or google-auth library not found. Please install them.")
    print("pip install google-cloud-vision google-auth")
    vision = None
    service_account = None
    google_auth_exceptions = None

# Load environment variables from .env file
# GOOGLE_APPLICATION_CREDENTIALS is now expected to be a JSON string.
load_dotenv()


def get_image_labels_and_entities(gcs_image_uri: str) -> dict[str, float]:
    """
    Analyzes an image stored in Google Cloud Storage using the Vision API
    and returns a dictionary of detected labels, objects, and web entities
    with their confidence scores.
    Expects GOOGLE_APPLICATION_CREDENTIALS to be a JSON string in the environment.

    Args:
        gcs_image_uri: The Google Cloud Storage URI of the image.
                       (e.g., "gs://your-bucket/your-image.jpg")

    Returns:
        A dictionary where keys are lowercase label/entity descriptions and
        values are their confidence scores.
        Returns a dictionary with an "error" key if an error occurs.
    """
    print(f"Analyzing image for labels and entities: {gcs_image_uri}")


    google_app_creds_json_string = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if google_app_creds_json_string is None:
        error_message = "Error: GOOGLE_APPLICATION_CREDENTIALS environment variable not set or is empty."
        print(error_message)
        return {"error": error_message}

    client = None
    try:
        # Attempt to parse the environment variable as a JSON string
        creds_info = json.loads(google_app_creds_json_string)
        # Create credentials directly from the parsed info
        credentials = service_account.Credentials.from_service_account_info(creds_info)
        client = vision.ImageAnnotatorClient(credentials=credentials)
        print("Initialized Vision API client from JSON string in GOOGLE_APPLICATION_CREDENTIALS.")

    except json.JSONDecodeError as e:
        error_message = f"Error: GOOGLE_APPLICATION_CREDENTIALS is not a valid JSON string: {e}. Please ensure it's the full JSON content, not a file path."
        print(error_message)
        return {"error": error_message}
    except (
    google_auth_exceptions.GoogleAuthError, ValueError) as e:  # ValueError can be raised by from_service_account_info
        error_message = f"Error creating credentials from JSON string: {e}"
        print(error_message)
        return {"error": error_message}
    except Exception as e:  # Catch any other unexpected error during client initialization
        error_message = f"Unexpected error initializing Vision API client: {e}"
        print(error_message)
        import traceback
        traceback.print_exc()
        return {"error": error_message}

    try:
        image = vision.Image()
        image.source.image_uri = gcs_image_uri

        # Using max_results as specified in the user's provided code
        features = [
            {"type_": vision.Feature.Type.LABEL_DETECTION, "max_results": 4},
            {"type_": vision.Feature.Type.OBJECT_LOCALIZATION, "max_results": 3},
            {"type_": vision.Feature.Type.WEB_DETECTION, "max_results": 30}
        ]

        request = vision.AnnotateImageRequest(image=image, features=features)
        response = client.annotate_image(request=request)

        if response.error.message:
            error_message = f"Vision API Error: {response.error.message}"
            print(error_message)
            return {"error": error_message}

        # --- Consolidate all detected labels, objects, and web entities with their scores ---
        all_detected_entities = {}  # Store entity_description_lower: score

        # 1. From Label Detection
        if response.label_annotations:
            for label in response.label_annotations:
                desc_lower = label.description.lower()
                if desc_lower not in all_detected_entities or label.score > all_detected_entities[desc_lower]:
                    all_detected_entities[desc_lower] = label.score

        # 2. From Object Localization
        if response.localized_object_annotations:
            for obj in response.localized_object_annotations:
                desc_lower = obj.name.lower()
                if desc_lower not in all_detected_entities or obj.score > all_detected_entities[desc_lower]:
                    all_detected_entities[desc_lower] = obj.score

        # 3. From Web Detection (Best Guess Labels and Web Entities)
        if response.web_detection:
            if response.web_detection.best_guess_labels:
                for label in response.web_detection.best_guess_labels:
                    desc_lower = label.label.lower()
                    if desc_lower not in all_detected_entities or 0.95 > all_detected_entities.get(desc_lower, 0):
                        all_detected_entities[desc_lower] = 0.95

            if response.web_detection.web_entities:
                for entity in response.web_detection.web_entities:
                    if entity.description:
                        desc_lower = entity.description.lower()
                        score = entity.score or 0.0
                        if desc_lower not in all_detected_entities or score > all_detected_entities[desc_lower]:
                            all_detected_entities[desc_lower] = score

        if not all_detected_entities:
            print("No labels or entities were detected in the image.")
            return {}  # Return empty dict if nothing found, not an error dict

        return all_detected_entities

    except Exception as e:  # Catch errors during API call or response processing
        error_message = f"An unexpected error occurred during Vision API request or processing: {e}"
        print(error_message)
        import traceback
        traceback.print_exc()
        return {"error": error_message}


# --- Example Usage ---
if __name__ == "__main__":
    # IMPORTANT: To test this, your .env file must have:
    # 1. GOOGLE_APPLICATION_CREDENTIALS set to the *actual JSON string content* of your service account key.
    #    Example .env entry for GOOGLE_APPLICATION_CREDENTIALS:
    #    GOOGLE_APPLICATION_CREDENTIALS='{"type": "service_account", "project_id": "your-project-id", ...rest of JSON...}'
    # 2. Ensure the service account has permissions to read from the GCS bucket.

    gcs_image_uri_test = "gs://karma-videos/new.png"  # Replace with your actual image URI in GCS

    # Basic check if the URI is still a placeholder
    is_placeholder_uri = "your-gcs-bucket-name" in gcs_image_uri_test or \
                         "your-image.jpg" in gcs_image_uri_test or \
                         ("new.png" not in gcs_image_uri_test and "karma-videos" not in gcs_image_uri_test)

    if is_placeholder_uri:
        print("\nIMPORTANT: Please update 'gcs_image_uri_test' in 'Image_recognizer.py' (this file)")
        print("           with a valid GCS path to an image you want to test.")
        print(f"           Current test URI is: {gcs_image_uri_test}")
    else:
        print(f"--- Analyzing image: {gcs_image_uri_test} ---")
        detected_entities_dict = get_image_labels_and_entities(gcs_image_uri_test)

        print("\nDetected Labels, Objects, and Web Entities (Sorted by Confidence):")
        if detected_entities_dict:
            if "error" in detected_entities_dict:
                print(f"Error encountered: {detected_entities_dict['error']}")
            elif not detected_entities_dict:  # Check if empty after successful run
                print("No entities detected.")
            else:
                # Sort the dictionary by confidence score for printing
                sorted_entities = sorted(detected_entities_dict.items(), key=lambda item: item[1], reverse=True)
                for description, score in sorted_entities:
                    print(f"- {description.capitalize()} (Score: {score:.2f})")
        else:  # Should be caught by the "error" in dict check if an error occurred
            print("No information returned from analysis or an error occurred.")
