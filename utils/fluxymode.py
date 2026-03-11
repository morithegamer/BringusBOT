import json
import os
from utils.helpers import safe_json_load

DATA_PATH = "data/fluxymode.json"

def ensure_file():
    if not os.path.exists("data"):
        os.makedirs("data")
    if not os.path.isfile(DATA_PATH):
        with open(DATA_PATH, "w") as f:
            json.dump({"enabled": False}, f)

def is_fluxy_mode_enabled() -> bool:
    ensure_file()
    data = safe_json_load(DATA_PATH)
    return data.get("enabled", False)

def get_fluxy_state() -> bool:
    return is_fluxy_mode_enabled()

def set_fluxy_mode(state: bool):
    ensure_file()
    with open(DATA_PATH, "w") as f:
        json.dump({"enabled": state}, f)
    print(f"[FluxyMode] Fluxy mode set to: {state}")

def toggle_fluxy_mode() -> bool:
    ensure_file()
    data = safe_json_load(DATA_PATH)
    new_state = not data.get("enabled", False)
    set_fluxy_mode(new_state)
    return new_state
def reset_fluxy_mode():
    ensure_file()
    set_fluxy_mode(False)
    print("[FluxyMode] Fluxy mode has been reset to default (disabled).")

def fluxy_mode_status() -> str:
    state = get_fluxy_state()
    return "Fluxy mode is currently enabled." if state else "Fluxy mode is currently disabled."