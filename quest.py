from bson.objectid import ObjectId

# EDWARD WANG PLEASE REPURPOUSE THIS FOR QUESTS
class User:
    def __init__(self, jamhacks_code, name, socials, karma=0, phone=None, friends=None, quests=None, photos=None, _id=None):
        self.jamhacks_code = jamhacks_code
        self.name = name
        self.socials = socials if socials else []
        self.karma = karma
        self.phone = phone
        self.friends = friends if friends else [] # store as list of objectid pointers
        self.quests = quests if quests else []
        self.photos = photos if photos else [] # list of pointers to google cloud
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
    def get_all_users(collection):
        users = collection.find()
        return [User.from_mongo(user) for user in users]

    def id(self):
        return self._id
