#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
PID_FILE="$RUN_DIR/start-all.pids"

BACKEND_PORT=8000
FRONTEND_PORT=5173

echo "[INFO] 停止 start-all 记录的进程..."
if [[ -f "$PID_FILE" ]]; then
  while IFS=":" read -r _ pid; do
    if [[ -n "${pid:-}" ]]; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done < "$PID_FILE"
  rm -f "$PID_FILE"
else
  echo "[INFO] 未找到 PID 文件: $PID_FILE"
fi

if [[ "${1:-}" == "--force-ports" ]]; then
  if command -v lsof >/dev/null 2>&1; then
    echo "[INFO] 强制释放端口: $BACKEND_PORT/$FRONTEND_PORT"
    for p in "$BACKEND_PORT" "$FRONTEND_PORT"; do
      lsof -nP -iTCP:"$p" -sTCP:LISTEN || true
      for pid in $(lsof -nP -tiTCP:"$p" -sTCP:LISTEN 2>/dev/null || true); do
        kill "$pid" >/dev/null 2>&1 || true
      done
    done
  else
    echo "[WARN] 当前系统无 lsof，跳过端口强制清理。"
  fi
fi

echo "[OK] 停止完成"
