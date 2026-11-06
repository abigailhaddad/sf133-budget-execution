import sys, time
from pathlib import Path
import openpyxl
RAW = Path.home()/ "Documents/repos/apportion/raw_data"
files = [
 RAW/"2025"/"FY2025_SF133_MONTHLY_Other_Independent_Agencies.xlsx",
 RAW/"2025"/"FY2025_SF133_MONTHLY_Department_of_Agriculture.xlsx",
 RAW/"2025"/"FY2025_SF133_MONTHLY_Social_Security_Administration.xlsx",
 RAW/"2022"/"FY2022_SF133_Other_Independent_Agencies.xlsx",
 RAW/"2019"/sorted(p.name for p in (RAW/"2019").glob("*.xlsx"))[0],
]
for f in files:
    if not f.exists():
        print("MISSING", f); continue
    t=time.time()
    wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
    print("\n==", f.parent.name, f.name, f"({f.stat().st_size/1e6:.1f} MB)")
    for ws in wb.worksheets:
        print(f"   {ws.title!r:32} rows={ws.max_row} cols={ws.max_column}")
    wb.close(); print("   t=%.1fs"%(time.time()-t))
