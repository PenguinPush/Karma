import os
from dotenv import load_dotenv
from flask import Flask, render_template

load_dotenv()

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
