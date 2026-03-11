# utils/helpers.py
import json

def safe_json_load(path: str) -> dict:
    """Safely loads JSON from a file, returns empty dict on error."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        print(f"[⚠️] Failed to load JSON from {path}, returning default.")
        return {}
def safe_json_dump(data: dict, path: str):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
    except IOError as e:
        print(f"[⚠️] Failed to write JSON to {path}: {e}")
def ensure_data_directory():
    import os
    if not os.path.exists("data"):
        os.makedirs("data")
        print("[✅] Created data directory.")
    else:
        print("[ℹ️] Data directory already exists.")