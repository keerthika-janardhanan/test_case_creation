import sqlite3
import os
import hashlib
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "hashstore.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS hashes (
        key TEXT PRIMARY KEY,
        hash TEXT,
        meta TEXT
    )
    """)
    conn.commit()
    conn.close()

def get_hash(key: str) -> Optional[str]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT hash FROM hashes WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def set_hash(key: str, hash_val: str, meta: str = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    INSERT INTO hashes (key, hash, meta) VALUES (?, ?, ?)
    ON CONFLICT(key) DO UPDATE SET hash=excluded.hash, meta=excluded.meta
    """, (key, hash_val, meta))
    conn.commit()
    conn.close()

# -------------------------------
# ✅ Missing helper functions
# -------------------------------
def compute_hash(content: str) -> str:
    """Return a stable hash for given content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def is_changed(key: str, content: str, meta: str = None) -> bool:
    """
    Check if content for a given key has changed compared to stored hash.
    Updates the DB if changed.
    """
    new_hash = compute_hash(content)
    old_hash = get_hash(key)

    if old_hash != new_hash:
        set_hash(key, new_hash, meta)
        return True
    return False
