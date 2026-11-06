import warnings
from pathlib import Path
import pandas as pd
import rawsummary
warnings.filterwarnings("ignore")
rows=[]
for f in sorted(Path("scratch/raw2026").glob("*.xlsx")):
    r=rawsummary.one(str(f)); r["year"]="2026"; rows.append(r); print(f.name, r.get("rows"), r.get("units"), r.get("nonzero_amt_cols"), flush=True)
pd.DataFrame(rows).to_csv("raw_data_sheet_summary_2026.csv", index=False)
