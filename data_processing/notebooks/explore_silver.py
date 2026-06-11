"""
Silver Layer Exploration — Pre-Gold Analysis
Reads cleaned interruptions data from ADLS silver layer
to understand what aggregations are needed for the gold layer.
"""

import os
import pandas as pd
from io import BytesIO
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()

# ── Read silver data ───────────────────────────────────────────────────────────
client = BlobServiceClient(
    account_url=f"https://{os.getenv('AZURE_STORAGE_ACCOUNT_NAME')}.blob.core.windows.net",
    credential=os.getenv("AZURE_STORAGE_ACCOUNT_KEY"),
)

blob = client.get_blob_client(
    container="silver",
    blob="comcom/interruptions_2025/silver_20260609.parquet"
)
df = pd.read_parquet(BytesIO(blob.download_blob().readall()))

print(f"Silver rows: {len(df):,}")
print(f"Columns: {df.columns.tolist()}")

# ── 1. SAIDI per company ───────────────────────────────────────────────────────
print("\n=== SAIDI per Company ===")
saidi = (
    df.groupby('edb')['saidi_value']
    .sum()
    .round(2)
    .sort_values(ascending=False)
    .reset_index()
)
print(saidi.to_string(index=False))

# ── 2. Duration stats ──────────────────────────────────────────────────────────
print("\n=== Duration Stats (minutes) ===")
print(df['duration_minutes'].describe().round(2))

# ── 3. Top 3 unplanned causes per company ─────────────────────────────────────
print("\n=== Top 3 Unplanned Causes per Company ===")
top_causes = (
    df[df['is_unplanned']]
    .groupby(['edb', 'cause_normalised'])
    .size()
    .reset_index(name='count')
    .sort_values(['edb', 'count'], ascending=[True, False])
    .groupby('edb')
    .head(3)
)
print(top_causes.to_string(index=False))

# ── 4. Monthly trend ──────────────────────────────────────────────────────────
print("\n=== Monthly Outage Trend ===")
df['month'] = df['start_datetime'].dt.to_period('M')
monthly = (
    df[df['is_unplanned']]
    .groupby('month')
    .agg(
        events=('edb', 'count'),
        total_saidi=('saidi_value', 'sum'),
        avg_duration=('duration_minutes', 'mean')
    )
    .round(2)
)
print(monthly.to_string())

# ── Investigate duration outliers ─────────────────────────────────────────────
print("\n=== Duration Outliers ===")
outliers = df[df['duration_minutes'] > 10000].sort_values(
    'duration_minutes', ascending=False
)[['edb', 'start_datetime', 'end_datetime', 'duration_minutes', 'cause_normalised']]
print(f"Events > 10,000 minutes: {len(outliers)}")
print(outliers.to_string(index=False))