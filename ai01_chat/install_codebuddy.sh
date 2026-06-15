#!/usr/bin/env bash
# 将 CodeBuddy CLI 安装到 /usr/local/bin/codebuddy（系统全局可用）
set -euo pipefail

NODE_BIN="/Users/shuchaowang/.nvm/versions/node/v20.20.2/bin/node"
CODEBUDDY_JS="$HOME/.local/lib/node_modules/@tencent-ai/codebuddy-code/bin/codebuddy"
TARGET="/usr/local/bin/codebuddy"

if [ ! -x "$NODE_BIN" ]; then
  echo "错误: 未找到 Node.js: $NODE_BIN"
  exit 1
fi

if [ ! -f "$CODEBUDDY_JS" ]; then
  echo "错误: 未找到 CodeBuddy: $CODEBUDDY_JS"
  echo "请先运行: npm install -g @tencent-ai/codebuddy-code --prefix ~/.local"
  exit 1
fi

echo "安装 CodeBuddy 到 $TARGET ..."
sudo tee "$TARGET" > /dev/null << EOF
#!/bin/bash
exec "$NODE_BIN" "$CODEBUDDY_JS" "\$@"
EOF
sudo chmod +x "$TARGET"

echo ""
echo "安装完成！验证："
"$TARGET" --version 2>&1 | head -3 || true
echo ""
echo "现在可以在任意终端直接运行: codebuddy"
