# sources/ui_crawls.py
import json
from typing import List, Tuple, Dict

def load_ui_crawl(file_path: str):
    with open(file_path, "r", encoding="utf-8") as f:
        crawl_data = json.load(f)
    docs = []
    for i, step in enumerate(crawl_data.get("steps", [])):
        content = f"UI Step {i}: {step}"
        metadata = {"source":"ui_crawl", "file": file_path, "step_index": i}
        docs.append((f"{file_path}_{i}", content, metadata))
    return docs
