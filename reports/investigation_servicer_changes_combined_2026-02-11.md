---
title: Cross-Agency Servicer Change Analysis (FNMA, FHLMC, GNMA)
date: 2026-02-11
status: complete
datasets: [FNMA MLLD bronze (201906–202602), FHLMC FU bronze (201906–202602), GNMA llmon1/llmon2 silver L (201504–202512)]
scripts: [investigation_mlld_servicer_changes_2026-02-11.py, investigation_fhlmc_servicer_changes_2026-02-11.py, investigation_gnma_servicer_changes_2026-02-11.py]
outputs: [investigation_mlld_servicer_changes_2026-02-11.csv, investigation_fhlmc_servicer_changes_2026-02-11.csv, investigation_gnma_servicer_changes_2026-02-11.csv]
---

# Cross-Agency Servicer Change Analysis

## Overview

This analysis tracks every loan-level servicer change across the three major agency disclosure datasets, producing a unified set of CSV files that document who transferred servicing to whom, when, and at what scale. The data covers 2015–2026 (GNMA) and 2019–2026 (FNMA, FHLMC).

## Summary Statistics

| | FNMA (MLLD) | FHLMC (FU) | GNMA (llmon1+2) |
|---|---:|---:|---:|
| **Period** | Jun 2019 – Feb 2026 | Jun 2019 – Feb 2026 | Apr 2015 – Dec 2025 |
| **Monthly files** | 81 | 81 | 129 |
| **Month-pair comparisons** | 80 | 80 | n/a (explicit flag) |
| **Universe (latest month)** | ~15.0M loans | ~10.2M loans | ~12.2M loans |
| **Total servicer changes** | 14.3M loans | 10.8M loans | 9.2M loans |
| **Total UPB changed** | $3.4T | $3.0T | $1.4T |
| **Unique (from, to) pairs** | 1,866 | 1,849 | 757 |
| **CSV rows** | 3,256 | 3,806 | 6,430 |

### Rebrands vs. Real Transfers

A large share of detected "transfers" in the conventional agencies (FNMA, FHLMC) are corporate rebrands — the same entity changing its legal name. Using a heuristic (>90% of seller's book AND >70% of buyer's book), we can separate these:

| | Rebrands | Real Transfers |
|---|---:|---:|
| **FNMA** | 5.2M loans ($1.1T) | 9.0M loans ($2.3T) |
| **FHLMC** | 4.1M loans ($1.1T) | 6.7M loans ($1.9T) |
| **GNMA** | 0.5M loans ($72B) | 8.7M loans ($1.4T) |

GNMA has far fewer rebrands because it uses issuer IDs rather than names — a name change doesn't produce a false positive unless the issuer ID itself changes (which is rare).

## Detection Method

**FNMA and FHLMC** lack an explicit transfer flag. We use a sliding-window approach: load two consecutive months, inner-join on Loan Identifier, and flag any loan whose Servicer Name differs. This catches both true MSR sales and corporate rebrands.

**GNMA** has an explicit `Seller Issuer ID` field populated only when an MSR transfer occurs. No month-over-month differencing is needed. We combine llmon1 + llmon2 L records (deduplicated) and filter to rows where this field is non-blank.

## Key Findings

### 1. The Nationstar-to-Rocket Rebrand (Feb 2026)

The single largest event across all three datasets. Nationstar Mortgage LLC rebranded to Rocket Mortgage, LLC:

- FNMA: 1.33M loans, $284B
- FHLMC: 896k loans, $218B
- Combined conventional: **2.2M loans, $502B** in a single month

This was purely a name change (99% of seller's book, 55% of buyer's book — the remainder being loans already under the Rocket name from Quicken Loans rebrands).

### 2. Quicken Loans Rebrands (2020–2021)

Quicken Loans underwent two sequential name changes visible in FNMA/FHLMC:
- **Aug 2020**: Quicken Loans Inc. → Quicken Loans, LLC (FNMA: 725k loans, FHLMC: 165k)
- **Sep 2021**: Quicken Loans, LLC → Rocket Mortgage, LLC (FNMA: 975k loans, FHLMC: 444k)

### 3. Major True MSR Sales

Filtering out rebrands, the largest actual transfers of servicing rights:

| Date | Seller | Buyer | FNMA | FHLMC | GNMA |
|------|--------|-------|-----:|------:|-----:|
| 2023-09 | HomePoint Financial | Nationstar | 163k | 119k | — |
| 2022-11 / 2024-01 | Caliber Home Loans | NewRez/New Residential | 146k | 93k + 74k | 204k |
| 2024-08 | Matrix Financial Services | TH MSR Holdings | 386k | 353k | — |
| 2024-12 | Flagstar Bank | Nationstar | 171k | — | — |
| 2023-08 | Wells Fargo | Nationstar | 109k | — | — |
| 2020-02 | Ditech Financial | NewRez | — | — | 123k |
| 2018-09 | SunTrust Mortgage | Truist | — | — | 116k |
| 2015-04/05 | Bank of America | Carrington + Nationstar | — | — | 110k + 112k |
| 2025-07 | Wells Fargo | Freedom Mortgage | — | — | 114k |

