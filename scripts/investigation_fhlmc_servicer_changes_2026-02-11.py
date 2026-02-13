"""
Full-history FHLMC (Freddie Mac) FU servicer change detection.

Same sliding-window approach as the FNMA script: load 2 months at a time,
inner-join on Loan Identifier, detect servicer name changes, aggregate.

Data: data/umbs/bronze/FHLMC/FU/ — 81 monthly files (201906–202602).
Columns: Loan Identifier, Servicer Name, Current Investor Loan UPB.

Output: CSV with one row per (servicer_from, servicer_to, transition_month).
"""

import gc
import time
from pathlib import Path

import polars as pl

DATA_DIR = Path("data/umbs/bronze/FHLMC/FU")
OUTPUT_CSV = Path("output/investigation_fhlmc_servicer_changes_2026-02-11.csv")

COLS = ["Loan Identifier", "Servicer Name", "Current Investor Loan UPB"]


def extract_month(p: Path) -> str:
    """Extract YYYYMM from filename like fu190606.parquet.

    FU filenames encode YYMM + day-of-month (e.g., fu190606 = 2019-06, day 06).
    We want YYYYMM.
    """
    raw = p.stem.replace("fu", "")  # e.g. "190606"
    yy = raw[:2]
    mm = raw[2:4]
    yyyy = f"20{yy}"
    return f"{yyyy}{mm}"


def load_month(path: Path) -> pl.DataFrame:
    """Load a single monthly file with column projection."""
    return pl.scan_parquet(path).select(COLS).collect()


def main():
    # -----------------------------------------------------------------------
    # Discover and sort all monthly files
    # -----------------------------------------------------------------------
    files = sorted(DATA_DIR.glob("fu*.parquet"))
    print(f"Found {len(files)} monthly FHLMC FU files")
    print(f"Range: {extract_month(files[0])} – {extract_month(files[-1])}")
    print(f"Pairs to compare: {len(files) - 1}\n")

    # -----------------------------------------------------------------------
    # Sliding window: compare consecutive month pairs
    # -----------------------------------------------------------------------
    all_results: list[pl.DataFrame] = []
    t_total = time.perf_counter()

    df_prev = load_month(files[0])
    print(f"Loaded {extract_month(files[0])}: {df_prev.height:>10,} loans")

    for i in range(1, len(files)):
        t0 = time.perf_counter()
        month_prev = extract_month(files[i - 1])
        month_curr = extract_month(files[i])

        df_curr = load_month(files[i])

        # Servicer-level totals for fraction columns
        seller_totals = (
            df_prev.group_by("Servicer Name")
            .agg(
                pl.col("Loan Identifier").count().alias("seller_total_n"),
                pl.col("Current Investor Loan UPB").sum().alias("seller_total_upb"),
            )
            .rename({"Servicer Name": "servicer_from"})
        )
        buyer_totals = (
            df_curr.group_by("Servicer Name")
            .agg(
                pl.col("Loan Identifier").count().alias("buyer_total_n"),
                pl.col("Current Investor Loan UPB").sum().alias("buyer_total_upb"),
            )
            .rename({"Servicer Name": "servicer_to"})
        )

        # Inner join on Loan Identifier
        joined = df_prev.select(
            "Loan Identifier",
            pl.col("Servicer Name").alias("servicer_from"),
            pl.col("Current Investor Loan UPB").alias("upb_from"),
        ).join(
            df_curr.select(
                "Loan Identifier",
                pl.col("Servicer Name").alias("servicer_to"),
                pl.col("Current Investor Loan UPB").alias("upb_to"),
            ),
            on="Loan Identifier",
            how="inner",
        )

        n_both = joined.height
        changed = joined.filter(pl.col("servicer_from") != pl.col("servicer_to"))
        n_changed = changed.height
        pct = n_changed / n_both * 100 if n_both > 0 else 0.0

        if n_changed > 0:
            agg = (
                changed.group_by("servicer_from", "servicer_to")
                .agg(
                    pl.col("Loan Identifier").count().alias("n_loans"),
                    pl.col("upb_from").sum().alias("total_upb_from"),
                    pl.col("upb_to").sum().alias("total_upb"),
                )
                .with_columns(pl.lit(month_curr).alias("transition_month"))
                # Join seller totals
                .join(seller_totals, on="servicer_from", how="left")
                # Join buyer totals
                .join(buyer_totals, on="servicer_to", how="left")
                # Compute fractions
                .with_columns(
                    (pl.col("n_loans") / pl.col("seller_total_n")).alias("frac_seller_n"),
                    (pl.col("total_upb_from") / pl.col("seller_total_upb")).alias("frac_seller_upb"),
                    (pl.col("n_loans") / pl.col("buyer_total_n")).alias("frac_buyer_n"),
                    (pl.col("total_upb") / pl.col("buyer_total_upb")).alias("frac_buyer_upb"),
                )
                # Drop intermediate columns
                .drop(
                    "total_upb_from",
                    "seller_total_n",
                    "seller_total_upb",
                    "buyer_total_n",
                    "buyer_total_upb",
                )
            )
            all_results.append(agg)

        elapsed = time.perf_counter() - t0
        print(
            f"  {month_prev} -> {month_curr}: "
            f"{n_both:>10,} in both, {n_changed:>8,} changed ({pct:>5.2f}%)  "
            f"[{elapsed:.1f}s]"
        )

        # Slide window
        df_prev = df_curr
        del joined, changed
        gc.collect()

    total_elapsed = time.perf_counter() - t_total
    print(f"\nAll pairs processed in {total_elapsed / 60:.1f} minutes")

    # -----------------------------------------------------------------------
    # Combine, sort, write CSV
    # -----------------------------------------------------------------------
    if not all_results:
        print("No servicer changes detected.")
        return

    combined = pl.concat(all_results).sort(
        ["transition_month", "n_loans"], descending=[False, True]
    )

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    combined.write_csv(OUTPUT_CSV)

    print(f"\nWrote {combined.height:,} rows to {OUTPUT_CSV}")
    print(f"Total loan-level servicer changes: {combined['n_loans'].sum():,}")
    print(f"Total UPB transferred: ${combined['total_upb'].sum() / 1e9:,.1f}B")
    print(f"Unique (from, to) pairs: {combined.select('servicer_from', 'servicer_to').unique().height:,}")

    # -----------------------------------------------------------------------
    # Top 20 largest single-month transitions
    # -----------------------------------------------------------------------
    print("\n" + "=" * 120)
    print("TOP 20 LARGEST SINGLE-MONTH TRANSITIONS")
    print("=" * 120)

    top20 = combined.sort("n_loans", descending=True).head(20)
    for row in top20.iter_rows(named=True):
        print(
            f"  {row['transition_month']}: "
            f"{row['servicer_from'][:40]:40s} -> {row['servicer_to'][:40]:40s} "
            f"| {row['n_loans']:>8,} loans | ${row['total_upb'] / 1e9:>7.2f}B "
            f"| sold {row['frac_seller_n']:>5.1%} of seller | = {row['frac_buyer_n']:>5.1%} of buyer"
        )

    print("\n--- Done ---")


if __name__ == "__main__":
    main()
