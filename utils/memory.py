import json, os

MEMORY_PATH = "data/user_memory.json"

def load_memory():
    if not os.path.exists(MEMORY_PATH):
        return {}
    with open(MEMORY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_memory(memory):
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)

def update_memory(user_id, note):
    memory = load_memory()
    user_mem = memory.get(str(user_id), [])
    user_mem.append(note)
    memory[str(user_id)] = user_mem[-10:]  # Keep last 10 entries
    save_memory(memory)

def get_memory(user_id):
    return load_memory().get(str(user_id), [])
def clear_memory(user_id):
    memory = load_memory()
    if str(user_id) in memory:
        del memory[str(user_id)]
        save_memory(memory)
        return True
    return False