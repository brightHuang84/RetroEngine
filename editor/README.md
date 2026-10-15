# RetroEngine 编辑器

桌面程序，用来改一个游戏的图块、调色板、地图和音乐，并在里面编译、试听、运行。界面是中文。游戏逻辑仍是 `games/<名字>/game.c`，编辑器里有一个带简单高亮的代码页。

## 在 Ubuntu 26.04 上安装一次

```sh
sudo apt install python3-pyside6 python3-pyside6.qtmultimedia python3-pil python3-numpy
```

这几项分别是界面、试听、读写 `tiles.png`、音频缓冲。系统没有 PySide6 包时：

```sh
python3 -m pip install --user PySide6 numpy
sudo apt install python3-pil
```

编译和运行游戏还需要引擎那一套工具，和仓库根目录 README 里写的一样：

```sh
sudo apt install build-essential libsdl2-dev gnu-efi mtools dosfstools \
                 qemu-system-x86 ovmf cc65 fceux gcc-arm-none-eabi mgba-sdl
```

缺哪个，编辑器的「检查依赖」会给出对应的 `apt install`。

装到应用程序菜单：

```sh
make editor-install
```

这会把 `~/.local/share/applications/retroengine-editor.desktop` 写好，图标指向仓库里的 `editor/icon.png`。注销一次或重新登录后，在应用程序里找 **RetroEngine 编辑器**。不装菜单也可以：

```sh
python3 editor/retro_editor.py
python3 editor/retro_editor.py games/platformer
```

## 怎么做一关

1. **文件 → 打开**，选 `breakout` 或 `platformer`。或者 **新建游戏**，从这两个例子复制，也可以从空白模板开始（空白模板会带上 breakout 的字体图块，这样 `bg_text` 能显示）。
2. **图块**：左边是 256 个图块，右边是放大的 8×8。左键涂当前颜色，右键取色。可以复制、粘贴、水平或垂直翻转。撤销和重做在「编辑」菜单里。预览调色板只影响编辑器里的颜色，不改图块数据。
3. **调色板**：上面 32 格是这个游戏的颜色（4 组背景 + 4 组精灵）。点一格，再点下面的 NES 64 色。写入 `palette.txt`。游戏里背景的颜色 0 永远用第一格，也就是共用背景色。
4. **地图**：选图块和背景调色板再涂。勾上「实心」后，这种图块在整张图里都挡人。「画的时候统一 16×16 调色板」会把 NES 的一个属性块涂成同一种调色板。黄线是第 32 列，也就是第二屏的起点。右键可以吸一个格子。保存后仍是原来的文本地图；只有同一图块在不同格子用了不同调色板时，才会多写一段 `palmap:`。
5. **音乐**：左边是 `songs.txt` 里的曲子。选通道，改速度、占空比（噪声通道上这一项是模式）、音量。点钢琴键改当前行，时值用 `4`、`8`、`8.` 或 `t12`（12 帧）。「从此循环」从当前行开始循环。「播放」在编辑器里试听，「音效」按钮播放引擎里那 6 个效果。桌面会话里用 Qt 播放；没有声音服务时改用 `paplay` 或 `aplay`（包 `alsa-utils`）。**导入 FamiStudio 文本** 把曲子追加进来。`music/*.fms.txt` 不在这个列表里，编译时仍会自动接在后面。
6. **预览** 用和游戏相同的上色看整张地图，包括 16×16 属性块。**运行 PC** 会先编译再打开窗口。
7. **代码** 改 `game.c`。金币、敌人、挡板这些仍写在代码里，编辑器不摆对象。
8. **编译** 里分别编 PC、UEFI、UEFI 镜像、NES、GBA。成功后用运行按钮打开。PC 直接运行编出来的程序；NES 用 fceux；GBA 用 mGBA；UEFI 用 QEMU 和 OVMF。

**文件 → 保存**（或编译前自动保存）把改过的文件写回游戏目录。没改过的 `songs.txt` 和地图不会被重排。

## 和命令行的关系

编辑器调用仓库根目录的 `make GAME=<名字> pc|uefi|img|nes|gba`。`make run` 仍然只编译并启动 PC 版。图块、地图、调色板和音乐的文件格式没有换，所以不打开编辑器时，原来的 `make` 流程照旧。
