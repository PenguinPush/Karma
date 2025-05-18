
import uuid
import datetime
import random  
from bson.objectid import ObjectId
from pymongo.collection import Collection 
from pymongo import MongoClient  
from typing import Optional, List, Dict 
from dotenv import load_dotenv

load_dotenv()


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
                 expiry_time: Optional[datetime.datetime] = None,
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

        if completion_time_db:  
            if completion_time_db.tzinfo is None:
                completion_time_db = completion_time_db.replace(tzinfo=datetime.timezone.utc)
            quest_data["completion_time"] = completion_time_db

        if self.mongo_id:
            quests_collection.update_one(  
                {"_id": self.mongo_id},
                {"$set": quest_data}
            )
            
        else:
           

            result = quests_collection.insert_one(quest_data)
            self.mongo_id = result.inserted_id

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
        return result.deleted_count

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
            "creation_time": now_utc,  
            "expiry_time": end_time_utc,  
            "status": "pending",
            "user_from_id": "682975d597fb90e0ad097cbf",
            "nominated_by_image_uri": None,
            "completion_image_uri": None,
            "points_awarded": None  
        }
        return quest_data

    def _generate_nomination_data_internal(self,
                                           next_user_to_id: str,
                                           next_target_category: str,
                                           nomination_duration_seconds: int = 24 * 60 * 60) -> Optional[Dict]:
        if self.status != "completed" or not self.completion_image_uri:
            return None  
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
                                       user_friends_list: List[str], 
                                       quests_collection: Collection,
                                       users_collection: Collection, 
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
            
            self.status = "expired_by_system"  
            self.save_to_db(quests_collection, completion_time_db=datetime.datetime.now(datetime.timezone.utc))
            Quest.delete_quest(quests_collection, self.quest_id_str)
            return Quest.generate_new_system_quest_data(self.user_to_id, random.choice(all_possible_categories),
                                                        nomination_duration_seconds)

        if not self._mark_as_completed_internal(completion_image_uri):
            return None

        self.save_to_db(quests_collection, completion_time_db=datetime.datetime.now(datetime.timezone.utc))

        Quest.delete_quest(quests_collection, self.quest_id_str)

        next_quest_data: Optional[Dict] = None
        eligible_friends = [f_id for f_id in user_friends_list if f_id != self.user_to_id]

        if eligible_friends:
            random_friend_id = random.choice(eligible_friends)
            new_target_category = random.choice(all_possible_categories)
            next_quest_data = self._generate_nomination_data_internal(
                random_friend_id, new_target_category, nomination_duration_seconds
            )
        else:  
            next_quest_data = Quest.generate_new_system_quest_data(
                self.user_to_id, random.choice(all_possible_categories), nomination_duration_seconds
            )

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
            return None

        Quest.delete_quest(quests_collection, self.quest_id_str)

        new_quest_data = Quest.generate_new_system_quest_data(
            self.user_to_id,
            random.choice(all_possible_categories),
            new_quest_duration_seconds
        )
        return new_quest_data

    def __repr__(self) -> str:
        expiry_str = self.expiry_time.isoformat() if self.expiry_time else "N/A"
        return (f"<Quest(quest_id_str='{self.quest_id_str}', mongo_id='{self.mongo_id}', user_to='{self.user_to_id}', "
                f"category='{self.target_category}', status='{self.status}', expiry='{expiry_str}')>")
