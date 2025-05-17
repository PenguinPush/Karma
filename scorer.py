# activity_scorer.py
import os
import openai
from dotenv import load_dotenv
import json

# Load environment variables from .env file
# Ensure your .env file has OPENAI_API_KEY defined
load_dotenv()

# Attempt to import necessary functions from other files
try:
    # This function is expected to be in image_recognizer.py and
    # return a dict: {'label_description_lower': score}
    from image_recognizer import get_image_labels_and_entities
except ImportError:
    print("Error: Could not import 'get_image_labels_and_entities' from 'image_recognizer.py'.")
    print("Please ensure 'image_recognizer.py' exists and contains this function for the example usage.")


    def get_image_labels_and_entities(gcs_image_uri: str) -> dict[str, float]:  # Placeholder
        print("Placeholder: Real 'get_image_labels_and_entities' not found.")
        return {"error": "image_recognizer.py or its function not found."}

try:
    # This function is expected to be in classifier.py
    # and return a string description.
    from classifier import get_description
    # This function is also expected to be in classifier.py and returns a category string
    from classifier import classify
except ImportError:
    print("Error: Could not import functions from 'classifier.py'.")
    print(
        "Please ensure 'classifier.py' exists and contains 'get_description' and 'classify_good_samaritan_activity_from_description_and_labels'.")


    def get_description(detected_labels: list[str], model_name: str = "gpt-4o") -> str | None:  # Placeholder
        print("Placeholder: Real 'get_description' not found.")
        return "Activity description could not be generated."



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

# Define the structure for the scoring output
SCORING_TOOL_NAME = "set_societal_benefit_score"
SCORING_TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "score": {
            "type": "integer",
            "description": "A score from 0 to 20 representing the societal benefit of the described activity. 0 is neutral or no benefit, 20 is highly beneficial.",
            "minimum": 0,
            "maximum": 20
        },
        "reasoning": {
            "type": "string",
            "description": "A brief explanation for the assigned score, highlighting why the activity is considered beneficial or not."
        }
    },
    "required": ["score", "reasoning"]
}


def get_score(
        activity_description: str,
        detected_labels: list[str] | None = None,
        classified_good_samaritan_category: str | None = None,  # New parameter
        model_name: str = "gpt-4o"
) -> dict[str, int | str] | None:
    """
    Uses OpenAI to generate a societal benefit score (0-20) and reasoning
    for a given activity description, optional supporting labels, and an optional
    pre-classified Good Samaritan category.

    Args:
        activity_description: A natural language description of the activity.
        detected_labels: An optional list of strings, where each string is a label
                         detected in an image related to the activity.
        classified_good_samaritan_category: An optional string representing the
                                            pre-classified Good Samaritan category.
        model_name: The OpenAI model to use. Defaults to "gpt-4o".

    Returns:
        A dictionary containing "score" (int) and "reasoning" (str),
        or None if scoring fails or an error occurs.
    """
    if not openai_client:
        print("OpenAI client not initialized. Cannot proceed with scoring.")
        return None

    if not activity_description:
        print("No activity description provided for scoring.")
        return {"score": 0, "reasoning": "No activity description provided."}

    tools = [
        {
            "type": "function",
            "function": {
                "name": SCORING_TOOL_NAME,
                "description": "Sets the societal benefit score and reasoning for an activity.",
                "parameters": SCORING_TOOL_PARAMETERS
            }
        }
    ]

    # Updated system prompt to include the pre-classified category if available
    prompt_system = (
        "You are an AI assistant tasked with evaluating the societal benefit of described activities. "
        "Consider environmental impact, community well-being, health benefits, acts of kindness, "
        "and other positive contributions to society. "
        "You must assign a score from 0 (neutral or no benefit, or even slightly negative if applicable but focus on positive scale) to 20 (highly beneficial). "
        "You must call the 'set_societal_benefit_score' function with your determined score and a brief reasoning."
        "Please note that the scores you give must be evenly distributed. Thus, an action like picking up trash, a lower effort action, would be around a 5."
        "Furthermore, an action that is neutral would earn a score of 0, such as watching TV."
        "A high effort or highly beneficial action, like donating to charities or volunteering would be 15-20."
        "The score is also ok if it is just individual benefit, like a self care activity including showering or fixing sleep schedules, these should also be scored based on effort."
        "You should evaluate scores based on how much they benefit the following goals set by the user:"
        "Recycling Activity, Litter Pickup, Using Public Transit, Environmental Care, "
        "Health and Wellness, Helping Others (General), Community Involvement, Creativity and Learning."
    )
    if classified_good_samaritan_category and classified_good_samaritan_category != "No Specific Good Samaritan Activity Detected":
        prompt_system += (
            f"\nThis activity has been classified as related to: '{classified_good_samaritan_category}'. "
            "Use this classification as additional context when determining the score and reasoning, "
        )

    labels_context = ""
    if detected_labels:
        labels_context = (
            "\nThe following labels were detected in an image associated with this activity, which might provide additional context:\n"
            f"{', '.join(detected_labels)}\n"
        )

    prompt_user = (
        "Activity Description:\n"
        f"{activity_description}\n"
        f"{labels_context}\n"
        "Based on this information (and the pre-classification if provided in the system prompt), please provide a societal benefit score (0-20) and a brief reasoning by calling the 'set_societal_benefit_score' function."
    )

    print(f"\nSending request to OpenAI model ({model_name}) for societal benefit scoring...")
    # print(f"System Prompt for Scorer: {prompt_system}") # For debugging
    # print(f"User Prompt for Scorer: {prompt_user}") # For debugging

    try:
        completion = openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": SCORING_TOOL_NAME}},
            temperature=0.2,
            max_tokens=200
        )

        response_message = completion.choices[0].message
        tool_calls = response_message.tool_calls

        if tool_calls:
            tool_call = tool_calls[0]
            if tool_call.function.name == SCORING_TOOL_NAME:
                try:
                    function_args = json.loads(tool_call.function.arguments)
                    score = function_args.get("score")
                    reasoning = function_args.get("reasoning")

                    if isinstance(score, int) and 0 <= score <= 20 and reasoning:
                        print(f"OpenAI called tool with arguments: {function_args}")
                        return {"score": score, "reasoning": reasoning}
                    else:
                        print(
                            f"Warning: Tool call returned invalid score/reasoning: {function_args}. Score must be int 0-20.")
                        return {"score": 0, "reasoning": "Invalid score or reasoning format from AI."}
                except json.JSONDecodeError:
                    print(f"Error: Tool call arguments were not valid JSON: {tool_call.function.arguments}")
                    return {"score": 0, "reasoning": "AI response for arguments was not valid JSON."}
            else:
                print(f"Error: Unexpected tool called: {tool_call.function.name}")
                return {"score": 0, "reasoning": "AI called an unexpected tool."}
        else:
            print(f"Warning: Model did not make a tool call as expected. Raw content: '{response_message.content}'")
            return {"score": 0, "reasoning": "AI did not make the expected tool call."}

    except openai.APIError as e:
        print(f"OpenAI API Error during scoring: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during OpenAI scoring: {e}")
        import traceback
        traceback.print_exc()
        return None


