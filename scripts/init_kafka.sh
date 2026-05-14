#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_SERVER="${KAFKA_BOOTSTRAP_SERVERS:-localhost:9092}"
CONTAINER="${KAFKA_CONTAINER:-sentinel-kafka}"

topics=(
  "sentinel.transactions:3"
  "sentinel.verdicts:3"
  "sentinel.retraining:1"
  "sentinel.otp_events:1"
)

for topic_spec in "${topics[@]}"; do
  topic="${topic_spec%%:*}"
  partitions="${topic_spec##*:}"

  docker exec "$CONTAINER" kafka-topics \
    --bootstrap-server "$BOOTSTRAP_SERVER" \
    --create \
    --if-not-exists \
    --topic "$topic" \
    --partitions "$partitions" \
    --replication-factor 1
done

docker exec "$CONTAINER" kafka-topics --bootstrap-server "$BOOTSTRAP_SERVER" --list
