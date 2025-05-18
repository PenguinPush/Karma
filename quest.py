# quest.py
import uuid
import datetime
import random
from bson.objectid import ObjectId
from pymongo.collection import Collection
from pymongo import MongoClient  # Only needed for __main__ example
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
        if not data:  # This is the line the user selected. It's an important check.
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

    def save_to_db(self,
                   quests_collection: Collection,
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
            result = quests_collection.update_one(
                {"_id": self.mongo_id},
                {"$set": quest_data}
            )
            print(f"Quest {self.quest_id_str} (MongoDB ID: {self.mongo_id}) updated.")
        else:
            if "creation_time" not in quest_data and self.expiry_time:
                print(
                    f"Warning: Saving new quest {self.quest_id_str} with expiry_time but without explicit 'creation_time' in this save call. Ensure it's set if needed for expiry logic.")
            if "expiry_time" not in quest_data and self.expiry_time:  # Ensure expiry_time from object is included if set
                quest_data["expiry_time"] = self.expiry_time
            elif "expiry_time" not in quest_data and not self.expiry_time:
                print(f"Warning: Saving new quest {self.quest_id_str} without 'expiry_time'.")

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
        return result.deleted_count

    # --- Class Methods for Quest Data Generation ---
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

    # --- Instance Methods for Workflow ---
    def _mark_as_completed_internal(self, completion_image_uri: str) -> bool:
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
                                       all_possible_categories: List[str] = POSSIBLE_QUEST_CATEGORIES,
                                       nomination_duration_seconds: int = 24 * 60 * 60) -> Optional[Dict]:
        """
        Handles the completion of this quest.
        1. Marks this quest as completed (in memory).
        2. Saves the completed status to DB (including a completion_time field).
        3. Deletes this quest from the database.
        4. Returns data for a new quest to be nominated to a random friend,
           or for a new system quest for the current user if no eligible friends.

        Args:
            completion_image_uri: GCS URI of the image for completing this quest.
            user_friends_list: A list of user IDs for the friends of the user completing this quest.
            quests_collection: MongoDB collection for quests.
            all_possible_categories: List of categories for the new nominated/system quest.
            nomination_duration_seconds: Duration for the nominated/system quest.

        Returns:
            A dictionary with data for the next quest to be created, or None if completion failed.
        """
        print(
            f"Attempting to complete and get next quest data from quest: {self.quest_id_str} for user {self.user_to_id}")
        if self.is_expired():
            print(f"Quest {self.quest_id_str} is expired. Cannot complete. Caller should handle expiry.")
            # Optionally update status in DB here before deletion if needed by caller
            # self.status = "expired_by_system"
            # self.save_to_db(quests_collection, completion_time_db=datetime.datetime.now(datetime.timezone.utc))
            Quest.delete_quest(quests_collection, self.quest_id_str)
            return self.handle_expiry_and_regenerate_data(quests_collection, all_possible_categories,
                                                          nomination_duration_seconds)

        if not self._mark_as_completed_internal(completion_image_uri):
            print(f"Could not mark quest {self.quest_id_str} as completed (status: {self.status}).")
            return None

        completion_time_for_db = datetime.datetime.now(datetime.timezone.utc)
        # Points would be calculated and passed by external logic to save_to_db if needed
        self.save_to_db(quests_collection, completion_time_db=completion_time_for_db)
        print(f"Quest {self.quest_id_str} marked completed in DB.")

        Quest.delete_quest(quests_collection, self.quest_id_str)
        print(f"Completed quest {self.quest_id_str} deleted from DB.")

        # Generate data for the next quest
        next_quest_data: Optional[Dict] = None
        eligible_friends = [f_id for f_id in user_friends_list if f_id != self.user_to_id]

        if eligible_friends:
            random_friend_id = random.choice(eligible_friends)
            new_target_category = random.choice(all_possible_categories)
            next_quest_data = self._generate_nomination_data_internal(
                random_friend_id, new_target_category, nomination_duration_seconds
            )
            if next_quest_data:
                print(
                    f"Generated nomination data for friend {random_friend_id}, new quest ID (to be created): {next_quest_data['quest_id_str']}.")
        else:
            print(f"User {self.user_to_id} has no eligible friends. Generating new system quest data for them.")
            next_quest_data = Quest.generate_new_system_quest_data(
                self.user_to_id, random.choice(all_possible_categories), nomination_duration_seconds
            )
            if next_quest_data:
                print(
                    f"Generated new system quest data for user {self.user_to_id}, new quest ID (to be created): {next_quest_data['quest_id_str']}.")

        return next_quest_data

    def handle_expiry_and_regenerate_data(self,
                                          quests_collection: Collection,
                                          all_possible_categories: List[str] = POSSIBLE_QUEST_CATEGORIES,
                                          new_quest_duration_seconds: int = 24 * 60 * 60) -> Optional[Dict]:
        """
        Handles the expiry of this quest:
        1. Checks if quest is pending and actually expired.
        2. If so, updates its status to "expired_by_system" in memory.
        3. Deletes this quest from the database.
        4. Returns data for a new system quest for the same user.

        Args:
            quests_collection: MongoDB collection for quests.
            all_possible_categories: List of categories for the new system quest.
            new_quest_duration_seconds: Duration for the new system quest.

        Returns:
            A dictionary with data for the new system-generated quest if successful, otherwise None.
        """
        print(f"Handling expiry for quest: {self.quest_id_str} for user {self.user_to_id}")
        if self.status != "pending":
            print(f"Quest {self.quest_id_str} is not pending (status: {self.status}). No expiry action taken.")
            return None

        if not self.is_expired():
            print(f"Quest {self.quest_id_str} is not yet expired. No expiry action taken.")
            return None

            # self.status = "expired_by_system" # Status change is implicit by deletion and regeneration
        # No need to save the "expired_by_system" status if we are deleting it immediately.

        Quest.delete_quest(quests_collection, self.quest_id_str)
        print(f"Expired quest {self.quest_id_str} deleted from DB.")

        new_quest_data = Quest.generate_new_system_quest_data(
            self.user_to_id,
            random.choice(all_possible_categories),
            new_quest_duration_seconds
        )
        print(
            f"Generated new system quest data for user {self.user_to_id} due to expiry of {self.quest_id_str}, new quest ID (to be created): {new_quest_data['quest_id_str']}.")
        return new_quest_data

    def __repr__(self) -> str:
        expiry_str = self.expiry_time.isoformat() if self.expiry_time else "N/A"
        return (f"<Quest(quest_id_str='{self.quest_id_str}', mongo_id='{self.mongo_id}', user_to='{self.user_to_id}', "
                f"category='{self.target_category}', status='{self.status}', expiry='{expiry_str}')>")


