-- Load seed data (files mounted from docker/init/data/)

COPY agents FROM '/docker-entrypoint-initdb.d/data/agents.csv'
    DELIMITER ',' CSV HEADER;

COPY customers FROM '/docker-entrypoint-initdb.d/data/customers.csv'
    DELIMITER ',' CSV HEADER;

COPY policies FROM '/docker-entrypoint-initdb.d/data/policies.csv'
    DELIMITER ',' CSV HEADER;

COPY coverages FROM '/docker-entrypoint-initdb.d/data/coverages.csv'
    DELIMITER ',' CSV HEADER;

COPY billing FROM '/docker-entrypoint-initdb.d/data/billing.csv'
    DELIMITER ',' CSV HEADER;
