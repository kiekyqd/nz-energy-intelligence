"""
Commerce Commission - Quality of Supply Data Fetcher
Fetches EDB Information Disclosure data and uploads to ADLS Gen2 bronze layer.

Data source: https://www.comcom.govt.nz/regulated-industries/electricity-lines/
             electricity-distributor-performance-and-data/
             information-disclosed-by-electricity-distributors/
"""

import os
import requests
import pandas as pd
from io import BytesIO
from datetime import datetime
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()

# ── Azure Storage config ───────────────────────────────────────────────────────
ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
ACCOUNT_KEY = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
BRONZE_CONTAINER = os.getenv("AZURE_CONTAINER_BRONZE", "bronze")

# ── ComCom data URLs ───────────────────────────────────────────────────────────
COMCOM_URLS = {
    "interruptions_2025": "https://www.comcom.govt.nz/assets/Uploads/EDB_ID_10a_interruptions_2025.09.1.parquet",
    "full_2026": "https://www.comcom.govt.nz/assets/file/0035/366299/EDB_ID_Full_2026-05-01.parquet",
}


def get_adls_client() -> BlobServiceClient:
    """Create and return Azure Blob Service client."""
    return BlobServiceClient(
        account_url=f"https://{ACCOUNT_NAME}.blob.core.windows.net",
        credential=ACCOUNT_KEY,
    )


def download_comcom_data(dataset_name: str, url: str) -> pd.DataFrame:
    """
    Download ComCom parquet file directly into memory.
    Reads straight into DataFrame without writing temp files.
    """
    print(f"Downloading {dataset_name}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.comcom.govt.nz/",
        "Accept": "application/octet-stream,*/*",
    }
    response = requests.get(url, headers=headers, timeout=60)
    response.raise_for_status()

    df = pd.read_parquet(BytesIO(response.content))
    print(f"  Downloaded {len(df):,} rows, {df['edb'].nunique()} companies")
    return df


def upload_to_bronze(df: pd.DataFrame, blob_path: str) -> None:
    """Upload DataFrame as parquet to ADLS bronze container."""
    client = get_adls_client()
    buffer = BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)

    blob = client.get_blob_client(container=BRONZE_CONTAINER, blob=blob_path)
    blob.upload_blob(buffer, overwrite=True)
    print(f"  Uploaded to bronze/{blob_path} ✓")


def run():
    """Main ingestion pipeline — download ComCom data and upload to bronze."""
    print("=== ComCom Fetcher Starting ===")
    ingested_at = datetime.utcnow().strftime("%Y%m%d")

    for dataset_name, url in COMCOM_URLS.items():
        try:
            df = download_comcom_data(dataset_name, url)

            # Add ingestion metadata
            df["ingested_at"] = datetime.utcnow()
            df["source"] = "COMCOM"

            blob_path = f"comcom/{dataset_name}/ingested_{ingested_at}.parquet"
            upload_to_bronze(df, blob_path)

        except Exception as e:
            print(f"  ERROR on {dataset_name}: {e}")

    print("\n=== ComCom Fetcher Complete ===")


if __name__ == "__main__":
    run()