#!/usr/bin/env bash

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CENTRAL_DIR="$PROJECT_ROOT/CentralServer"

ENV_FILE="$CENTRAL_DIR/dev.env"
VENV_DIR="$CENTRAL_DIR/.venv"
CERT_FILE="$CENTRAL_DIR/certs/server.crt"
KEY_FILE="$CENTRAL_DIR/certs/server.key"

HOST="0.0.0.0"
PORT="8443"

echo "[VirtualManager] Starting Central Server..."

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: Development environment file not found:"
    echo "  $ENV_FILE"
    exit 1
fi

set -a
source "$ENV_FILE"
set +a

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

source "$VENV_DIR/bin/activate"

cd "$CENTRAL_DIR"

exec python -m uvicorn src.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --ssl-keyfile "$KEY_FILE" \
    --ssl-certfile "$CERT_FILE" \
    --reload