"""
Data Exploration & Industry Overview
Analyses ComCom EDB datasets to understand NZ electricity distribution sector
performance across all 29 lines companies.
"""

import pandas as pd

# ── Load datasets once ─────────────────────────────────────────────────────────
print("=== Loading Datasets ===")
df_full = pd.read_parquet(r"data_ingestion\raw_samples\EDB_ID_Full_2026-05-01.parquet")
df_int = pd.read_parquet(r"data_ingestion\raw_samples\EDB_ID_10a_interruptions_2025.09.1.parquet")

print(f"Full dataset:          {df_full.shape[0]:>10,} rows x {df_full.shape[1]} columns")
print(f"Interruptions dataset: {df_int.shape[0]:>10,} rows x {df_int.shape[1]} columns")

# ── Basic overview ─────────────────────────────────────────────────────────────
print("\n=== Interruptions Overview ===")
print(f"Years available: {sorted(df_int['disc_yr'].unique().tolist())}")
print(f"Total companies: {df_int['edb'].nunique()}")
print(f"\nPlanned vs Unplanned:\n{df_int['planned_or_unplanned'].value_counts().to_string()}")
print(f"\nTop 10 causes:\n{df_int['cause'].value_counts().head(10).to_string()}")

# ── Metric 1: Total SAIDI per company ─────────────────────────────────────────
saidi = (
    df_int.groupby('edb')['saidi_value']
    .sum()
    .round(2)
    .reset_index()
    .rename(columns={'saidi_value': 'total_saidi_2025'})
)

# ── Metric 2: Unplanned outage rate ───────────────────────────────────────────
unplanned_rate = (
    df_int.groupby('edb')
    .apply(lambda x: (x['planned_or_unplanned'] == 'Unplanned').mean())
    .round(3)
    .reset_index(name='unplanned_rate')
)

# ── Metric 3: Event count ──────────────────────────────────────────────────────
event_count = (
    df_int.groupby('edb')
    .size()
    .reset_index(name='event_count')
)

# ── Combine all metrics ────────────────────────────────────────────────────────
summary = (
    saidi
    .merge(unplanned_rate, on='edb')
    .merge(event_count, on='edb')
    .sort_values('total_saidi_2025', ascending=False)
)

print("\n=== Company Performance Analysis ===")
print(summary.to_string(index=False))

# ── Industry summary ───────────────────────────────────────────────────────────
industry_avg = summary['total_saidi_2025'].mean()

print("\n=== Industry Summary ===")
print(f"Total companies analysed: {len(summary)}")
print(f"Industry avg SAIDI:       {industry_avg:.2f} minutes")
print(f"Best performer:           {summary.iloc[-1]['edb']} (SAIDI: {summary.iloc[-1]['total_saidi_2025']:.2f})")
print(f"Worst performer:          {summary.iloc[0]['edb']} (SAIDI: {summary.iloc[0]['total_saidi_2025']:.2f})")
print(f"Above industry avg:       {(summary['total_saidi_2025'] > industry_avg).sum()} companies")
print(f"Below industry avg:       {(summary['total_saidi_2025'] <= industry_avg).sum()} companies")


# ── Pre-transformation exploration ────────────────────────────────────────────
print("\n=== Pre-Silver Exploration ===")

# 1. Check datetime columns — are they strings or datetime?
print("start_datetime dtype:", df_int['start_datetime'].dtype)
print("end_datetime dtype:  ", df_int['end_datetime'].dtype)
print("Sample values:")
print(df_int[['start_datetime', 'end_datetime']].head(3))

# 2. Check for missing values
print("\nMissing values:")
print(df_int.isnull().sum()[df_int.isnull().sum() > 0])

# 3. Check cause inconsistencies
print("\nAll unique causes:")
print(sorted(df_int['cause'].dropna().unique().tolist()))

# 4. Check planned_or_unplanned unique values
print("\nplanned_or_unplanned unique values:")
print(df_int['planned_or_unplanned'].unique().tolist())

# 5. Check for duplicate rows
print(f"\nDuplicate rows: {df_int.duplicated().sum()}")