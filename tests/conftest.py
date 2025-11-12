import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_SRC = ROOT / "app"

for path in [str(ROOT), str(APP_SRC)]:
    if path not in sys.path:
        sys.path.insert(0, path)

