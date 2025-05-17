# quest.py
import uuid
import datetime
import random  # For potentially picking a random friend or category later
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
    Application logic for completion, and nomination is handled externally.
    """

    def __init__(self,
                 user_to_id: str,
                 target_category: str,
                 expiry_time: Optional[datetime.datetime] = None,  # Added expiry_time
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
            expiry_time: (Optional) The datetime when this quest expires (timezone-aware recommended).
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

        if expiry_time:
            self.expiry_time: Optional[datetime.datetime] = expiry_time if expiry_time.tzinfo else expiry_time.replace(
                tzinfo=datetime.timezone.utc)
        else:
            self.expiry_time: Optional[datetime.datetime] = None  # Can be set later or if not applicable initially

        self.status: str = status
        self.completion_image_uri: Optional[str] = completion_image_uri
        self.mongo_id: Optional[ObjectId] = mongo_id

    # --- MongoDB Interaction Methods ---
    def to_mongo(self) -> Dict:
        """Converts the Quest object to a dictionary suitable for MongoDB."""
        data = {
            "quest_id_str": self.quest_id_str,
            "user_to_id": self.user_to_id,
            "user_from_id": self.user_from_id,
            "nominated_by_image_uri": self.nominated_by_image_uri,
            "target_category": self.target_category,
            "status": self.status,
            "completion_image_uri": self.completion_image_uri,
        }
        if self.expiry_time:
            data["expiry_time"] = self.expiry_time  # Store as BSON date
        return data

    @classmethod
    def from_mongo(cls, data: Dict) -> 'Quest':
        """Creates a Quest object from MongoDB data dictionary."""
        if not data:
            raise ValueError("Cannot create Quest from empty data.")

        expiry_time_data = data.get("expiry_time")  # MongoDB returns datetime objects
        expiry_time_obj: Optional[datetime.datetime] = None
        if expiry_time_data and isinstance(expiry_time_data, datetime.datetime):
            expiry_time_obj = expiry_time_data if expiry_time_data.tzinfo else expiry_time_data.replace(
                tzinfo=datetime.timezone.utc)
        elif expiry_time_data and isinstance(expiry_time_data, str):  # Handle if stored as ISO string
            try:
                expiry_time_obj = datetime.datetime.fromisoformat(expiry_time_data)
                if expiry_time_obj.tzinfo is None:
                    expiry_time_obj = expiry_time_obj.replace(tzinfo=datetime.timezone.utc)
            except ValueError:
                print(f"Warning: Could not parse expiry_time string '{expiry_time_data}' from MongoDB.")

        return cls(
            quest_id_str=data.get("quest_id_str"),
            user_to_id=data["user_to_id"],
            target_category=data["target_category"],
            expiry_time=expiry_time_obj,
            user_from_id=data.get("user_from_id"),
            nominated_by_image_uri=data.get("nominated_by_image_uri"),
            status=data.get("status", "pending"),
            completion_image_uri=data.get("completion_image_uri"),
            mongo_id=data.get("_id")
        )

    def save_to_db(self, quests_collection: Collection,
                   creation_time: Optional[datetime.datetime] = None,
                   # end_time parameter removed, use self.expiry_time
                   points_awarded: Optional[int] = None):
        """
        Saves the current quest object to the MongoDB collection.
        Optionally includes creation_time and points_awarded if provided,
        as these are managed externally to the Quest object itself.
        expiry_time is saved if it's an attribute of the object.
        """
        quest_data = self.to_mongo()  # This will include self.expiry_time if set

        # Add externally managed fields if provided
        if creation_time:
            # Ensure creation_time is timezone-aware for consistency
            if creation_time.tzinfo is None:
                creation_time = creation_time.replace(tzinfo=datetime.timezone.utc)
            quest_data["creation_time"] = creation_time

        if points_awarded is not None:
            quest_data["points_awarded"] = points_awarded

        if self.mongo_id:
            result = quests_collection.update_one(
                {"_id": self.mongo_id},
                {"$set": quest_data}
            )
            print(f"Quest {self.quest_id_str} (MongoDB ID: {self.mongo_id}) updated.")
        else:
            if "creation_time" not in quest_data and self.expiry_time:  # If expiry_time is set, creation_time is also important
                print(
                    f"Warning: Saving new quest {self.quest_id_str} with expiry_time but without explicit 'creation_time'.")

            result = quests_collection.insert_one(quest_data)
            self.mongo_id = result.inserted_id
            print(f"Quest {self.quest_id_str} inserted with MongoDB ID: {self.mongo_id}")

    @classmethod
    def get_quest_by_quest_id_str(cls, quests_collection: Collection, quest_id_str: str) -> Optional['Quest']:
        data = quests_collection.find_one({"quest_id_str": quest_id_str})
        if data:
            return cls.from_mongo(data)
        return None

    @classmethod
    def get_quest_by_mongo_id(cls, quests_collection: Collection, mongo_id: str | ObjectId) -> Optional['Quest']:
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
        query: Dict[str, any] = {"user_to_id": user_to_id}
        if status:
            query["status"] = status
        quests_data = quests_collection.find(query)
        return [cls.from_mongo(data) for data in quests_data]

    @classmethod
    def get_all_quests(cls, quests_collection: Collection) -> List['Quest']:
        quests_data = quests_collection.find()
        return [cls.from_mongo(data) for data in quests_data]

    @classmethod
    def delete_quest(cls, quests_collection: Collection, quest_id_str: str) -> int:
        result = quests_collection.delete_one({"quest_id_str": quest_id_str})
        print(f"Quest {quest_id_str} deletion attempt. Deleted count: {result.deleted_count}")
        return result.deleted_count

    # --- Methods for application logic to call ---
    def mark_as_completed(self, completion_image_uri: str) -> bool:
        """
        Marks the current quest as completed.
        Expiry check and point awarding are handled by the calling application logic.
        """
        allowed_statuses_for_completion = ["pending"]
        if self.status not in allowed_statuses_for_completion:
            return False

        # Application logic should check self.is_expired() before calling this.
        self.completion_image_uri = completion_image_uri
        self.status = "completed"
        return True

    def is_expired(self) -> bool:
        """
        Checks if the quest is past its expiry_time.
        Returns True if expired, False otherwise or if expiry_time is not set.
        """
        if self.expiry_time and datetime.datetime.now(datetime.timezone.utc) > self.expiry_time:
            return True
        return False

    def __repr__(self) -> str:
        expiry_str = self.expiry_time.isoformat() if self.expiry_time else "N/A"
        return (f"<Quest(quest_id_str='{self.quest_id_str}', mongo_id='{self.mongo_id}', user_to='{self.user_to_id}', "
                f"category='{self.target_category}', status='{self.status}', expiry='{expiry_str}')>")
