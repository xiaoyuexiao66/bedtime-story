#!/usr/bin/env bash
# 在 Mac 上运行：把项目同步到 Linux 笔记本并安装依赖。
# 用法：
#   ./deploy.sh            # 默认主机 vivobook
#   ./deploy.sh vivobook
set -euo pipefail

HOST="${1:-vivobook}"
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "== 1/4 同步代码到 $HOST =="
rsync -av --delete \
  --exclude .venv --exclude models --exclude data \
  --exclude __pycache__ --exclude '.env' --exclude certs \
  "$DIR/" "$HOST:~/bedtime-story/"

echo "== 2/4 同步 API 配置 =="
scp "$DIR/.env" "$HOST:~/bedtime-story/.env"
ssh "$HOST" 'chmod 600 ~/bedtime-story/.env'

echo "== 3/4 安装 Python 依赖 =="
ssh "$HOST" 'cd ~/bedtime-story && \
  if [ ! -d .venv ]; then python3 -m venv .venv; fi && \
  .venv/bin/python -m pip install -q --upgrade pip && \
  .venv/bin/pip install -q -r requirements.txt -r requirements-tts.txt && \
  echo "依赖安装完成"'

echo "== 4/4 完成 =="
echo "下一步在 Linux 上执行："
echo "  ssh $HOST"
echo "  cd ~/bedtime-story"
echo "  .venv/bin/python scripts/download_models.py"
echo "  .venv/bin/python scripts/test_tts.py"
echo "  .venv/bin/python app.py"