import pandas as pd
from pathlib import Path
path = next(Path("framework_repos").rglob("testmanager.xlsx"))
df = pd.read_excel(path)
print(df.columns.tolist())
print(df.head().to_string())
