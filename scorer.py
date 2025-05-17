# activity_scorer.py
import os
import openai
from dotenv import load_dotenv
import json

# Load environment variables from .env file
# Ensure your .env file has OPENAI_API_KEY defined
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
        model_name: str = "gpt-4o"
) -> dict[str, int | str] | None:
    """
    Uses OpenAI to generate a societal benefit score (0-20) and reasoning
    for a given activity description and optional supporting labels.

    Args:
        activity_description: A natural language description of the activity.
        detected_labels: An optional list of strings, where each string is a label
                         detected in an image related to the activity.
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
        "Recycling Activity"
        "Litter Pickup"
        "Using Public Transit"
        "Environmental Care"
        "Health and Wellness"
        "Helping Others (General)"
        "Community Involvement"
        "Creativity and Learning"
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
        "Based on this information, please provide a societal benefit score (0-20) and a brief reasoning by calling the 'set_societal_benefit_score' function."
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
            temperature=0.2,  # Lower temperature for more consistent scoring
            max_tokens=200  # Ample space for score and reasoning
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
    # Example 1: Recycling
    desc1 = "A person is placing a plastic bottle into a clearly marked recycling bin."
    labels1 = ["Plastic bottle", "Recycling bin", "Hand", "Person"]
    print(f"\n--- Scoring Activity 1: Recycling ---")
    score_info1 = get_score(desc1, labels1)
    if score_info1:
        print(f"Score: {score_info1['score']}, Reasoning: {score_info1['reasoning']}")

    # Example 2: Picking up litter
    desc2 = "Someone is picking up trash from a public park and putting it into a bag."
    labels2 = ["Trash", "Park", "Person", "Picking up", "Plastic bag"]
    print(f"\n--- Scoring Activity 2: Litter Pickup ---")
    score_info2 = get_score(desc2, labels2)
    if score_info2:
        print(f"Score: {score_info2['score']}, Reasoning: {score_info2['reasoning']}")

    # Example 3: Neutral activity
    desc3 = "A man takes a shower and shaves his beard"
    labels3 = ["Man, hair, care, cleaning"]
    print(f"\n--- Scoring Activity 3: Neutral ---")
    score_info3 = get_score(desc3, labels3)
    if score_info3:
        print(f"Score: {score_info3['score']}, Reasoning: {score_info3['reasoning']}")

    # Example 4: Activity with less obvious direct societal benefit
    desc4 = "Someone is playing a video game."
    labels4 = ["Video game", "Controller", "Screen", "Person", "Sitting"]
    print(f"\n--- Scoring Activity 4: Playing Video Game ---")
    score_info4 = get_score(desc4, labels4)
    if score_info4:
        print(f"Score: {score_info4['score']}, Reasoning: {score_info4['reasoning']}")

    # Example 5: Description only
    desc5 = "Volunteering at a local soup kitchen to serve meals to the homeless."
    print(f"\n--- Scoring Activity 5: Volunteering (Description Only) ---")
    score_info5 = get_score(desc5)
    if score_info5:
        print(f"Score: {score_info5['score']}, Reasoning: {score_info5['reasoning']}")

    print("\nNote: This script uses OpenAI to assign a societal benefit score.")
    print("Ensure your OPENAI_API_KEY is set in your .env file.")
