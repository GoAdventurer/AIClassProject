#!/usr/bin/env bash
# CodeBuddy 聊天快速启动脚本

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

MODE="${1:-ui}"
PORT="${PORT:-7860}"

free_port() {
  local port="$1"
  local pids

  pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  if [ -z "$pids" ]; then
    return 0
  fi

  echo "端口 $port 已被占用，正在终止进程: $(echo "$pids" | tr '\n' ' ')"
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null || true
  sleep 1

  pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "进程未退出，强制终止..."
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
    sleep 1
  fi

  if lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "错误: 无法释放端口 $port"
    exit 1
  fi

  echo "端口 $port 已释放"
}

echo "CodeBuddy Chat 快速启动"
echo "========================"

if [ -d "venv" ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
  echo "已激活虚拟环境"
else
  echo "未找到 venv，使用系统 Python"
fi

if ! command -v codebuddy >/dev/null 2>&1; then
  CODEBUDDY="/usr/local/bin/codebuddy"
  if [ ! -x "$CODEBUDDY" ]; then
    CODEBUDDY="$HOME/.local/bin/codebuddy"
  fi
  if [ ! -x "$CODEBUDDY" ]; then
    echo "错误: 未找到 codebuddy，请运行 ./install_codebuddy.sh 安装"
    exit 1
  fi
  export PATH="$(dirname "$CODEBUDDY"):$PATH"
  echo "使用 CodeBuddy: $CODEBUDDY"
else
  echo "使用 CodeBuddy: $(command -v codebuddy)"
fi

case "$MODE" in
  ui|web)
    free_port "$PORT"
    echo "安装/检查 Gradio..."
    pip install -q gradio
    echo ""
    echo "启动 Web 界面: http://127.0.0.1:$PORT"
    echo "按 Ctrl+C 停止"
    echo ""
    PORT="$PORT" PYTHONPATH="$ROOT_DIR/src" python3 "$ROOT_DIR/src/codebuddy_chat_ui.py"
    ;;
  cli|terminal)
    echo ""
    echo "启动终端聊天..."
    PYTHONPATH="$ROOT_DIR/src" python3 "$ROOT_DIR/src/codebuddy_chat.py" "${@:2}"
    ;;
  *)
    echo "用法:"
    echo "  ./start_chat.sh          # 启动 Web 界面（默认）"
    echo "  ./start_chat.sh ui       # 启动 Web 界面"
    echo "  ./start_chat.sh cli      # 启动终端聊天"
    echo "  ./start_chat.sh cli -m 1 # 终端模式并指定模型"
    exit 1
    ;;
esac
