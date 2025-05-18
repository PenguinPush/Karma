# quest.py
import uuid
import datetime
import random  # For potentially picking a random friend or category later
from bson.objectid import ObjectId
from pymongo.collection import Collection  # For type hinting
from pymongo import MongoClient  # Only needed for __main__ example
from typing import Optional, List, Dict  # For type hinting
from dotenv import load_dotenv

load_dotenv()

# Define a list of possible quest categories for random selection
# This is added as it's necessary for the new methods.
POSSIBLE_QUEST_CATEGORIES = [
    "Recycling Activity",
    "Litter Pickup",
    "Using Public Transit",
    "Environmental Care",
    "Self-Care Activity",
    "Helping Others (General)",
    "Community Involvement",
    "Creativity and Learning"
]


class Quest:
    """
    Represents a quest assigned to a user, potentially nominated by another user.
    Focuses on core attributes and MongoDB interaction.
    Workflow methods for completion/expiry now return data for the next quest.
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
            self.expiry_time: Optional[datetime.datetime] = None

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
            data["expiry_time"] = self.expiry_time
        return data

    @classmethod
    def from_mongo(cls, data: Dict) -> 'Quest':
        """Creates a Quest object from MongoDB data dictionary."""
        if not data:
            raise ValueError("Cannot create Quest from empty data.")

        expiry_time_data = data.get("expiry_time")
        expiry_time_obj: Optional[datetime.datetime] = None
        if expiry_time_data and isinstance(expiry_time_data, datetime.datetime):
            expiry_time_obj = expiry_time_data if expiry_time_data.tzinfo else expiry_time_data.replace(
                tzinfo=datetime.timezone.utc)
        elif expiry_time_data and isinstance(expiry_time_data, str):
            try:
                expiry_time_obj = datetime.datetime.fromisoformat(expiry_time_data)
                if expiry_time_obj.tzinfo is None:
                    expiry_time_obj = expiry_time_obj.replace(tzinfo=datetime.timezone.utc)
            except ValueError:  # Keep existing print for this specific warning as it was in user's context
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
                   points_awarded: Optional[int] = None,
                   completion_time_db: Optional[datetime.datetime] = None):
        """
        Saves the current quest object to the MongoDB collection.
        """
        quest_data = self.to_mongo()

        if creation_time:
            if creation_time.tzinfo is None:
                creation_time = creation_time.replace(tzinfo=datetime.timezone.utc)
            quest_data["creation_time"] = creation_time

        if points_awarded is not None:
            quest_data["points_awarded"] = points_awarded

        if completion_time_db:  # For storing actual completion time in DB
            if completion_time_db.tzinfo is None:
                completion_time_db = completion_time_db.replace(tzinfo=datetime.timezone.utc)
            quest_data["completion_time"] = completion_time_db

        if self.mongo_id:
            quests_collection.update_one(  # Corrected: No insert_one after update
                {"_id": self.mongo_id},
                {"$set": quest_data}
            )
            # print(f"Quest {self.quest_id_str} (MongoDB ID: {self.mongo_id}) updated.") # Removed print
        else:
            # if "creation_time" not in quest_data and self.expiry_time: # Removed print
            #     pass
            # if "expiry_time" not in quest_data and self.expiry_time: # Removed print
            #      quest_data["expiry_time"] = self.expiry_time
            # elif "expiry_time" not in quest_data and not self.expiry_time: # Removed print
            #      pass

            result = quests_collection.insert_one(quest_data)
            self.mongo_id = result.inserted_id
            # print(f"Quest {self.quest_id_str} inserted with MongoDB ID: {self.mongo_id}") # Removed print

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
                # print(f"Invalid string format for MongoDB ObjectId: {mongo_id}") # Removed print
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
        # print(f"Quest {quest_id_str} deletion attempt. Deleted count: {result.deleted_count}") # Removed print
        return result.deleted_count

    # --- Class Methods for Quest Data Generation (Necessary for new methods) ---
    @classmethod
    def generate_new_system_quest_data(cls,
                                       user_to_id: str,
                                       target_category: str,
                                       duration_seconds: int = 24 * 60 * 60) -> Dict:
        if duration_seconds <= 0:
            raise ValueError("Quest duration must be positive.")
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        end_time_utc = now_utc + datetime.timedelta(seconds=duration_seconds)
        quest_data: Dict[str, any] = {
            "quest_id_str": str(uuid.uuid4()),
            "user_to_id": user_to_id,
            "target_category": target_category,
            "creation_time": now_utc,  # Stored in DB for expiry logic
            "expiry_time": end_time_utc,  # Stored in DB for expiry logic
            "status": "pending",
            "user_from_id": "682975d597fb90e0ad097cbf",
            "nominated_by_image_uri": None,
            "completion_image_uri": None,
            "points_awarded": None  # Points handled externally
        }
        return quest_data

    def _generate_nomination_data_internal(self,
                                           next_user_to_id: str,
                                           next_target_category: str,
                                           nomination_duration_seconds: int = 24 * 60 * 60) -> Optional[Dict]:
        if self.status != "completed" or not self.completion_image_uri:
            return None  # Should not happen if called correctly after completion
        if nomination_duration_seconds <= 0:
            raise ValueError("Nominated quest duration must be positive.")
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        new_end_time_utc = now_utc + datetime.timedelta(seconds=nomination_duration_seconds)
        new_quest_data: Dict[str, any] = {
            "quest_id_str": str(uuid.uuid4()),
            "user_to_id": next_user_to_id,
            "target_category": next_target_category,
            "creation_time": now_utc,
            "expiry_time": new_end_time_utc,
            "user_from_id": self.user_to_id,
            "nominated_by_image_uri": self.completion_image_uri,
            "status": "pending",
            "completion_image_uri": None,
            "points_awarded": None
        }
        return new_quest_data

    # --- Instance Methods for Workflow ---
    def _mark_as_completed_internal(self,
                                    completion_image_uri: str) -> bool:  # Renamed to avoid conflict with user's flow
        if self.status != "pending":
            return False
        self.completion_image_uri = completion_image_uri
        self.status = "completed"
        return True

    def is_expired(self) -> bool:
        if self.expiry_time and datetime.datetime.now(datetime.timezone.utc) > self.expiry_time:
            return True
        return False

    def handle_completion_and_nominate(self,
                                       completion_image_uri: str,
                                       user_friends_list: List[str],  # List of friend user_ids (strings)
                                       quests_collection: Collection,
                                       users_collection: Collection, # Not directly needed if User object updates itself
                                       all_possible_categories: List[str] = POSSIBLE_QUEST_CATEGORIES,
                                       nomination_duration_seconds: int = 24 * 60 * 60) -> Optional[Dict]:
        """
        Handles the completion of this quest by the user.
        1. Marks this quest as completed.
        2. Saves its updated status and completion image to the DB.
        3. Deletes this quest from the database.
        4. Returns data for a new quest to be nominated to a random friend,
           or for a new system quest for the current user if no eligible friends.
        Points awarding is handled externally.
        """
        if self.is_expired():
            # print(f"Quest {self.quest_id_str} is expired. Cannot complete. Triggering expiry logic instead.") # Removed print
            # This method should not call another workflow method directly to avoid complex call chains.
            # The calling application logic should check is_expired() before calling this.
            # If it's called on an expired quest, we mark it and delete, then return data for a new system quest.
            self.status = "expired_by_system"  # Mark as expired before deletion
            # For record keeping, save the expired status and completion attempt time
            self.save_to_db(quests_collection, completion_time_db=datetime.datetime.now(datetime.timezone.utc))
            Quest.delete_quest(quests_collection, self.quest_id_str)
            return Quest.generate_new_system_quest_data(self.user_to_id, random.choice(all_possible_categories),
                                                        nomination_duration_seconds)

        if not self._mark_as_completed_internal(completion_image_uri):
            # print(f"Could not mark quest {self.quest_id_str} as completed (status: {self.status}).") # Removed print
            return None

        # Save the completed status, completion image, and a completion timestamp to DB
        self.save_to_db(quests_collection, completion_time_db=datetime.datetime.now(datetime.timezone.utc))
        # print(f"Quest {self.quest_id_str} marked completed in DB.") # Removed print

        Quest.delete_quest(quests_collection, self.quest_id_str)
        # print(f"Completed quest {self.quest_id_str} deleted from DB.") # Removed print

        next_quest_data: Optional[Dict] = None
        eligible_friends = [f_id for f_id in user_friends_list if f_id != self.user_to_id]

        if eligible_friends:
            random_friend_id = random.choice(eligible_friends)
            new_target_category = random.choice(all_possible_categories)
            next_quest_data = self._generate_nomination_data_internal(
                random_friend_id, new_target_category, nomination_duration_seconds
            )
            # if next_quest_data: # Removed print
            # print(f"Generated nomination data for friend {random_friend_id}, new quest ID (to be created): {next_quest_data['quest_id_str']}.")
        else:  # No eligible friends, generate a new system quest for the current user
            # print(f"User {self.user_to_id} has no eligible friends. Generating new system quest data for them.") # Removed print
            next_quest_data = Quest.generate_new_system_quest_data(
                self.user_to_id, random.choice(all_possible_categories), nomination_duration_seconds
            )
            # if next_quest_data: # Removed print
            # print(f"Generated new system quest data for user {self.user_to_id}, new quest ID (to be created): {next_quest_data['quest_id_str']}.")

        return next_quest_data

    def handle_expiry_and_regenerate_data(self,
                                          quests_collection: Collection,
                                          all_possible_categories: List[str] = POSSIBLE_QUEST_CATEGORIES,
                                          new_quest_duration_seconds: int = 24 * 60 * 60) -> Optional[Dict]:
        """
        Handles the expiry of this quest if it's pending and expired.
        1. Deletes this quest from the database.
        2. Returns data for a new system quest for the same user.
        """
        if self.status != "pending" or not self.is_expired():
            # print(f"Quest {self.quest_id_str} is not pending or not expired (status: {self.status}, expired: {self.is_expired()}). No expiry action taken.") # Removed print
            return None

        Quest.delete_quest(quests_collection, self.quest_id_str)
        # print(f"Expired quest {self.quest_id_str} deleted from DB.") # Removed print

        new_quest_data = Quest.generate_new_system_quest_data(
            self.user_to_id,
            random.choice(all_possible_categories),
            new_quest_duration_seconds
        )
        # print(f"Generated new system quest data for user {self.user_to_id} due to expiry of {self.quest_id_str}, new quest ID (to be created): {new_quest_data['quest_id_str']}.") # Removed print
        return new_quest_data

    def __repr__(self) -> str:
        expiry_str = self.expiry_time.isoformat() if self.expiry_time else "N/A"
        return (f"<Quest(quest_id_str='{self.quest_id_str}', mongo_id='{self.mongo_id}', user_to='{self.user_to_id}', "
                f"category='{self.target_category}', status='{self.status}', expiry='{expiry_str}')>")
