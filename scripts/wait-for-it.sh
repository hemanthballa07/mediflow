#!/usr/bin/env bash
# Lightweight wait-for-it — waits for a host:port to be reachable
set -e
HOST=$1
PORT=$2
TIMEOUT=${3:-30}
echo "Waiting for $HOST:$PORT..."
for i in $(seq 1 $TIMEOUT); do
  if nc -z "$HOST" "$PORT" 2>/dev/null; then
    echo "$HOST:$PORT is ready."
    exit 0
  fi
  sleep 1
done
echo "Timeout waiting for $HOST:$PORT" >&2
exit 1
