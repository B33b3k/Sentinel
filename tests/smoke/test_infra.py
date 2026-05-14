import socket
import subprocess
import time
import urllib.request

import psycopg
import pytest
import redis
from kafka import KafkaAdminClient
from neo4j import GraphDatabase


KAFKA_TOPICS = {
    "sentinel.transactions",
    "sentinel.verdicts",
    "sentinel.retraining",
    "sentinel.otp_events",
}


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _wait_until(check, timeout: float = 30.0, interval: float = 1.0):
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            result = check()
            if result:
                return result
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = exc
        time.sleep(interval)
    raise AssertionError(f"service did not become ready: {last_error}")


@pytest.mark.parametrize(
    ("name", "host", "port"),
    [
        ("kafka", "localhost", 9092),
        ("redis", "localhost", 6379),
        ("neo4j-bolt", "localhost", 7687),
        ("postgres", "localhost", 5432),
        ("mlflow", "localhost", 5000),
    ],
)
def test_ports_are_open(name: str, host: str, port: int):
    assert _wait_until(lambda: _port_open(host, port)), f"{name} is not reachable"


def test_kafka_topics_exist():
    subprocess.run(["bash", "scripts/init_kafka.sh"], check=True)
    admin = KafkaAdminClient(bootstrap_servers="localhost:9092", client_id="sentinel-smoke")
    try:
        assert KAFKA_TOPICS.issubset(set(admin.list_topics()))
    finally:
        admin.close()


def test_redis_ping():
    client = redis.Redis.from_url("redis://localhost:6379/0")
    assert _wait_until(client.ping) is True


def test_neo4j_connects():
    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "sentinelpass"))
    try:
        with driver.session() as session:
            assert session.run("RETURN 1 AS ok").single()["ok"] == 1
    finally:
        driver.close()


def test_postgres_connects():
    with psycopg.connect(
        host="localhost",
        port=5432,
        user="sentinel",
        password="sentinel",
        dbname="sentinel_audit",
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)


def test_mlflow_health_endpoint():
    def check():
        with urllib.request.urlopen("http://localhost:5000/health", timeout=3) as response:
            return response.status == 200

    assert _wait_until(check)
