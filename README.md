# retro_engine —— 可移植的 2D 复古小引擎（PC/SDL2 · UEFI 裸机 · NES · GBA）

**游戏逻辑在各平台上完全相同，只有构建方式不同。** 引擎和游戏都用 C89 编写（可以用 cc65 编译），只用整数和定点数，不使用 malloc。所有限制以 NES 为准：屏幕 256x240、8x8 tile、最多 64 个精灵、2KB RAM、NTSC 60Hz。

> ⚠️ 压缩包里已经带了预编译文件。`make` 会**跳过已经是最新的输出**；如果想从头完整重新编译，请先执行 `make clean`。

## 架构
```mermaid
flowchart TD
  subgraph games[games/&lt;name&gt; —— 只调用 engine.h]
    BG[breakout/game.c]:::g
    PF[platformer/game.c]:::g
  end
  games --> E[engine/engine.c<br>背景/属性/文字, 精灵/metasprite, 输入边沿,<br>场景, 六通道乐曲+音效, 定点数/AABB/地图碰撞, 实体表]
  E -->|engine/backend.h| RS[render/render_soft.c<br>模拟 NES PPU：2 张 nametable, 属性, 64 精灵, 翻转, 滚动]
  E -->|engine/backend.h| RN[render/render_nes.c<br>VRAM 更新队列 → NMI/vblank, OAM DMA, APU 与 MMC5 方波]
  E -->|engine/backend.h| RG[render/render_gba.c<br>mode 0 4bpp, BG+OBJ, HBlank 分屏, DMG 四通道]
  RS --> SDL[platform/sdl<br>窗口 3x, 键盘, 方波/三角波/噪声混合]
  RS --> UEFI[platform/uefi<br>GOP 缩放居中, SimpleTextInput, Stall, PC 喇叭]
  RN --> NES[platform/nes<br>crt0.s, mmc5.cfg / nes.cfg, 手柄]
  RG --> GBA[platform/gba<br>crt0.s, gba.ld, 手柄, vblank]
  A[games/&lt;name&gt;/tiles.png + maps/*.txt + palette.txt + entities.txt] --> T[tools/build_assets.py<br>png2chr.py + png2gba.py + mappack.py + ent2c.py]
  T --> CHR[game.chr → NES]
  T --> CA[tiles.c / tiles_gba.c / maps.c / palette.c / assets.h → 各平台]
  S[games/&lt;name&gt;/songs.txt<br>以及 music/*.fms.txt] --> FM[tools/fms2mus.py]
  FM --> TM[tools/txt2mus.py]
  TM --> MU[music.c / music.h → 所有平台]
  classDef g fill:#ffd
```

## 目录结构
```
engine/   engine.h（公开 API） backend.h（后端接口） engine.c
render/   render_soft.c/.h（PC 和 UEFI 共用） render_nes.c  render_gba.c
platform/ sdl/main_sdl.c  uefi/main_uefi.c  nes/{main.c,crt0.s,mmc5.cfg,nes.cfg,nes.h}  gba/{main_gba.c,crt0.s,gba.ld,gba.h}
games/    breakout/{game.c,tiles.png,palette.txt,nes.txt,maps/,entities.txt,songs.txt,music/*.fms.txt,fami/*.fms.txt}  platformer/ 同样
editor/   桌面编辑器（图块、调色板、地图、实体、音乐、编译运行）。见 editor/README.md
tools/    build_assets.py png2chr.py png2gba.py gbafix.py map2c.py mappack.py nes_target.py romusage.py ent2c.py txt2mus.py fms2mus.py songs2fms.py make_sheets.py mkimg.sh uefi_probe.sh uefi_link.sh fceux_test.lua fceux_cam.lua qemu_test.sh
lib/      none.lib（cc65 运行库副本，用于离线编译）
build/<game>/{pc,uefi,nes,gba,gen}/   编译输出
shots/    测试截图
```

## 平台限制（以 NES 为准）
| 项目 | 限制 |
|---|---|
| 屏幕 | 256x240；nametable 仍是 64x30 tile。地图可以比两屏宽，相机移动时按列流进去。滚动寄存器仍是 0..511 |
| 颜色 | 4 组背景调色板 + 4 组精灵调色板，每组 3 色 + 公共背景色。默认按 16x16 属性块上色。`nes.txt` 里 `exattr 1` 时，MMC5 的 ExRAM 改成每个 8x8 一色，只覆盖左边 32 列 |
| 精灵 | 8x8，每帧最多 64 个；NES 上**同一扫描线最多 8 个**，超出的会消失 |
| RAM | 2KB 内部 RAM：$0200 是 OAM，$0300 是 VRAM 队列，$0700 是 C 栈；游戏和引擎变量放在 $0400-$06FF。默认 MMC5 的 DATA+BSS：platformer 513 字节，breakout 514 字节，blocks 414 字节（768 字节里）。另外有 64KB WRAM（8 个 8KB bank，窗口在 $6000）。示例游戏没有把变量放进这段，所以用量行是 `WRAM 0/65536`。长地图不展开进 RAM，碰撞按列从 ROM 里的 RLE 读。脚本虚拟机大约 90 字节，动画 6 个槽大约 18 字节，算在上面的数字里 |
| 音频 | 乐曲模型是 6 个通道：两路 APU 方波、三角波、噪声，再加上 MMC5 的两路扩展方波。没有 DPCM。音效占用 pulse2。示例曲子不用扩展方波，这两路保持静音 |
| VRAM 写入 | 每帧大约 96 字节，超出时引擎会等一帧（掉一帧）；在场景 `init` 里写入不受限制（此时渲染已关闭） |
| ROM | 默认 MMC5（iNES mapper 5，NES 2.0 头）：128KB PRG + 128KB CHR + 64KB PRG-RAM。`make` 打印 `rom nes: mapper 5 PRG n/131072 (%) CHR n/131072 RAM n/768 WRAM n/65536`。本仓库现在是 platformer PRG 28672/131072（21%）、CHR 8192/131072、RAM 513/768、WRAM 0/65536；breakout PRG 19392/131072（14%）、RAM 514/768；blocks PRG 17458/131072（13%）、RAM 414/768。小游戏可以在 `nes.txt` 写 `mapper nrom`，或 `make NES_MAPPER=nrom`，回到 mapper 0 的 32KB PRG + 8KB CHR。NROM 放不下时构建停止，提示里有 `32KB PRG 放不下`。加上脚本之后 NROM 仍能编过：platformer 27794/32768（84%）、breakout 18514/32768（56%）、blocks 16580/32768（50%），CHR 仍是 8192/8192 |
| 数值 | 整数；`fx` 是 12.4 定点数（范围 ±2047 像素）；cc65 的 `int` 是 16 位 |

