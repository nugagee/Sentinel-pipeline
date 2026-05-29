-- Policy admin source schema (from internal_system_source CSVs)

CREATE TABLE agents (
    agent_id        VARCHAR(20) PRIMARY KEY,
    agent_name      VARCHAR(255) NOT NULL,
    territory       VARCHAR(100),
    hire_date       DATE,
    license_number  VARCHAR(50)
);

CREATE TABLE customers (
    customer_id  VARCHAR(20) PRIMARY KEY,
    first_name   VARCHAR(100),
    last_name    VARCHAR(100),
    dob          DATE,
    email        VARCHAR(255),
    phone        VARCHAR(50),
    address      TEXT,
    city         VARCHAR(100),
    state        VARCHAR(10),
    zip_code     VARCHAR(10),
    created_at   TIMESTAMP
);

CREATE TABLE policies (
    policy_id       VARCHAR(20) PRIMARY KEY,
    customer_id     VARCHAR(20) NOT NULL REFERENCES customers (customer_id),
    agent_id        VARCHAR(20) NOT NULL REFERENCES agents (agent_id),
    policy_number   VARCHAR(50),
    coverage_type   VARCHAR(50),
    start_date      DATE,
    end_date        DATE,
    premium_amount  NUMERIC(12, 2),
    status          VARCHAR(20),
    created_at      TIMESTAMP
);

CREATE TABLE coverages (
    coverage_id     VARCHAR(20) PRIMARY KEY,
    policy_id       VARCHAR(20) NOT NULL REFERENCES policies (policy_id),
    coverage_code   VARCHAR(20),
    coverage_limit  INTEGER,
    deductible      INTEGER
);

CREATE TABLE billing (
    transaction_id    VARCHAR(20) PRIMARY KEY,
    policy_id         VARCHAR(20) NOT NULL REFERENCES policies (policy_id),
    customer_id       VARCHAR(20) NOT NULL REFERENCES customers (customer_id),
    transaction_date  DATE,
    transaction_type  VARCHAR(50),
    amount            NUMERIC(12, 2),
    payment_method    VARCHAR(50),
    status            VARCHAR(20)
);
