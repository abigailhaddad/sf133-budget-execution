# What went wrong in the earlier version

An earlier build of the same workbooks, in the `apportion` repo (abigailhaddad/apportionment), had four
errors. This build was made to avoid them. They are the first thing to look for if a number looks off.

1. Every row in a workbook got the first agency name in it, so 14% to 27% of rows per year carried the wrong
   agency. This build labels each row from its own agency, bureau and account columns.
2. It read every workbook in the folder, including 141 exact duplicate downloads and the DEFC workbooks, so each
   account appeared about four times in FY2018 to FY2022. `select_workbooks.py` keeps one per agency per year.
3. Allocation accounts were added into their parent accounts. TAFS and allocation code are keys here.
4. A column called budget authority was really line 2500. Here line 1900 and line 2500 have separate names.

The fix and the numbers are in https://github.com/abigailhaddad/apportionment/pull/2.
