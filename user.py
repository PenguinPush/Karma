from bson.objectid import ObjectId
import datetime
import random
import uuid
from typing import Optional, List
from bson.objectid import ObjectId
from pymongo.collection import Collection
from quest import Quest

POSSIBLE_QUEST_CATEGORIES = [
    "Environmental Care",
    "Self-Care Activity",
    "Helping Others (General)",
    "Community Involvement",
    "Creativity and Learning"
]
class User:
    def __init__(self, jamhacks_code, name, socials, karma=0, phone=None, friends=None, quests=None, photos=None, _id=None):
        self.jamhacks_code = jamhacks_code
        self.name = name
        self.socials = socials if socials else []
        self.karma = karma
        self.phone = phone
        self.friends = friends if friends else []  # store as list of objectid pointers
        self.quests = quests if quests else []
        self.photos = photos if photos else []  # list of pointers to google cloud
        self._id = _id

    def to_mongo(self):
        return {
            "jamhacks_code": self.jamhacks_code,
            "name": self.name,
            "socials": self.socials,
            "karma": self.karma,
            "phone": self.phone,
            "friends": self.friends,
            "quests": self.quests,
            "photos": self.photos,
        }

    @staticmethod
    def from_mongo(data):
        return User(
            jamhacks_code=data["jamhacks_code"],
            name=data["name"],
            socials=data["socials"],
            karma=data["karma"],
            phone=data["phone"],
            friends=data.get("friends", []),
            quests=data.get("quests", []),
            photos=data.get("photos", []),
            _id=data.get("_id"),
        )

    def save_to_db(self, collection):
        if self._id:
            collection.update_one(
                {"_id": ObjectId(self._id)},
                {"$set": self.to_mongo()}
            )
        else:
            result = collection.insert_one(self.to_mongo())
            self._id = result.inserted_id

    @staticmethod
    def get_user(collection, jamhacks_code):
        data = collection.find_one({"jamhacks_code": jamhacks_code})
        if data:
            return User.from_mongo(data)
        return None

    @staticmethod
    def get_user_by_id(collection, mongo_id):
        data = collection.find_one({"_id": ObjectId(mongo_id)})
        if data:
            return User.from_mongo(data)
        return None

    @staticmethod
    def get_all_users(collection):
        users = collection.find()
        return [User.from_mongo(user) for user in users]

    def id(self):
        return self._id

    def add_nominated_quest(self,
                            user_from_id: str,
                            nominated_by_image_uri: str,
                            quests_collection: Collection,  # MongoDB collection for quests
                            all_possible_categories: List[str] = POSSIBLE_QUEST_CATEGORIES,
                            min_duration_hours: int = 1,
                            max_duration_hours: int = 1) -> Optional[str]:
        """
        Generates and assigns a new nominated quest to this user.
        The new Quest object is saved to the quests_collection.
        The quest_id_str is added to this user's quests list.
        The User object itself is NOT saved by this method; call user.save_to_db() afterwards.

        Args:
            user_from_id: The string ID of the user who nominated this quest.
            nominated_by_image_uri: The GCS URI of the image from the nominator's completed deed.
            quests_collection: The MongoDB collection where quests are stored.
            all_possible_categories: A list of categories to choose from randomly.
            min_duration_hours: Minimum duration for the quest's expiry.
            max_duration_hours: Maximum duration for the quest's expiry.

        Returns:
            The quest_id_str of the newly created and assigned quest, or None if creation failed.
        """
        if not self._id:
            # print("Error: User must be saved to DB (have an _id) before receiving a quest.") # Removed print
            return None
        # The 'Quest' class check and try-except for its import is at the module level.
        # If 'Quest' is None due to import failure, instantiating it will raise an error.

        try:
            target_category = random.choice(all_possible_categories)

            now_utc = datetime.datetime.now(datetime.timezone.utc)
            random_duration_hours = random.randint(min_duration_hours, max_duration_hours)
            expiry_time = now_utc + datetime.timedelta(hours=random_duration_hours)

            # Assumes the imported Quest class (real or dummy) has a compatible constructor
            # and a save_to_db method. The dummy Quest in this file matches this.
            new_quest = Quest(
                user_to_id=str(self._id),  # The user this quest is for
                target_category=target_category,
                expiry_time=expiry_time,
                user_from_id=user_from_id,
                nominated_by_image_uri=nominated_by_image_uri,
                status="pending"
                # quest_id_str is generated by Quest.__init__ if not provided
            )

            # The dummy Quest's save_to_db takes 'creation_time'.
            # If your actual Quest class's save_to_db is different (e.g., takes no extra args
            # because creation_time is an attribute), this call would need adjustment
            # or the Quest class would need to handle it.
            # For consistency with the dummy Quest provided, we pass creation_time.
            new_quest.save_to_db(quests_collection, creation_time=now_utc)

            if new_quest.quest_id_str not in self.quests:
                self.quests.append(new_quest.quest_id_str)
                # print(f"Quest {new_quest.quest_id_str} added to user {self.name}'s local quest list.") # Removed print

            return new_quest.quest_id_str

        except Exception as e:
            # print(f"Error creating or assigning nominated quest: {e}") # Removed print
            # import traceback # Not strictly necessary if not printing stack
            # traceback.print_exc() # Not strictly necessary if not printing stack
            return None