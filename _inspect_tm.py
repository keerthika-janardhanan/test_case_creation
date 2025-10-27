import pandas as pd
from pathlib import Path
path = next(Path("framework_repos").rglob("testmanager.xlsx"))
print(path)
df = pd.read_excel(path)
print(df[["TestCaseDescription","Execute"]].to_string())
