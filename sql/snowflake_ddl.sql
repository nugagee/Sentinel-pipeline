-- =====================================================================
-- Sentinel data warehouse DDL
-- Database: SENTINEL
-- Schemas:  STAGING   (transient load targets, COPY INTO from S3)
--           WAREHOUSE (durable tables, MERGE target keyed on PK)
-- Column types mirror the processed-zone Parquet:
--   money       -> NUMBER(18,2)
--   dates       -> DATE
--   claim/payment timestamps (tz-aware UTC) -> TIMESTAMP_TZ
--   dim created_at (no tz)                   -> TIMESTAMP_NTZ
-- =====================================================================

CREATE DATABASE IF NOT EXISTS SENTINEL;

CREATE SCHEMA IF NOT EXISTS SENTINEL.STAGING;
CREATE SCHEMA IF NOT EXISTS SENTINEL.WAREHOUSE;

-- ---------------------------------------------------------------------
-- WAREHOUSE tables (durable, MERGE targets)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS SENTINEL.WAREHOUSE.DIM_CUSTOMER (
    customer_id   VARCHAR        NOT NULL,
    first_name    VARCHAR,
    last_name     VARCHAR,
    dob           DATE,
    email         VARCHAR,
    phone         VARCHAR,
    address       VARCHAR,
    city          VARCHAR,
    state         VARCHAR,
    zip_code      VARCHAR,
    created_at    TIMESTAMP_NTZ,
    PRIMARY KEY (customer_id)
);

CREATE TABLE IF NOT EXISTS SENTINEL.WAREHOUSE.DIM_AGENT (
    agent_id        VARCHAR     NOT NULL,
    agent_name      VARCHAR,
    territory       VARCHAR,
    hire_date       DATE,
    license_number  VARCHAR,
    PRIMARY KEY (agent_id)
);

CREATE TABLE IF NOT EXISTS SENTINEL.WAREHOUSE.DIM_POLICY (
    policy_id       VARCHAR        NOT NULL,
    customer_id     VARCHAR,
    agent_id        VARCHAR,
    policy_number   VARCHAR,
    coverage_type   VARCHAR,
    start_date      DATE,
    end_date        DATE,
    premium_amount  NUMBER(18,2),
    status          VARCHAR,
    created_at      TIMESTAMP_NTZ,
    PRIMARY KEY (policy_id)
);

CREATE TABLE IF NOT EXISTS SENTINEL.WAREHOUSE.DIM_COVERAGE (
    coverage_id     VARCHAR        NOT NULL,
    policy_id       VARCHAR,
    coverage_code   VARCHAR,
    coverage_limit  NUMBER(18,2),
    deductible      NUMBER(18,2),
    PRIMARY KEY (coverage_id)
);

CREATE TABLE IF NOT EXISTS SENTINEL.WAREHOUSE.CLAIMS_FACT (
    claim_id        VARCHAR        NOT NULL,
    policy_id       VARCHAR,
    customer_id     VARCHAR,
    incident_date   DATE,
    report_date     DATE,
    incident_city   VARCHAR,
    incident_state  VARCHAR,
    incident_zip    VARCHAR,
    incident_type   VARCHAR,
    description     VARCHAR,
    status          VARCHAR,
    claim_amount    NUMBER(18,2),
    approved_amount NUMBER(18,2),
    created_at      TIMESTAMP_TZ,
    PRIMARY KEY (claim_id)
);

CREATE TABLE IF NOT EXISTS SENTINEL.WAREHOUSE.PAYMENTS (
    payment_id      VARCHAR        NOT NULL,
    claim_id        VARCHAR,
    policy_id       VARCHAR,
    payment_seq     NUMBER(38,0),
    payment_amount  NUMBER(18,2),
    payment_type    VARCHAR,
    adjuster_id     VARCHAR,
    paid_at         TIMESTAMP_TZ,
    PRIMARY KEY (payment_id)
);

CREATE TABLE IF NOT EXISTS SENTINEL.WAREHOUSE.WEATHER_DAILY (
    weather_date     DATE          NOT NULL,
    zip_code         VARCHAR       NOT NULL,
    max_temp_c       FLOAT,
    min_temp_c       FLOAT,
    precipitation_mm FLOAT,
    max_wind_kmh     FLOAT,
    weather_code     NUMBER(38,0),
    PRIMARY KEY (zip_code, weather_date)
);

-- ---------------------------------------------------------------------
-- STAGING tables (transient, structurally identical to warehouse).
-- Recreated/truncated each load; COPY INTO target before MERGE.
-- ---------------------------------------------------------------------

CREATE TRANSIENT TABLE IF NOT EXISTS SENTINEL.STAGING.DIM_CUSTOMER   LIKE SENTINEL.WAREHOUSE.DIM_CUSTOMER;
CREATE TRANSIENT TABLE IF NOT EXISTS SENTINEL.STAGING.DIM_AGENT      LIKE SENTINEL.WAREHOUSE.DIM_AGENT;
CREATE TRANSIENT TABLE IF NOT EXISTS SENTINEL.STAGING.DIM_POLICY     LIKE SENTINEL.WAREHOUSE.DIM_POLICY;
CREATE TRANSIENT TABLE IF NOT EXISTS SENTINEL.STAGING.DIM_COVERAGE   LIKE SENTINEL.WAREHOUSE.DIM_COVERAGE;
CREATE TRANSIENT TABLE IF NOT EXISTS SENTINEL.STAGING.CLAIMS_FACT    LIKE SENTINEL.WAREHOUSE.CLAIMS_FACT;
CREATE TRANSIENT TABLE IF NOT EXISTS SENTINEL.STAGING.PAYMENTS       LIKE SENTINEL.WAREHOUSE.PAYMENTS;
CREATE TRANSIENT TABLE IF NOT EXISTS SENTINEL.STAGING.WEATHER_DAILY  LIKE SENTINEL.WAREHOUSE.WEATHER_DAILY;