## 引擎 API 参考（engine/engine.h）
**类型**：`u8 s8 u16 s16`，`fx`（12.4 定点数），`FX(n)` 把整数转成定点数，`FX_INT(v)` 把定点数转回整数。

**背景**
- `gfx_palette(const u8 pal[32])`：设置调色板（NES 颜色编号）。每个游戏的 32 色写在 `palette.txt`，编译后变成 `game_palette`
- `bg_tile(x,y,t)`、`bg_tiles(x,y,ptr,n)`、`bg_fill(x,y,w,h,t)`：写入 tile（会排队，x 范围 0..63）
- `bg_attr(x,y,pal)`：设置 tile (x,y) 所在 16x16 区块的调色板
- `bg_text(x,y,"TEXT")`、`bg_number(x,y,value,digits)`：显示文字和数字（tile 编号就是 ASCII 码）
- `bg_load(map,w,h,attr)`：批量载入一张不超过 64 列的原始地图（**只能在场景 init 里调用**）
- `bg_scroll(x)`：水平滚动。关卡请用 `level_scroll`，它会在滚动的同时把新的一列写进 nametable

**精灵**（每帧画之前会自动清空）
- `spr(x,y,tile,attr)`：attr = 调色板 0..3 | `SPR_FLIPH` | `SPR_FLIPV` | `SPR_BEHIND`，超出屏幕的会被裁掉
- `spr_meta(x,y,def,flip)`：def 格式是 `{dx,dy,tile,attr,..., -128}`
- `spr_text`、`spr_number`：用精灵显示文字，适合做滚动画面上的 HUD

**输入**：`pad_held` / `pad_pressed` / `pad_released` 三个位掩码，按键为 `BTN_UP/DOWN/LEFT/RIGHT/A/B/START/SELECT`

**场景**：`Scene {init, update, draw}`，`scene_go(&scene)` 在下一帧开始时切换。游戏要提供 `game_boot()`（返回第一个场景）和 `game_autopilot()`（PC 测试模式下的自动输入）。

**音频**：四个通道同时出声（方波、方波、三角波、噪声）。`music_play` / `music_stop` / `music_pause` / `music_volume` 播循环乐曲，`sfx(SFX_BLIP|HIT|COIN|JUMP|LOSE|WIN)` 暂时占用第二路方波，结束后那一路乐曲继续。详见下面的「音频」。

**物理**：`aabb(ax,ay,aw,ah,bx,by,bw,bh)`，`tm_bind(map,w,h,flags)`，`tm_flags_at(px,py)`（返回 `TF_SOLID`，地图左右和上方之外都算实心），`rnd()`。全局变量 `frame_count`。

**实体**：`entities.txt` 定义类型，地图末尾的 `entities:` 放实例。生成的表每条 12 字节（类型、x 低/高、y、4 个小端 u16 属性），一张图最多 32 个。`ent_ptr`、`ent_type`、`ent_x`、`ent_y`、`ent_prop(p, n)` 读一条记录，`ent_find` 找第一种类型（找不到返回 255）。引擎不跑实体逻辑，每个游戏自己解释这些数。

**脚本**：`games/<游戏>/scripts.json` 由 `tools/scriptc.py` 编成字节码（`scriptdata.c`）。没有这个文件时生成空表，游戏照常链接。虚拟机在 `engine/script.c`，和 `game.c` 一起跑。`script_emit(事件, 参数)` 启动匹配的脚本，`script_update` 每帧处理等待、计时器、每帧和按键。`script_set` / `script_get` 读写变量（`SCRIPT_GLOBAL` 或 `SCRIPT_LEVEL`）。`script_set_hook` 让积木调用 C 函数。`script_pull` 取回「下一关 / 受伤 / 过关 / 结束 / 跳关 / 切场景」。`script_draw` 在文字还显示时用精灵把 ASCII 画出来。`game.c` 仍可以写物理和特殊规则。

**动画**：`anims.json` 由 `tools/animc.py` 编成 `animdata.c`。`anim_play(槽, id)` 开始一段动画（同一个 id 不会把帧号清掉），`anim_update` 按帧时长前进，`anim_draw` 用 `spr_meta` 画当前元精灵。`anim_for_type` 读实体类型的默认动画，没有时返回 255。一共 6 个槽。

**关卡**：`games/<游戏>/maps/order.txt` 一行一个地图名，顺序就是关卡号。`level_load(n)` 载入第 n 关（从 0 起），`level_count` / `level_current` / `level_cols` / `level_music` / `level_ents` / `level_ent_n` 读当前关。`level_scroll(像素)` 让两屏宽的 nametable 跟着相机走。`tm_flags_at` 在关卡载入后按世界坐标查碰撞，不用把整张图解进 RAM。每关可以在地图第一行写 `music 歌名`，编号是 `songs.txt` 里 `song` 的顺序。地图还可以写 `tileset N`，选择第 N 页 CHR（每页 256 个图块，0 是原来的那一页）。`test_level`（255 表示不用）和 `test_cam`（65535 表示不用）给截图用；SDL 读 `RETRO_LEVEL` 和 `RETRO_CAM`。

**卡带**（游戏代码不用写平台判断；NROM 和没有这块硬件的平台上这些调用是空操作或软件等价）：

- `prg_bank(n)`：把 8KB PRG 窗口切到 CPU `$8000`。`level_load` 会按关卡自己切，关卡压缩数据就放在这个窗口里。代码、音乐和关卡表留在 `$A000`–`$FFFF` 的 24KB 固定区。窗口里的指针只在对应 bank 映射着的时候有效。
- `chr_bank(page)`：切换 8KB 图案表。`level_load` 按该关的 `tileset` 调用。
- `wram_bank(n)` / `wram_banks()` / `wram_page()`：MMC5 上有 8 个 8KB WRAM bank，当前页在 `$6000`。PC、UEFI、GBA 用一块 64KB 模拟。
- `mul8(a, b)`：8 位乘 8 位，得到 16 位。MMC5 用 `$5205`/`$5206`，其它平台用普通乘法。
- `video_split(scanline)`：0 表示关闭。非 0 时，NMI 先把滚动设为 0、名表 0，到这条扫描线 MMC5 的扫描线 IRQ 再恢复游戏相机的滚动。示例游戏不调用它。
- `video_exattr(on)`：打开后用 ExRAM 做每个 8×8 的调色板。`nes.txt` 的 `exattr 1` 会在载入关卡时打开。默认是 0，属性仍是 16×16。

## 音频

乐曲和音效同时播放。模型是 NES APU 的前四个通道，再加上 MMC5 的两路扩展方波，没有 DPCM。游戏代码和 `engine.c` 里没有平台 `#ifdef`，只用整数，每帧（60Hz）走一步。示例曲子只写前四路，扩展方波的音量是 0，听起来和原来一样。

