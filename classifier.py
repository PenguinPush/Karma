# openai_classifier.py
import os
import openai
from dotenv import load_dotenv

# Import Google Cloud Vision client library
try:
    from google.cloud import vision
except ImportError:
    print("Error: google-cloud-vision library not found. Please install it: pip install google-cloud-vision")
    vision = None  # Will be checked before use

# Load environment variables from .env file
# Ensure your .env file has OPENAI_API_KEY and GOOGLE_APPLICATION_CREDENTIALS defined
load_dotenv()

# Initialize the OpenAI client
# The client will automatically look for the OPENAI_API_KEY environment variable
try:
    openai_client = openai.OpenAI()  # Renamed to avoid conflict
except openai.OpenAIError as e:
    print(f"Error initializing OpenAI client: {e}")
    print("Please ensure your OPENAI_API_KEY environment variable is set correctly.")
    openai_client = None
except Exception as e_general_openai:  # Catch any other potential errors during init
    print(f"A general error occurred initializing OpenAI client: {e_general_openai}")
    openai_client = None

# Define your "Good Samaritan" categories
GOOD_SAMARITAN_CATEGORIES = [
    "Recycling Activity",
    "Environmental Care - Litter Pickup",
    "Using Public Transit",
    "Self-Care Activity",
    "Helping Others (General)",
    "Sustainable Gardening/Planting",
    "No Specific Good Samaritan Activity Detected"  # Important fallback category
]


# --- Google Vision API Function to get image labels ---
def get_image_labels_from_gcs(gcs_image_uri: str) -> dict[str, float]:
    """
    Analyzes an image stored in Google Cloud Storage using the Vision API
    and returns a dictionary of detected labels, objects, and web entities
    with their confidence scores.

    Args:
        gcs_image_uri: The Google Cloud Storage URI of the image.

    Returns:
        A dictionary where keys are lowercase label/entity descriptions and
        values are their confidence scores.
        Returns an empty dictionary if an error occurs or no entities are found,
        or a dict with an "error" key if there's a setup issue.
    """
    print(f"Analyzing image with Google Vision API: {gcs_image_uri}")

    if not vision:  # Check if the import was successful
        return {"error": "Google Cloud Vision library not imported correctly."}

    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        error_message = "Error: GOOGLE_APPLICATION_CREDENTIALS for Vision API not set."
        print(error_message)
        return {"error": error_message}

    try:
        # Instantiates a Vision API client
        vision_api_client = vision.ImageAnnotatorClient()  # Corrected client name
        image = vision.Image()
        image.source.image_uri = gcs_image_uri

        features = [
            {"type_": vision.Feature.Type.LABEL_DETECTION, "max_results": 30},
            {"type_": vision.Feature.Type.OBJECT_LOCALIZATION, "max_results": 30},
            {"type_": vision.Feature.Type.WEB_DETECTION, "max_results": 30}
        ]

        request = vision.AnnotateImageRequest(image=image, features=features)
        response = vision_api_client.annotate_image(request=request)

        if response.error.message:
            error_message = f"Google Vision API Error: {response.error.message}"
            print(error_message)
            return {"error": error_message}

        all_detected_entities = {}

        if response.label_annotations:
            for label in response.label_annotations:
                desc_lower = label.description.lower()
                if desc_lower not in all_detected_entities or label.score > all_detected_entities[desc_lower]:
                    all_detected_entities[desc_lower] = label.score

        if response.localized_object_annotations:
            for obj in response.localized_object_annotations:
                desc_lower = obj.name.lower()
                if desc_lower not in all_detected_entities or obj.score > all_detected_entities[desc_lower]:
                    all_detected_entities[desc_lower] = obj.score

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
            print("No labels or entities were detected in the image by Vision API.")
            return {}
        return all_detected_entities

    except Exception as e:
        error_message = f"An unexpected error occurred during Vision API analysis: {e}"
        print(error_message)
        import traceback
        traceback.print_exc()
        return {"error": error_message}


