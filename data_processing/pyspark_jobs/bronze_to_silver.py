"""
Bronze to Silver Transformation — Interruptions Dataset
Reads raw ComCom interruptions data from ADLS bronze layer,
cleans and standardises it, then writes to silver layer.

Findings from exploration:
- datetime columns already parsed (datetime64[us, UTC]) — no conversion needed
- 617 duplicate rows to remove
- cause column has 80+ inconsistent variants — normalised to 8 categories
- subnetwork and explanation columns have missing values — acceptable, not critical
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
BRONZE_CONTAINER = "bronze"
SILVER_CONTAINER = "silver"

# ── Cause normalisation map ────────────────────────────────────────────────────
# Built from actual data exploration — 80+ variants mapped to 8 categories
CAUSE_MAP = {
    # Defective Equipment
    "defective equipment": "Defective Equipment",
    "defectiveequipment": "Defective Equipment",
    "8.0 defective equipment": "Defective Equipment",
    "defective equipment - jumper failure": "Defective Equipment",
    "defective equipment - line clash": "Defective Equipment",
    "defective equipment - oh equipment failure": "Defective Equipment",
    "defective equipment - ug equipment failure": "Defective Equipment",
    "defective equipment - zone substation": "Defective Equipment",

    # Vegetation
    "vegetation": "Vegetation",
    "vegeatation": "Vegetation",
    "trees": "Vegetation",
    "2.0 vegetation": "Vegetation",
    "vegetation - inside zone": "Vegetation",
    "vegetation - outside zone": "Vegetation",
    "vegetation - wind-blown debris - trees": "Vegetation",

    # Wildlife
    "wildlife": "Wildlife",
    "6.0 wildlife": "Wildlife",
    "wildlife - bird": "Wildlife",
    "wildlife - possum": "Wildlife",
    "wildlife - other": "Wildlife",

    # Adverse Weather
    "adverse weather": "Adverse Weather",
    "adverseweather": "Adverse Weather",
    "3.0 adverse weather": "Adverse Weather",
    "adverse weather - snow/ice": "Adverse Weather",
    "adverse weather - wind": "Adverse Weather",
    "adverse weather - wind-blown debris (not trees)": "Adverse Weather",
    "adverse environment": "Adverse Weather",
    "adverse environment - fire": "Adverse Weather",
    "adverse environment - land slippage": "Adverse Weather",
    "4.0 adverse environment": "Adverse Weather",
    "lighting": "Adverse Weather",
    "lightning": "Adverse Weather",
    "lightning - lightning strike": "Adverse Weather",

    # Third Party Interference
    "third party interference": "Third Party Interference",
    "thirdpartyinterference": "Third Party Interference",
    "third party": "Third Party Interference",
    "third-party interference": "Third Party Interference",
    "third_party": "Third Party Interference",
    "3rd party interference": "Third Party Interference",
    "5.0 third party interference": "Third Party Interference",
    "third party interference - dig in": "Third Party Interference",
    "third party interference - other": "Third Party Interference",
    "third party interference - overhead contact": "Third Party Interference",
    "third party interference - trees": "Third Party Interference",
    "third party interference - vandalism/theft": "Third Party Interference",
    "third party interference - vehicle damage": "Third Party Interference",
    "third party services - customer request": "Third Party Interference",
    "foreign interference": "Third Party Interference",
    "transpower": "Third Party Interference",

    # Planned
    "planned": "Planned",
    "planned interruption": "Planned",
    "planned outage": "Planned",
    "planned shutdown": "Planned",
    "11.0 planned shutdown": "Planned",
    "planned capital / maintenance outage": "Planned",
    "planned shutdown - capital works": "Planned",
    "planned shutdown - maintenance": "Planned",

    # Human Error
    "human error": "Human Error",
    "humanerror": "Human Error",
    "human element": "Human Error",
    "human error - load shedding - network load": "Human Error",
    "human error - potential switching error": "Human Error",
    "human error - potential workmanship": "Human Error",
    "human error - protection settings - incorrect/error": "Human Error",

    # Unknown
    "unknown": "Unknown",
    "cause unknown": "Unknown",
    "causeunknown": "Unknown",
    "unknown cause": "Unknown",
    "9.0 cause unknown": "Unknown",
    "other": "Unknown",
    "other cause": "Unknown",
    "unknown - cursory patrolled - cause unknown": "Unknown",
    "unknown - data quality": "Unknown",
    "unknown - not patrolled - cause unknown": "Unknown",
    "unknown - operational patrolled - cause unknown": "Unknown",
}


def get_adls_client() -> BlobServiceClient:
    """Create and return Azure Blob Service client."""
    return BlobServiceClient(
        account_url=f"https://{ACCOUNT_NAME}.blob.core.windows.net",
        credential=ACCOUNT_KEY,
    )


def read_from_bronze(blob_path: str) -> pd.DataFrame:
    """Read parquet file from ADLS bronze container."""
    client = get_adls_client()
    blob = client.get_blob_client(container=BRONZE_CONTAINER, blob=blob_path)
    data = blob.download_blob().readall()
    df = pd.read_parquet(BytesIO(data))
    print(f"  Read {len(df):,} rows from bronze/{blob_path}")
    return df


def write_to_silver(df: pd.DataFrame, blob_path: str) -> None:
    """Write parquet file to ADLS silver container."""
    client = get_adls_client()
    buffer = BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)
    blob = client.get_blob_client(container=SILVER_CONTAINER, blob=blob_path)
    blob.upload_blob(buffer, overwrite=True)
    print(f"  Written {len(df):,} rows to silver/{blob_path}")


def normalise_cause(cause: str) -> str:
    """Map raw cause string to one of 8 standardised categories."""
    if pd.isna(cause):
        return "Unknown"
    return CAUSE_MAP.get(cause.lower().strip(), "Unknown")


def transform_interruptions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and transform raw interruptions data.
    Steps derived from data exploration findings.
    """

    # 1. Remove duplicates
    before = len(df)
    df = df.drop_duplicates()
    print(f"  Removed {before - len(df):,} duplicate rows")

    # 2. Calculate outage duration in minutes
    # datetime already parsed as datetime64[us, UTC] — no conversion needed
    df = df.copy()
    df["duration_minutes"] = (
        (df["end_datetime"] - df["start_datetime"])
        .dt.total_seconds()
        .div(60)
        .round(2)
    )

    # 3. Remove rows with invalid duration
    before = len(df)
    df = df[df["duration_minutes"] > 0].copy()
    print(f"  Removed {before - len(df):,} rows with invalid duration")

    # 4. Normalise cause to 8 standard categories
    df["cause_normalised"] = df["cause"].apply(normalise_cause)

    # 5. Add is_unplanned boolean
    df["is_unplanned"] = df["planned_or_unplanned"].str.lower() == "unplanned"

    # 6. Add silver metadata
    df["silver_processed_at"] = datetime.utcnow()

    return df


def run():
    """Main transformation pipeline — bronze to silver."""
    print("=== Bronze to Silver Starting ===")

    blob_path = "comcom/interruptions_2025/ingested_20260609.parquet"

    print(f"\nReading from bronze...")
    df = read_from_bronze(blob_path)

    print("\nTransforming...")
    df = transform_interruptions(df)

    print("\nWriting to silver...")
    silver_path = "comcom/interruptions_2025/silver_20260609.parquet"
    write_to_silver(df, silver_path)

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"\n=== Transformation Summary ===")
    print(f"Total records:     {len(df):,}")
    print(f"Companies:         {df['edb'].nunique()}")
    print(f"Date range:        {df['start_datetime'].min().date()} → {df['start_datetime'].max().date()}")
    print(f"Avg duration:      {df['duration_minutes'].mean():.1f} minutes")
    print(f"Unplanned events:  {df['is_unplanned'].sum():,} ({df['is_unplanned'].mean():.1%})")
    print(f"\nNormalised cause breakdown:")
    print(df['cause_normalised'].value_counts().to_string())

    print("\n=== Bronze to Silver Complete ===")


if __name__ == "__main__":
    run()