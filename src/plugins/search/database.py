import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Tuple, Set

DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DB_DIR, "map_queries.db")
os.makedirs(DB_DIR, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_queries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        qq_number INTEGER NOT NULL,
        query_time INTEGER NOT NULL,
        query_date TEXT NOT NULL,
        query_param TEXT NOT NULL
    )''')

    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_user_analysis 
    ON user_queries(qq_number, query_date)
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        qq_number INTEGER NOT NULL UNIQUE
    )''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS alert_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL UNIQUE
    )''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS system_config (
        key TEXT PRIMARY KEY NOT NULL,
        value TEXT NOT NULL
    )''')

    cursor.execute("INSERT OR IGNORE INTO system_config (key, value) VALUES ('hourly_limit', '4')")

    conn.commit()
    conn.close()

def insert_query_record(qq_number: int, query_param: str):
    now = datetime.now()
    query_time = int(now.timestamp())
    query_date = now.strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("BEGIN TRANSACTION")
        conn.execute(
            "INSERT INTO user_queries (qq_number, query_time, query_date, query_param) VALUES (?, ?, ?, ?)",
            (qq_number, query_time, query_date, query_param)
        )
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_query_count(query_param: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if query_param:
        cursor.execute("SELECT COUNT(*) FROM user_queries WHERE query_param = ?", (query_param,))
        r = cursor.fetchone()[0]
    else:
        cursor.execute("SELECT query_param, COUNT(*) FROM user_queries GROUP BY query_param ORDER BY 2 DESC")
        r = cursor.fetchall()
    conn.close()
    return r

def add_admin(qq_number: int) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO admins (qq_number) VALUES (?)", (qq_number,))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def remove_admin(qq_number: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("DELETE FROM admins WHERE qq_number = ?", (qq_number,))
    cnt = cur.rowcount > 0
    conn.commit()
    conn.close()
    return cnt

def is_admin(qq_number: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT 1 FROM admins WHERE qq_number = ? LIMIT 1", (qq_number,))
    r = cur.fetchone() is not None
    conn.close()
    return r

def add_alert_group(gid: int) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO alert_groups (group_id) VALUES (?)", (gid,))
        conn.commit()
        conn.close()
        return True
    except:
        return False

def remove_alert_group(gid: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("DELETE FROM alert_groups WHERE group_id = ?", (gid,))
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok

def get_all_alert_groups() -> set:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT group_id FROM alert_groups")
    s = {i[0] for i in cur.fetchall()}
    conn.close()
    return s

def set_hourly_limit(n: int) -> bool:
    if n < 1:
        return False
    conn = sqlite3.connect(DB_PATH)
    conn.execute("REPLACE INTO system_config (key,value) VALUES ('hourly_limit',?)", (str(n),))
    conn.commit()
    conn.close()
    return True

def get_hourly_limit() -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT value FROM system_config WHERE key='hourly_limit'")
    r = cur.fetchone()
    conn.close()
    return int(r[0]) if r else 4

def get_user_map_query_count(qq: int, name: str, hours=1):
    now = datetime.now().timestamp()
    start = now - hours * 3600
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "SELECT COUNT(*) FROM user_queries WHERE qq_number=? AND query_param=? AND query_time>=?",
        (qq, name, start)
    )
    r = cur.fetchone()[0]
    conn.close()
    return r

init_db()