from pathlib import Path
import sqlite3

# File: utils/xp_engine.py
# Contains reusable logic for BringusXP cog enhancements
xp_engine_code = '''
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import math

DB_PATH = Path("bringus_xp.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_xp (
            user_id INTEGER PRIMARY KEY,
            xp INTEGER NOT NULL DEFAULT 0,
            last_claim TEXT,
            milestones TEXT
        )
    """)
    conn.commit()
    conn.close()

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

def award_xp(user_id: int, amount: int = 10) -> int:
    current = get_user_xp(user_id)
    new_xp = current + amount
    set_user_xp(user_id, new_xp)
    return new_xp

def calculate_level(xp: int) -> int:
    return int((xp / 100) ** 0.5 * 2)

def get_badge(level: int) -> str:
    if level >= 10:
        return "🌟 Master"
    elif level >= 5:
        return "🔥 Intermediate"
    elif level >= 2:
        return "✨ Beginner"
    return "🎈 Newbie"
'''
with open("/mnt/data/xp_engine.py", "w") as f:
    f.write(xp_engine_code.strip())
