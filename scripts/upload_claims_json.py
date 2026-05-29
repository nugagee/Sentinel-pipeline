import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load environment variables (.env at the project root)
load_dotenv()

# Initialize S3 client (uses the dedicated sentinel-pipeline-user keys from .env)
s3 = boto3.client("s3")

# Bucket name
BUCKET_NAME = os.getenv("AWS_BUCKET")

# Local claims directory (resolved relative to the project, not the cwd)
CLAIMS_DIR = Path(__file__).resolve().parents[1] / "data" / "claims"

# Source prefix in the landing zone
SOURCE_PREFIX = "source=claims_mgmt"

# Track uploads per day partition
upload_counts = {}


def file_exists(bucket, key):
    """Return True only when the object already exists in S3.

    A 404 means "not found" (safe to upload). Any other error (e.g. 403)
    is re-raised so real problems are not silently treated as missing files.
    """
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise


# Walk through the claims directory
for root, dirs, files in os.walk(CLAIMS_DIR):

    # Only process day=YYYY-MM-DD folders that actually contain files
    if not files:
        continue

    # Extract the partition folder, e.g. "day=2026-01-08"
    day_folder = os.path.basename(root)

    upload_counts.setdefault(day_folder, 0)

    for file_name in sorted(files):

        if not file_name.endswith(".json"):
            continue

        local_path = os.path.join(root, file_name)

        # s3://<bucket>/source=claims_mgmt/day=YYYY-MM-DD/<filename>.json
        s3_key = f"{SOURCE_PREFIX}/{day_folder}/{file_name}"

        # Skip files already in S3 (idempotent re-runs)
        if file_exists(BUCKET_NAME, s3_key):
            print(f"Skipping existing file: {s3_key}")
            continue

        s3.upload_file(local_path, BUCKET_NAME, s3_key)
        print(f"Uploaded: {s3_key}")

        upload_counts[day_folder] += 1

# Print upload summary
print("\n=== Upload Summary ===")

total_uploaded = 0
for day in sorted(upload_counts):
    count = upload_counts[day]
    total_uploaded += count
    print(f"{day}: {count} files uploaded")

print(f"\nTotal uploaded this run: {total_uploaded}")
print("✅ Claims upload completed successfully.")
