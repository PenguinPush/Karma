# image_scene_describer.py
import os
from dotenv import load_dotenv
from google.cloud import vision

# Load environment variables from .env file
# Ensure your .env file has GOOGLE_APPLICATION_CREDENTIALS defined
# e.g., GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-key.json"
load_dotenv()


def get_image_labels_and_entities(gcs_image_uri: str) -> dict[str, float]:
    """
    Analyzes an image stored in Google Cloud Storage using the Vision API
    and returns a dictionary of detected labels, objects, and web entities
    with their confidence scores.

    Args:
        gcs_image_uri: The Google Cloud Storage URI of the image.
                       (e.g., "gs://your-bucket/your-image.jpg")

    Returns:
        A dictionary where keys are lowercase label/entity descriptions and
        values are their confidence scores.
        Returns an empty dictionary if an error occurs or no entities are found.
    """
    print(f"Analyzing image for labels and entities: {gcs_image_uri}")

    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        error_message = "Error: GOOGLE_APPLICATION_CREDENTIALS environment variable not set."
        print(error_message)
        # Return a dictionary with the error message for consistency in handling
        return {"error": error_message}

    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image()
        image.source.image_uri = gcs_image_uri

        features = [
            {"type_": vision.Feature.Type.LABEL_DETECTION, "max_results": 4},  # Get more labels
            {"type_": vision.Feature.Type.OBJECT_LOCALIZATION, "max_results": 3},  # Get more localized objects
            {"type_": vision.Feature.Type.WEB_DETECTION, "max_results": 30}  # Get more web entities and guesses
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
                # Prioritize higher score if label detected multiple times
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
                    # Assign a high confidence score for best guess if not already present with a higher score
                    # This prioritizes best_guess_labels as they are often very accurate summaries.
                    if desc_lower not in all_detected_entities or 0.95 > all_detected_entities.get(desc_lower, 0):
                        all_detected_entities[desc_lower] = 0.95

            if response.web_detection.web_entities:
                for entity in response.web_detection.web_entities:
                    if entity.description:  # Ensure description is not empty
                        desc_lower = entity.description.lower()
                        # Use entity.score directly; if it's None or 0, 'or 0.0' handles it.
                        # This ensures we use the API's score if available, otherwise default to 0.0.
                        score = entity.score or 0.0
                        if desc_lower not in all_detected_entities or score > all_detected_entities[desc_lower]:
                            all_detected_entities[desc_lower] = score

        if not all_detected_entities:
            print("No labels or entities were detected in the image.")
            return {}

        return all_detected_entities

    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        print(error_message)
        import traceback
        traceback.print_exc()
        return {"error": error_message}


# --- Example Usage ---
if __name__ == "__main__":
    # IMPORTANT: Replace with the GCS URI of your image file.
    # Example: gcs_image_uri = "gs://your-gcs-bucket-name/your-image.jpg"

    gcs_image_uri_test = "gs://karma-videos/new.png"  # Replace with your actual image URI

    if "your-gcs-bucket-name" in gcs_image_uri_test or "your-image.jpg" in gcs_image_uri_test:  # Basic placeholder check
        print("\nIMPORTANT: Please update 'gcs_image_uri_test' with a valid GCS path to your image.")
    else:
        print(f"--- Analyzing image: {gcs_image_uri_test} ---")
        detected_entities_dict = get_image_labels_and_entities(gcs_image_uri_test)

        print("\nDetected Labels, Objects, and Web Entities (Sorted by Confidence):")
        if detected_entities_dict:
            if "error" in detected_entities_dict:
                print(detected_entities_dict["error"])
            else:
                # Sort the dictionary by confidence score for printing
                sorted_entities = sorted(detected_entities_dict.items(), key=lambda item: item[1], reverse=True)
                for description, score in sorted_entities:
                    print(f"- {description.capitalize()} (Score: {score:.2f})")
        else:
            print("No information returned from analysis or an error occurred.")

