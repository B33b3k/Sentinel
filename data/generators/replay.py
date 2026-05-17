"""Stream transactions.parquet to Kafka at configurable TPS."""
import asyncio
import argparse
import json
import pathlib
import time

import pandas as pd
from aiokafka import AIOKafkaProducer

SEEDS_DIR = pathlib.Path("data/seeds")
TOPIC = "sentinel.transactions"


async def main(tps: int = 1000, loop: bool = False) -> None:
    try:
        producer = AIOKafkaProducer(
            bootstrap_servers="localhost:9092",
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        await producer.start()
        kafka_enabled = True
        print(f"[replay] Kafka connected to localhost:9092")
    except Exception as e:
        print(f"[replay] Kafka unavailable ({e}), dry-run mode")
        kafka_enabled = False

    txs_path = SEEDS_DIR / "transactions.parquet"
    if not txs_path.exists():
        raise FileNotFoundError(f"{txs_path} not found — run generate.py first")

    df = pd.read_parquet(txs_path)
    interval = 1.0 / tps
    total = 0

    try:
        while True:
            for _, row in df.iterrows():
                record = row.to_dict()
                # Ensure JSON-serialisable types
                for k, v in record.items():
                    if hasattr(v, "isoformat"):
                        record[k] = v.isoformat()
                    elif hasattr(v, "item"):  # numpy scalar
                        record[k] = v.item()

                if kafka_enabled:
                    await producer.send(TOPIC, record)
                total += 1
                await asyncio.sleep(interval)

                if total % 1000 == 0:
                    print(f"[replay] sent {total} transactions")

            if not loop:
                break
    finally:
        if kafka_enabled:
            await producer.stop()
        print(f"[replay] done — {total} transactions sent")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tps", type=int, default=1000)
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(tps=args.tps, loop=args.loop))
