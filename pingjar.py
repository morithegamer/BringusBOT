
import sqlite3
import os

DB_FILE = "pingjar.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS jar (
            user_id TEXT PRIMARY KEY,
            balance INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def add_ping_fine(user_id, amount=1):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO jar (user_id, balance) VALUES (?, 0)", (str(user_id),))
    c.execute("UPDATE jar SET balance = balance + ? WHERE user_id = ?", (amount, str(user_id)))
    conn.commit()
    conn.close()

def get_user_balance(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT balance FROM jar WHERE user_id = ?", (str(user_id),))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def get_total_debt():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT SUM(balance) FROM jar")
    row = c.fetchone()
    conn.close()
    return row[0] if row[0] else 0
