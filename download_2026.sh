#!/bin/bash
# The FY2026 workbooks. Kept so earlier notes still work; it calls download_workbooks.sh.
exec bash "$(dirname "$0")/download_workbooks.sh" 2026 \
  "https://portal.max.gov/portal/document/SF133/Budget/attachments/2692285459" "${1:-scratch/raw2026}"