| 通道 | 波形 | 谁在用 |
|---|---|---|
| pulse1 | 方波，占空比 12.5/25/50/75% | 乐曲主旋律 |
| pulse2 | 方波 | 乐曲和声；`sfx()` 临时占用，结束后回到乐曲 |
| triangle | 三角波 | 低音。NES 上没有音量，只有开和关 |
| noise | 15 位 LFSR | 打击乐。`mode 1` 是短模式 |
| pulse3 | MMC5 方波 | 可选的额外旋律。NES 写到 `$5000`。其它平台有音量时用软件混进去 |
| pulse4 | MMC5 方波 | 同上，NES 写到 `$5004` |

音高用 NTSC 的 APU 周期：方波频率是 `1789773/16/(period+1)`，三角波是 `1789773/32/(period+1)`。SDL 用同一组周期去合成，所以和 NES 是同一个调。

**API**（`engine/engine.h`）

- `music_play(MUS_TITLE)`：从头播放。`MUS_*` 由 `songs.txt` 里的 `song` 名字生成。
- `music_stop()`：停掉乐曲。正在响的音效会继续。
- `music_pause(1)` 暂停并保持当前音符，`music_pause(0)` 继续。
- `music_volume(0..15)`：只缩小乐曲。音效不跟着变。默认 12。
- `sfx(SFX_BLIP|HIT|COIN|JUMP|LOSE|WIN)`：和原来的编号一样，占 pulse2，音量比乐曲和声高。

两个示例的标题画面播 `MUS_TITLE`，局内播 `MUS_PLAY`，结束画面停乐，胜利/失败音效盖在最后一拍上。

**songs.txt**

```
song title
tempo 128

pulse1 duty 2 vol 10
  E5 8 G5 8 A5 8 G5 8
  loop
  C5 4 E5 4

pulse2 duty 1 vol 5
  C4 4 E4 4

triangle vol 15
  C3 2 G2 2

noise vol 6 mode 0
  N1 8 N12 8

pulse3 duty 2 vol 8
  E5 8 R 8

pulse4 duty 2 vol 6
  C5 4
```

- `tempo` 是四分音符的 BPM。八分音符正好是它的一半（四分音符帧数会取整，写十六分音符时最好让这个帧数能被 4 整除，例如 tempo 120 → 30 帧，tempo 128 → 28 帧，tempo 150 → 24 帧）。
- 音符：`C4` `C#4` `Bb3`，音域 C1–B7。`R` 或 `-` 是休止。
- 时值：`1` 全音符、`2` 二分、`4` 四分、`8` 八分、`16` 十六分、`32` 三十二分。`8.` 是附点八分。`t12` 表示正好 12 帧。
- `loop` 单独一行：它上面的是前奏，只播一次；下面的反复。不写 `loop` 就整段循环。通道行上写 `once` 则播完就停。
- 噪声只用 `N0`（最高、最尖）到 `N15`（最低）。`mode 1` 切换短 LFSR。
- 六个通道各自循环。总帧数不一样时，`txt2mus.py` 会警告，听起来会慢慢错开。`pulse3` / `pulse4` 也可以写成 `mmc5pulse1` / `mmc5pulse2`。不写这两段时，生成的轨道是空的。
- `duty` 只对方波有意义：0 = 12.5%，1 = 25%，2 = 50%，3 = 75%。`vol` 是 0..15。

`make` 先用 `tools/fms2mus.py` 把 `songs.txt` 和 FamiStudio 文本合成 `build/<游戏>/gen/songs.gen.txt`，再调用 `tools/txt2mus.py` 生成 `music.c` 和 `music.h`（里面有 `MUS_TITLE` 这类宏，以及 `music_lookup()`）。`songs.txt` 里的歌排在前面。

**写一首新曲子**

1. 在 `games/<游戏>/songs.txt` 里加一段 `song mytune`，或者用下面的 FamiStudio 流程。
2. 先写 pulse1 的旋律，再让 pulse2、triangle、noise 的总时值和它相同。
3. `make GAME=<游戏> pc`，用耳机听。想只录声音：`RETRO_WAV=tune.wav RETRO_TEST=/tmp/shot ./build/<游戏>/pc/<游戏>`。
4. 在场景 `init` 里调用 `music_play(MUS_MYTUNE)`。

**用 FamiStudio 写曲子**

FamiStudio 是原生桌面程序（Linux 上用 .NET 启动，也有 Flatpak）。通道对应是：Square1 → pulse1，Square2 → pulse2，Triangle → triangle，Noise → noise，MMC5Square1 → pulse3，MMC5Square2 → pulse4。

在 Ubuntu 上安装官方压缩包：

```sh
sudo apt install dotnet-runtime-8.0
# 从 https://famistudio.org/ 或 GitHub Releases 下载 FamiStudio453-LinuxAMD64.zip（4.5.x）
unzip FamiStudio453-LinuxAMD64.zip -d ~/FamiStudio
cd ~/FamiStudio && dotnet FamiStudio.dll
```

Flatpak 会自己带上依赖：`flatpak install flathub org.famistudio.FamiStudio`。文本格式跨小版本不兼容，打开工程时看 Project 行的 `Version`。这里的示例是 `4.5.3`。

在引擎能播的范围内作曲：

- 只用 Square1、Square2、Triangle、Noise。速度用 FamiStudio 模式，Groove 最好只写一个数（例如 `10`），这样一行就是固定的 NTSC 帧数，导入后时值是准的。两个数的摇摆 groove 会按播放器的垫帧规则展开成帧；一行内部的滑音和音量变化不会。
- FamiTracker 速度也可以。tempo 150、speed 6 是每行 6 帧（NTSC）。标了 PAL 的工程仍按 60Hz 计算，听起来会偏快。
- 方波的占空比和音量来自乐器。音量包络只留下峰值，占空比包络只留下第一个值。同一个通道里混了几种音量或占空比时，留下出现最多的那个，并打印警告。
- 音符、休止、Stop、Release、pattern 的排列和 Loop point 会保留。Release 当成提前停音，不播释音包络。Loop point 是整首歌的，落在某个 pattern 列的开头。`-1` 表示每个通道只播一次。
- 一条音符在引擎里最长 255 帧。更长的会拆成几段相同音高接在一起，波形不会重新触发。

MMC5 的两路方波会导入成 pulse3 / pulse4。不会导入、但也不会让转换失败的内容：DPCM 采样和 DPCM 通道，其它扩展芯片（VRC6、VRC7、FDS、N163、S5B、EPSM），滑音、颤音、琶音、微调音高、音量滑动。音高停在音符本身。`tools/fms2mus.py` 把这些写到标准错误。

导出并编进游戏：

