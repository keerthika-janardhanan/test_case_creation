import tempfile
import os
from app.hashstore import HashStore

def test_add_and_check_new_content():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        path = tmp.name
    try:
        store = HashStore(path)
        content = {"key": "value"}

        assert store.is_new(content) is True
        store.add(content)
        assert store.is_new(content) is False  # already exists
    finally:
        os.remove(path)
