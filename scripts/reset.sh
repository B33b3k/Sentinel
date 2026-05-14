#!/usr/bin/env bash
set -euo pipefail

docker compose down -v
docker compose up -d

echo "Waiting for Kafka to become healthy..."
until docker exec sentinel-kafka kafka-broker-api-versions --bootstrap-server localhost:9092 >/dev/null 2>&1; do
  sleep 2
done

bash scripts/init_kafka.sh
