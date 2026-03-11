import sqlite3
import os
import time
from typing import Optional

DB_PATH = "fluxy_data.db"
EXPIRATION_SECONDS = 14 * 24 * 60 * 60  # 2 weeks

# Toggle this to True if you want debug info
DEBUG = False

def init_db():
    """Initialize the database and create table if not exists."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_moods (
                user_id TEXT PRIMARY KEY,
                mood TEXT NOT NULL,
                timestamp INTEGER NOT NULL
            )
        """)
        conn.commit()
    if DEBUG:
        print("[DB] Initialized database.")

def save_user_mood(user_id: int, mood: str) -> None:
    """Store or update a user's mood with timestamp."""
    timestamp = int(time.time())
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "REPLACE INTO user_moods (user_id, mood, timestamp) VALUES (?, ?, ?)",
                (str(user_id), mood, timestamp)
            )
            conn.commit()
        if DEBUG:
            print(f"[DB] Saved mood '{mood}' for user {user_id}")
    except Exception as e:
        print(f"[DB] Error saving user mood: {e}")

def get_user_mood(user_id: int, fallback: str = "friendly") -> str:
    """Retrieve the last known mood for a user, or fallback if not found."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT mood FROM user_moods WHERE user_id = ?", (str(user_id),))
            result = cursor.fetchone()
        return result[0] if result else fallback
    except Exception as e:
        print(f"[DB] Error fetching user mood: {e}")
        return fallback

def purge_old_data() -> None:
    """Remove entries older than EXPIRATION_SECONDS."""
    cutoff = int(time.time()) - EXPIRATION_SECONDS
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_moods WHERE timestamp < ?", (cutoff,))
            deleted = cursor.rowcount
            conn.commit()
        if DEBUG:
            print(f"[DB] Purged {deleted} old records.")
    except Exception as e:
        print(f"[DB] Error purging old data: {e}")