1. File → Export → FamiStudio Text。
2. 保存为 `games/<游戏>/music/歌名.fms.txt`。游戏目录根下的 `*.fms.txt` 也会被捡起来。`fami/` 下面的文件不会。
3. `make GAME=<游戏> pc`。歌曲名字变成 `MUS_名字`（小写，其他字符变成下划线）。重名时会加上 `_2`，并打印警告。
4. 在场景 `init` 里调用 `music_play(MUS_...)`。

`games/breakout/music/sample.fms.txt` 是一首手写的示例，导入后是 `MUS_SAMPLE`（breakout 里排在 `MUS_TITLE`、`MUS_PLAY` 后面，编号 2）。`games/breakout/fami/breakout.fms.txt` 和 `games/platformer/fami/platformer.fms.txt` 是现有曲子导出的起点，用 FamiStudio 打开就能改。改完后导出到 `music/`，不要把这个起点本身放进 `music/`，否则会和 `title` / `play` 重名。重新生成起点：

```sh
python3 tools/songs2fms.py games/breakout/songs.txt games/breakout/fami/breakout.fms.txt
```

PC 上只听某一首、并且游戏里的 `music_play` 都改播它：`RETRO_MUS=2 RETRO_WAV=sample.wav RETRO_FRAMES=160 ./build/breakout/pc/breakout`。`RETRO_FRAMES` 按引擎帧计数。这只影响 SDL 测试，游戏代码不用调用 `music_lock`。

**四个后端**

- NES：每帧写 `$4000`–`$400F`，并打开 `$4015` 的低四位。只有音高的高 3 位变了，或者一个通道从静音变成发声时，才写 `$4003` / `$400B` / `$400F`，避免每帧重置相位发出杂音。pulse3 / pulse4 有音量时才写 `$5000` / `$5004` 并打开 `$5015`，避免空的扩展通道去动 APU 的相位。
- SDL：回调里用同一套周期合成方波（占空比序列）、32 步三角波和噪声 LFSR，混合成 44100Hz 单声道。pulse3 / pulse4 只在音量不为 0 时加进去，所以示例曲子的采样和以前一致。`RETRO_WAV=文件.wav` 时不打开声卡，改为每个引擎帧写 735 个采样。
- UEFI：PC 喇叭（端口 `0x61`，PIT 通道 2 `0x42`）。同时只能响一个音，优先级是 pulse2、pulse1、三角波，这样音效能盖过旋律。噪声和 MMC5 扩展方波不走喇叭。QEMU 需要把 PC speaker 接到音频设备，例如 `-audiodev wav,id=snd,path=uefi.wav -machine pcspk-audiodev=snd`。没有这块设备时喇叭是静音的。
- GBA：DMG 音源的四路，读的是 pulse1、pulse2、三角波和噪声。方波 1、方波 2 的占空比和 NES 一样（12.5/25/50/75%）。三角波写进 wave RAM，音量分成 100/50/25% 三档。噪声用最接近的多项式计数器；NES 的 `duty` 最低位是短模式。只有音高变了或者从静音变成发声时才重新触发，避免每帧咔哒一声。音效仍占方波 2。MMC5 的两路扩展方波在 GBA 上不发声。GBA 方波最低大约 64Hz，比 NES 的最低音稍高，那些音会被夹到最低。最快的噪声（N0）大约偏高 17%。

## 一步一步做一个新游戏
1. `mkdir games/mygame`
2. 画 tile 表 `tiles.png`：宽 128。默认一页高 128，共 256 个 8x8 tile，编号按行排列。MMC5 可以再往下加页，每页 128 像素、256 个图块，最多 16 页（高 2048）。NROM 只接受一页。只能用 4 种灰度：黑=0、85 灰=1、170 灰=2、白=3，分别对应调色板里的颜色编号。字体放在 ASCII 码对应的位置；可以运行 `python3 tools/make_sheets.py breakout games/mygame/tiles.png` 生成一张带字体的起始图。某一关要用后面的页时，在地图第一行写 `tileset N`（从 0 起）。
3. 做地图（可选），放在 `games/mygame/maps/`：
   - `order.txt` 决定关卡顺序，一行一个名字。
   - 文本格式 `maps/level.txt`（高度必须是 30 行，宽度 1..512 列，编辑器里新建时按 32 列对齐）：
     ```
     music play
     legend:
     ; 字符 tile 编号 [pal=N] [solid]
     . 0x20 pal=0
     # 0x80 pal=1 solid
     map:
     ######....
     ```
   - 第一行 `music 歌名` 可以不写。不写时，如果 `songs.txt` 里有 `play`，就用它。
   - 编译时 `tools/mappack.py` 把每一列做成 RLE，生成 `maps.c` 里的 `Level` 表：压缩后的列、列索引、属性、碰撞标志、实体、宽高、音乐编号。编辑器里仍是明文格子。
   - 可选：`entities.txt` 定义类型，地图末尾加 `entities:` 放实例。见上面的「实体」。
   - `map2c.py` 仍能单独看一张不超过 64 列的明文地图，游戏构建走的是 `mappack.py`。
4. 写 `songs.txt`，或者在 `music/` 里放 FamiStudio 文本导出（至少一首循环；`make` 会生成 `music.h`）。格式见上面的「音频」。
5. 写 `game.c`：只 `#include "../../engine/engine.h"`、`"assets.h"` 和 `"music.h"`，实现场景、`game_boot()`、`game_autopilot()`。要背景音乐就在场景 `init` 里调用 `music_play(MUS_...)`。
6. `make GAME=mygame pc`（以及 uefi、img、nes、gba、all）

**保持可移植的规则**：不使用 `#ifdef 平台`、浮点数、malloc、libc；变量声明放在代码块开头（C89）；大的常量数据加 `const`（会放进 ROM）；每帧的背景修改要少（大改动放在场景 init 里做）；HUD 如果要跟着滚动，就用精灵来画。

## 添加一个新平台
1. 帧缓冲类平台：复用 `render_soft.c`。平台层负责：`engine_init()` → 每 1/60 秒调用 `engine_frame(按键位掩码)` → `soft_compose(fb)` → 显示。音频读 `soft_period[4]`、`soft_vol[4]`、`soft_duty[4]`（已经是 NES 定时器数值）。
2. tile 硬件类平台（GB、SMS、PCE…）：照着 `render_nes.c` 实现 `backend.h` 里的函数（`r_init r_palette r_tiles r_column r_attr r_scroll r_bulk_begin/end r_in_bulk r_oam snd_hw`，以及 `r_prg_bank r_chr_bank r_wram_bank r_wram_banks r_wram_page r_mul8 r_split r_exattr r_excol`）。没有对应硬件时，bank 和分屏做成空操作，乘法用软件算。`r_column` 按列写 nametable（NES 上长度字节的最高位表示纵向 +32）。`r_in_bulk` 告诉 `level_load` 现在是不是已经在整屏上传里，避免提前结束。`snd_hw` 收到 6 个 `SndCh`，下标 4 和 5 是 MMC5 扩展方波。
3. 在 Makefile 里加一个 target，把 `engine/engine.c`、`games/$(GAME)/game.c` 和生成的资源编进去。

