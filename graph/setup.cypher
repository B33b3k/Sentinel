// Neo4j schema + indexes for SENTINEL graph layer

// Constraints
CREATE CONSTRAINT account_id_unique IF NOT EXISTS
FOR (a:Account) REQUIRE a.id IS UNIQUE;

// Indexes
CREATE INDEX account_district IF NOT EXISTS FOR (a:Account) ON (a.district);
CREATE INDEX account_type IF NOT EXISTS FOR (a:Account) ON (a.type);
CREATE INDEX transfer_timestamp IF NOT EXISTS FOR ()-[t:TRANSFERRED]-() ON (t.timestamp);
