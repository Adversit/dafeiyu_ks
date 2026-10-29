#!/usr/bin/env bash
# 快手大肥鱼一键启动
#  1) 首次自动安装依赖（含 Chromium）
#  2) 交互式补齐缺失配置（DeepSeek API Key / 作品链接）
#  3) 启动机器人（未登录时会引导扫码登录）
set -euo pipefail
cd "$(dirname "$0")"

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "==> 未检测到虚拟环境，安装依赖（含 Chromium，约 150MB，耐心等待）…"
  python3 -m venv .venv
  "$PY" -m pip install -q -r requirements.txt
  "$PY" -m playwright install chromium
  echo "==> 依赖就绪"
fi

"$PY" -m app.main --setup
echo ""
echo "==> 启动机器人…"
"$PY" -m app.main
