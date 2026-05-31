# Snowflake ↔ S3 Storage Integration (reproducible setup)

This describes how Snowflake reads the processed zone
(`s3://sentinel-processed-olajide/`) through a **Storage Integration** backed by
an AWS IAM role. It is a **two-phase handshake**: Snowflake generates an IAM
principal + external ID, and you grant that principal access via the role's
trust policy.

| Item | Value |
|------|-------|
| AWS account | `281851730941` |
| Processed bucket | `s3://sentinel-processed-olajide/` |
| IAM role | `sentinel-snowflake-role` |
| IAM policy | `sentinel-snowflake-s3-read` |
| Storage integration | `SENTINEL_S3_INT` |
| External stage | `@SENTINEL.STAGING.S3_PROCESSED_STAGE` |

---

## Step 1 — Create the IAM policy (S3 read access)

Least-privilege read on the processed bucket. Save as `iam/sentinel-snowflake-s3-policy.json`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SnowflakeReadObjects",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:GetObjectVersion"],
      "Resource": "arn:aws:s3:::sentinel-processed-olajide/*"
    },
    {
      "Sid": "SnowflakeListBucket",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::sentinel-processed-olajide",
      "Condition": { "StringLike": { "s3:prefix": ["*"] } }
    }
  ]
}
```

## Step 2 — Create the IAM role (placeholder trust, updated in Step 5)

Create a role `sentinel-snowflake-role` and attach the policy above. Start with a
placeholder trust policy that trusts your own account; it is replaced in Step 5
with Snowflake's principal.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::281851730941:root" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

```bash
aws iam create-role --role-name sentinel-snowflake-role \
  --assume-role-policy-document file://trust-placeholder.json
aws iam put-role-policy --role-name sentinel-snowflake-role \
  --policy-name sentinel-snowflake-s3-read \
  --policy-document file://iam/sentinel-snowflake-s3-policy.json
```

Note the role ARN: `arn:aws:iam::281851730941:role/sentinel-snowflake-role`.

## Step 3 — Create the Storage Integration in Snowflake

Put the role ARN from Step 2 into `STORAGE_AWS_ROLE_ARN` (see
`sql/snowflake_integration_setup.sql`) and run as `ACCOUNTADMIN`:

```sql
CREATE STORAGE INTEGRATION SENTINEL_S3_INT
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  ENABLED = TRUE
  STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::281851730941:role/sentinel-snowflake-role'
  STORAGE_ALLOWED_LOCATIONS = ('s3://sentinel-processed-olajide/');
```

## Step 4 — Read Snowflake's generated identity

```sql
DESC INTEGRATION SENTINEL_S3_INT;
```

Record these two property values:

- `STORAGE_AWS_IAM_USER_ARN` — e.g. `arn:aws:iam::<snowflake-acct>:user/abc1-s-xxxx`
- `STORAGE_AWS_EXTERNAL_ID` — e.g. `ABC12345_SFCRole=2_xxxxxxxx=`

## Step 5 — Update the IAM role trust policy with Snowflake's values

Replace the role's trust policy so **only** the Snowflake IAM user can assume it,
scoped by the external ID:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "AWS": "<STORAGE_AWS_IAM_USER_ARN>" },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": { "sts:ExternalId": "<STORAGE_AWS_EXTERNAL_ID>" }
      }
    }
  ]
}
```

```bash
aws iam update-assume-role-policy --role-name sentinel-snowflake-role \
  --policy-document file://trust-snowflake.json
```

## Step 6 — Create the file format + external stage

```sql
CREATE FILE FORMAT SENTINEL.STAGING.PARQUET_FMT TYPE = PARQUET;

CREATE STAGE SENTINEL.STAGING.S3_PROCESSED_STAGE
  STORAGE_INTEGRATION = SENTINEL_S3_INT
  URL = 's3://sentinel-processed-olajide/'
  FILE_FORMAT = SENTINEL.STAGING.PARQUET_FMT;
```

## Step 7 — Verify

```sql
LIST @SENTINEL.STAGING.S3_PROCESSED_STAGE;
```

You should see the processed Parquet keys (e.g. `customers/day=.../customers.parquet`).
If you get an `Access Denied`, the trust policy principal/external ID (Step 5) is
wrong, or IAM changes have not propagated yet (wait ~30–60s).

---

## Notes

- **Why a role, not access keys?** Snowflake assumes a cross-account role with an
  external ID — no long-lived keys are shared with Snowflake.
- **External ID matters.** It prevents the "confused deputy" problem; without the
  `sts:ExternalId` condition any Snowflake account could assume the role.
- **Scope.** The role grants read-only access to the processed bucket only. The
  ingestion pipeline continues to use the separate `sentinel-pipeline-user` keys.
- **Propagation.** After editing the trust policy, allow up to a minute before
  `LIST`/`COPY` succeeds.
```
