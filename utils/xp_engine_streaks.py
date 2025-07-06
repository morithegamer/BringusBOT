# Expanding the XP system with additional database fields and daily streak logic

xp_streak_upgrade = '''
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path("bringus_xp.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_xp (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            xp INTEGER NOT NULL DEFAULT 0,
            last_active TEXT,
            daily_streak INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def update_user_activity(user_id: int, username: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT last_active, daily_streak FROM user_xp WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    today = datetime.utcnow().date()
    if row:
        last_active_str, streak = row
        last_active = datetime.strptime(last_active_str, "%Y-%m-%d").date() if last_active_str else None

        if last_active is None or (today - last_active).days > 1:
            streak = 1
        elif (today - last_active).days == 1:
            streak += 1
        # else: streak remains the same (same day)

        cursor.execute("""
            UPDATE user_xp SET last_active = ?, daily_streak = ?, username = ?
            WHERE user_id = ?
        """, (today.isoformat(), streak, username, user_id))
    else:
        streak = 1
        cursor.execute("""
            INSERT INTO user_xp (user_id, username, xp, last_active, daily_streak)
            VALUES (?, ?, 0, ?, ?)
        """, (user_id, username, today.isoformat(), streak))

    conn.commit()
    conn.close()
    return {"streak": streak, "date": today}

def get_user_xp(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT xp FROM user_xp WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def set_user_xp(user_id: int, xp: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_xp (user_id, xp) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET xp = excluded.xp
    """, (user_id, xp))
    conn.commit()
    conn.close()

def award_xp(user_id: int, username: str, amount: int = 10) -> dict:
    current = get_user_xp(user_id)
    new_xp = current + amount
    set_user_xp(user_id, new_xp)
    activity = update_user_activity(user_id, username)
    return {
        "xp": new_xp,
        "streak": activity["streak"],
        "date": activity["date"]
    }

def get_top_users(limit: int = 5):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, xp FROM user_xp ORDER BY xp DESC LIMIT ?", (limit,))
    results = cursor.fetchall()
    conn.close()
    return results

def export_all_xp():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_xp")
    results = cursor.fetchall()
    conn.close()
    return results
'''

with open("/mnt/data/xp_engine_streaks.py", "w") as f:
    f.write(xp_streak_upgrade.strip())
