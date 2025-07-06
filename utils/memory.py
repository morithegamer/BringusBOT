import json
import os

MEMORY_FILE = "data/memory.json"

# Ensure folder exists
os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {}
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_memory(memories: dict):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memories, f, indent=2)
