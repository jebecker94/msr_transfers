# MSR Transfer Detection & Analysis

Loan-level mortgage servicing rights (MSR) transfer detection across three agency datasets: FNMA (Fannie Mae), FHLMC (Freddie Mac), and GNMA (Ginnie Mae).

## What's here

- **Servicer change detection** — sliding-window comparison of monthly loan-level files to identify when a loan's servicer changes between consecutive months (FNMA/FHLMC) or via an explicit transfer flag (GNMA).
- **Aggregated transfer CSVs** — one row per (seller, buyer, transition_month) with loan counts, UPB, and portfolio fractions.
- **Survival analysis** — adverse selection test on partial-portfolio GNMA transfers: do sold loans perform differently from kept loans?

## Folder structure

```
msr_transfers/
├── README.md
├── scripts/                  # Analysis scripts (run from project root)
│   ├── investigation_mlld_servicer_changes_2026-02-11.py     # FNMA full history (81 months)
│   ├── investigation_fhlmc_servicer_changes_2026-02-11.py    # FHLMC full history (81 months)
│   ├── investigation_gnma_servicer_changes_2026-02-11.py     # GNMA full history (129 months)
│   └── investigation_gnma_msr_adverse_selection_2025-02-08.py       # GNMA survival analysis
├── reports/                  # Output reports and CSVs
│   ├── investigation_servicer_changes_combined_2026-02-11.md  # Combined writeup
│   ├── investigation_gnma_msr_adverse_selection_2025-02-08.md
│   ├── investigation_mlld_servicer_changes_2026-02-11.csv     # 3,256 rows
│   ├── investigation_fhlmc_servicer_changes_2026-02-11.csv    # 3,806 rows
│   ├── investigation_gnma_servicer_changes_2026-02-11.csv     # 6,430 rows
│   └── figures/
│       └── gnma_adverse_selection/   # KM curves, competing risks, forest plot
└── data/                     # Agency loan-level data (parquet)
```

## Running scripts

All scripts are designed to run from the **project root** (the directory containing `data/`):

```bash
# Full-history servicer change detection (main scripts)
python investigations/msr_transfers/scripts/investigation_mlld_servicer_changes_2026-02-11.py
python investigations/msr_transfers/scripts/investigation_fhlmc_servicer_changes_2026-02-11.py
python investigations/msr_transfers/scripts/investigation_gnma_servicer_changes_2026-02-11.py

# Survival analysis (requires lifelines, statsmodels)
python investigations/msr_transfers/scripts/investigation_gnma_msr_adverse_selection_2025-02-08.py
```

## Dependencies

- `polars` — all scripts
- `lifelines`, `scipy`, `matplotlib`, `numpy` — adverse selection script only

## Key findings

- **34.3M loan-level servicer changes** across all three agencies (14.3M FNMA, 10.8M FHLMC, 9.2M GNMA)
- **$7.8T total UPB transferred** (2015-2026)
- Top buyers: Rocket/Nationstar, Freedom/Lakeview, NewRez, Carrington
- Major bank exits: Bank of America, JPMorgan, Wells Fargo systematically sold GNMA servicing
- **No adverse selection** on credit risk: sold loans default at 31% the rate of kept loans; servicers select on prepayment risk, not credit quality
