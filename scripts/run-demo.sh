#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "${script_dir}/.." && pwd)"
python_bin="${SMART_RETAIL_PYTHON:-${project_dir}/.venv/bin/python}"

if [[ ! -x "${python_bin}" ]]; then
  echo "Python environment not found at ${python_bin}." >&2
  echo "Create .venv and install the project first; see README.md." >&2
  exit 1
fi

if [[ ! -d "${project_dir}/frontend/node_modules" ]]; then
  echo "Frontend dependencies are missing. Run: cd frontend && npm ci" >&2
  exit 1
fi

export SMART_RETAIL_DEMO_MODE=true
export SMART_RETAIL_DATABASE_PATH="${SMART_RETAIL_DATABASE_PATH:-${project_dir}/data/smart_retail_demo.db}"
export SMART_RETAIL_API_HOST="${SMART_RETAIL_API_HOST:-127.0.0.1}"
export SMART_RETAIL_API_PORT="${SMART_RETAIL_API_PORT:-8000}"
export SMART_RETAIL_API_CORS_ALLOWED_ORIGINS="${SMART_RETAIL_API_CORS_ALLOWED_ORIGINS:-http://localhost:5173,http://127.0.0.1:5173}"
export PYTHONPATH="${project_dir}/src${PYTHONPATH:+:${PYTHONPATH}}"
export VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://localhost:${SMART_RETAIL_API_PORT}}"

backend_pid=""
frontend_pid=""

cleanup() {
  trap - INT TERM EXIT
  [[ -n "${frontend_pid}" ]] && kill "${frontend_pid}" 2>/dev/null || true
  [[ -n "${backend_pid}" ]] && kill "${backend_pid}" 2>/dev/null || true
  [[ -n "${frontend_pid}" ]] && wait "${frontend_pid}" 2>/dev/null || true
  [[ -n "${backend_pid}" ]] && wait "${backend_pid}" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

echo "Smart Retail Checkout"
echo "Mode: DEMO (synthetic checkout events; computer vision disabled)"
echo "API: http://${SMART_RETAIL_API_HOST}:${SMART_RETAIL_API_PORT}"
echo "Frontend: http://localhost:5173"
echo "Database: ${SMART_RETAIL_DATABASE_PATH}"

cd "${project_dir}"
"${python_bin}" -m smart_retail.api.service &
backend_pid="$!"

health_url="http://${SMART_RETAIL_API_HOST}:${SMART_RETAIL_API_PORT}/health"
for _ in {1..40}; do
  if curl --fail --silent --show-error "${health_url}" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "${backend_pid}" 2>/dev/null; then
    echo "Demo backend stopped during startup." >&2
    exit 1
  fi
  sleep 0.25
done

if ! curl --fail --silent --show-error "${health_url}" >/dev/null 2>&1; then
  echo "Demo backend did not become healthy at ${health_url}." >&2
  exit 1
fi

cd "${project_dir}/frontend"
npm run dev -- --host 127.0.0.1 --strictPort &
frontend_pid="$!"

wait "${frontend_pid}"
