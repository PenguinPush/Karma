# openai_classifier.py
import os
import openai
from dotenv import load_dotenv
import json  # For parsing JSON response

# Attempt to import the image label extraction function from Image_recognizer.py
try:
    from Image_recognizer import get_image_labels_and_entities
    # This assumes Image_recognizer.py is in the same directory or Python path
    # and contains a function get_image_labels_and_entities(gcs_image_uri) -> dict[str, float]
except ImportError:
    print("Error: Could not import 'get_image_labels_and_entities' from 'Image_recognizer.py'.")
    print("Please ensure 'Image_recognizer.py' exists and contains this function.")


    # Define a placeholder if the import fails, so the script can still be loaded (but not run successfully)
    def get_image_labels_and_entities(gcs_image_uri: str) -> dict[str, float]:
        print("Placeholder function: Real 'get_image_labels_and_entities' not found.")
        return {"error": "Image_recognizer.py or its function not found."}

# Load environment variables from .env file
# Ensure your .env file has OPENAI_API_KEY defined (and GOOGLE_APPLICATION_CREDENTIALS if Image_recognizer.py needs it)
load_dotenv()

# Initialize the OpenAI client
# The client will automatically look for the OPENAI_API_KEY environment variable
try:
    openai_client = openai.OpenAI()
except openai.OpenAIError as e:
    print(f"Error initializing OpenAI client: {e}")
    print("Please ensure your OPENAI_API_KEY environment variable is set correctly.")
    openai_client = None
except Exception as e_general_openai:  # Catch any other potential errors during init
    print(f"A general error occurred initializing OpenAI client: {e_general_openai}")
    openai_client = None

# Define your "Good Samaritan" categories (as per user's last provided code)
GOOD_SAMARITAN_CATEGORIES = [
    "Recycling Activity",
    "Litter Pickup",
    "Using Public Transit",
    "Environmental Care",
    "Health and Wellness",
    "Helping Others (General)",
    "Community Involvement",
    "Creativity and Learning",
    "No Specific Good Samaritan Activity Detected"
]


# --- OpenAI Function to get activity description from labels ---
def get_description(detected_labels: list[str], model_name: str = "gpt-4o") -> str | None:
    """
    Generates a short natural language description of the activity depicted
    in an image, based on a list of detected labels.

    Args:
        detected_labels: A list of strings, where each string is a label
                         detected in the image (e.g., "Label (Score: 0.xx)").
        model_name: The OpenAI model to use. Defaults to "gpt-4o".

    Returns:
        A string containing a short description of the activity, or None if an error occurs.
    """
    if not openai_client:
        print("OpenAI client not initialized. Cannot proceed with description generation.")
        return None

    if not detected_labels:
        print("No labels provided for activity description.")
        return "No specific activity could be determined due to lack of labels."

    prompt_system = (
        "You are an expert at interpreting image content. Based on the following list of labels "
        "detected in an image, provide a concise, one to two-sentence natural language description "
        "of the primary activity or scene depicted. Focus on what is happening."
    )
    prompt_user = (
        "Detected labels from an image:\n"
        f"{', '.join(detected_labels)}\n\n"
        "Describe the primary activity or scene in one or two sentences."
    )

    print(f"\nSending request to OpenAI model ({model_name}) for activity description...")
    try:
        completion = openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            temperature=0.5,  # Allow for some natural language generation
            max_tokens=100  # Sufficient for a short description
        )
        description = completion.choices[0].message.content.strip()
        print(f"OpenAI Generated Description: {description}")
        return description
    except openai.APIError as e:
        print(f"OpenAI API Error during description generation: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during description generation: {e}")
        import traceback
        traceback.print_exc()
        return None


