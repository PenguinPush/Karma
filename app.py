import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
from pymongo import MongoClient
import re
from user import User
from web_scraper import get_jamhacks_data

load_dotenv()

app = Flask(__name__)

client = MongoClient(os.getenv("MONGO_CONNECTION_STRING"))
db = client["karma"]
users_collection = db["users"]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/url_to_user", methods=["POST"])
def url_to_user():
    # loads a user from a qr code, creates a new user if user doesn't exist in db
    try:
        data = request.json
        if not data or "url" not in data:
            return jsonify({"error": "url payload required"}), 400

        url = data["url"]
        match = re.search(r"https://app\.jamhacks\.ca/social/\s*(\d+)", url)
        if not match:
            return jsonify({"error": "invalid url format"}), 400

        print(match.group(1))
        jamhacks_code = match.group(1)
        fetched_user = User.get_user(users_collection, jamhacks_code)

        name, socials = get_jamhacks_data(jamhacks_code)
        user = User(
            jamhacks_code,
            name,
            socials,
            fetched_user.karma,
            fetched_user.friends,
            fetched_user.quests,
            fetched_user.id()
        )

        user.save_to_db(users_collection)

        return jsonify({
            "user_id": str(user.id())
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
