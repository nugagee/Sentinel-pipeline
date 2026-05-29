import os
from datetime import datetime
import boto3
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def export_aws_credentials():
    """Bridge boto3-resolved credentials into env vars.

    Credentials are resolved via boto3's standard chain, which prefers the
    static AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY loaded from .env (the
    dedicated sentinel-pipeline-user). pandas/pyarrow writes to s3:// through
    Arrow's native (C++ SDK) S3 filesystem, which does not support every
    botocore provider (e.g. the short-lived `login` session). Exporting the
    resolved credentials guarantees the Arrow layer authenticates with the same
    principal instead of falling back to anonymous access.
    """
    session = boto3.Session()
    creds = session.get_credentials()
    if creds is None:
        raise RuntimeError(
            "No AWS credentials found. Configure a profile, env vars, or `aws login`."
        )
    frozen = creds.get_frozen_credentials()
    os.environ["AWS_ACCESS_KEY_ID"] = frozen.access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = frozen.secret_key
    if frozen.token:
        os.environ["AWS_SESSION_TOKEN"] = frozen.token
    os.environ.setdefault("AWS_DEFAULT_REGION", session.region_name or "us-east-2")


export_aws_credentials()

# PostgreSQL connection details
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# AWS bucket
AWS_BUCKET = os.getenv("AWS_BUCKET")

# Create SQLAlchemy engine
engine = create_engine(
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# Tables to extract
tables = [
    "customers",
    "agents",
    "policies",
    "coverages"
]

# Current date partition
today = datetime.today().strftime("%Y-%m-%d")

# Extract each table
for table in tables:
    print(f"Extracting table: {table}")

    # Read data from Postgres
    query = f"SELECT * FROM {table}"
    df = pd.read_sql(query, engine)

    # S3 output path
    s3_path = (
        f"s3://{AWS_BUCKET}/"
        f"source=policy_admin/"
        f"table={table}/"
        f"day={today}/"
        f"{table}.parquet"
    )

    # Write to S3 as Parquet
    df.to_parquet(
        s3_path,
        engine="pyarrow",
        compression="snappy",
        index=False
    )

    print(f"Uploaded: {s3_path}")

print("✅ Extraction completed successfully.")