# --- OpenAI Classifier Function (Unchanged as per request) ---
def classify_with_openai(detected_labels: list[str], model_name: str = "gpt-3.5-turbo") -> str | None:
    """
    Classifies an image into a "Good Samaritan" category using OpenAI's API
    based on a list of detected labels.

    Args:
        detected_labels: A list of strings, where each string is a label
                         detected in the image (e.g., from Google Vision API).
        model_name: The OpenAI model to use for classification.

    Returns:
        A string representing the classified "Good Samaritan" category,
        or None if classification fails or an error occurs.
    """
    if not openai_client:  # Use the globally initialized openai_client
        print("OpenAI client not initialized. Cannot proceed with classification.")
        return None

    if not detected_labels:
        print("No labels provided for OpenAI classification.")
        return "No Specific Good Samaritan Activity Detected"

    prompt_system = (
        "You are an expert image content classifier. Your task is to classify an image "
        "into one of the following 'Good Samaritan' activity categories based on a list "
        "of labels detected in the image. The categories are: "
        f"{', '.join(GOOD_SAMARITAN_CATEGORIES)}. "
        "Analyze the provided labels and determine which single category best describes "
        "a potential 'Good Samaritan' activity depicted. If no specific activity from the list "
        "is clearly indicated by the labels, choose 'No Specific Good Samaritan Activity Detected'. "
        "Return only the name of the chosen category and nothing else."
    )

    prompt_user = (
        "Here is a list of labels detected in an image (some may include confidence scores, "
        "focus on the descriptive part of the labels):\n"
        f"{', '.join(detected_labels)}\n\n"
        "Based on these labels, which 'Good Samaritan' category best fits? "
        "Remember to only return the category name."
    )

    print(f"\nSending request to OpenAI model: {model_name}")
    # print(f"System Prompt (for context): {prompt_system}") # For debugging
    # print(f"User Prompt (labels): {prompt_user}") # For debugging

    try:
        completion = openai_client.chat.completions.create(  # Use the globally initialized openai_client
            model=model_name,
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            temperature=0.2,
            max_tokens=50
        )

        classified_category = completion.choices[0].message.content.strip()
        print(f"OpenAI Raw Response: {classified_category}")

        if classified_category in GOOD_SAMARITAN_CATEGORIES:
            return classified_category
        else:
            print(
                f"Warning: OpenAI returned '{classified_category}', which is not in the predefined list. Attempting to find a close match or defaulting.")
            # Attempt to find if the response contains any of the category names (case-insensitive substring match)
            for cat in GOOD_SAMARITAN_CATEGORIES:
                if cat.lower() in classified_category.lower():
                    print(f"Found close match: '{cat}'")
                    return cat
            return "No Specific Good Samaritan Activity Detected"  # Default if no close match

    except openai.APIError as e:
        print(f"OpenAI API Error: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during OpenAI classification: {e}")
        import traceback
        traceback.print_exc()
        return None


# --- Main Execution Block (Modified for Integrated Testing) ---
if __name__ == "__main__":
    # IMPORTANT: Replace with the GCS URI of an image file you want to test.
    # This image should be in a GCS bucket accessible by your Google service account.
    gcs_image_uri_to_test = "gs://karma-videos/recycle.png"  # Replace with your actual image URI

    # Ensure your .env file contains:
    # GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/google-service-account-key.json"
    # OPENAI_API_KEY="your_openai_api_key"

    # Check if the placeholder GCS URI is still being used
    is_placeholder_uri = "your-gcs-bucket-name" in gcs_image_uri_to_test or \
                         "your-image.jpg" in gcs_image_uri_to_test or \
                         (
                                     "recycle.png" not in gcs_image_uri_to_test and "karma-videos" not in gcs_image_uri_to_test)  # Example specific check

    if is_placeholder_uri:
        print("\nIMPORTANT: Please update 'gcs_image_uri_to_test' in this script ('openai_classifier.py')")
        print("           with a valid GCS path to an image you want to test.")
        print(f"           Current test URI is: {gcs_image_uri_to_test}")
    else:
        print(f"--- Starting Full Image to Good Samaritan Classification Pipeline for: {gcs_image_uri_to_test} ---")

        # Step 1: Get labels from Google Vision API using the function within this file
        detected_entities_dict = get_image_labels_from_gcs(gcs_image_uri_to_test)

        if not detected_entities_dict or "error" in detected_entities_dict:
            print("\nPipeline halted: Failed to get labels from the image or an error occurred in Vision API analysis.")
            if detected_entities_dict and "error" in detected_entities_dict:
                print(f"Error details: {detected_entities_dict['error']}")
        else:
            print("\n--- Labels/Entities from Google Vision API (Sorted by Confidence) ---")
            # Sort the dictionary by confidence score for printing
            sorted_entities_for_print = sorted(detected_entities_dict.items(), key=lambda item: item[1], reverse=True)
            for description, score in sorted_entities_for_print:
                print(f"- {description.capitalize()} (Score: {score:.2f})")

            # Format labels for OpenAI classifier: list of strings like "Label (Score: 0.xx)"
            labels_for_openai_input = [
                f"{desc.capitalize()} (Score: {score:.2f})" for desc, score in sorted_entities_for_print
            ]

            # Step 2: Classify using OpenAI
            print("\n--- Classifying with OpenAI ---")
            final_classified_category = classify_with_openai(labels_for_openai_input)

            print("\n--- Final Classification Result ---")
            if final_classified_category:
                print(
                    f"The image '{gcs_image_uri_to_test}' has been classified by OpenAI as: {final_classified_category}")
                if final_classified_category not in GOOD_SAMARITAN_CATEGORIES:  # Check against the global list
                    print(
                        f"Warning: The returned category '{final_classified_category}' might be a slight variation or unexpected response from OpenAI.")
                    print(f"Expected categories are: {GOOD_SAMARITAN_CATEGORIES}")
            else:
                print(
                    f"Could not classify the image '{gcs_image_uri_to_test}' into a Good Samaritan category using OpenAI.")
