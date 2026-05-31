"""Load processed-zone Parquet into Snowflake.

For each table:
  1. TRUNCATE the STAGING table.
  2. COPY INTO STAGING.<table> from the external stage (one day= partition).
  3. MERGE INTO WAREHOUSE.<table> keyed on the primary key (upsert).

Connection settings come from the environment (.env):
  SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD,
  SNOWFLAKE_ROLE, SNOWFLAKE_WAREHOUSE
Database is fixed to SENTINEL. The external stage and file format are created
by sql/snowflake_integration_setup.sql.
"""

import argparse
import os
from datetime import datetime
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

DATABASE = "SENTINEL"
STAGE = "SENTINEL.STAGING.S3_PROCESSED_STAGE"
FILE_FORMAT = "SENTINEL.STAGING.PARQUET_FMT"

# warehouse/staging table name -> (processed-zone folder, primary key columns)
TABLES = [
    {"name": "DIM_CUSTOMER", "path": "customers", "pk": ["customer_id"]},
    {"name": "DIM_AGENT", "path": "agents", "pk": ["agent_id"]},
    {"name": "DIM_POLICY", "path": "policies", "pk": ["policy_id"]},
    {"name": "DIM_COVERAGE", "path": "coverages", "pk": ["coverage_id"]},
    {"name": "CLAIMS_FACT", "path": "claims_fact", "pk": ["claim_id"]},
    {"name": "PAYMENTS", "path": "payments", "pk": ["payment_id"]},
    {"name": "WEATHER_DAILY", "path": "weather_daily", "pk": ["zip_code", "weather_date"]},
]


def connect():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.getenv("SNOWFLAKE_ROLE"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=DATABASE,
    )


def get_columns(cur, table):
    """Return the column names of WAREHOUSE.<table> (load order)."""
    cur.execute(f"DESC TABLE {DATABASE}.WAREHOUSE.{table}")
    return [row[0] for row in cur.fetchall()]


def build_merge(table, columns, pk):
    """Build an upsert MERGE from STAGING.<table> into WAREHOUSE.<table>."""
    tgt = f"{DATABASE}.WAREHOUSE.{table}"
    src = f"{DATABASE}.STAGING.{table}"

    on_clause = " AND ".join(f"t.{c} = s.{c}" for c in pk)
    non_pk = [c for c in columns if c not in pk]
    set_clause = ", ".join(f"t.{c} = s.{c}" for c in non_pk)
    insert_cols = ", ".join(columns)
    insert_vals = ", ".join(f"s.{c}" for c in columns)

    merge = f"MERGE INTO {tgt} t USING {src} s ON {on_clause}\n"
    if non_pk:
        merge += f"WHEN MATCHED THEN UPDATE SET {set_clause}\n"
    merge += (
        f"WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})"
    )
    return merge


def load_table(cur, cfg, day):
    name, path, pk = cfg["name"], cfg["path"], cfg["pk"]
    staging = f"{DATABASE}.STAGING.{name}"
    location = f"@{STAGE}/{path}/day={day}/"

    cur.execute(f"TRUNCATE TABLE {staging}")

    cur.execute(
        f"COPY INTO {staging}\n"
        f"FROM {location}\n"
        f"FILE_FORMAT = (FORMAT_NAME = {FILE_FORMAT})\n"
        f"MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE\n"
        f"ON_ERROR = ABORT_STATEMENT"
    )

    columns = get_columns(cur, name)
    cur.execute(build_merge(name, columns, pk))

    cur.execute(f"SELECT COUNT(*) FROM {staging}")
    staged = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM {DATABASE}.WAREHOUSE.{name}")
    total = cur.fetchone()[0]
    print(f"✅ {name}: staged {staged} rows from {location} -> warehouse total {total}")


def main():
    parser = argparse.ArgumentParser(description="Load processed Parquet into Snowflake.")
    parser.add_argument(
        "--date",
        default=datetime.today().strftime("%Y-%m-%d"),
        help="processed-zone day= partition to load (YYYY-MM-DD)",
    )
    args = parser.parse_args()

    conn = connect()
    try:
        cur = conn.cursor()
        print(f"Loading processed data for day={args.date}\n")
        for cfg in TABLES:
            load_table(cur, cfg, args.date)

        # Deliverable check: warehouse claims_fact count
        cur.execute(f"SELECT COUNT(*) FROM {DATABASE}.WAREHOUSE.CLAIMS_FACT")
        print(f"\nSELECT COUNT(*) FROM WAREHOUSE.CLAIMS_FACT = {cur.fetchone()[0]}")
    finally:
        conn.close()

    print("\n✅ Warehouse load completed.")


if __name__ == "__main__":
    main()
