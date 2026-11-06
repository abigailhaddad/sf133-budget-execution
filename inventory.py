import warnings, zipfile, csv, sys
from pathlib import Path
import openpyxl
warnings.filterwarnings("ignore")
RAW = Path.home()/"Documents/repos/apportion/raw_data"
out = csv.writer(open("inventory_workbooks.csv","w",newline=""))
out.writerow(["year","file","ext","mb","is_zip","sheets","has_raw_data"])
for ydir in sorted(p for p in RAW.iterdir() if p.is_dir() and p.name.isdigit()):
    for f in sorted(ydir.iterdir()):
        if f.suffix.lower() not in (".xlsx",".xls"): continue
        isz = zipfile.is_zipfile(f); sheets=""
        if isz:
            try:
                wb = openpyxl.load_workbook(f, read_only=True); sheets="|".join(wb.sheetnames); wb.close()
            except Exception as e: sheets="ERR "+str(e)[:40]
        out.writerow([ydir.name,f.name,f.suffix,round(f.stat().st_size/1e6,1),isz,sheets,"Raw Data" in sheets])
