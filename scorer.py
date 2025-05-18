import os
import openai
from dotenv import load_dotenv
import json

load_dotenv()


from image_recognizer import get_image_labels_and_entities

from classifier import get_description
from classifier import classify


try:
    openai_client = openai.OpenAI()
except openai.OpenAIError as e:
    print(f"error initializing openaoi client: {e}")
    openai_client = None


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
        classified_good_samaritan_category: str | None = None,  
        model_name: str = "gpt-4o"
) -> dict[str, int | str] | None:

    if not openai_client:
        print("openai client not initialized")
        return None

    if not activity_description:
        print("no activity description provided for scoring")
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
                    print(f"Error: tool call arguments were not valid json: {tool_call.function.arguments}")
                    return {"score": 0, "reasoning": "ai response for arguments was not valid json."}
            else:
                print(f"rrror: unexpected tool called: {tool_call.function.name}")
                return {"score": 0, "reasoning": "ai called an unexpected tool."}
        else:
            print(f"warning: model did not make a tool call as expected. raw content: '{response_message.content}'")
            return {"score": 0, "reasoning": "ai did not make the expected tool call."}

    except openai.APIError as e:
        print(f"openai api Error during scoring: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during opneai scoring: {e}")
        import traceback
        traceback.print_exc()
        return None


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
            good_samaritan_category = classify(
                activity_description_from_ai,
                labels_for_openai_processing
            )
            if good_samaritan_category is None:
                print("Could not determine Good Samaritan category. Proceeding without this context for scoring.")
                good_samaritan_category = "No Specific Good Samaritan Activity Detected" 
            else:
                print(f"Classified Good Samaritan Category: {good_samaritan_category}")

            print("\nStep 4: Getting societal benefit score...")
            score_info = get_score(
                activity_description_from_ai,
                labels_for_openai_processing,
                good_samaritan_category  
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