# --- Example Usage ---
if __name__ == "__main__":
    gcs_image_uri_for_scoring = "gs://karma-videos/recycle.png"

    print(f"--- Attempting to score activity based on image: {gcs_image_uri_for_scoring} ---")

    print(f"\nStep 1: Getting labels from image_recognizer.py for: {gcs_image_uri_for_scoring}")
    detected_entities_dict = get_image_labels_and_entities(gcs_image_uri_for_scoring)

    if not detected_entities_dict or "error" in detected_entities_dict:
        print("\nScoring pipeline halted: Failed to get labels from the image.")
        if detected_entities_dict and "error" in detected_entities_dict:
            print(f"Error details: {detected_entities_dict['error']}")
    else:
        print("\n--- Labels/Entities from Image Recognizer (Sorted by Confidence) ---")
        sorted_entities_for_print = sorted(detected_entities_dict.items(), key=lambda item: item[1], reverse=True)
        for desc, score_val in sorted_entities_for_print:
            print(f"- {desc.capitalize()} (Score: {score_val:.2f})")

        labels_for_openai_processing = [
            f"{desc.capitalize()} (Score: {score_val:.2f})" for desc, score_val in sorted_entities_for_print
        ]

        print("\nStep 2: Generating activity description with OpenAI (from classifier.py)...")
        activity_description_from_ai = get_description(labels_for_openai_processing)

        if not activity_description_from_ai:
            print("\nScoring pipeline halted: Failed to generate activity description.")
        else:
            print(f"\nGenerated Activity Description: {activity_description_from_ai}")

            print("\nStep 3: Classifying Good Samaritan category (from classifier.py)...")
            # This function is expected to be imported from classifier.py
            good_samaritan_category = classify(
                activity_description_from_ai,
                labels_for_openai_processing
            )
            if not good_samaritan_category:
                print("Could not determine Good Samaritan category. Proceeding without this context for scoring.")
                good_samaritan_category = "No Specific Good Samaritan Activity Detected"  # Default
            else:
                print(f"Classified Good Samaritan Category: {good_samaritan_category}")

            print("\nStep 4: Getting societal benefit score...")
            score_info = get_score(
                activity_description_from_ai,
                labels_for_openai_processing,
                good_samaritan_category  # Pass the category here
            )

            if score_info:
                print(f"\n--- Societal Benefit Score for '{gcs_image_uri_for_scoring}' ---")
                print(f"Activity: {activity_description_from_ai}")
                if good_samaritan_category != "No Specific Good Samaritan Activity Detected":
                    print(f"Pre-classified Category: {good_samaritan_category}")
                print(f"Score: {score_info['score']}/20")
                print(f"Reasoning: {score_info['reasoning']}")
            else:
                print(
                    f"\nCould not determine societal benefit score for the activity from '{gcs_image_uri_for_scoring}'.")

    print(
        "\n\nNote: This script uses OpenAI to assign a societal benefit score based on an activity description and pre-classification.")
    print("      Ensure all necessary API keys and credentials are set in your .env file.")
    print(
        "      Also, ensure 'image_recognizer.py' and 'classifier.py' (containing 'get_description' and 'classify_good_samaritan_activity_from_description_and_labels') are in the same directory or accessible in PYTHONPATH.")