### 4. Serial Rebranders

Some servicers changed names multiple times, creating noise in the conventional data:

- **Nationstar**: LLC → LLC with comma (May 2022) → back to LLC (May 2023) on FHLMC
- **New Residential**: Multiple name variants (NewRez LLC, New Residential Mortgage LLC/,LLC) shuffled across FHLMC in 2022–2023
- **Flagstar**: FSB → National Association (Jan 2023) → N.A. (Apr 2023) on FNMA
- **PennyMac**: "Corp" → "Corp." (a single period) moved 173k loans on FHLMC

### 5. Wells Fargo's Multi-Year Exit

Wells Fargo has been steadily selling MSRs across all three agencies:
- GNMA: Selling to Freedom Mortgage and Nationstar from 2019 onward (17–22% of book per event)
- FNMA: 109k loans to Nationstar in Aug 2023 (8% of book)
- The partial-sale pattern (small % of seller per event) distinguishes this from a corporate exit — Wells Fargo retains the majority of its book

### 6. The Nonbank Consolidation Pattern

The data reveals an ongoing consolidation where independent mortgage banks (IMBs) acquire servicing from both banks and smaller nonbanks:

- **Nationstar/Rocket**: Largest acquirer across FNMA and FHLMC, absorbing HomePoint, Flagstar, Caliber, Wells Fargo portfolios
- **NewRez/New Residential**: Major acquirer on GNMA (Caliber, Ditech) and FHLMC
- **Freedom Mortgage**: Dominant GNMA buyer (RoundPoint, Wells Fargo government portfolios)
- **TH MSR Holdings**: Absorbed the entire Matrix Financial book ($193B combined) in a single month
- **Lakeview Loan Servicing**: Major GNMA buyer of JPMorgan Chase government MSRs (2018–2019)

## CSV File Reference

Each CSV has the same schema. One row = one (servicer_from, servicer_to) pair for a given month.

### Columns

| Column | Description |
|--------|-------------|
| `servicer_from` | Previous servicer name (seller) |
| `servicer_to` | New servicer name (buyer) |
| `transition_month` | YYYYMM when the new servicer appears |
| `n_loans` | Number of loans that changed |
| `total_upb` | Sum of Current Investor Loan UPB (dollars) from the "to" month |
| `frac_seller_n` | Loans transferred / seller's total loan count in the selling month |
| `frac_seller_upb` | UPB transferred / seller's total UPB in the selling month |
| `frac_buyer_n` | Loans transferred / buyer's total loan count in the buying month |
| `frac_buyer_upb` | UPB transferred / buyer's total UPB in the buying month |

### How to Use the Fraction Columns

The four fraction columns let you distinguish transfer types at a glance:

| frac_seller | frac_buyer | Interpretation |
|:-----------:|:----------:|----------------|
| ~100% | ~100% | **Rebrand** — same entity, new name (e.g., Quicken → Rocket) |
| ~100% | low | **Full exit to large buyer** — seller left market, buyer already large (e.g., HomePoint → Nationstar) |
| ~100% | high | **Full exit to new/small buyer** — seller's book IS the buyer's book (e.g., Matrix → TH MSR Holdings) |
| low | low | **Partial portfolio sale** — seller retains most of book, buyer has diverse sources (e.g., Wells Fargo → Nationstar) |
| low | high | **Flow sale to small buyer** — small recurring transfers to a dedicated acquirer |

### GNMA-Specific Notes

- Servicer names come from an issuer ID lookup table, not directly from the data. Some names may have extra spaces or abbreviation differences (e.g., "WELLS FARGO BANK  NA." with double space).
- The `frac_seller` columns approximate the seller's pre-transfer book as (loans still serviced) + (loans transferred), since the GNMA file only shows the post-transfer state.
- GNMA covers Apr 2015–Dec 2025 (longer history than the conventional agencies).

### Example Queries

```python
import polars as pl

# Load one file
df = pl.read_csv("investigations/reports/investigation_mlld_servicer_changes_2026-02-11.csv")

# Filter out likely rebrands
real = df.filter(~((pl.col("frac_seller_n") > 0.90) & (pl.col("frac_buyer_n") > 0.70)))

# Largest true MSR sales
real.sort("n_loans", descending=True).head(20)

# All transfers involving a specific servicer (as seller)
df.filter(pl.col("servicer_from").str.contains("WELLS FARGO"))

# Monthly total transfer volume
df.group_by("transition_month").agg(
    pl.col("n_loans").sum(),
    pl.col("total_upb").sum(),
).sort("transition_month")
```
