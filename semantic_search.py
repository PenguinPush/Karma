# semantic_search.py
import os
import openai  # For embeddings and scorer
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.collection import Collection
from bson.objectid import ObjectId  # If you store a unique _id for embeddings
# SentenceTransformer is no longer needed
# from sentence_transformers import SentenceTransformer
import numpy as np  # OpenAI embeddings are lists of floats, numpy might not be directly needed here
import datetime  # For timestamping new embeddings
import certifi  # For SSL certificate verification with MongoDB Atlas

# Imports - Assuming these files and functions exist and are importable
# The script will raise ImportError if they are not found.
from scorer import get_score
from image_recognizer import get_image_labels_and_entities # Corrected filename based on user's last code
from classifier import get_description
from classifier import classify

# Load environment variables from .env file
# GOOGLE_APPLICATION_CREDENTIALS (for Image_recognizer.py) is now expected to be a JSON string.
# OPENAI_API_KEY (for this script and scorer.py)
# MONGO_CONNECTION_STRING (for this script)
load_dotenv()

# --- Configuration ---
MONGO_URI = os.getenv("MONGO_CONNECTION_STRING")
DB_NAME = "karma"
EMBEDDINGS_COLLECTION_NAME = "vectors"
ATLAS_VECTOR_SEARCH_INDEX_NAME = "vector_index"
OPENAI_EMBEDDING_MODEL = "text-embedding-3-large" # Using the model specified by the user

print("a")  # From user's provided code; keeping it as requested.
SIMILARITY_THRESHOLD = 0.80 # User specified 0.80. Note: OpenAI embedding similarity scores might behave differently.

# Initialize OpenAI client
# This will raise an exception if OPENAI_API_KEY is not set or client init fails.
openai_client = openai.OpenAI()

# SentenceTransformer model is no longer initialized here.
# embedding_model = SentenceTransformer('all-MiniLM-L6-v2')


# --- MongoDB Connection ---
# This will raise an exception if MONGO_URI is None or connection fails.
if not MONGO_URI:  # This check is essential for operation.
    raise ValueError("MONGO_CONNECTION_STRING not found in environment variables. Cannot connect to MongoDB.")

print(f"Connecting to MongoDB...")
mongo_client = MongoClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
db = mongo_client[DB_NAME]
embeddings_collection = db[EMBEDDINGS_COLLECTION_NAME]
mongo_client.admin.command('ping')  # Test connection - will raise ConnectionFailure if fails
print("MongoDB connection successful.")
print(f"Using embeddings collection for search and storage: {DB_NAME}.{EMBEDDINGS_COLLECTION_NAME}")
print(
    f"Ensure Atlas Vector Search Index '{ATLAS_VECTOR_SEARCH_INDEX_NAME}' exists on the 'embedding' field and is configured for {OPENAI_EMBEDDING_MODEL} dimensions (e.g., 3072 for text-embedding-3-large).")


def get_text_embedding(text: str, model: str = OPENAI_EMBEDDING_MODEL) -> list[float]:
    """Generates a numerical embedding for a given text string using OpenAI."""
    # Assumes openai_client is initialized successfully and text is valid.
    print(f"Generating OpenAI embedding for text (model: {model}): '{text[:70]}...'")
    response = openai_client.embeddings.create(input=[text], model=model)
    return response.data[0].embedding


def find_similar_embedding_in_db_atlas(query_embedding: list[float], collection: Collection,
                                       index_name: str) -> dict | None:
    """
    Finds a similar embedding in the MongoDB Atlas collection using Vector Search.
    Will raise exceptions on DB errors. Returns None if no suitable match.
    """
    # Assumes query_embedding, collection, and index_name are valid and collection exists.
    print(f"Performing Atlas Vector Search on index '{index_name}'...")

    vector_search_pipeline = [
        {
            "$vectorSearch": {
                "index": index_name,
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": 100,
                "limit": 1
            }
        },
        {
            "$project": {
                "_id": 1,
                "description_text": 1,
                "karma_points": 1,
                "score": {"$meta": "vectorSearchScore"}
            }
        }
    ]

    results = list(collection.aggregate(vector_search_pipeline))

    if results:
        best_match_doc = results[0]
        search_score = best_match_doc.get("score", 0.0)
        print(
            f"Atlas Vector Search found a match: '{best_match_doc.get('description_text', 'N/A')}' with search score: {search_score:.4f}")

        if search_score >= SIMILARITY_THRESHOLD:
            print(f"Score: {search_score:.4f}") # From user's code, can be re-added if needed for debugging
            return best_match_doc
        else:
            print(f"Match found but score {search_score:.4f} is below threshold {SIMILARITY_THRESHOLD}.")
            return None
    else:
        print("No results from Atlas Vector Search.")
        return None