## 资源流程
`tools/build_assets.py games/<g> build/<g>/gen` 会生成：
- `game.chr`：NES 图案表，ca65 用 `.incbin` 引进来。每一页 8KB（4096 字节图块 + 4096 字节空白；背景和精灵都用图案表 0）。MMC5 的链接脚本再把 CHR 补到 128KB
- `tiles.c`：`chr_tiles[]`，每页 4096 字节图块（不含那 4KB 空白），给软件渲染器用。页号乘 4096 就是这页的起点
- `maps.c` 和 `assets.h`：关卡表（列 RLE、列索引、属性、碰撞标志、实体、音乐编号），以及 `game_palette` 的声明
- `palette.c`：`game_palette[32]`，从 `palette.txt` 来
- `tiles_gba.c`：`gba_tiles[8192]`，同一张图的 GBA 4bpp（每 tile 32 字节，低 nibble 是左边的像素）

所以每个游戏只有一份图形源（`tiles.png`）、一份调色板（`palette.txt`）和 `maps/` 里的关卡，各平台的画面用的是同一套 tile。`make` 会自动运行这一步，也会把 `songs.txt` 和 `music/*.fms.txt` 编成 `music.c`。链接完会打印一行 `rom pc|uefi|gba|nes: ...`。NES 用哪张卡由 `games/<游戏>/nes.txt` 决定，缺文件时按 MMC5。命令行的 `NES_MAPPER=nrom` 或 `NES_MAPPER=mmc5` 盖过这个文件。内部 RAM 超过 768 时 `romusage.py` 以非 0 退出。NROM 的 PRG 超过 32768 或 CHR 超过 8192 时同样退出，提示里有 `32KB PRG 放不下`。ld65 自己报放不下时，Makefile 再打印一句：NROM 是 `错误：NES NROM 的 32KB PRG 放不下。这是 mapper 0，没有升级到 UxROM 或 MMC1。`；MMC5 是固定代码窗口（`$A000`–`$FFFF`，24KB）放不下，关卡数据要放进 8KB 的 PRG 窗口。一关压缩后超过大约 8160 字节时，资源脚本会先报 `8KB PRG 窗口放不下`。

地图文本可以在 `map:` 后面加可选的 `palmap:`，每格一位数字（0–3）。没有这一段时，调色板仍按 legend 里图块的 `pal=` 来，和以前的文件完全一样。同一 16×16 里如果出现两种非 0 调色板，采用先遇到的那个。

再往后可以加 `entities:`。每一行是 `类型 x y 属性=数字`。类型写在 `games/<名字>/entities.txt`：

```
limit 32
type coin id=2 w=8 h=8 pal=1
  label 硬币
  sprite 0 0 0xB0
type enemy id=3 w=8 h=8 pal=2
  label 敌人
  sprite 0 0 0xB8
  prop left 0
  prop right 64
```

`sprite` 是编辑器和预览用的显示（相对坐标、图块、精灵调色板 0–3，颜色 0 透明）。`prop` 最多 4 个，生成进那条记录的 u16 字段。`limit` 是每张地图的上限，不能超过 32。超过上限、未知类型、未知属性，`ent2c.py` 会直接报错停掉。没有 `entities.txt` 的游戏不生成这些表。空的 `entities:` 会生成长度为 0 的计数和一个占位字节。

## 在 Ubuntu 26.04 上安装和编译
```sh
sudo apt install build-essential python3 python3-pil libsdl2-dev gnu-efi mtools dosfstools \
                 qemu-system-x86 ovmf cc65 fceux gcc-arm-none-eabi
# 如果 26.04 上没有 libsdl2-dev，改装 libsdl2-compat-dev（提供同样的 sdl2-config 和头文件）
# 想运行 GBA ROM：sudo apt install mgba-sdl
#   可执行文件是 /usr/games/mgba（不一定在默认 PATH 里）
make GAME=breakout   pc|uefi|img|nes|gba|all
make GAME=platformer pc|uefi|img|nes|gba|all
make games-all       # 两个游戏 × pc/uefi/img/nes（不含 gba）
make clean           # 删除 build/（想完整重新编译时先执行它）
```
编辑器还需要 Qt6。Ubuntu 26.04：

```sh
sudo apt install python3-pyside6 python3-pyside6.qtmultimedia python3-pil python3-numpy
```

没有这些包时：`python3 -m pip install --user PySide6 numpy`（Pillow 用 `python3-pil`）。安装和用法见下一节，细节在 `editor/README.md`。

输出文件：`build/<game>/pc/<game>`、`build/<game>/uefi/BOOTX64.EFI` 和 `<game>.img`、`build/<game>/nes/<game>.nes`、`build/<game>/gba/<game>.gba`

`make all` 会编 pc、uefi、img、nes。某个可选工具链没装时只打印一行 `skip <目标>: ...`，其余目标继续。直接执行 `make uefi`（或 `pc` / `img` / `nes`）时，工具链缺失仍然失败。`gba` 不在 `all` 里。

GBA 不用 devkitARM，也不用 libtonc：Ubuntu 的仓库里没有这两个。工具链是 `gcc-arm-none-eabi`（`-marm -mcpu=arm7tdmi -ffreestanding -nostdlib`），启动代码和链接脚本在 `platform/gba/`。没有这套编译器时，`make all` 里的其他目标照常能编。

卡头由 `tools/gbafix.py` 写入 12 字节标题和补码校验（`0xB2 = 0x96`）。它不写入任天堂 Logo。如果 PATH 里有 devkitARM 的 `gbafix`，Makefile 会改用那个，Logo 会写进去，真机 BIOS 才能过启动画面。mGBA 自带的 BIOS 不检查 Logo，可以直接运行这里编出来的 ROM。

## 图形编辑器

不用命令行也能改图、改地图、改音乐，再编译运行。界面是中文。

```sh
sudo apt install python3-pyside6 python3-pyside6.qtmultimedia python3-pil python3-numpy
make editor-install          # 装到应用程序菜单
python3 editor/retro_editor.py
```

`make editor-install` 把启动器写到 `~/.local/share/applications/`。菜单里的名字是「RetroEngine 编辑器」。也可以 `python3 editor/retro_editor.py games/platformer` 直接打开某个游戏。

打开 `games/<名字>/` 之后：

