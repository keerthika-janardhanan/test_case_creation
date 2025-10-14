import sqlite3
import os
import hashlib
import json
from typing import Optional, Any, Dict

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


# -------------------------------
# JSON file-based HashStore (for tests)
# -------------------------------
class HashStore:
    """
    Lightweight JSON file-based hash store used by tests.

    - add(payload): store the hash of payload
    - is_new(payload): return True if hash not seen
    The file stores a dict { "hashes": [sha256, ...] } for simplicity.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        # ensure directory exists
        folder = os.path.dirname(os.path.abspath(file_path))
        if folder and not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.file_path):
            return {"hashes": []}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "hashes" in data and isinstance(data["hashes"], list):
                    return data
                return {"hashes": []}
        except Exception:
            return {"hashes": []}

    def _save(self, data: Dict[str, Any]) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _hash_payload(self, payload: Any) -> str:
        try:
            text = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        except Exception:
            text = str(payload)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def is_new(self, payload: Any) -> bool:
        data = self._load()
        digest = self._hash_payload(payload)
        return digest not in data.get("hashes", [])

    def add(self, payload: Any) -> None:
        data = self._load()
        digest = self._hash_payload(payload)
        if digest not in data.get("hashes", []):
            data.setdefault("hashes", []).append(digest)
            self._save(data)

