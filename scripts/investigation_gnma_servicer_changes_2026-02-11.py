"""
Full-history GNMA servicer change detection.

Unlike FNMA (which requires month-over-month differencing), GNMA loan-level
data has an explicit Seller Issuer ID field — populated ONLY when an MSR transfer
occurs. This script processes all available months (Apr 2015+), builds an issuer
ID → name lookup, and produces a CSV matching the FNMA output format.

Data sources: llmon1 + llmon2 L records, deduplicated on (Pool ID, Loan Seq, As-of Date).
Issuer lookup: issrcutoff (bronze) + nissues D (silver).

Output: CSV with one row per (seller, buyer, transition_month) aggregation.
"""

import gc
import time
from pathlib import Path

import polars as pl

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
LLMON1_L_DIR = Path("data/gnma/silver/llmon1/L/")
LLMON2_L_DIR = Path("data/gnma/silver/llmon2/L/")
ISSRCUTOFF_DIR = Path("data/gnma/bronze/issrcutoff/")
NISSUES_DIR = Path("data/gnma/silver/nissues/D/")
OUTPUT_CSV = Path("output/investigation_gnma_servicer_changes_2026-02-11.csv")

# ---------------------------------------------------------------------------
# Column names
# ---------------------------------------------------------------------------
COL_ISSUER = "Issuer ID (including for loan packages in MIP pool)"
COL_SELLER = "Seller Issuer ID"
COL_UPB = "Unpaid Principal Balance (UPB of the loan)"
COL_DATE = "As of Date (CCYYMM)"
COL_POOL = "Pool ID"
COL_LOAN_NEW = "Disclosure Sequence Number (A sequence number unique to loan level)"
COL_LOAN_OLD = "Disclosure Sequence Number (A sequence number unique to loan level )"  # trailing space
COL_LOAN = "loan_seq"


def extract_month(f: Path) -> str:
    """Extract YYYYMM from filename like llmon1_201504_L.parquet."""
    return f.stem.split("_")[1]


def build_issuer_lookup() -> dict[str, str]:
    """Build issuer ID → name mapping from issrcutoff + nissues D files."""
    print("=" * 90)
    print("BUILDING ISSUER ID → NAME LOOKUP")
    print("=" * 90)

    name_map: dict[str, str] = {}

    # Source 1: nissues D files (older, filled first so issrcutoff overwrites)
    nissues_files = sorted(NISSUES_DIR.glob("*.parquet"))
    for f in nissues_files:
        df = (
            pl.scan_parquet(f)
            .select(
                pl.col("Issuer Number").alias("issuer_id"),
                pl.col("Issuer Name").alias("issuer_name"),
            )
            .collect()
        )
        for row in df.iter_rows(named=True):
            name_map[row["issuer_id"]] = row["issuer_name"]
    print(f"  nissues D:    {len(name_map)} issuers from {len(nissues_files)} files")

    # Source 2: issrcutoff files (more recent, overwrites older names)
    issrcutoff_files = sorted(ISSRCUTOFF_DIR.glob("*.parquet"))
    for f in issrcutoff_files:
        df = (
            pl.scan_parquet(f)
            .with_columns(
                pl.col("text_content").str.slice(0, 4).str.strip_chars().alias("issuer_id"),
                pl.col("text_content").str.slice(4, 56).str.strip_chars().alias("issuer_name"),
            )
            .select("issuer_id", "issuer_name")
            .collect()
        )
        for row in df.iter_rows(named=True):
            name_map[row["issuer_id"]] = row["issuer_name"]
    print(f"  Combined:     {len(name_map)} unique issuers\n")

    return name_map


