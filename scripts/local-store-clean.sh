#!/usr/bin/env bash

set -euo pipefail

STORE_DIR="${LOCAL_STORE_DIR:-/tmp/sre_debate_store}"

echo "[info] clean local store temp files in: $STORE_DIR"
mkdir -p "$STORE_DIR"

find "$STORE_DIR" -type f \( -name "*.tmp" -o -name "*.bak" \) -print -delete
echo "[ok] clean completed"
