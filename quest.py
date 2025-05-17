# quest.py
import uuid
import datetime
# import random # No longer needed for simplified example
from bson.objectid import ObjectId
from pymongo.collection import Collection
from pymongo import MongoClient
from typing import Optional, List, Dict
from dotenv import load_dotenv

load_dotenv()


class Quest:
    """
    Represents a quest assigned to a user, potentially nominated by another user.
    Focuses on core attributes and MongoDB interaction.
    Application logic for completion, expiry, and nomination is handled externally.
    """

    def __init__(self,
                 user_to_id: str,
                 target_category: str,
                 user_from_id: Optional[str] = None,
                 nominated_by_image_uri: Optional[str] = None,
                 quest_id_str: Optional[str] = None,
                 status: str = "pending",
                 completion_image_uri: Optional[str] = None,
                 mongo_id: Optional[ObjectId] = None):
        """
        Initializes a Quest object.

        Args:
            user_to_id: The ID of the user to whom this quest is assigned.
            target_category: The category of "Good Samaritan" deed for bonus points.
            user_from_id: (Optional) The ID of the user who nominated/sent this quest.
            nominated_by_image_uri: (Optional) GCS URI of the image from the nominator's completed deed.
            quest_id_str: (Optional) A unique string ID for the quest. If None, one will be generated.
            status: (Optional) The current status of the quest (e.g., "pending", "completed", "expired_by_system").
            completion_image_uri: (Optional) GCS URI of the image uploaded by user_to_id upon completion.
            mongo_id: (Optional) The MongoDB ObjectId if this quest is loaded from DB.
        """
        self.quest_id_str: str = quest_id_str if quest_id_str else str(uuid.uuid4())
        self.user_to_id: str = user_to_id
        self.user_from_id: Optional[str] = user_from_id
        self.nominated_by_image_uri: Optional[str] = nominated_by_image_uri
        self.target_category: str = target_category
        self.status: str = status
        self.completion_image_uri: Optional[str] = completion_image_uri
        self.mongo_id: Optional[ObjectId] = mongo_id
        # Removed: creation_time, end_time, points_awarded, completion_time as direct attributes
        # These are now expected to be stored directly in MongoDB by the application logic if needed.

    # --- MongoDB Interaction Methods ---
    def to_mongo(self) -> Dict:
        """Converts the Quest object to a dictionary suitable for MongoDB."""
        # Note: creation_time and end_time are not part of the Quest object anymore.
        # If your application needs to store them, they should be added to the dictionary
        # by the calling code before inserting/updating into MongoDB.
        return {
            "quest_id_str": self.quest_id_str,
            "user_to_id": self.user_to_id,
            "user_from_id": self.user_from_id,
            "nominated_by_image_uri": self.nominated_by_image_uri,
            "target_category": self.target_category,
            "status": self.status,
            "completion_image_uri": self.completion_image_uri,
        }

    @classmethod
    def from_mongo(cls, data: Dict) -> 'Quest':
        """Creates a Quest object from MongoDB data dictionary."""
        if not data:
            raise ValueError("Cannot create Quest from empty data.")

        return cls(
            quest_id_str=data.get("quest_id_str"),
            user_to_id=data["user_to_id"],
            target_category=data["target_category"],
            user_from_id=data.get("user_from_id"),
            nominated_by_image_uri=data.get("nominated_by_image_uri"),
            status=data.get("status", "pending"),
            completion_image_uri=data.get("completion_image_uri"),
            mongo_id=data.get("_id")
        )

    def save_to_db(self, quests_collection: Collection,
                   creation_time: Optional[datetime.datetime] = None,
                   end_time: Optional[datetime.datetime] = None,
                   points_awarded: Optional[int] = None):
        """
        Saves the current quest object to the MongoDB collection.
        Optionally includes creation_time, end_time, and points_awarded if provided,
        as these are now managed externally to the Quest object itself.
        """
        quest_data = self.to_mongo()

        # Add externally managed fields if provided
        if creation_time:
            quest_data["creation_time"] = creation_time
        if end_time:
            quest_data["end_time"] = end_time
        if points_awarded is not None:  # Allow 0 points
            quest_data["points_awarded"] = points_awarded

        if self.mongo_id:
            result = quests_collection.update_one(
                {"_id": self.mongo_id},
                {"$set": quest_data}
            )
            print(f"Quest {self.quest_id_str} (MongoDB ID: {self.mongo_id}) updated.")
        else:
            # If it's a new quest, creation_time and end_time are particularly important
            # to be stored by the application logic.
            if "creation_time" not in quest_data:
                print(
                    f"Warning: Saving new quest {self.quest_id_str} without 'creation_time'. Expiry management might be affected.")
            if "end_time" not in quest_data:
                print(
                    f"Warning: Saving new quest {self.quest_id_str} without 'end_time'. Expiry management might be affected.")

            result = quests_collection.insert_one(quest_data)
            self.mongo_id = result.inserted_id
            print(f"Quest {self.quest_id_str} inserted with MongoDB ID: {self.mongo_id}")

    @classmethod
    def get_quest_by_quest_id_str(cls, quests_collection: Collection, quest_id_str: str) -> Optional['Quest']:
        """Retrieves a quest by its application-level string ID (quest_id_str)."""
        data = quests_collection.find_one({"quest_id_str": quest_id_str})
        if data:
            return cls.from_mongo(data)
        return None

    @classmethod
    def get_quest_by_mongo_id(cls, quests_collection: Collection, mongo_id: str | ObjectId) -> Optional['Quest']:
        """Retrieves a quest by its MongoDB ObjectId."""
        if isinstance(mongo_id, str):
            try:
                mongo_id = ObjectId(mongo_id)
            except Exception:
                print(f"Invalid string format for MongoDB ObjectId: {mongo_id}")
                return None
        data = quests_collection.find_one({"_id": mongo_id})
        if data:
            return cls.from_mongo(data)
        return None

    @classmethod
    def get_quests_for_user(cls, quests_collection: Collection, user_to_id: str, status: Optional[str] = "pending") -> \
    List['Quest']:
        """Retrieves quests for a specific user, optionally filtered by status."""
        query: Dict[str, any] = {"user_to_id": user_to_id}
        if status:
            query["status"] = status
        quests_data = quests_collection.find(query)
        return [cls.from_mongo(data) for data in quests_data]

    @classmethod
    def get_all_quests(cls, quests_collection: Collection) -> List['Quest']:
        """Retrieves all quests from the collection."""
        quests_data = quests_collection.find()
        return [cls.from_mongo(data) for data in quests_data]


    def __repr__(self) -> str:
        return (f"<Quest(quest_id_str='{self.quest_id_str}', mongo_id='{self.mongo_id}', user_to='{self.user_to_id}', "
                f"category='{self.target_category}', status='{self.status}')>")
