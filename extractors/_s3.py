"""Shared AWS/S3 setup for the extractor scripts."""

import os
from pathlib import Path

import boto3
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def configure_aws():
    """Load .env and export resolved AWS credentials into the environment.

    pandas/pyarrow writes to s3:// through Arrow's native (C++ SDK) S3
    filesystem, which does not read every botocore credential provider. Exporting
    the credentials resolved by boto3 (the static sentinel-pipeline-user keys in
    .env) ensures the Arrow layer authenticates instead of going anonymous.

    Returns the landing bucket name (AWS_BUCKET).
    """
    load_dotenv(PROJECT_ROOT / ".env")

    session = boto3.Session()
    creds = session.get_credentials()
    if creds is None:
        raise RuntimeError(
            "No AWS credentials found. Check .env or configure a profile."
        )

    frozen = creds.get_frozen_credentials()
    os.environ["AWS_ACCESS_KEY_ID"] = frozen.access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = frozen.secret_key
    if frozen.token:
        os.environ["AWS_SESSION_TOKEN"] = frozen.token
    os.environ.setdefault("AWS_DEFAULT_REGION", session.region_name or "us-east-2")

    bucket = os.getenv("AWS_BUCKET")
    if not bucket:
        raise RuntimeError("AWS_BUCKET is not set in .env")
    return bucket
