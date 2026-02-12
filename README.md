# MSR Transfer Detection & Analysis

Loan-level mortgage servicing rights (MSR) transfer detection across three agency datasets: FNMA (Fannie Mae), FHLMC (Freddie Mac), and GNMA (Ginnie Mae).

## What's here

- **Servicer change detection** — sliding-window comparison of monthly loan-level files to identify when a loan's servicer changes between consecutive months (FNMA/FHLMC) or via an explicit transfer flag (GNMA).
- **Aggregated transfer CSVs** — one row per (seller, buyer, transition_month) with loan counts, UPB, and portfolio fractions.

## Folder structure

```
msr_transfers/
├── README.md
├── scripts/                  # Analysis scripts (run from project root)
│   ├── investigation_mlld_servicer_changes_2026-02-11.py     # FNMA full history (81 months)
│   ├── investigation_fhlmc_servicer_changes_2026-02-11.py    # FHLMC full history (81 months)
│   └── investigation_gnma_servicer_changes_2026-02-11.py     # GNMA full history (129 months)
├── reports/                  # Output reports and CSVs
│   ├── investigation_servicer_changes_combined_2026-02-11.md  # Combined writeup
│   ├── investigation_mlld_servicer_changes_2026-02-11.csv     # 3,256 rows
│   ├── investigation_fhlmc_servicer_changes_2026-02-11.csv    # 3,806 rows
│   └── investigation_gnma_servicer_changes_2026-02-11.csv     # 6,430 rows
└── data/                     # Agency loan-level data (parquet)
```

## Data sources

All three datasets are publicly available from the respective agencies:

- **FNMA (Fannie Mae)** — Multi-Lender Loan-Level Disclosure (MLLD) files, available monthly since the June 2019 launch of the Uniform MBS (UMBS) program. Each file contains ~15M loans with 116 fields. We use only `Loan Identifier`, `Servicer Name`, and `Current Investor Loan UPB`.
- **FHLMC (Freddie Mac)** — Fixed-Rate and Adjustable-Rate loan-level disclosure files (the "FU" dataset), also available monthly from June 2019 onward under the UMBS framework. ~10M loans per month. Same three fields used.
- **GNMA (Ginnie Mae)** — Loan-level monthly disclosures (`llmon1` and `llmon2`, record type L), available from April 2015 onward. ~12M loans per month. Unlike FNMA/FHLMC, GNMA data includes an explicit `Seller Issuer ID` field that is populated only when an MSR transfer occurs, so no month-over-month differencing is needed. Issuer names are resolved from GNMA's `issrcutoff` and `nissues` lookup tables.

The input parquet files were imported from agency flat files with appropriate record-type filters (GNMA) and column typing, but the fields used in this analysis (`Servicer Name`, `Loan Identifier`, `UPB`, `Seller Issuer ID`, `Issuer ID`) are unchanged from the source data.

## CSV schema

Each output CSV contains one row per (servicer_from, servicer_to, transition_month) triple. The FNMA and FHLMC files share a common schema; the GNMA file adds two issuer ID columns because GNMA identifies servicers by numeric issuer ID (the names are resolved via lookup and may contain minor formatting artifacts like double spaces).

### Common columns (all three CSVs)

| Column | Description |
|--------|-------------|
| `servicer_from` | Previous servicer name (the seller) |
| `servicer_to` | New servicer name (the buyer) |
| `transition_month` | `YYYYMM` when the change is observed |
| `n_loans` | Number of loans that changed servicer |
| `total_upb` | Sum of current UPB (dollars) for those loans, measured in the destination month |
| `frac_seller_n` | `n_loans` / seller's total loan count |
| `frac_seller_upb` | `total_upb` / seller's total UPB |
| `frac_buyer_n` | `n_loans` / buyer's total loan count |
| `frac_buyer_upb` | `total_upb` / buyer's total UPB |

### GNMA-only columns

| Column | Description |
|--------|-------------|
| `seller_issuer_id` | GNMA numeric issuer ID of the seller |
| `issuer_id` | GNMA numeric issuer ID of the buyer (current servicer) |

FNMA and FHLMC do not have servicer ID numbers — servicers are identified solely by name, which means corporate rebrands (e.g., Quicken Loans → Rocket Mortgage) appear as transfers in those datasets.

### How the fraction columns are computed

For **FNMA/FHLMC**, the seller's book is measured in the month *before* the transition (the last month the seller still appears as servicer), and the buyer's book is measured in the transition month. For each consecutive month-pair, loans present in both months are inner-joined on `Loan Identifier`; any loan whose `Servicer Name` changed is counted as a transfer.

For **GNMA**, the data only shows the post-transfer state (the buyer is the current `Issuer ID`). The seller's pre-transfer book is approximated as loans still serviced by the seller in that month *plus* loans transferred away, since the seller may still retain part of its portfolio.

### Interpreting the fractions

| frac_seller | frac_buyer | Likely interpretation |
|:-----------:|:----------:|----------------------|
| ~100% | ~100% | **Rebrand** — same entity, new name (e.g., Quicken → Rocket) |
| ~100% | low | **Full exit to large buyer** — seller left the market (e.g., HomePoint → Nationstar) |
| ~100% | high | **Full exit to new/small buyer** — seller's book *is* the buyer's book (e.g., Matrix → TH MSR Holdings) |
| low | low | **Partial portfolio sale** — both parties retain large books (e.g., Wells Fargo → Nationstar) |
| low | high | **Flow sale to small buyer** — recurring small transfers to a dedicated acquirer |

## Running scripts

All scripts are designed to run from the **project root** (the directory containing `data/`):

```bash
python scripts/investigation_mlld_servicer_changes_2026-02-11.py
python scripts/investigation_fhlmc_servicer_changes_2026-02-11.py
python scripts/investigation_gnma_servicer_changes_2026-02-11.py
```

## Dependencies

- `polars`

## Key findings

- **34.3M loan-level servicer changes** across all three agencies (14.3M FNMA, 10.8M FHLMC, 9.2M GNMA)
- **$7.8T total UPB transferred** (2015-2026)
- Top buyers: Rocket/Nationstar, Freedom/Lakeview, NewRez, Carrington
- Major bank exits: Bank of America, JPMorgan, Wells Fargo systematically sold GNMA servicing
