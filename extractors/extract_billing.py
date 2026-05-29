import pandas as pd

from _s3 import PROJECT_ROOT, configure_aws

# Load .env, export AWS creds, and get the landing bucket
AWS_BUCKET = configure_aws()

# Source CSV (resolved relative to the project, not the cwd)
BILLING_CSV = PROJECT_ROOT / "data" / "source" / "billing.csv"

# Load billing CSV
df = pd.read_csv(BILLING_CSV)

# Convert transaction_date to datetime
df["transaction_date"] = pd.to_datetime(df["transaction_date"])

# Group by calendar date
grouped = df.groupby(df["transaction_date"].dt.date)

# Save each date group as its own daily partition
for transaction_date, group in grouped:

    day = transaction_date.strftime("%Y-%m-%d")

    s3_path = (
        f"s3://{AWS_BUCKET}/"
        f"source=billing/"
        f"day={day}/"
        f"billing.parquet"
    )

    group.to_parquet(
        s3_path,
        engine="pyarrow",
        compression="snappy",
        index=False,
    )

    print(f"Uploaded billing data ({len(group)} rows): {s3_path}")

print(f"\n✅ Billing extraction completed. {grouped.ngroups} daily partitions written.")