def main():
    name_map = build_issuer_lookup()

    def issuer_name(iid: str) -> str:
        return name_map.get(iid, f"ID:{iid}")

    # -----------------------------------------------------------------------
    # Discover and sort all llmon1/llmon2 L files (Apr 2015+)
    # -----------------------------------------------------------------------
    llmon1_files = sorted(LLMON1_L_DIR.glob("llmon1_*_L.parquet"))
    llmon2_files = sorted(LLMON2_L_DIR.glob("llmon2_*_L.parquet"))

    llmon1_files = [f for f in llmon1_files if extract_month(f) >= "201504"]
    llmon2_files = [f for f in llmon2_files if extract_month(f) >= "201504"]

    files_by_month: dict[str, list[Path]] = {}
    for f in llmon1_files + llmon2_files:
        files_by_month.setdefault(extract_month(f), []).append(f)

    months = sorted(files_by_month.keys())
    print(f"Files: {len(llmon1_files)} llmon1 + {len(llmon2_files)} llmon2")
    print(f"Month range: {months[0]} – {months[-1]} ({len(months)} months)\n")

    # -----------------------------------------------------------------------
    # Process each month: load, compute servicer totals, extract transfers
    # -----------------------------------------------------------------------
    print("=" * 90)
    print("PROCESSING ALL MONTHS")
    print("=" * 90)

    all_results: list[pl.DataFrame] = []
    t_total = time.perf_counter()

    for i, month in enumerate(months):
        t0 = time.perf_counter()
        month_frames = []

        for f in files_by_month[month]:
            lf = pl.scan_parquet(f)
            schema_cols = lf.collect_schema().names()

            if COL_LOAN_NEW in schema_cols:
                loan_col = COL_LOAN_NEW
            elif COL_LOAN_OLD in schema_cols:
                loan_col = COL_LOAN_OLD
            else:
                continue

            df = lf.select(
                pl.col(COL_POOL),
                pl.col(loan_col).alias(COL_LOAN),
                pl.col(COL_ISSUER),
                pl.col(COL_SELLER),
                pl.col(COL_UPB),
            ).collect()
            month_frames.append(df)

        # Combine llmon1 + llmon2, deduplicate
        df_month = pl.concat(month_frames).unique(subset=[COL_POOL, COL_LOAN])
        total = df_month.height

        # Parse UPB to dollars (stored as string in cents)
        df_month = df_month.with_columns(
            (
                pl.col(COL_UPB)
                .str.strip_chars()
                .replace("", None)
                .cast(pl.Float64, strict=False)
                / 100
            ).alias("upb_dollars")
        )

        # Servicer totals by Issuer ID (= current servicer in this month)
        servicer_totals = df_month.group_by(COL_ISSUER).agg(
            pl.len().alias("servicer_total_n"),
            pl.col("upb_dollars").sum().alias("servicer_total_upb"),
        )

        # Filter to transfers (Seller Issuer ID populated)
        transfers = df_month.filter(
            pl.col(COL_SELLER).is_not_null()
            & (pl.col(COL_SELLER).str.strip_chars() != "")
        )
        n_transfers = transfers.height
        pct = n_transfers / total * 100 if total > 0 else 0.0

        if n_transfers > 0:
            # Aggregate by (seller_id, buyer_id)
            agg = (
                transfers.group_by(COL_SELLER, COL_ISSUER)
                .agg(
                    pl.len().alias("n_loans"),
                    pl.col("upb_dollars").sum().alias("total_upb"),
                )
                .with_columns(pl.lit(month).alias("transition_month"))
            )

            # Join buyer totals (buyer = current Issuer ID)
            agg = agg.join(
                servicer_totals.rename({
                    COL_ISSUER: COL_ISSUER,
                    "servicer_total_n": "buyer_total_n",
                    "servicer_total_upb": "buyer_total_upb",
                }),
                on=COL_ISSUER,
                how="left",
            )

            # Seller totals: loans still serviced by seller + loans transferred away
            # In this month, seller's remaining book = servicer_totals[seller_id]
            # Seller's pre-transfer book ≈ remaining + transferred
            seller_transferred = (
                transfers.group_by(COL_SELLER)
                .agg(
                    pl.len().alias("seller_xfer_n"),
                    pl.col("upb_dollars").sum().alias("seller_xfer_upb"),
                )
            )
            seller_remaining = (
                servicer_totals.rename({
                    COL_ISSUER: COL_SELLER,
                    "servicer_total_n": "seller_remain_n",
                    "servicer_total_upb": "seller_remain_upb",
                })
            )
            seller_book = seller_transferred.join(
                seller_remaining, on=COL_SELLER, how="left"
            ).with_columns(
                (pl.col("seller_xfer_n") + pl.col("seller_remain_n").fill_null(0)).alias("seller_total_n"),
                (pl.col("seller_xfer_upb") + pl.col("seller_remain_upb").fill_null(0)).alias("seller_total_upb"),
            ).select(COL_SELLER, "seller_total_n", "seller_total_upb")

            agg = agg.join(seller_book, on=COL_SELLER, how="left")

            # Compute fractions
            agg = agg.with_columns(
                (pl.col("n_loans") / pl.col("seller_total_n")).alias("frac_seller_n"),
                (pl.col("total_upb") / pl.col("seller_total_upb")).alias("frac_seller_upb"),
                (pl.col("n_loans") / pl.col("buyer_total_n")).alias("frac_buyer_n"),
                (pl.col("total_upb") / pl.col("buyer_total_upb")).alias("frac_buyer_upb"),
            )

            # Resolve names, keep raw IDs
            agg = agg.with_columns(
                pl.col(COL_SELLER).alias("seller_issuer_id"),
                pl.col(COL_ISSUER).alias("issuer_id"),
                pl.col(COL_SELLER).map_elements(issuer_name, return_dtype=pl.Utf8).alias("servicer_from"),
                pl.col(COL_ISSUER).map_elements(issuer_name, return_dtype=pl.Utf8).alias("servicer_to"),
            ).select(
                "seller_issuer_id", "servicer_from",
                "issuer_id", "servicer_to",
                "transition_month",
                "n_loans", "total_upb",
                "frac_seller_n", "frac_seller_upb",
                "frac_buyer_n", "frac_buyer_upb",
            )

            all_results.append(agg)

        elapsed = time.perf_counter() - t0

        if (i + 1) % 12 == 0 or i == len(months) - 1:
            print(
                f"  {month}: {total:>10,} loans, {n_transfers:>8,} transfers ({pct:>5.2f}%)  "
                f"[{elapsed:.1f}s]  ({i+1}/{len(months)})"
            )

        del df_month, transfers, month_frames, servicer_totals
        gc.collect()

    total_elapsed = time.perf_counter() - t_total
    print(f"\nAll months processed in {total_elapsed / 60:.1f} minutes")

    # -----------------------------------------------------------------------
    # Combine, sort, write CSV
    # -----------------------------------------------------------------------
    if not all_results:
        print("No transfers detected.")
        return

    combined = pl.concat(all_results).sort(
        ["transition_month", "n_loans"], descending=[False, True]
    )

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    combined.write_csv(OUTPUT_CSV)

    print(f"\nWrote {combined.height:,} rows to {OUTPUT_CSV}")
    print(f"Total loan-level transfers: {combined['n_loans'].sum():,}")
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