1. **图块**：画 `tiles.png` 里的 8×8 图块（4 色），可缩放、复制、翻转、撤销。MMC5 可以用「加一页」把图块表加高一页（最多 16 页）。
2. **调色板**：从 NES 的 64 色里点选 32 个颜色，存进 `palette.txt`。
3. **地图**：用真彩色涂格子，选图块和调色板，标实心。「图块页」决定这一关用 CHR 的哪一页。16×16 的属性块会画出来；勾上「统一 16×16 调色板」时，涂一格会把那一块的调色板改成同一个。编译页打开 ExRAM 之后，预览改成 8×8 一格一色，左边 32 列不再画属性冲突框。黄线是屏幕分界。图层可以切到「实体」：左边是类型（用真实精灵画），左键放置，拖动移动，右键或 Delete 删除，下面改坐标和属性。默认吸附 8 像素，取消勾选就是 1 像素。「编辑类型」改 `entities.txt`。预览里也能看到这些精灵。
4. **音乐**：按通道改音符、速度、占空比、音量、循环，在编辑器里试听，也可以导入 FamiStudio 文本。通道列表里有「MMC5 方波 1」和「MMC5 方波 2」。保存进 `songs.txt`。撤销和重做包括改音符、加行、删行、循环、速度和新建/删除曲子。
5. **预览**：按游戏的上色方式看当前地图，实体叠在上面。
6. **代码**：编辑 `game.c`（逻辑仍然是 C，给脚本当宿主，也可以写脚本做不到的事）。
7. **编译**：PC / UEFI / NES / GBA。NES 一行可以选择 MMC5（默认）或 NROM，勾选框是 ExRAM 扩展属性（默认关）。选择写进 `nes.txt`，编译时还会带上 `NES_MAPPER=`。日志里会提示缺哪个 apt 包。「检查依赖」列出还要装什么。运行按钮会启动 PC 程序、fceux、mGBA 或 QEMU。用量行在 MMC5 下带 mapper 号、PRG/131072、CHR/131072、RAM/768 和 WRAM/65536。
8. **脚本**：列表式积木。左边是脚本和事件，中间是积木树（如果 / 否则 / 重复可以套），右边是积木面板和当前积木的参数。下拉框来自这个项目的实体、曲子、关卡、变量和动画。变量分全局和本关，大小标成 u8 或 u16。「检查编译」用中文报错。存成 `scripts.json`。
9. **动画**：元精灵是若干 8×8，带偏移、图块号、属性和翻转。动画是一串帧，每帧有时长，可以循环或只播一次。预览可以缩放、洋葱皮、水平翻转（朝向）。一帧超过 64 个精灵，或同一行超过 8 个，下面会用中文警告。实体类型可以选一个默认动画。存成 `anims.json`。

`make run` 仍然只编译并启动当前游戏的 PC 版。新建游戏可以从空白模板，或复制 breakout / platformer。

## 运行
- PC：`./build/platformer/pc/platformer`
  - 测试模式：`RETRO_TEST=shots/x RETRO_SHOT_A=60 RETRO_SHOT_B=600 ./build/breakout/pc/breakout`
  - 把混合结果写成 WAV（不打开声卡）：`RETRO_WAV=breakout.wav RETRO_TEST=/tmp/br RETRO_SHOT_B=360 ./build/breakout/pc/breakout`
  - 锁定某一首并录固定帧数：`RETRO_MUS=2 RETRO_WAV=sample.wav RETRO_FRAMES=160 ./build/breakout/pc/breakout`
- UEFI：
  ```sh
  qemu-system-x86_64 -m 256 -net none \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=$(cp /usr/share/OVMF/OVMF_VARS_4M.fd /tmp/v.fd; echo /tmp/v.fd) \
    -drive format=raw,file=build/breakout/uefi/breakout.img
  ```
  写入 U 盘（**会清空设备**）：`sudo dd if=build/breakout/uefi/breakout.img of=/dev/sdX bs=4M conv=fsync status=progress`，关闭 Secure Boot，以 UEFI 方式启动。
- NES：`fceux build/platformer/nes/platformer.nes`，也可以用 Mesen（MMC5 的扫描线 IRQ 以 Mesen 为准更稳妥）。默认 ROM 是 NES 2.0、mapper 5、128KB PRG、128KB CHR、64KB WRAM、文件 262160 字节。真机要用支持 MMC5 的烧录卡：EverDrive N8 Pro 支持 MMC5，N8 初代对 MMC5 的支持有限。小游戏用 `make NES_MAPPER=nrom` 得到 mapper 0 的 40KB ROM（16 字节头 + 32KB PRG + 8KB CHR）。
- GBA：`mgba build/breakout/gba/breakout.gba`（或 `/usr/games/mgba`）。主循环每进一次 vblank 走一帧，大约 59.73Hz，引擎仍按 60Hz 计。自动演示 ROM（不读手柄，改喂 `game_autopilot()`）：`make GAME=breakout gba-auto`，输出 `build/breakout/gba/breakout-auto.gba`。
- 自动测试：`tools/qemu_test.sh <game> shots/uefi_<game>`；`RETRO_GAME=<game> RETRO_SHOTS=$PWD/shots/nes_<game> fceux --loadlua tools/fceux_test.lua build/<game>/nes/<game>.nes`（无界面时需要配合 Xvfb）

## 操作
| 手柄 | PC 键盘 | UEFI 键盘 | NES | GBA |
|---|---|---|---|---|
| 方向 | 方向键 / WASD | 方向键 / wasd | 十字键 | 十字键 |
| A（跳跃、发球） | Z / 空格 | 空格 / z | A | A |
| B | X | x | B | B |
| Start | Enter | Enter | Start | Start |
| Select | 右 Shift / Tab | Tab | Select | Select |
| 退出 | Esc | Esc | — | — |

GBA 的 L / R 没有接到引擎。

Breakout：左右移动挡板，A 或 Start 发球。Platformer：左右跑动，A 跳跃（按得越久跳得越高），踩敌人可以把它消灭。收集当前关的全部硬币，或者碰到终点，就进入下一关；最后一关之后是胜利画面。掉进坑里会损失一条命。分数和命数跨关保留。相机跟着玩家。第一关是原来的 64 列地图；后面有一关普通宽度的图，还有一关 256 列（8 屏）的长图。硬币、终点、第 2 关的告示牌和开关写在脚本里：捡硬币加 100 分并播放硬币音效，收齐就下一关；告示牌显示 `HI`，开关显示 `OPEN`、镜头抖一下，并把上方那扇不挡路的门打开。玩家有待机、跑、跳三段动画，敌人有走路动画，用的还是原来的图块。站着不动时，第 1 关和长地图的画面与加动画之前一致。

`games/blocks` 是一个只用脚本做玩法的小例子：按住右就往右走并切换跑步动画，碰到硬币就响一声、硬币消失、显示 `GOT IT`，然后过关。`game.c` 只负责把玩家放进 0 号角色槽并调用脚本。

## 只用积木做一个小游戏

