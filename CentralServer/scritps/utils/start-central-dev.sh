#!/usr/bin/env bash

set -e

# Script location:
# CentralServer/scritps/utils/start-central-dev.sh
#
# Move two directories up to reach CentralServer.
CENTRAL_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/../.." \
    && pwd
)"

ENV_FILE="$CENTRAL_DIR/dev.env"
VENV_DIR="$CENTRAL_DIR/.venv"
CERT_FILE="$CENTRAL_DIR/certs/server.crt"
KEY_FILE="$CENTRAL_DIR/certs/server.key"

HOST="0.0.0.0"
PORT="8443"

echo "[VirtualManager] Starting Central Server..."
echo "[VirtualManager] Central Server directory: $CENTRAL_DIR"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: Development environment file not found:"
    echo "  $ENV_FILE"
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "ERROR: Python virtual environment not found:"
    echo "  $VENV_DIR"
    exit 1
fi

if [ ! -f "$CERT_FILE" ]; then
    echo "ERROR: Server certificate not found:"
    echo "  $CERT_FILE"
    exit 1
fi

if [ ! -f "$KEY_FILE" ]; then
    echo "ERROR: Server private key not found:"
    echo "  $KEY_FILE"
    exit 1
fi

set -a
source "$ENV_FILE"
set +a

if [ -z "$VIRTUALMANAGER_AGENT_TOKEN" ]; then
    echo "ERROR: VIRTUALMANAGER_AGENT_TOKEN is not defined."
    exit 1
fi

if [ -z "$VIRTUALMANAGER_DATABASE_URL" ]; then
    echo "ERROR: VIRTUALMANAGER_DATABASE_URL is not defined."
    exit 1
fi

source "$VENV_DIR/bin/activate"

cd "$CENTRAL_DIR"

echo "[VirtualManager] Environment loaded."
echo "[VirtualManager] Central Server ready."
echo "[VirtualManager] Swagger: https://localhost:$PORT/docs"

exec python -m uvicorn src.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --ssl-keyfile "$KEY_FILE" \
    --ssl-certfile "$CERT_FILE" \
    --reload