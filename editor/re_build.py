"""How the editor talks to make, and which Ubuntu packages supply each tool."""
import os
import shutil

# (command, extra paths, apt package, Chinese description)
TOOLS = (
    ('python3', (), 'python3', '资源脚本'),
    ('gcc', (), 'build-essential', 'PC 编译器'),
    ('sdl2-config', (), 'libsdl2-dev', 'PC 窗口和声音'),
    ('cc65', (), 'cc65', 'NES 编译器'),
    ('ca65', (), 'cc65', 'NES 汇编器'),
    ('ld65', (), 'cc65', 'NES 链接器'),
    ('arm-none-eabi-gcc', (), 'gcc-arm-none-eabi', 'GBA 编译器'),
    ('mcopy', (), 'mtools', 'UEFI 磁盘镜像'),
    ('mkfs.fat', (), 'dosfstools', 'UEFI 磁盘镜像'),
    ('qemu-system-x86_64', (), 'qemu-system-x86', 'UEFI 模拟器'),
    ('fceux', ('/usr/games/fceux',), 'fceux', 'NES 模拟器'),
    ('mgba', ('/usr/games/mgba',), 'mgba-sdl', 'GBA 模拟器'),
)

HINTS = (
    ('sdl2-config not found', '缺少 SDL2。安装：sudo apt install libsdl2-dev'),
    ('cc65, ca65, or ld65 not found', '缺少 cc65。安装：sudo apt install cc65'),
    ('cc65, ca65, and ld65 not found', '缺少 cc65。安装：sudo apt install cc65'),
    ('mcopy or mkfs.fat not found', '缺少 mtools 或 dosfstools。安装：sudo apt install mtools dosfstools'),
    ('mcopy and mkfs.fat not found', '缺少 mtools 或 dosfstools。安装：sudo apt install mtools dosfstools'),
    ('elf_x86_64_efi.lds not found', '缺少 gnu-efi。安装：sudo apt install gnu-efi'),
    ('file format not recognized', 'objcopy 版本不兼容。请使用仓库里的 tools/uefi_link.sh（已用 --output-target）。'),
    ('arm-none-eabi-gcc: not found', '缺少 GBA 工具链。安装：sudo apt install gcc-arm-none-eabi'),
    ('No such file or directory', '有源文件缺失。先确认游戏目录里有 game.c、tiles.png、palette.txt。'),
)


def tool_path(command, extra):
    found = shutil.which(command)
    if found:
        return found
    for path in extra:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return ''


def dependency_rows():
    rows = []
    seen = set()
    for command, extra, package, desc in TOOLS:
        ok = bool(tool_path(command, extra))
        rows.append({'desc': desc, 'command': command, 'package': package, 'ok': ok})
        if not ok:
            seen.add(package)
    ovmf = os.path.isfile('/usr/share/OVMF/OVMF_CODE_4M.fd')
    rows.append({'desc': 'UEFI 固件', 'command': 'OVMF', 'package': 'ovmf', 'ok': ovmf})
    if not ovmf:
        seen.add('ovmf')
    pyside = False
    try:
        import PySide6  # noqa: F401
        pyside = True
    except ImportError:
        pass
    rows.append({'desc': '编辑器界面 PySide6', 'command': 'PySide6', 'package': 'python3-pyside6', 'ok': pyside})
    if not pyside:
        seen.add('python3-pyside6')
    return rows, ' '.join(sorted(seen))


def hints_for(log):
    found = []
    for needle, msg in HINTS:
        if needle in log and msg not in found:
            found.append(msg)
    return found


def pc_binary(repo, game):
    return os.path.join(repo, 'build', game, 'pc', game)


def nes_rom(repo, game):
    return os.path.join(repo, 'build', game, 'nes', game + '.nes')


def gba_rom(repo, game):
    return os.path.join(repo, 'build', game, 'gba', game + '.gba')


def uefi_img(repo, game):
    return os.path.join(repo, 'build', game, 'uefi', game + '.img')


def launch_argv(repo, game, target):
    """Return (argv, error_message). argv is None when the tool or output is missing."""
    if target == 'pc':
        path = pc_binary(repo, game)
        if not os.path.isfile(path):
            return None, '还没有 PC 程序。先点「编译 PC」。'
        return [path], ''
    if target == 'nes':
        path = nes_rom(repo, game)
        exe = tool_path('fceux', ('/usr/games/fceux',))
        if not exe:
            return None, '没有 fceux。安装：sudo apt install fceux'
        if not os.path.isfile(path):
            return None, '还没有 NES ROM。先点「编译 NES」。'
        return [exe, path], ''
    if target == 'gba':
        path = gba_rom(repo, game)
        exe = tool_path('mgba', ('/usr/games/mgba',))
        if not exe:
            return None, '没有 mGBA。安装：sudo apt install mgba-sdl\n程序通常在 /usr/games/mgba。'
        if not os.path.isfile(path):
            return None, '还没有 GBA ROM。先点「编译 GBA」。'
        return [exe, path], ''
    if target == 'uefi':
        img = uefi_img(repo, game)
        exe = tool_path('qemu-system-x86_64', ())
        code = '/usr/share/OVMF/OVMF_CODE_4M.fd'
        var_src = '/usr/share/OVMF/OVMF_VARS_4M.fd'
        if not exe:
            return None, '没有 QEMU。安装：sudo apt install qemu-system-x86'
        if not os.path.isfile(code) or not os.path.isfile(var_src):
            return None, '没有 OVMF 固件。安装：sudo apt install ovmf'
        if not os.path.isfile(img):
            return None, '还没有 UEFI 镜像。先点「编译 UEFI 镜像」。'
        var = '/tmp/retroengine-%s-ovmf.fd' % game
        import shutil
        shutil.copy(var_src, var)
        return [exe, '-m', '256', '-net', 'none',
                '-drive', 'if=pflash,format=raw,readonly=on,file=%s' % code,
                '-drive', 'if=pflash,format=raw,file=%s' % var,
                '-drive', 'format=raw,file=%s' % img], ''
    return None, '未知目标'
