import argparse
import json
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import boto3
import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

try:
    from schemas import SCHEMAS
except ModuleNotFoundError:  # when run as `python -m validators.validate_file`
    from validators.schemas import SCHEMAS

BUCKET = os.getenv("AWS_BUCKET")
s3 = boto3.client("s3")

QUARANTINE_PREFIX = "quarantine/"

# Landing-zone prefix for each source/schema
SOURCE_PREFIXES = {
    "customers": "source=policy_admin/table=customers/",
    "agents": "source=policy_admin/table=agents/",
    "policies": "source=policy_admin/table=policies/",
    "coverages": "source=policy_admin/table=coverages/",
    "billing": "source=billing/",
    "weather": "source=weather_api/",
    "claims": "source=claims_mgmt/",
}

# Logical JSON types -> python types for instance checks
JSON_TYPES = {
    "str": str,
    "float": (int, float),
    "int": int,
    "bool": bool,
    "dict": dict,
    "list": list,
}


def validate_dataframe(df, schema):
    """Validate a tabular (parquet) file against its schema."""
    errors = []

    expected_cols = set(schema["columns"])
    actual_cols = set(df.columns)

    missing = sorted(expected_cols - actual_cols)
    if missing:
        errors.append(f"Missing columns: {missing}")

    extra = sorted(actual_cols - expected_cols)
    if extra:
        errors.append(f"Unexpected columns: {extra}")

    # Data types
    for col, expected_dtype in schema["columns"].items():
        if col in df.columns:
            actual_dtype = str(df[col].dtype)
            if actual_dtype != expected_dtype:
                errors.append(
                    f"Column '{col}' expected dtype {expected_dtype} "
                    f"but got {actual_dtype}"
                )

    # Required non-null fields
    for col in schema["required"]:
        if col not in df.columns:
            errors.append(f"Required column '{col}' is missing")
        elif df[col].isnull().any():
            n = int(df[col].isnull().sum())
            errors.append(f"Required column '{col}' contains {n} null(s)")

    return errors


def validate_record(record, schema):
    """Validate a single JSON record (e.g. a claim) against its schema."""
    if not isinstance(record, dict):
        return ["File is not a JSON object"]

    errors = []

    expected_fields = set(schema["columns"])
    actual_fields = set(record)

    missing = sorted(expected_fields - actual_fields)
    if missing:
        errors.append(f"Missing fields: {missing}")

    extra = sorted(actual_fields - expected_fields)
    if extra:
        errors.append(f"Unexpected fields: {extra}")

    # Types
    for field, type_name in schema["columns"].items():
        if field in record and record[field] is not None:
            if not isinstance(record[field], JSON_TYPES[type_name]):
                errors.append(
                    f"Field '{field}' expected {type_name} "
                    f"but got {type(record[field]).__name__}"
                )

    # Required non-null fields
    for field in schema["required"]:
        if field not in record or record[field] in (None, ""):
            errors.append(f"Required field '{field}' is missing or null")

    return errors


def quarantine_file(source_key, report):
    """Move the bad file to quarantine/ and write its validation report.

    The original landing-zone path is preserved under quarantine/ so files that
    share a name (e.g. every billing.parquet) do not collide.
    """
    quarantine_key = f"{QUARANTINE_PREFIX}{source_key}"

    # Copy the bad file into quarantine
    s3.copy_object(
        Bucket=BUCKET,
        CopySource={"Bucket": BUCKET, "Key": source_key},
        Key=quarantine_key,
    )

    # Write the rejection report next to it
    report_key = f"{quarantine_key}.validation_report.json"
    s3.put_object(
        Bucket=BUCKET,
        Key=report_key,
        Body=json.dumps(report, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    # Remove the original from the landing zone (move semantics)
    s3.delete_object(Bucket=BUCKET, Key=source_key)

    print(f"❌ QUARANTINED  {source_key}")
    for err in report["errors"]:
        print(f"      - {err}")
    print(f"   report -> {report_key}")


def _read_parquet(key):
    obj = s3.get_object(Bucket=BUCKET, Key=key)
    return pd.read_parquet(BytesIO(obj["Body"].read()))


def _read_json(key):
    obj = s3.get_object(Bucket=BUCKET, Key=key)
    return json.loads(obj["Body"].read())


def validate_s3_file(s3_key, schema_name):
    """Validate one S3 object; quarantine it if it fails. Returns True if valid."""
    schema = SCHEMAS[schema_name]

    if schema["format"] == "parquet":
        errors = validate_dataframe(_read_parquet(s3_key), schema)
    else:
        errors = validate_record(_read_json(s3_key), schema)

    if errors:
        report = {
            "file": s3_key,
            "schema": schema_name,
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "status": "FAILED",
            "errors": errors,
        }
        quarantine_file(s3_key, report)
        return False

    print(f"✅ PASS  {s3_key}")
    return True


def _iter_keys(prefix, suffix):
    token = None
    while True:
        kwargs = {"Bucket": BUCKET, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            key = obj["Key"]
            if key.startswith(QUARANTINE_PREFIX):
                continue
            if key.endswith(suffix):
                yield key
        if resp.get("IsTruncated"):
            token = resp["NextContinuationToken"]
        else:
            break


def validate_source(schema_name, limit=None):
    """Validate every file under a source's landing prefix."""
    schema = SCHEMAS[schema_name]
    prefix = SOURCE_PREFIXES[schema_name]
    suffix = ".parquet" if schema["format"] == "parquet" else ".json"

    passed = failed = 0
    for i, key in enumerate(_iter_keys(prefix, suffix)):
        if limit is not None and i >= limit:
            break
        if validate_s3_file(key, schema_name):
            passed += 1
        else:
            failed += 1

    print(f"--- {schema_name}: {passed} passed, {failed} quarantined ---")
    return passed, failed


def main():
    parser = argparse.ArgumentParser(description="Validate landing-zone files against schemas.")
    parser.add_argument("--source", default="all", help="schema name (e.g. billing) or 'all'")
    parser.add_argument("--key", help="validate a single S3 key")
    parser.add_argument("--schema", help="schema name to use with --key")
    parser.add_argument("--limit", type=int, default=None, help="max files per source")
    args = parser.parse_args()

    if args.key:
        if not args.schema:
            parser.error("--key requires --schema")
        validate_s3_file(args.key, args.schema)
    elif args.source == "all":
        for name in SCHEMAS:
            validate_source(name, args.limit)
    else:
        validate_source(args.source, args.limit)


if __name__ == "__main__":
    main()
