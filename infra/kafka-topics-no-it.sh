#!/bin/bash

# Wait for Kafka to be ready
echo "Waiting for Kafka to be ready..."
sleep 10

# Kafka container name (adjust if needed)
KAFKA_CONTAINER="kafka"
KAFKA_BROKER="localhost:29092"

# Create topics
echo "Creating Kafka topics..."

docker exec $KAFKA_CONTAINER kafka-topics --create --if-not-exists \
  --bootstrap-server $KAFKA_BROKER \
  --topic raw-events \
  --partitions 3 \
  --replication-factor 1

docker exec $KAFKA_CONTAINER kafka-topics --create --if-not-exists \
  --bootstrap-server $KAFKA_BROKER \
  --topic features \
  --partitions 3 \
  --replication-factor 1

docker exec $KAFKA_CONTAINER kafka-topics --create --if-not-exists \
  --bootstrap-server $KAFKA_BROKER \
  --topic predictions \
  --partitions 3 \
  --replication-factor 1

docker exec $KAFKA_CONTAINER kafka-topics --create --if-not-exists \
  --bootstrap-server $KAFKA_BROKER \
  --topic decisions \
  --partitions 3 \
  --replication-factor 1

docker exec $KAFKA_CONTAINER kafka-topics --create --if-not-exists \
  --bootstrap-server $KAFKA_BROKER \
  --topic agent-metrics \
  --partitions 2 \
  --replication-factor 1

docker exec $KAFKA_CONTAINER kafka-topics --create --if-not-exists \
  --bootstrap-server $KAFKA_BROKER \
  --topic feedback \
  --partitions 2 \
  --replication-factor 1

docker exec $KAFKA_CONTAINER kafka-topics --create --if-not-exists \
  --bootstrap-server $KAFKA_BROKER \
  --topic alerts \
  --partitions 2 \
  --replication-factor 1

docker exec $KAFKA_CONTAINER kafka-topics --create --if-not-exists \
  --bootstrap-server $KAFKA_BROKER \
  --topic policy-requests \
  --partitions 2 \
  --replication-factor 1

docker exec $KAFKA_CONTAINER kafka-topics --create --if-not-exists \
  --bootstrap-server $KAFKA_BROKER \
  --topic policy-decisions \
  --partitions 2 \
  --replication-factor 1

docker exec $KAFKA_CONTAINER kafka-topics --create --if-not-exists \
  --bootstrap-server $KAFKA_BROKER \
  --topic config-updates \
  --partitions 1 \
  --replication-factor 1

docker exec $KAFKA_CONTAINER kafka-topics --create --if-not-exists \
  --bootstrap-server $KAFKA_BROKER \
  --topic incident-log \
  --partitions 1 \
  --replication-factor 1

echo "Topics created successfully!"
echo "Listing all topics:"
docker exec $KAFKA_CONTAINER kafka-topics --list --bootstrap-server $KAFKA_BROKER
