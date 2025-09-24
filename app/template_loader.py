import os
import json
import pandas as pd

def load_template(file_path: str):
    """Load a template from JSON, YAML, TXT, CSV, or Excel."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    elif ext in (".yaml", ".yml"):
        import yaml
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    elif ext in (".txt", ".md"):
        with open(file_path, "r", encoding="utf-8") as f:
            return {"format": f.read(), "fields": []}

    elif ext in (".csv", ".xlsx"):
        df = pd.read_excel(file_path) if ext == ".xlsx" else pd.read_csv(file_path)
        return {
            "fields": list(df.columns),
            "rows": df.to_dict(orient="records"),
            "format": None  # Excel/CSV may define rows instead of format string
        }

    else:
        raise ValueError(f"Unsupported template file type: {ext}")
