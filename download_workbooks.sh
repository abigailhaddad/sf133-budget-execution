#!/bin/bash
# Download one fiscal year's SF-133 agency workbooks from MAX.gov (public), one at a time, with a pause.
#
#   bash download_workbooks.sh FISCAL_YEAR ATTACHMENTS_BASE_URL [OUTPUT_DIR]
#
# ATTACHMENTS_BASE_URL is the folder that holds the year's workbooks. Find it on MAX.gov:
#   1. Open https://portal.max.gov/portal/document/SF133/Budget/ and pick the fiscal year's page.
#   2. Copy the link of any workbook on that page.
#   3. Drop the file name from the end. What is left is the base, for example
#      https://portal.max.gov/portal/document/SF133/Budget/attachments/2692285459  (FY2026).
# The file names below follow the FY2026 pattern, FY<year>_SF133_MONTHLY_<agency>.xlsx. Earlier years
# may name their files differently: if a download returns a 404 or a tiny file, open the year's page
# and compare the real names with this list. I have not tested this script on years before 2026.
#
# It asks for one file every few seconds and sends an honest User-Agent. It skips files already
# downloaded, and it stops at the first sign of a block (403, 429 or a challenge page).
set -u
FY="${1:?fiscal year, e.g. 2027}"
BASE="${2:?attachments base URL, see the comments above}"
OUT="${3:-${SF133_RAW:-raw_data}/$FY}"
PAUSE="${SF133_PAUSE:-3}"
UA="sf133-dataset (public data research; https://github.com/abigailhaddad/sf133-budget-execution)"
mkdir -p "$OUT"
for f in Legislative_Branch Judicial_Branch Department_of_Agriculture Department_of_Commerce \
  Department_of_Defense_Military Department_of_Education Department_of_Energy \
  Department_of_Health_and_Human_Services Department_of_Homeland_Security \
  Department_of_Housing_and_Urban_Development Department_of_the_Interior \
  Department_of_Justice Department_of_Labor Department_of_State \
  Department_of_Transportation Department_of_the_Treasury Department_of_Veterans_Affairs \
  Corps_of_Engineers_Civil_Works Other_Defense_Civil_Programs \
  Environmental_Protection_Agency Executive_Office_of_the_President \
  General_Services_Administration International_Assistance_Programs \
  National_Aeronautics_and_Space_Administration National_Science_Foundation \
  Office_of_Personnel_Management Small_Business_Administration \
  Social_Security_Administration Other_Independent_Agencies ; do
  name="FY${FY}_SF133_MONTHLY_${f}.xlsx"
  if [ -s "$OUT/$name" ]; then echo "skip $name"; continue; fi
  code=$(curl -s -A "$UA" -o "$OUT/$name" -w "%{http_code}" "$BASE/$name")
  echo "$code $(du -h "$OUT/$name" | cut -f1) $name"
  case "$code" in
    403|429) echo "STOPPED: the server answered $code. Do not retry from this address today."; rm -f "$OUT/$name"; exit 2 ;;
    200) ;;
    *) echo "WARNING: $name returned $code; check the name on the year's page"; rm -f "$OUT/$name" ;;
  esac
  sleep "$PAUSE"
done
echo "DONE: $OUT"
