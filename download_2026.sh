#!/bin/bash
# FY2026 SF-133 agency workbooks from MAX.gov (public), one at a time, with a pause.
set -u
BASE="https://portal.max.gov/portal/document/SF133/Budget/attachments/2692285459"
OUT="${1:-scratch/raw2026}"; mkdir -p "$OUT"
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
  name="FY2026_SF133_MONTHLY_${f}.xlsx"
  if [ -s "$OUT/$name" ]; then echo "skip $name"; continue; fi
  code=$(curl -s -A "sf133-dataset-staging (public data research)" -o "$OUT/$name" -w "%{http_code}" "$BASE/$name")
  echo "$code $(du -h "$OUT/$name" | cut -f1) $name"
  sleep 2
done
echo DOWNLOAD DONE