# --- Example Usage with Mock MongoDB ---
if __name__ == "__main__":

    class MockMongoCollection:
        def __init__(self, name="quests"):
            self.name = name
            self._data: List[Dict] = []
            self._next_id_counter = 0

        def insert_one(self, document: Dict):
            if "_id" not in document:
                document["_id"] = ObjectId()
            self._data.append(dict(document))

            class InsertResult:
                def __init__(self, inserted_id): self.inserted_id = inserted_id

            return InsertResult(document["_id"])

        def update_one(self, filter_query: Dict, update_doc: Dict):
            mc, mc_mod = 0, 0
            for i, doc in enumerate(self._data):
                if filter_query.get("_id") and doc.get("_id") and filter_query["_id"] == doc["_id"]:
                    mc += 1
                    if "$set" in update_doc:
                        for k, v in update_doc["$set"].items():
                            if doc.get(k) != v: doc[k] = v; mc_mod += 1
                    break
            return type('UpdateResult', (), {'matched_count': mc, 'modified_count': mc_mod})()

        def find_one(self, query: Dict) -> Optional[Dict]:
            for doc in self._data:
                if all(doc.get(k) == v for k, v in query.items()): return dict(doc)
            return None

        def find(self, query: Optional[Dict] = None) -> List[Dict]:
            res = []
            if query is None: query = {}
            for doc in self._data:
                if all(doc.get(k) == v for k, v in query.items()): res.append(dict(doc))
            return res

        def delete_one(self, query: Dict) -> object:
            idx_to_del = -1
            for i, doc in enumerate(self._data):
                if all(doc.get(k) == v for k, v in query.items()): idx_to_del = i; break
            dc = 0
            if idx_to_del != -1: self._data.pop(idx_to_del); dc = 1
            return type('DeleteResult', (), {'deleted_count': dc})()


    print("\n--- Testing Quest Class with Workflow Methods Returning Data (Mock DB) ---")
    mock_quests_collection = MockMongoCollection(name="quests")
    mock_users_collection = MockMongoCollection(name="users")

    user_A_id = str(ObjectId())
    user_B_id = str(ObjectId())
    user_C_id = str(ObjectId())
    mock_users_collection.insert_one(
        {"_id": ObjectId(user_A_id), "name": "UserA", "friends": [ObjectId(user_B_id), ObjectId(user_C_id)],
         "quests": []})
    mock_users_collection.insert_one(
        {"_id": ObjectId(user_B_id), "name": "UserB", "friends": [ObjectId(user_A_id)], "quests": []})
    mock_users_collection.insert_one({"_id": ObjectId(user_C_id), "name": "UserC", "friends": [], "quests": []})


    # --- Application Logic Example ---
    def create_and_save_quest_from_data(quest_data: Dict, collection: Collection, user_collection: Collection):
        if not quest_data: return None
        # The data from generate methods already includes creation_time and expiry_time
        # Quest.from_mongo will handle these if they are in the dict.
        # The Quest __init__ now takes expiry_time directly.
        new_quest = Quest(
            user_to_id=quest_data["user_to_id"],
            target_category=quest_data["target_category"],
            expiry_time=quest_data.get("expiry_time"),  # Should be present
            user_from_id=quest_data.get("user_from_id"),
            nominated_by_image_uri=quest_data.get("nominated_by_image_uri"),
            quest_id_str=quest_data.get("quest_id_str"),
            status=quest_data.get("status", "pending")
        )
        # Pass creation_time to save_to_db if it's managed externally for the DB document
        new_quest.save_to_db(collection, creation_time=quest_data.get("creation_time"))

        # Update user's quest list
        user_obj = Quest.from_mongo(
            user_collection.find_one({"_id": ObjectId(new_quest.user_to_id)}))  # Simplified User fetch for mock
        if user_obj:  # This is a mock User object, not the full User class from user.py
            if not hasattr(user_obj, 'quests_list_attr'): user_obj.quests_list_attr = []  # Mock attribute
            user_obj.quests_list_attr.append(new_quest.quest_id_str)
            # In real app: user.quests.append(new_quest.quest_id_str); user.save_to_db()
            print(f"Quest {new_quest.quest_id_str} notionally added to user {new_quest.user_to_id}'s list.")
        return new_quest


    # 1. Generate an initial quest for userA
    initial_quest_data = Quest.generate_new_system_quest_data(user_A_id, POSSIBLE_QUEST_CATEGORIES[0],
                                                              duration_seconds=60 * 5)
    quest_A = create_and_save_quest_from_data(initial_quest_data, mock_quests_collection, mock_users_collection)
    print(f"Initial quest for UserA: {quest_A.quest_id_str if quest_A else 'Failed'}")

    # 2. Simulate UserA completing the quest
    if quest_A:
        user_A_doc = mock_users_collection.find_one({"_id": ObjectId(user_A_id)})
        user_A_friends_ids = [str(f_id) for f_id in user_A_doc.get("friends", [])] if user_A_doc else []

        next_quest_data_after_A = quest_A.handle_completion_and_nominate(
            completion_image_uri="gs://images/userA_completed.jpg",
            user_friends_list=user_A_friends_ids,
            quests_collection=mock_quests_collection,
            users_collection=mock_users_collection
        )
        if next_quest_data_after_A:
            print(f"Data for next quest received: {next_quest_data_after_A['quest_id_str']}")
            create_and_save_quest_from_data(next_quest_data_after_A, mock_quests_collection, mock_users_collection)
        else:
            print(f"Quest A completion or nomination data generation failed. Status: {quest_A.status}")

    # 3. Simulate a quest expiring for UserC
    initial_quest_data_C = Quest.generate_new_system_quest_data(user_C_id, POSSIBLE_QUEST_CATEGORIES[1],
                                                                duration_seconds=1)  # Expires quickly
    quest_C = create_and_save_quest_from_data(initial_quest_data_C, mock_quests_collection, mock_users_collection)
    print(f"\nGenerated short-lived quest for UserC: {quest_C.quest_id_str if quest_C else 'Failed'}")

    if quest_C:
        print("Waiting for 2 seconds for Quest C to expire...")
        import time

        time.sleep(2)

        # Fetch it again to ensure we have the latest status if it was modified elsewhere (not in this simple test)
        quest_C_reloaded = Quest.get_quest_by_quest_id_str(mock_quests_collection, quest_C.quest_id_str)
        if quest_C_reloaded:
            next_quest_data_for_C = quest_C_reloaded.handle_expiry_and_regenerate_data(mock_quests_collection)
            if next_quest_data_for_C:
                print(f"Data for new system quest for UserC received: {next_quest_data_for_C['quest_id_str']}")
                create_and_save_quest_from_data(next_quest_data_for_C, mock_quests_collection, mock_users_collection)
            else:
                print(f"Quest C expiry handling failed or quest was not actually expired/pending.")
        else:
            print(f"Quest C {quest_C.quest_id_str} not found after expiry simulation (was already deleted).")

    print("\n--- Quest Workflow Methods Returning Data Testing Complete ---")

