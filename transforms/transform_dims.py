"""Clean dimension tables (+ weather) from the landing zone into the processed zone.

Reads raw Parquet from s3://<landing>/..., applies cleaning rules
(dedupe on primary key, money -> Decimal(18,2), proper date types, string
casing), and writes one cleaned Parquet per table to
s3://<processed>/<table>/day=YYYY-MM-DD/<table>.parquet.

Reads use boto3 get_object and writes use pyarrow -> BytesIO -> put_object, so
all S3 access goes through boto3 (which uses the .env static keys) and we get
exact control over the output Parquet types.
"""

import os
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

LANDING_BUCKET = os.getenv("AWS_BUCKET")
PROCESSED_BUCKET = os.getenv("S3_PROCESSED_PREFIX")  # actual bucket name
RUN_DAY = datetime.today().strftime("%Y-%m-%d")

s3 = boto3.client("s3")

MONEY_TYPE = pa.decimal128(18, 2)
_CENTS = Decimal("0.01")

# Per-table cleaning configuration
DIMENSIONS = {
    "customers": {
        "prefix": "source=policy_admin/table=customers/",
        "pk": "customer_id",
        "date_cols": ["dob"],
        "money_cols": [],
        "upper_cols": ["state"],
    },
    "agents": {
        "prefix": "source=policy_admin/table=agents/",
        "pk": "agent_id",
        "date_cols": ["hire_date"],
        "money_cols": [],
        "upper_cols": [],
    },
    "policies": {
        "prefix": "source=policy_admin/table=policies/",
        "pk": "policy_id",
        "date_cols": ["start_date", "end_date"],
        "money_cols": ["premium_amount"],
        "upper_cols": [],
    },
    "coverages": {
        "prefix": "source=policy_admin/table=coverages/",
        "pk": "coverage_id",
        "date_cols": [],
        "money_cols": ["coverage_limit", "deductible"],
        "upper_cols": ["coverage_code"],
    },
}

WEATHER = {
    "prefix": "source=weather_api/",
    "out_name": "weather_daily",
    "pk": ["zip_code", "weather_date"],
    "date_cols": ["weather_date"],
    "money_cols": [],
    "upper_cols": [],
}


def read_prefix(prefix):
    """Read and concatenate every Parquet object under a landing prefix."""
    frames = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=LANDING_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.startswith("quarantine/") or not key.endswith(".parquet"):
                continue
            body = s3.get_object(Bucket=LANDING_BUCKET, Key=key)["Body"].read()
            frames.append(pd.read_parquet(BytesIO(body)))
    if not frames:
        raise FileNotFoundError(f"No parquet files under s3://{LANDING_BUCKET}/{prefix}")
    return pd.concat(frames, ignore_index=True)


def to_decimal(series):
    """Convert a numeric series to Decimal(_, 2) objects (None for nulls)."""
    def conv(v):
        if pd.isna(v):
            return None
        return Decimal(str(v)).quantize(_CENTS, rounding=ROUND_HALF_UP)
    return series.map(conv)


def to_date(series):
    """Convert a series to python date objects (None for nulls)."""
    parsed = pd.to_datetime(series, errors="coerce")
    return [d.date() if pd.notna(d) else None for d in parsed]


def clean(df, cfg):
    df = df.copy()

    # 3. Drop duplicate rows based on the primary key
    df = df.drop_duplicates(subset=cfg["pk"], keep="first").reset_index(drop=True)

    # 6. Normalize string casing where appropriate
    for col in cfg["upper_cols"]:
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip().str.upper()

    # 5. Parse date columns into proper date types
    for col in cfg["date_cols"]:
        if col in df.columns:
            df[col] = to_date(df[col])

    # 4. Convert money fields to Decimal(18,2)
    for col in cfg["money_cols"]:
        if col in df.columns:
            df[col] = to_decimal(df[col])

    return df


def to_arrow(df, cfg):
    """Build a pyarrow Table with enforced money (decimal128(18,2)) types."""
    table = pa.Table.from_pandas(df, preserve_index=False)
    for col in cfg["money_cols"]:
        if col in table.schema.names:
            idx = table.schema.get_field_index(col)
            table = table.set_column(idx, col, table.column(col).cast(MONEY_TYPE))
    return table


def write_processed(table, out_name):
    key = f"{out_name}/day={RUN_DAY}/{out_name}.parquet"
    buf = BytesIO()
    pq.write_table(table, buf, compression="snappy")
    s3.put_object(Bucket=PROCESSED_BUCKET, Key=key, Body=buf.getvalue())
    return key


def transform_table(name, cfg, out_name=None):
    out_name = out_name or name
    raw = read_prefix(cfg["prefix"])
    raw_rows = len(raw)
    cleaned = clean(raw, cfg)
    table = to_arrow(cleaned, cfg)
    key = write_processed(table, out_name)
    print(
        f"✅ {out_name}: {raw_rows} raw -> {len(cleaned)} cleaned rows "
        f"({raw_rows - len(cleaned)} dupes dropped) -> s3://{PROCESSED_BUCKET}/{key}"
    )


def main():
    if not PROCESSED_BUCKET:
        raise RuntimeError("S3_PROCESSED_PREFIX (processed bucket) is not set in .env")

    for name, cfg in DIMENSIONS.items():
        transform_table(name, cfg)

    # 8. Same cleanup for weather, saved as weather_daily
    transform_table("weather", WEATHER, out_name=WEATHER["out_name"])

    print("\n✅ Dimension + weather transforms completed.")


if __name__ == "__main__":
    main()
