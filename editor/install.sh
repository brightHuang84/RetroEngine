#!/bin/sh
# 把编辑器放进当前用户的应用程序菜单。
set -e
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$HOME/.local/share/applications"
sed "s|@ROOT@|$ROOT|g" "$ROOT/editor/retroengine-editor.desktop.in" \
  > "$HOME/.local/share/applications/retroengine-editor.desktop"
chmod +x "$ROOT/editor/retro_editor.py" "$ROOT/editor/install.sh"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
fi
echo "已安装。应用程序菜单里的名字是「RetroEngine 编辑器」。"
echo "也可以直接运行：python3 $ROOT/editor/retro_editor.py"
