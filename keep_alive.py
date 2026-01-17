from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.get("/")
def home():
    return "✅ Mast Prank 69 bot is running on Replit!"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
