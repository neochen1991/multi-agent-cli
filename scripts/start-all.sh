#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$RUN_DIR/logs"
PID_FILE="$RUN_DIR/start-all.pids"

BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_LOG_CONFIG="$BACKEND_DIR/logging.ini"
BACKEND_PORT=8000
FRONTEND_PORT=5173

mkdir -p "$LOG_DIR"

if [[ -x "$BACKEND_DIR/.venv/bin/uvicorn" ]]; then
  uvicorn_bin="$BACKEND_DIR/.venv/bin/uvicorn"
elif [[ -x "$BACKEND_DIR/venv/bin/uvicorn" ]]; then
  uvicorn_bin="$BACKEND_DIR/venv/bin/uvicorn"
elif command -v uvicorn >/dev/null 2>&1; then
  uvicorn_bin="uvicorn"
else
  echo "[ERROR] 未找到 uvicorn。请先在 backend 安装依赖。"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[ERROR] 未找到 npm。请先安装 Node.js/npm。"
  exit 1
fi

check_port_available() {
  name="$1"
  port="$2"
  if command -v lsof >/dev/null 2>&1; then
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "[ERROR] $name 端口 $port 已被占用，请先释放后重试。"
      lsof -nP -iTCP:"$port" -sTCP:LISTEN || true
      exit 1
    fi
  fi
}

if [[ -f "$PID_FILE" ]]; then
  active_found=0
  while IFS=":" read -r _ pid; do
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      active_found=1
      break
    fi
  done < "$PID_FILE"
  if [[ "$active_found" -eq 1 ]]; then
    echo "[ERROR] 检测到已有运行中的启动记录: $PID_FILE"
    echo "请先结束旧进程后再重试。"
    exit 1
  else
    rm -f "$PID_FILE"
  fi
fi

cleanup() {
  if [[ -f "$PID_FILE" ]]; then
    while IFS=":" read -r _ pid; do
      if [[ -n "${pid:-}" ]]; then
        kill "$pid" >/dev/null 2>&1 || true
      fi
    done < "$PID_FILE"
    rm -f "$PID_FILE"
  fi
}

trap cleanup EXIT INT TERM

wait_for_port() {
  name="$1"
  host="$2"
  port="$3"
  timeout="${4:-30}"

  for _ in $(seq 1 "$timeout"); do
    if (echo >"/dev/tcp/$host/$port") >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "[ERROR] $name 未在 ${timeout}s 内就绪，请检查日志。"
  return 1
}

start_service() {
  name="$1"
  workdir="$2"
  logfile="$3"
  shift 3

  (
    cd "$workdir"
    "$@" >>"$logfile" 2>&1
  ) &

  pid=$!
  echo "$name:$pid" >> "$PID_FILE"
  echo "[OK] $name 已启动 (PID=$pid, log=$logfile)"
}

: > "$PID_FILE"
: > "$LOG_DIR/backend.log"
: > "$LOG_DIR/frontend.log"

check_port_available "Backend" "$BACKEND_PORT"
check_port_available "Frontend" "$FRONTEND_PORT"

start_service "backend" "$BACKEND_DIR" "$LOG_DIR/backend.log" "$uvicorn_bin" "app.main:app" "--reload" "--host" "0.0.0.0" "--port" "$BACKEND_PORT" "--log-config" "$BACKEND_LOG_CONFIG"
start_service "frontend" "$FRONTEND_DIR" "$LOG_DIR/frontend.log" "npm" "run" "dev" "--" "--host" "0.0.0.0" "--port" "$FRONTEND_PORT"

wait_for_port "Backend" "127.0.0.1" "$BACKEND_PORT"
wait_for_port "Frontend" "127.0.0.1" "$FRONTEND_PORT"

echo ""
echo "全部服务已启动："
echo "- Backend:  http://localhost:$BACKEND_PORT"
echo "- Frontend: http://localhost:$FRONTEND_PORT"
echo ""
echo "日志目录: $LOG_DIR"
echo "按 Ctrl+C 可停止全部服务。"

while true; do
  failed=0
  while IFS=":" read -r name pid; do
    if [[ -z "${pid:-}" ]]; then
      continue
    fi
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      echo "[ERROR] $name 进程已退出，请检查日志: $LOG_DIR/$name.log"
      failed=1
      break
    fi
  done < "$PID_FILE"

  if [[ "$failed" -eq 1 ]]; then
    exit 1
  fi
  sleep 2
done
