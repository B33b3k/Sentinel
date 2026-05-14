CREATE CONSTRAINT account_id IF NOT EXISTS
FOR (account:Account)
REQUIRE account.account_id IS UNIQUE;

CREATE CONSTRAINT transaction_id IF NOT EXISTS
FOR (transaction:Transaction)
REQUIRE transaction.transaction_id IS UNIQUE;
