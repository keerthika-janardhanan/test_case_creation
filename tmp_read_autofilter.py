import pandas as pd

try:
    df = pd.read_excel("tmp_autofilter.xlsx")
    print(df)
except Exception as exc:
    import traceback
    traceback.print_exc()
