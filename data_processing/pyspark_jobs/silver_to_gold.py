"""
Silver to Gold Transformation — Company Performance & Reliability Analytics
Reads cleaned interruptions data from ADLS silver layer,
aggregates into analysis-ready tables, then writes to gold layer.

Gold tables:
1. company_performance  — SAIDI, SAIFI, event counts per company
2. cause_breakdown      — top causes per company
3. monthly_trend        — monthly outage trend (Apr 2024 - Mar 2025 only)
"""

import os
import pandas as pd
from io import BytesIO
from datetime import datetime
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()

# ── Azure Storage config ───────────────────────────────────────────────────────
ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
ACCOUNT_KEY = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
SILVER_CONTAINER = "silver"
GOLD_CONTAINER = "gold"


def get_adls_client() -> BlobServiceClient:
    """Create and return Azure Blob Service client."""
    return BlobServiceClient(
        account_url=f"https://{ACCOUNT_NAME}.blob.core.windows.net",
        credential=ACCOUNT_KEY,
    )


def read_from_silver(blob_path: str) -> pd.DataFrame:
    """Read parquet file from ADLS silver container."""
    client = get_adls_client()
    blob = client.get_blob_client(container=SILVER_CONTAINER, blob=blob_path)
    data = blob.download_blob().readall()
    df = pd.read_parquet(BytesIO(data))
    print(f"  Read {len(df):,} rows from silver/{blob_path}")
    return df


def write_to_gold(df: pd.DataFrame, blob_path: str) -> None:
    """Write parquet file to ADLS gold container."""
    client = get_adls_client()
    buffer = BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)
    blob = client.get_blob_client(container=GOLD_CONTAINER, blob=blob_path)
    blob.upload_blob(buffer, overwrite=True)
    print(f"  Written {len(df):,} rows to gold/{blob_path}")


def build_company_performance(df: pd.DataFrame) -> pd.DataFrame:
    """
    Table 1: Company-level performance summary.
    Metrics: SAIDI, SAIFI, event counts, unplanned rate,
             avg duration, top cause.
    """
    perf = df.groupby("edb").agg(
        total_saidi=("saidi_value", "sum"),
        total_saifi=("saifi_value", "sum"),
        total_events=("interruption_identifier", "count"),
        unplanned_events=("is_unplanned", "sum"),
        avg_duration_minutes=("duration_minutes", "mean"),
        median_duration_minutes=("duration_minutes", "median"),
    ).round(2).reset_index()

    perf["unplanned_rate"] = (
        perf["unplanned_events"] / perf["total_events"]
    ).round(3)

    industry_avg_saidi = perf["total_saidi"].mean().round(2)
    perf["industry_avg_saidi"] = industry_avg_saidi

    perf["saidi_vs_avg"] = (
        perf["total_saidi"] - industry_avg_saidi
    ).round(2)

    perf["saidi_rank"] = perf["total_saidi"].rank(
        ascending=False, method="min"
    ).astype(int)

    perf["gold_processed_at"] = datetime.utcnow()

    return perf.sort_values("total_saidi", ascending=False)


def build_cause_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """
    Table 2: Cause breakdown per company.
    Unplanned events only — planned maintenance excluded.
    """
    cause = (
        df[df["is_unplanned"]]
        .groupby(["edb", "cause_normalised"])
        .agg(
            event_count=("interruption_identifier", "count"),
            total_saidi=("saidi_value", "sum"),
            avg_duration_minutes=("duration_minutes", "mean"),
        )
        .round(2)
        .reset_index()
    )

    cause["cause_rank"] = (
        cause.groupby("edb")["event_count"]
        .rank(ascending=False, method="min")
        .astype(int)
    )

    total_per_company = (
        cause.groupby("edb")["event_count"]
        .sum()
        .reset_index(name="total_unplanned")
    )
    cause = cause.merge(total_per_company, on="edb")
    cause["cause_share"] = (
        cause["event_count"] / cause["total_unplanned"]
    ).round(3)

    cause["gold_processed_at"] = datetime.utcnow()

    return cause.sort_values(["edb", "cause_rank"])


def build_monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    """
    Table 3: Monthly outage trend.
    Apr 2024 - Mar 2025 only — excludes incomplete months.
    """
    df = df.copy()
    df["month"] = df["start_datetime"].dt.tz_localize(None).dt.to_period("M")

    # Keep only complete months: Apr 2024 - Mar 2025
    df = df[
        (df["month"] >= "2024-04") &
        (df["month"] <= "2025-03")
    ]

    monthly = (
        df[df["is_unplanned"]]
        .groupby("month")
        .agg(
            total_events=("interruption_identifier", "count"),
            total_saidi=("saidi_value", "sum"),
            avg_duration_minutes=("duration_minutes", "mean"),
            companies_affected=("edb", "nunique"),
        )
        .round(2)
        .reset_index()
    )

    monthly["month"] = monthly["month"].astype(str)
    monthly["gold_processed_at"] = datetime.utcnow()

    return monthly


def run():
    """Main transformation pipeline — silver to gold."""
    print("=== Silver to Gold Starting ===")

    print("\nReading from silver...")
    df = read_from_silver(
        "comcom/interruptions_2025/silver_20260609.parquet"
    )

    # ── Table 1: Company Performance ──────────────────────────────────────────
    print("\nBuilding Table 1: company_performance...")
    company_perf = build_company_performance(df)
    write_to_gold(company_perf, "comcom/company_performance.parquet")
    print(company_perf[[
        "edb", "total_saidi", "total_events",
        "unplanned_rate", "saidi_vs_avg", "saidi_rank"
    ]].to_string(index=False))

    # ── Table 2: Cause Breakdown ───────────────────────────────────────────────
    print("\nBuilding Table 2: cause_breakdown...")
    cause_breakdown = build_cause_breakdown(df)
    write_to_gold(cause_breakdown, "comcom/cause_breakdown.parquet")
    print("\nCause Breakdown Preview (Aurora Energy):")
    aurora = cause_breakdown[cause_breakdown["edb"] == "Aurora Energy"]
    print(aurora[[
        "cause_normalised", "event_count", "cause_share", "total_saidi"
    ]].to_string(index=False))

    # ── Table 3: Monthly Trend ─────────────────────────────────────────────────
    print("\nBuilding Table 3: monthly_trend...")
    monthly_trend = build_monthly_trend(df)
    write_to_gold(monthly_trend, "comcom/monthly_trend.parquet")
    print(monthly_trend.to_string(index=False))

    print("\n=== Silver to Gold Complete ===")


if __name__ == "__main__":
    run()