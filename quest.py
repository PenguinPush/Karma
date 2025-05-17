# quest.py
import uuid
import datetime
import random  # For potentially picking a random friend or category later
from bson.objectid import ObjectId  # For MongoDB interaction
from pymongo.collection import Collection  # For type hinting
from typing import Optional, List, Dict  # Import necessary types


class Quest:
    """
    Represents a quest assigned to a user, potentially nominated by another user.
    Attributes are accessed directly. Focuses on core quest data.
    Expiry and point awarding are handled by external application logic.
    """

    def __init__(self,
                 user_to_id: str,
                 target_category: str,
                 # end_time, creation_time, points_awarded, completion_time removed
                 user_from_id: Optional[str] = None,
                 nominated_by_image_uri: Optional[str] = None,
                 quest_id_str: Optional[str] = None,  # Application-level UUID string
                 status: str = "pending",
                 completion_image_uri: Optional[str] = None,
                 mongo_id: Optional[ObjectId] = None):  # MongoDB's _id
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
        self.status: str = status  # Valid statuses: "pending", "completed", "expired_by_system"
        self.completion_image_uri: Optional[str] = completion_image_uri
        self.mongo_id: Optional[ObjectId] = mongo_id

        # --- MongoDB Interaction Methods ---

    def to_mongo(self) -> Dict:
        """Converts the Quest object to a dictionary suitable for MongoDB."""
        return {
            "quest_id_str": self.quest_id_str,
            "user_to_id": self.user_to_id,
            "user_from_id": self.user_from_id,
            "nominated_by_image_uri": self.nominated_by_image_uri,
            "target_category": self.target_category,
            "status": self.status,
            "completion_image_uri": self.completion_image_uri,
            # Creation time, end time, points, completion time are now managed externally
            # or stored in MongoDB directly by the application logic if needed.
        }

    @classmethod
    def from_mongo(cls, data: Dict) -> 'Quest':
        """Creates a Quest object from MongoDB data dictionary."""
        if not data:
            raise ValueError("Cannot create Quest from empty data.")

        return cls(
            quest_id_str=data.get("quest_id_str"),
            user_to_id=data["user_to_id"],  # Assuming these are required
            target_category=data["target_category"],
            user_from_id=data.get("user_from_id"),
            nominated_by_image_uri=data.get("nominated_by_image_uri"),
            status=data.get("status", "pending"),
            completion_image_uri=data.get("completion_image_uri"),
            mongo_id=data.get("_id")
        )

    def save_to_db(self, quests_collection: Collection):
        """Saves the current quest object to the MongoDB collection."""
        quest_data = self.to_mongo()
        if self.mongo_id:
            result = quests_collection.update_one(
                {"_id": self.mongo_id},
                {"$set": quest_data}
            )
            # print(f"Quest {self.quest_id_str} (MongoDB ID: {self.mongo_id}) updated.")
        else:
            result = quests_collection.insert_one(quest_data)
            self.mongo_id = result.inserted_id
            # print(f"Quest {self.quest_id_str} inserted with MongoDB ID: {self.mongo_id}")

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
        # Ensure `typing.Union` is used for Python < 3.10 if `|` causes issues,
        # but for Python 3.11, `str | ObjectId` should be fine.
        # For broader compatibility, one might use `Union[str, ObjectId]`.
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

    @classmethod
    def delete_quest(cls, quests_collection: Collection, quest_id_str: str) -> int:
        """Deletes a quest by its application-level string ID. Returns delete count."""
        result = quests_collection.delete_one({"quest_id_str": quest_id_str})
        print(f"Quest {quest_id_str} deletion attempt. Deleted count: {result.deleted_count}")
        return result.deleted_count

    # --- Class Methods for Quest Generation ---
    @classmethod
    def generate_new_system_quest_data(cls,
                                       user_to_id: str,
                                       target_category: str,
                                       duration_seconds: int = 24 * 60 * 60) -> Dict:
        """
        Generates data for a brand new quest, typically system-initiated.
        This data can then be used to create a Quest object or save directly to DB.
        Includes creation_time and end_time for external management.
        """
        if duration_seconds <= 0:
            raise ValueError("Quest duration must be positive.")

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        end_time_utc = now_utc + datetime.timedelta(seconds=duration_seconds)

        quest_data: Dict[str, any] = {
            "quest_id_str": str(uuid.uuid4()),
            "user_to_id": user_to_id,
            "target_category": target_category,
            "creation_time": now_utc,  # For external tracking of expiry
            "end_time": end_time_utc,  # For external tracking of expiry
            "status": "pending",
            "user_from_id": None,
            "nominated_by_image_uri": None,
            "completion_image_uri": None,
            "points_awarded": None
        }
        # print(f"Generated new system quest data for user '{user_to_id}', category '{target_category}', ends {end_time_utc.isoformat()}.")
        return quest_data

    # --- Instance Methods ---
    def mark_as_completed(self, completion_image_uri: str) -> bool:
        """
        Marks the current quest as completed.
        Expiry check should be done by the calling application logic.
        Point awarding is handled externally.

        Args:
            completion_image_uri: The GCS URI of the image uploaded by the user for this quest.

        Returns:
            True if the quest status was successfully updated to "completed", False otherwise.
        """
        allowed_statuses_for_completion = ["pending"]
        if self.status not in allowed_statuses_for_completion:
            # print(f"Quest {self.quest_id_str} cannot be completed. Current status: {self.status}")
            return False

        # External logic should verify if quest is expired before calling this.
        # For example, by checking creation_time + duration against current time.

        self.completion_image_uri = completion_image_uri
        self.status = "completed"
        # print(f"Quest {self.quest_id_str} marked as completed by user '{self.user_to_id}'.")
        return True

    def generate_nomination_data(self,
                                 next_user_to_id: str,
                                 next_target_category: str,
                                 nomination_duration_seconds: int = 24 * 60 * 60) -> Optional[Dict]:
        """
        Generates data for a new quest to be nominated to a friend.
        This should be called after the current quest is confirmed completed.
        Includes creation_time and end_time for external management of the new quest.
        """
        if self.status != "completed" or not self.completion_image_uri:
            # print(f"Quest {self.quest_id_str} must be completed before nominating. Current status: {self.status}")
            return None

        if nomination_duration_seconds <= 0:
            raise ValueError("Nominated quest duration must be positive.")

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        new_end_time_utc = now_utc + datetime.timedelta(seconds=nomination_duration_seconds)

        # print(f"User '{self.user_to_id}' generating nomination data for user '{next_user_to_id}', category '{next_target_category}'.")
        new_quest_data: Dict[str, any] = {
            "quest_id_str": str(uuid.uuid4()),
            "user_to_id": next_user_to_id,
            "target_category": next_target_category,
            "creation_time": now_utc,  # For external tracking of expiry
            "end_time": new_end_time_utc,  # For external tracking of expiry
            "user_from_id": self.user_to_id,
            "nominated_by_image_uri": self.completion_image_uri,
            "status": "pending",
            "completion_image_uri": None,
            "points_awarded": None
        }
        return new_quest_data

    def __repr__(self) -> str:
        return (f"<Quest(quest_id_str='{self.quest_id_str}', mongo_id='{self.mongo_id}', user_to='{self.user_to_id}', "
                f"category='{self.target_category}', status='{self.status}')>")


if __name__ == "__main__":
    pass