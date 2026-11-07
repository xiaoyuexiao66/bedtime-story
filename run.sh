#!/usr/bin/env bash
# 一键启动（首次会自动创建虚拟环境并安装网页依赖）
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "创建虚拟环境…"
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

echo "启动：http://localhost:${BEDTIME_PORT:-8000}"
exec python app.py