下面这套不用改 C。可以从 `games/blocks` 打开，也可以 **新建游戏**（空白模板会写好空的 `scripts.json` 和 `anims.json`，并带上字体图块）。

1. **动画**页新建两个元精灵。站立用两块：`(0,0)` 图块 `0xA0`，`(0,8)` 图块 `0xA1`。迈步把第二块换成 `0xA2`。再建动画 `idle`（站立，时长 20，循环）和 `run`（站立 6 帧、迈步 6 帧，循环）。实体 `player` 的默认动画选 `idle`。点「检查编译」。一帧如果在同一行叠了 9 块，这里会写「扫描线」。
2. **地图**上放一个 `player` 和一个 `coin`（类型在 `entities.txt`，第 2 关的 platformer 还放了 `sign`、`switch`、`door`）。地面用实心图块铺一行，看起来有地方站。
3. **脚本**页新建「向右走」，事件选「每帧」。加一块「如果」，比较方式选「按住」，按键 `right`。在「那么」里加「移动实体」（角色槽 0，dx = 1）和「切换动画」`run`。在「否则」里加「切换动画」`idle`。
4. 再新建「捡到硬币」，事件选「玩家碰到实体」，实体选 `coin`。按顺序加：播放音效 `coin`、删除实体、显示文字 `GOT IT`（帧数 120）、等待 20、过关。
5. 点「检查编译」。通过时会写出脚本条数和字节数。未知变量、未知音效、两个变量做了小于比较，都会用中文说明。**文件 → 保存**。
6. **编译**页编 PC 或 NES，运行。按住右，人会走到硬币上，文字出现，然后脚本发出过关。

积木还能做这些事：游戏开始、关卡开始、按下按键、碰到图块、碰到另一种实体、计时器、变量变成某个值、进入区域；加分或设置变量、播放音乐、生成实体、跳到某一关或场景、摇镜头、生命减一、游戏结束、重复、随机、调用在 `game.c` 里用 `script_set_hook` 登记的函数。全局变量和本关变量各自最多 8 个。`u8` / `u16` 只是编辑器里的检查，运行时都占 16 位。

## GBA 画面

面板是 240x160，引擎的逻辑画面是 256x240。仿射背景是 8bpp，对不上这套 4 色 tile，所以用 mode 0（普通 4bpp），不缩放。

- 左右各裁掉 8 像素：`BG0HOFS = scroll + 8`。HUD 上靠两边的数字（比如 platformer 最右边的命数）仍在屏幕内。
- 上下用 HBlank 中断切成两段。最上面 16 行永远显示地图的 y = 0..15，Breakout 的 `SCORE` / `LIVES` 不会跟着滚走。剩下 144 行显示 `view_y .. view_y+143`。
- `view_y` 跟着逻辑 y ≥ 24 的精灵走，并夹在 16..96。差得不远时取中点；上下拉开超过 130 像素而且上面还有东西（球打进砖里）时跟着上面，挡板会暂时出画面，球回到下方再把挡板找回来。没有这类精灵时（标题）取 140，三行标题都看得到，装饰用的砖会裁掉一截。
- Platformer 的 HUD 是精灵，画在 y = 8 和 y = 20，不参与取景，钉在屏幕上方。

## 排错

### `objcopy: file format not recognized`

Ubuntu 26.04 的 binutils 2.46（从 2.45 起）里，`objcopy --target efi-app-x86_64` 会把这个名字同时当作输入格式和输出格式。链接出来的 `app.so` 是 ELF，按 EFI 应用去读就会报 `file format not recognized`。`tools/uefi_link.sh` 使用 `--output-target=efi-app-x86_64`。binutils 2.42 和 2.46 都能据此把 ELF 转成 PE32+。

gnu-efi 4.0 的链接脚本把 `.rodata` 做成独立的段（3.0.x 多数版本把它并进 `.data`）。这一段没被拷进镜像时，字符串、乐曲和贴图常量都不会出现在 `BOOTX64.EFI` 里。转换时按 `readelf -S` 里实际存在的段来选，包括 `.rodata`，以及存在时的 `.sbat` / `.sbatlevel`。`.rela.reloc` 不打进镜像，避免重定位做两次。

`tools/uefi_probe.sh` 查找 `elf_x86_64_efi.lds`、`crt0-efi-x86_64.o`、`libefi.a` 和 `efi.h`：先问 `pkg-config gnu-efi`，再查 `/usr/lib`、`/usr/lib/x86_64-linux-gnu`、`/usr/lib64`、`/usr/local/lib`（以及这些目录下的 `gnuefi/`）。gnu-efi 3.0.15 没有 pkg-config 文件，会落到后面的目录搜索。路径不在这些位置时：

```sh
make UEFI_LIBDIRS=/path/to/lib UEFI_INCDIR=/path/to/include/efi GAME=breakout uefi
```

`UEFI_LIBDIRS` 用冒号分隔多个目录。一旦设置，就只在这些目录里找，不再回退到系统路径。`app.so` 缺失、为空或不是 ELF，或者 `BOOTX64.EFI` 缺失、为空或不以 `MZ` 开头，会马上停并打印原因。换一套 objcopy 时可以设 `OBJCOPY=/path/to/objcopy`。

### `make all` 缺工具链

缺的是可选工具时打印 `skip pc`、`skip uefi`、`skip img` 或 `skip nes`，后面的目标继续编。例如没装 cc65 时 NES 被跳过，PC 和 UEFI 照常完成。直接 `make uefi`、`make pc`、`make img`、`make nes` 在工具缺失时失败，并说明该装什么。编译或链接本身失败时，`make all` 会停。