def process_activity_and_get_points(
        activity_category: str,
        activity_description: str,
        detected_labels: list[str] | None = None
) -> int:
    """
    Orchestrates getting points for an activity using OpenAI embeddings and Atlas Vector Search.
    Compares new activity embedding to existing ones in the DB.
    If similar, uses existing points. Otherwise, calculates points independently and
    STORES the new embedding and points in the database.
    Will raise exceptions on errors.
    """
    if not embeddings_collection: # This check is more for logical completeness
        raise ConnectionError("Critical: MongoDB embeddings collection not initialized (should have failed earlier if MONGO_URI was an issue).")

    text_for_embedding = f"Category: {activity_category}. Description: {activity_description}"
    print(f"\nText for embedding: {text_for_embedding}")

    query_embedding = get_text_embedding(text_for_embedding)

    similar_doc = find_similar_embedding_in_db_atlas(query_embedding, embeddings_collection,
                                                     ATLAS_VECTOR_SEARCH_INDEX_NAME)

    if similar_doc and "karma_points" in similar_doc:
        points = int(similar_doc["karma_points"])
        print(f"Similar activity found in DB. Using existing karma points: {points}")
        return points
    else:
        print("No sufficiently similar activity found in DB. Calculating new karma points...")
        calculated_score_data = get_score(activity_description, detected_labels, activity_category)

        new_karma_points = calculated_score_data["score"]
        reasoning = calculated_score_data.get("reasoning", "N/A")
        print(f"Calculated new points: {new_karma_points}. Reasoning: {reasoning}")

        # Store the new embedding, points, and the text used for embedding
        new_embedding_doc = {
            "embedding": query_embedding,
            "karma_points": new_karma_points,
            "description_text": text_for_embedding,  # Store the text that generated this embedding
            "original_activity_description": activity_description,  # Store for reference
            "original_category": activity_category,  # Store for reference
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        }
        # This will raise an exception if DB insertion fails
        insert_result = embeddings_collection.insert_one(new_embedding_doc)
        print(f"New activity embedding and points stored in DB with ID: {insert_result.inserted_id}")

        return new_karma_points


# --- Example Usage ---
if __name__ == "__main__":
    # The script will now fail at the MongoDB or OpenAI client initialization if issues occur,
    # or on imports if the other files/functions are missing.

    test_gcs_image_uri = "gs://karma-videos/litter.png"
    print(f"\n--- Full Pipeline Test for Image: {test_gcs_image_uri} ---")

    print("\nStep 1: Getting image labels...")
    image_labels_dict = get_image_labels_and_entities(test_gcs_image_uri)

    formatted_labels = [f"{desc.capitalize()} (Score: {score:.2f})" for desc, score in image_labels_dict.items()]
    print("Image Labels:", formatted_labels if formatted_labels else "None")

    print("\nStep 2: Getting activity description...")
    img_activity_description = get_description(formatted_labels)
    if not img_activity_description:
        raise ValueError(
            "img_activity_description from classifier.get_description cannot be None for further processing.")
    print(f"Generated Activity Description: {img_activity_description}")

    print("\nStep 3: Classifying Good Samaritan category...")
    good_samaritan_category = classify(
        img_activity_description,
        formatted_labels
    )
    if not good_samaritan_category:
        raise ValueError("good_samaritan_category from classifier.classify cannot be None for further processing.")
    print(f"Classified Category: {good_samaritan_category}")

    print("\nStep 4: Processing activity for karma points...")
    final_points = process_activity_and_get_points(
        activity_category=good_samaritan_category,
        activity_description=img_activity_description,
        detected_labels=formatted_labels
    )

    print(f"\n--- Final Karma Points for '{test_gcs_image_uri}': {final_points} ---")

    print("\n--- Direct Test with 'litter a bottle' ---") # User's example text
    known_desc = "A person is picking up garbage found on a sidewalk"
    known_cat = "Litter Pickup"
    known_labels = ["sidewalk", "litter", "cleaning", "garbage", "city"]
    points_for_known = process_activity_and_get_points(known_cat, known_desc, known_labels)
    print(f"Points for '{known_desc}': {points_for_known}")

    # Example of a new activity that might not be in the DB initially
    print("\n--- Test with a potentially new activity: 'Planting a tree in a community garden' ---")
    new_activity_desc = "Someone is planting a small tree in a designated community garden plot."
    new_activity_cat = "Sustainable Gardening/Planting"
    new_activity_labels = ["tree", "planting", "community garden", "soil", "person"]
    points_for_new_activity = process_activity_and_get_points(
        new_activity_cat,
        new_activity_desc,
        new_activity_labels
    )
    print(f"Points for '{new_activity_desc}': {points_for_new_activity}")
    print("(Check your MongoDB 'vectors' collection to see if this new entry was added if it wasn't found initially)")

    if mongo_client: # This check remains to prevent AttributeError if mongo_client is None due to connection failure
        mongo_client.close()
        print("\nMongoDB connection closed.")

    print(
        "\nReminder: Ensure your Atlas Vector Search index is configured for the chosen OpenAI embedding model's dimensions.")
    print("And that GOOGLE_APPLICATION_CREDENTIALS in .env is a JSON string if Image_recognizer.py expects that.")
