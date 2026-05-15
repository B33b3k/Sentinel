"""Cohort storage — persist cohort assignment to Postgres and cache in Redis."""
from __future__ import annotations

import json
import os
from typing import Optional

import redis as _redis

from ml.cohorts.assign import AccountMeta, assign_cohort

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DB_URL = os.environ.get("DATABASE_URL", "postgresql://sentinel:sentinel@localhost:5432/sentinel_audit")
COHORT_TTL = 86400 * 7  # 7 days


def _redis_client() -> _redis.Redis:
    return _redis.Redis.from_url(REDIS_URL, decode_responses=True)


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

def cache_cohort(account_id: str, cohort: str, r: Optional[_redis.Redis] = None) -> None:
    """Write cohort to Redis with 7-day TTL."""
    client = r or _redis_client()
    client.setex(f"cohort:{account_id}", COHORT_TTL, cohort)


def get_cached_cohort(account_id: str, r: Optional[_redis.Redis] = None) -> Optional[str]:
    """O(1) cohort lookup from Redis. Returns None on cache miss."""
    client = r or _redis_client()
    return client.get(f"cohort:{account_id}")


# ---------------------------------------------------------------------------
# Postgres helpers (sync, using psycopg2 for simplicity in scripts)
# ---------------------------------------------------------------------------

def ensure_accounts_table() -> None:
    """Create accounts table if it doesn't exist."""
    import psycopg2
    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    account_id   TEXT PRIMARY KEY,
                    account_type TEXT NOT NULL,
                    home_district TEXT NOT NULL,
                    account_age_days INT NOT NULL,
                    cohort       TEXT NOT NULL,
                    created_at   TIMESTAMPTZ DEFAULT NOW(),
                    updated_at   TIMESTAMPTZ DEFAULT NOW()
                )
            """)
        conn.commit()
    finally:
        conn.close()


def upsert_account_cohort(meta: AccountMeta, cohort: str) -> None:
    """Insert or update account row with cohort in Postgres."""
    import psycopg2
    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO accounts (account_id, account_type, home_district, account_age_days, cohort)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (account_id) DO UPDATE
                  SET cohort = EXCLUDED.cohort,
                      account_age_days = EXCLUDED.account_age_days,
                      updated_at = NOW()
            """, (meta.account_id, meta.account_type, meta.home_district,
                  meta.account_age_days, cohort))
        conn.commit()
    finally:
        conn.close()


def get_account_cohort_from_db(account_id: str) -> Optional[str]:
    """Fetch cohort from Postgres (fallback when Redis misses)."""
    import psycopg2
    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT cohort FROM accounts WHERE account_id = %s", (account_id,))
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------

def register_account(meta: AccountMeta, r: Optional[_redis.Redis] = None,
                     persist_db: bool = True) -> str:
    """Assign cohort, store in Postgres (optional) and Redis. Returns cohort name."""
    cohort = assign_cohort(meta)
    cache_cohort(meta.account_id, cohort, r=r)
    if persist_db:
        try:
            upsert_account_cohort(meta, cohort)
        except Exception:
            pass  # DB unavailable — Redis cache is sufficient for demo
    return cohort


def resolve_cohort(account_id: str, meta: Optional[AccountMeta] = None,
                   r: Optional[_redis.Redis] = None) -> str:
    """Resolve cohort: Redis → Postgres → recompute from meta → fallback."""
    # 1. Redis cache (O(1))
    cached = get_cached_cohort(account_id, r=r)
    if cached:
        return cached

    # 2. Postgres
    try:
        from_db = get_account_cohort_from_db(account_id)
        if from_db:
            cache_cohort(account_id, from_db, r=r)
            return from_db
    except Exception:
        pass

    # 3. Recompute from meta if provided
    if meta:
        cohort = assign_cohort(meta)
        cache_cohort(account_id, cohort, r=r)
        return cohort

    return "fallback"


def seed_cohorts_from_parquet(parquet_path: str = "data/seeds/accounts.parquet",
                               r: Optional[_redis.Redis] = None) -> dict[str, int]:
    """Bulk-assign cohorts to all seed accounts. Returns cohort → count stats."""
    import pandas as pd
    df = pd.read_parquet(parquet_path)
    client = r or _redis_client()
    stats: dict[str, int] = {}
    pipe = client.pipeline()
    for _, row in df.iterrows():
        meta = AccountMeta(
            account_id=row["account_id"],
            account_type=row["account_type"],
            home_district=row["home_district"],
            account_age_days=int(row.get("account_age_days", 365)),
        )
        cohort = assign_cohort(meta)
        pipe.setex(f"cohort:{meta.account_id}", COHORT_TTL, cohort)
        stats[cohort] = stats.get(cohort, 0) + 1
    pipe.execute()
    return stats