## 已知限制
- UEFI 没有“按键松开”事件：引擎会在按键事件之后把它当作按住几帧（方向键 8 帧），持续按住要靠键盘自动重复。UEFI 只用 PC 喇叭，同一时刻一个音（pulse2 优先，然后 pulse1，然后三角波），噪声听不到。QEMU 要加 `-machine pcspk-audiodev=...` 才能出声。
- 没有 DPCM。音效和乐曲和声共用 pulse2：音效响起时这一路的和声暂时让位，另外三路继续走，音效结束的下一帧和声回到当前音符（乐曲时钟没有停）。FamiStudio 里的音量包络、滑音、颤音、琶音、扩展芯片和 DPCM 导入时会被丢掉（有警告）。摇摆速度按帧展开，PAL 歌曲按 60Hz 播放。超过 255 帧的音符会拆成几段相同音高。
- 三角波在 NES 上没有音量；SDL 会按 `vol` 缩放，UEFI 喇叭只把它当成开或关。
- NES 每条扫描线最多 8 个精灵，背景色块是 16x16；fceux 默认会裁掉画面最上和最下各 8 行（屏幕顶部的 HUD 会被切掉一部分）。
- 软件渲染器的 RGB 调色板和 fceux 的不完全一样，颜色会略有差异。
- 修改背景 tile 不会自动更新碰撞地图（`tm_bind` 绑定的是 ROM 里的地图）。
- 只支持水平滚动。nametable 始终是两屏（64 列）。比这更宽的地图按列流进去：世界第 c 列画在 nametable 的 `c & 63`，滚动值是 `相机 & 511`。玩家大约每 5 帧走出新的一列。一列是 30 个 tile 加 8 个属性字节，排队大约 65 字节，在每帧约 96 字节的 vblank 预算里。PC、UEFI 和 GBA 用同一套窗口。竖直方向仍是 30 行。格式上限 512 列。`fx` 是 12.4 有符号数，实用上玩家坐标到 2047 像素，所以示例长关是 256 列（2048 像素）。滚动场景的 HUD 默认用精灵来画。NES 上可以再调用 `video_split` 把名表滚动 0 钉在扫描线以上，见上面的卡带 API。GBA 额外把地图最上面两行钉在屏幕顶部，见上面的「GBA 画面」。
- GBA 不写入任天堂 Logo，真机原装 BIOS 会停在启动画面；模拟器和烧录卡上自带的 BIOS 替换一般能过。噪声音高是近似值。L/R 未使用。
- 实体表只负责摆放和属性。Platformer 读玩家起点、全部硬币、终点，以及靠近相机的敌人（最多 4 个槽，用 `left`/`right` 巡逻）。离开相机一段距离后槽会空出来，后面的敌人再进来。Breakout 的挡板位置来自 `paddle`，球的待机位置是相对挡板的有符号 8 位偏移（默认 +12, −8）。标题画面上的装饰精灵仍写在 `game.c` 里。y 只到 255。一张图最多 32 个实体、每种类型最多 4 个属性。
- 列压缩是按列的 RLE，不是 16×16 metatile。一列固定 30 字节：`0nnnnnnn` 后面跟 n 个原样 tile（n 为 1..127），`1nnnnnnn` 后面跟一个 tile、重复 n 次（n 为 2..127）。每关另有一张 `u16` 列索引（长度是列数 + 1）指向这块数据。属性字节是编译时算好的，不在运行时重算。碰撞用这条索引走到那一列，再查 256 字节的标志表。RLE 块超过 65535 字节会报错。
- 换关时 `level_load` 会关画面，把可见的 64 列直接写进 PPU。NES 上这一步大约二十帧。流进新列的上传在游戏帧里排队，由 NMI 在 vblank 写完再改滚动。
- 默认 NES 目标是 MMC5。`NES_MAPPER=nrom` 仍是 mapper 0：32KB PRG 放不下就停，错误原文说明这是 mapper 0、没有升级到 UxROM 或 MMC1。MMC5 的关卡数据在 `$8000` 的 8KB 窗口里，一关一个 bank（超过 13 关时再往窗口里拼）。代码和音乐在后面的 24KB。CHR 按 8KB 一页切换，示例游戏只用第 0 页。
- `video_split` 把屏幕上半截钉在滚动 0、名表 0，下半截恢复相机滚动。fceux 2.6.5 里对过：上半截和「整帧滚动 0」一致，下半截和「不开分屏」一致。上半截显示的是当前两屏名表在滚动 0 的内容，也就是 64 列窗口的左端，不是另一块 HUD 缓冲。列流会改写这些列，相机走出第一屏之后，滚动 0 不再是关卡开头。示例游戏不调用它，画面和以前一样。
- ExRAM 扩展属性打开后，只有名表最左边 32 列按 8×8 上色（ExRAM 只有一屏，后面的名表会镜像这 32 列）。示例游戏的 `nes.txt` 是 `exattr 0`。编辑器的勾选默认关闭。
- 64KB WRAM 可以换 bank 来用（`wram_bank` / `wram_page`）。示例游戏没有把 BSS 放进 `XRAM` 段，用量是 0。复位时 8 个 bank 都会清零。
- MMC5 扩展方波已经接到乐曲的 pulse3 / pulse4，也能从 FamiStudio 的 MMC5Square1 / MMC5Square2 导入。示例曲子没有写这两路。SDL 只在音量不为 0 时混入；UEFI 喇叭和 GBA 的 DMG 音源不播放它们。这次没有单独录一条带扩展方波的曲子。
- 8×8 乘法在 NES 上走 MMC5 的 `$5205`/`$5206`（fceux 里 12×13=156、200×200=40000），其它平台用 C 的乘法。游戏代码目前没有调用它。
- 地图的调色板按图块记在 legend 里；同一图块要在不同格子用不同调色板时，才写出 `palmap:`。试听用的合成器和 SDL 那一版一致，不是 NES APU 的逐周期模拟。音乐撤销覆盖音符、行、循环、速度和曲目列表，不记录试听播放本身。
- 脚本虚拟机同时只有 2 个任务。带「等待」的脚本会占住一个槽，占满时新的脚本要等下一帧。每帧脚本如果正停在等待上，这一帧不会再启动一次。「重复」在编译时展开，次数是 1 到 8。两个变量只能比是否相等；和常数可以比等于、不等于、小于、大于。变量条件只看低 8 位，并且只在变成相等的那一帧启动一次。游戏里显示的文字是 ASCII，中文只在编辑器里。上限是 32 个脚本、16 条文字、8+8 个变量、4 个 C 函数、4 个角色槽、6 个动画槽。
- 区域不区分关卡。实体碰到图块、实体碰到实体、计时器、变量条件和进入区域，编辑器和虚拟机都有，`blocks` 和 platformer 的例子没有每种都用上。
- Platformer 的物理、敌人和 HUD 仍在 `game.c`。硬币、终点、告示牌和开关在 `scripts.json`。没有对应脚本时，硬币和终点仍走原来的 C。门是实体，不是图块：`door` 为 0 时挡住它所在的 8×16，设成 1 就消失。第 2 关的门在起点上方，不挡去终点的路。告示牌显示 `HI`，开关显示 `OPEN` 并摇镜头。
- 玩家待机、跑、跳用原来的 `0xA0` / `0xA1` / `0xA2`。站立时第 1 关和长地图与加动画之前的画面一致。跑步两帧各 8 帧，和以前「走动时每 8 帧换一次腿」接近，相位可能差一两帧。敌人走路是同一张 `0xB8` 水平翻转，从它出现时开始计时，不再跟全局帧号。第 1 关帧 90 的敌人在屏幕外，所以那张对照图看不出这个差别。CHR 没有加新图块，NROM 的 8KB 图案表仍然满满一页、可以编过。
- NES 的 cc65 用 `-Ors`（优化，但不把小函数内联进调用处）。`-Oirs` 会把脚本虚拟机胀过 MMC5 固定代码窗口（`$A000`–`$FFFF`，24KB）。NROM 的 32KB 在这三个游戏上仍放得下。
