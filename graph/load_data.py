"""Load accounts + transactions from parquet into Neo4j via LOAD CSV."""
from __future__ import annotations

import pathlib

import pandas as pd
from neo4j import GraphDatabase

from data.loader import load_accounts, load_transactions

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "sentinelpass")


def load_graph(uri: str = NEO4J_URI, auth: tuple = NEO4J_AUTH) -> None:
    driver = GraphDatabase.driver(uri, auth=auth)

    accts = load_accounts()
    txs = load_transactions()

    with driver.session() as session:
        # Apply schema
        schema = pathlib.Path("graph/setup.cypher").read_text()
        for stmt in schema.split(";"):
            stmt = stmt.strip()
            if stmt:
                session.run(stmt)

        # Batch-upsert accounts
        print(f"Loading {len(accts)} accounts...")
        batch = accts[["account_id", "account_type", "home_district", "account_age_days"]].to_dict("records")
        session.run("""
            UNWIND $rows AS row
            MERGE (a:Account {id: row.account_id})
            SET a.type = row.account_type,
                a.district = row.home_district,
                a.age_days = row.account_age_days
        """, rows=batch)

        # Batch-upsert transfer edges (only P2P / SWIFT with counterparty)
        transfers = txs[txs["counterparty_id"].notna()][
            ["account_id", "counterparty_id", "amount_npr", "timestamp", "transaction_id"]
        ].copy()
        transfers["timestamp"] = transfers["timestamp"].astype(str)
        print(f"Loading {len(transfers)} transfer edges...")

        CHUNK = 2000
        for i in range(0, len(transfers), CHUNK):
            chunk = transfers.iloc[i : i + CHUNK].to_dict("records")
            session.run("""
                UNWIND $rows AS row
                MERGE (src:Account {id: row.account_id})
                MERGE (dst:Account {id: row.counterparty_id})
                CREATE (src)-[:TRANSFERRED {
                    amount: row.amount_npr,
                    timestamp: datetime(row.timestamp),
                    tx_id: row.transaction_id
                }]->(dst)
            """, rows=chunk)

        count = session.run("MATCH (n:Account) RETURN count(n) AS c").single()["c"]
        print(f"Graph loaded — {count} Account nodes")

    driver.close()


if __name__ == "__main__":
    load_graph()
