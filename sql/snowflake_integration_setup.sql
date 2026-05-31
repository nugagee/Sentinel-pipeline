-- =====================================================================
-- One-time Snowflake <-> S3 integration setup
-- Run as ACCOUNTADMIN (or a role with CREATE INTEGRATION).
--
-- This is a TWO-PHASE handshake with AWS IAM:
--   1) Create the storage integration below (with a placeholder role ARN).
--   2) DESC INTEGRATION to read STORAGE_AWS_IAM_USER_ARN + STORAGE_AWS_EXTERNAL_ID.
--   3) Put those two values into the AWS IAM role's trust policy
--      (see docs/snowflake_s3_integration.md).
--   4) Then create the stage + file format below.
-- =====================================================================

-- 1. Storage integration pointing at the processed bucket -------------
CREATE STORAGE INTEGRATION IF NOT EXISTS SENTINEL_S3_INT
    TYPE = EXTERNAL_STAGE
    STORAGE_PROVIDER = 'S3'
    ENABLED = TRUE
    -- Replace <AWS_ACCOUNT_ID> after you create the IAM role (see docs).
    STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::<AWS_ACCOUNT_ID>:role/sentinel-snowflake-role'
    STORAGE_ALLOWED_LOCATIONS = ('s3://sentinel-processed-olajide/');

-- After creating it, run this and copy the two values into the IAM trust policy:
--   DESC INTEGRATION SENTINEL_S3_INT;
-- Look for:
--   STORAGE_AWS_IAM_USER_ARN   (principal for the trust policy)
--   STORAGE_AWS_EXTERNAL_ID    (sts:ExternalId condition)

-- 2. Parquet file format ----------------------------------------------
-- USE_LOGICAL_TYPE = TRUE makes Snowflake honor Parquet logical-type
-- annotations (timestamp unit + isAdjustedToUTC). Without it, COPY reads
-- timestamp ints at the wrong scale -> out-of-range / "invalid" dates.
CREATE FILE FORMAT IF NOT EXISTS SENTINEL.STAGING.PARQUET_FMT
    TYPE = PARQUET
    USE_LOGICAL_TYPE = TRUE;

-- 3. External stage on the processed bucket ---------------------------
CREATE STAGE IF NOT EXISTS SENTINEL.STAGING.S3_PROCESSED_STAGE
    STORAGE_INTEGRATION = SENTINEL_S3_INT
    URL = 's3://sentinel-processed-olajide/'
    FILE_FORMAT = SENTINEL.STAGING.PARQUET_FMT;

-- Sanity check that Snowflake can list the bucket through the integration:
--   LIST @SENTINEL.STAGING.S3_PROCESSED_STAGE;
