"""Flatten nested claim JSON files into two flat tables: claims_fact and payments.

- claims_fact: one row per claim, events array dropped, incident_location flattened.
- payments:    one row per Payment_Issued event, with a generated payment_id.

Money -> Decimal(18,2); timestamps parsed as UTC. Reads use boto3 get_object and
writes use pyarrow -> BytesIO -> put_object (boto3 uses the .env static keys).
"""

import argparse
import json
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
PROCESSED_BUCKET = os.getenv("S3_PROCESSED_PREFIX")  # actual processed bucket name
RUN_DAY = datetime.today().strftime("%Y-%m-%d")

s3 = boto3.client("s3")

CLAIMS_PREFIX = "source=claims_mgmt/"
MONEY_TYPE = pa.decimal128(18, 2)
_CENTS = Decimal("0.01")


def to_decimal(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP)


def to_date_col(series):
    parsed = pd.to_datetime(series, errors="coerce")
    return [d.date() if pd.notna(d) else None for d in parsed]


def read_claims(day=None):
    """Read all claim JSON files (optionally for a single landing day=)."""
    prefix = CLAIMS_PREFIX + (f"day={day}/" if day else "")
    claims = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=LANDING_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.startswith("quarantine/") or not key.endswith(".json"):
                continue
            body = s3.get_object(Bucket=LANDING_BUCKET, Key=key)["Body"].read()
            claims.append(json.loads(body))
    return claims


def build_rows(claims):
    fact_rows = []
    payment_rows = []

    for claim in claims:
        claim_id = claim.get("claim_id")
        loc = claim.get("incident_location") or {}

        # claims_fact: drop events, flatten incident_location
        fact_rows.append(
            {
                "claim_id": claim_id,
                "policy_id": claim.get("policy_id"),
                "customer_id": claim.get("customer_id"),
                "incident_date": claim.get("incident_date"),
                "report_date": claim.get("report_date"),
                "incident_city": loc.get("city"),
                "incident_state": (loc.get("state") or "").strip().upper() or None,
                "incident_zip": loc.get("zip"),
                "incident_type": claim.get("incident_type"),
                "description": claim.get("description"),
                "status": claim.get("status"),
                "claim_amount": to_decimal(claim.get("claim_amount")),
                "approved_amount": to_decimal(claim.get("approved_amount")),
                "created_at": claim.get("created_at"),
            }
        )

        # payments: one row per Payment_Issued event
        seq = 0
        for event in claim.get("events", []) or []:
            if event.get("event_type") != "Payment_Issued":
                continue
            seq += 1
            payment_rows.append(
                {
                    "payment_id": f"{claim_id}-PAY-{seq}",
                    "claim_id": claim_id,
                    "policy_id": claim.get("policy_id"),
                    "payment_seq": seq,
                    "payment_amount": to_decimal(event.get("payment_amount")),
                    "payment_type": event.get("payment_type"),
                    "adjuster_id": event.get("adjuster_id"),
                    "paid_at": event.get("timestamp"),
                }
            )

    fact = pd.DataFrame(fact_rows)
    payments = pd.DataFrame(payment_rows)

    # Proper date types
    for col in ("incident_date", "report_date"):
        fact[col] = to_date_col(fact[col])

    # Timestamps parsed as UTC
    fact["created_at"] = pd.to_datetime(fact["created_at"], utc=True, errors="coerce")
    if not payments.empty:
        payments["paid_at"] = pd.to_datetime(payments["paid_at"], utc=True, errors="coerce")

    return fact, payments


def to_arrow(df, money_cols):
    table = pa.Table.from_pandas(df, preserve_index=False)
    for col in money_cols:
        if col in table.schema.names:
            idx = table.schema.get_field_index(col)
            table = table.set_column(idx, col, table.column(col).cast(MONEY_TYPE))
    return table


def write_processed(table, name):
    key = f"{name}/day={RUN_DAY}/{name}.parquet"
    buf = BytesIO()
    pq.write_table(table, buf, compression="snappy")
    s3.put_object(Bucket=PROCESSED_BUCKET, Key=key, Body=buf.getvalue())
    return key


def sanity_check(fact, payments):
    total_paid = sum((v for v in payments["payment_amount"] if v is not None), Decimal("0"))
    total_approved = sum((v for v in fact["approved_amount"] if v is not None), Decimal("0"))
    ok = total_paid <= total_approved
    print(
        f"\nSanity check: total payment_amount ({total_paid}) "
        f"<= total approved_amount ({total_approved}) -> {'PASS' if ok else 'FAIL'}"
    )
    if not ok:
        raise AssertionError("Sanity check failed: payments exceed approved amounts.")


def main():
    parser = argparse.ArgumentParser(description="Flatten claim JSON into claims_fact + payments.")
    parser.add_argument("--day", help="process only one landing day= partition (default: all)")
    args = parser.parse_args()

    if not PROCESSED_BUCKET:
        raise RuntimeError("S3_PROCESSED_PREFIX (processed bucket) is not set in .env")

    claims = read_claims(args.day)
    if not claims:
        raise FileNotFoundError("No claim JSON files found in landing zone.")
    print(f"Read {len(claims)} claim files.")

    fact, payments = build_rows(claims)

    fact_table = to_arrow(fact, money_cols=["claim_amount", "approved_amount"])
    pay_table = to_arrow(payments, money_cols=["payment_amount"])

    fact_key = write_processed(fact_table, "claims_fact")
    pay_key = write_processed(pay_table, "payments")

    print(f"✅ claims_fact: {len(fact)} rows -> s3://{PROCESSED_BUCKET}/{fact_key}")
    print(f"✅ payments:    {len(payments)} rows -> s3://{PROCESSED_BUCKET}/{pay_key}")

    sanity_check(fact, payments)
    print("\n✅ Claims transform completed.")


if __name__ == "__main__":
    main()