# --- OpenAI Classifier Function (Using Tool Calling for structured output) ---
def classify(
        activity_description: str,
        detected_labels: list[str],
        model_name: str = "gpt-4o"
) -> str | None:
    """
    Classifies an image into a "Good Samaritan" category using OpenAI's API
    based on a generated activity description and a list of detected labels,
    ensuring the output is one of the specified categories by using tool calling.

    Args:
        activity_description: A natural language description of the activity in the image.
        detected_labels: A list of strings, where each string is a label
                         detected in the image.
        model_name: The OpenAI model to use for classification. Defaults to "gpt-4o".

    Returns:
        A string representing the classified "Good Samaritan" category,
        or None if classification fails or an error occurs.
    """
    if not openai_client:
        print("OpenAI client not initialized. Cannot proceed with classification.")
        return None

    if not activity_description and not detected_labels:
        print("No activity description or labels provided for OpenAI classification.")
        return "No Specific Good Samaritan Activity Detected"
    elif not detected_labels:
        print("Warning: No labels provided, relying solely on activity description for classification.")
    elif not activity_description:
        print("Warning: No activity description provided, relying solely on labels for classification.")

    tools = [
        {
            "type": "function",
            "function": {
                "name": "set_good_samaritan_category",
                "description": "Sets the Good Samaritan category based on image description and labels.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": GOOD_SAMARITAN_CATEGORIES,
                            "description": "The classified Good Samaritan category. Must be one of the predefined enum values."
                        }
                    },
                    "required": ["category"]
                }
            }
        }
    ]

    prompt_system = (
        "You are an expert image content classifier. Your task is to analyze a generated description of an image "
        "and a list of labels detected in that image. Based on this combined information, classify the image "
        "into one of the 'Good Samaritan' activity categories. "
        "You must call the 'set_good_samaritan_category' function with your determined category. "
        "The category must be one of the following: "
        f"{', '.join([f'{cat}' for cat in GOOD_SAMARITAN_CATEGORIES])}. "
        "If no specific activity from the list is clearly indicated, "
        "the category should be 'No Specific Good Samaritan Activity Detected'."
    )

    prompt_user = (
        "Generated activity description for an image:\n"
        f"{activity_description}\n\n"
        "Original labels detected in the image (some may include confidence scores, focus on the descriptive part):\n"
        f"{', '.join(detected_labels)}\n\n"
        "Based on both the description and the labels, call the 'set_good_samaritan_category' function with the most appropriate category."
    )

    print(f"\nSending request to OpenAI model ({model_name}) for category classification using tool calling...")

    try:
        completion = openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "set_good_samaritan_category"}},
            temperature=0.1,
            max_tokens=150
        )

        response_message = completion.choices[0].message
        tool_calls = response_message.tool_calls

        if tool_calls:
            tool_call = tool_calls[0]
            if tool_call.function.name == "set_good_samaritan_category":
                try:
                    function_args = json.loads(tool_call.function.arguments)
                    classified_category = function_args.get("category")

                    if classified_category and classified_category in GOOD_SAMARITAN_CATEGORIES:
                        print(f"OpenAI called tool with arguments: {function_args}")
                        return classified_category
                    elif classified_category:
                        print(
                            f"Warning: Tool call returned category '{classified_category}', which is not strictly in the predefined enum. Defaulting.")
                        return "No Specific Good Samaritan Activity Detected"
                    else:
                        print("Warning: Tool call arguments did not contain the 'category' key.")
                        return "No Specific Good Samaritan Activity Detected"
                except json.JSONDecodeError:
                    print(f"Error: Tool call arguments were not valid JSON: {tool_call.function.arguments}")
                    return "No Specific Good Samaritan Activity Detected"
            else:
                print(f"Error: Unexpected tool called: {tool_call.function.name}")
                return "No Specific Good Samaritan Activity Detected"
        else:
            raw_content = response_message.content
            print(f"Warning: Model did not make a tool call as expected. Raw content: '{raw_content}'")
            if raw_content:
                try:
                    potential_json = json.loads(raw_content)
                    category = potential_json.get("category")
                    if category and category in GOOD_SAMARITAN_CATEGORIES:
                        return category
                except json.JSONDecodeError:
                    pass
            return "No Specific Good Samaritan Activity Detected"

    except openai.APIError as e:
        print(f"OpenAI API Error during classification: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during OpenAI classification: {e}")
        import traceback
        traceback.print_exc()
        return None


# --- Main Execution Block (Modified for Integrated Testing) ---
if __name__ == "__main__":
    gcs_image_uri_to_test = "gs://karma-videos/litter.png"  # Replace with your actual image URI

    is_placeholder_uri = "your-gcs-bucket-name" in gcs_image_uri_to_test or \
                         "your-image.jpg" in gcs_image_uri_to_test or \
                         (
                                     "recycle.png" not in gcs_image_uri_to_test and "litter.png" not in gcs_image_uri_to_test and "karma-videos" not in gcs_image_uri_to_test)

    if is_placeholder_uri:
        print("\nIMPORTANT: Please update 'gcs_image_uri_to_test' in this script ('openai_classifier.py')")
        print("           with a valid GCS path to an image you want to test.")
        print(f"           Current test URI is: {gcs_image_uri_to_test}")
    else:
        print(f"--- Starting Full Image to Good Samaritan Classification Pipeline for: {gcs_image_uri_to_test} ---")

        print(f"\nStep 1: Getting labels from Image_recognizer.py for: {gcs_image_uri_to_test}")
        detected_entities_dict = get_image_labels_and_entities(gcs_image_uri_to_test)

        if not detected_entities_dict or "error" in detected_entities_dict:
            print(
                "\nPipeline halted: Failed to get labels from the image or an error occurred in the image recognizer.")
            if detected_entities_dict and "error" in detected_entities_dict:
                print(f"Error details: {detected_entities_dict['error']}")
        else:
            print("\n--- Labels/Entities from Image Recognizer (Sorted by Confidence) ---")
            sorted_entities_for_print = sorted(detected_entities_dict.items(), key=lambda item: item[1], reverse=True)
            for description, score in sorted_entities_for_print:
                print(f"- {description.capitalize()} (Score: {score:.2f})")

            labels_for_openai_input = [
                f"{desc.capitalize()} (Score: {score:.2f})" for desc, score in sorted_entities_for_print
            ]

            print("\nStep 2: Generating activity description with OpenAI ---")
            activity_description = get_description(labels_for_openai_input)

            if not activity_description:
                print("\nPipeline halted: Failed to generate activity description from OpenAI.")
            else:
                print(f"\nGenerated Activity Description: {activity_description}")

                print("\nStep 3: Classifying Good Samaritan category with OpenAI using description and labels ---")
                final_classified_category = classify(
                    activity_description,
                    labels_for_openai_input
                )

                print("\n--- Final Classification Result ---")
                if final_classified_category:
                    print(
                        f"The image '{gcs_image_uri_to_test}' has been classified by OpenAI as: {final_classified_category}")
                else:
                    print(
                        f"Could not classify the image '{gcs_image_uri_to_test}' into a Good Samaritan category using OpenAI.")

