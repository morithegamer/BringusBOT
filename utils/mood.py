import json
import os

MOOD_FILE = "data/user_moods.json"

def load_moods():
    if not os.path.exists(MOOD_FILE):
        return {}
    with open(MOOD_FILE, "r") as f:
        return json.load(f)

def save_moods(moods):
    with open(MOOD_FILE, "w") as f:
        json.dump(moods, f, indent=2)