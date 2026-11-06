---
license: other
license_name: us-government-works-public-domain
pretty_name: SF-133 budget execution, every federal account, FY2018 to FY2026
language:
- en
tags:
- government
- budget
- omb
- sf-133
- appropriations
- federal-spending
configs:
- config_name: lines
  default: true
  data_files: data/sf133_lines.parquet
- config_name: accounts
  data_files: data/sf133_accounts.parquet
- config_name: workbooks
  data_files: data/sf133_workbooks.parquet
---

# SF-133 budget execution, FY2018 to FY2026

The SF-133, Report on Budget Execution and Budgetary Resources, for every federal account,
month by month. OMB publishes it as 29 Excel workbooks per fiscal year on MAX.gov. This dataset
reads the workbooks' `Raw Data` sheets into one table per fiscal year, FY2018 through FY2026.

Source: [OMB MAX.gov, SF 133 Reports on Budget Execution and Budgetary Resources](https://portal.max.gov/portal/document/SF133/Budget/)
Unofficial copy. U.S. government works are in the public domain.

## As of

Each fiscal year is the last version of its workbooks that I had. `source_updated` in the
lines table gives the date OMB stamped on the data.

| Fiscal year | OMB data updated | Lines rows |
|---|---|---|
| 2018 | 2018-11-14 | 271,500 |
| 2019 | 2019-10-18 | 274,335 |
| 2020 | 2020-10-18 | 340,121 |
| 2021 | 2021-10-19 | 342,770 |
| 2022 | 2022-11-07 | 353,714 |
| 2023 | 2023-11-14 | 359,438 |
| 2024 | 2024-11-08 to 2024-11-12 | 368,419 |
| 2025 | 2025-12-03 | 374,711 |
| 2026 | 2026-10-21 to 2026-10-22 | 375,946 |

Every year runs through September. FY2026 was downloaded on 2026-11-05.

## Tables

`data/sf133_lines.parquet`, 3,060,954 rows. One row for each row of a workbook's Raw Data sheet:
an account's TAFS (Treasury Appropriation Fund Symbol) by SF-133 line number. Add up the rows
that share a TAFS and a line number to get the value on the report (see Things to know).

| Column | Meaning |
|---|---|
| `fiscal_year` | Fiscal year of the report |
| `agency`, `bureau` | As OMB labels the row |
| `omb_account` | OMB account code and title |
| `tafs` | TAFS code and title, for example `51-4596 /X - Deposit Insurance Fund` |
| `agency_code`, `account_code`, `allocation_code` | Treasury codes, stored as text so leading zeros stay |
| `begin_year`, `end_year` | Period of availability. `end_year` is `X` for no-year funds |
| `availability` | `U` unexpired, `E` expired |
| `financing` | `NON-FINANCING ACCOUNTS` or `FINANCING ACCOUNTS` |
| `line_no`, `line_desc` | SF-133 line number and its description |
| `section`, `section_no`, `line_type` | Report section. `line_type` is `D` for a detail line and `S` for a subtotal |
| `cat_b`, `program_category` | Category B activity or program category, on lines that have one |
| `oct` ... `sep` | Amount in dollars, fiscal-year-to-date through that month |
| `source_units` | Units in the source workbook (`dollars` for every workbook here) |
| `source_file`, `source_row`, `source_updated` | The workbook, the Excel row in its Raw Data sheet, and OMB's update date |

`data/sf133_accounts.parquet`, 77,771 rows. One row per fiscal year, TAFS, allocation and
financing type, with the headline lines at September (the last month of every year here):
`unobligated_balance_brought_forward` (line 1000), `budget_authority_total` (1900),
`total_budgetary_resources` (2500), `new_obligations_and_upward_adjustments` (2190),
`unobligated_balance_end_of_period` (2490), `outlays_gross_change_in_obligated_balance` (3020),
`outlays_net` (4190). `is_gift_account` is true when the TAFS title contains gift, donation or
bequest (see Gift accounts).

`data/sf133_workbooks.parquet`, 261 rows. One row per source workbook: rows, units and the months
that have data.

## Things to know

**Amounts are fiscal-year-to-date.** February means October through February. A change between
months is that month's activity on a flow line. On a balance line it means the balance was revised.

**Months OMB did not report are null, not zero.** No workbook reports October. The October column
is empty in every year. FY2019 has no January or February in any workbook. In FY2026, the General
Services Administration workbook has no January or February; its March figure includes them.

**Line 2500 is total budgetary resources, not budget authority.** Budget authority total is line 1900.

**Rows repeat a key on purpose.** On Category B lines (2002 and 2102, for example), several
reporters file detail for the same account, so a TAFS and line number can appear on many rows.
They add up to the SF-133 line. Across workbooks in the same year, no key repeats.

**The Other Independent Agencies workbook holds about a hundred agencies.** The `agency` column is
the label OMB put on each row. It is not the name of the workbook.

**What is left out.** The DEFC workbooks (a separate cut by Disaster Emergency Funding Code that
repeats accounts already in the agency workbooks) are not included. Most workbooks for FY2018 through
FY2022 (141 of them) exist twice in the files I had, as identical downloads; one copy of each is used.
FY2016 and FY2017 are not included. The names and email addresses of the people who filed each
Category B row are in the source and are not in this dataset.

## Gift accounts

`is_gift_account` is a text match on the TAFS title: gift, gifts, donation, donations, bequest or
bequests. It matches 65 accounts. It is not a judgment about what an account is. It includes the
Library of Congress gift shop account (03-4346) and an account that pays interest on a bequest
(03-8022). It will miss a gift account whose title uses other words. An account's balance says
nothing about who gave the money.

## How it was checked

- Every row of every one of the 261 workbooks is in the table (3,060,954 of 3,060,954 rows).
- A random sample of 104 rows, plus edge cases (negative values, no-year and multi-year accounts,
  Category B lines, financing accounts, gift accounts, the largest September values), was read back
  from the source cells with a different reader. All 2,080 fields matched.
- The workbooks carry their own summary sheets ("Agency Total" and others), which are pivot tables
  over the Raw Data sheet. For all 29 workbooks in each of FY2018, FY2022, FY2025 and FY2026
  (116 workbooks), every pivot cell equals the sum of the Raw Data rows: 415,798 cells, 0
  differences. The FY2018 pivots leave out some months that the Raw Data sheet has. The Raw Data
  sheet is the complete one.

Not checked: the figures against OMB's published PDFs, and the sign of each amount beyond the
sample. What the amounts mean is up to OMB's definitions of each line.

## Code

The build, the checks and the notes on the labeling errors found in an earlier version of this data
are in the repository: https://github.com/abigailhaddad/sf133-budget-execution (to be created).
