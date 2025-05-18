import datetime
from google.cloud import storage


class Photo:
    def __init__(self, user_id, quest_id, url=None, _id=None):
        self._id = _id
        self.user_id = user_id
        self.quest_id = quest_id
        self.url = url

    def save_to_db(self, photos_collection):
        record = {
            "user_id": self.user_id,
            "quest_id": self.quest_id,
            "url": self.url
        }
        if self._id:
            photos_collection.update_one({"_id": self._id}, {"$set": record})
        else:
            insert_result = photos_collection.insert_one(record)
            self._id = insert_result.inserted_id

    @classmethod
    def get_photo_by_id(cls, photos_collection, photo_id):
        doc = photos_collection.find_one({"_id": photo_id})
        if doc:
            return cls(
                user_id=doc.get("user_id"),
                quest_id=doc.get("quest_id"),
                url=doc.get("url"),
                _id=doc["_id"]
            )
        return None

    @classmethod
    def generate_signed_url(cls, bucket_name, blob_name):
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=15),
            method="GET"
        )
        return url

    def id(self):
        return self._id
