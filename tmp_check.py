import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent / "app"))

from template_utils import load_excel_template
print(load_excel_template)
