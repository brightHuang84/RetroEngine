#!/usr/bin/env python3
"""Read games/<game>/nes.txt and print the NES mapper (mmc5 or nrom).

A missing file means MMC5. `make NES_MAPPER=nrom` overrides this script.
"""
import os
import sys


def read(game_dir):
    mapper, exattr = 'mmc5', False
    path = os.path.join(game_dir, 'nes.txt')
    if os.path.exists(path):
        for line in open(path):
            parts = line.split('#', 1)[0].split()
            if len(parts) < 2:
                continue
            if parts[0] == 'mapper' and parts[1] in ('mmc5', 'nrom'):
                mapper = parts[1]
            elif parts[0] == 'exattr':
                exattr = parts[1] not in ('0', 'off', 'false')
    return mapper, exattr


def main(argv):
    if len(argv) < 2:
        sys.exit('usage: nes_target.py games/<game> [--exattr]')
    mapper, exattr = read(argv[1])
    if '--exattr' in argv:
        print(1 if exattr else 0)
    else:
        print(mapper)


if __name__ == '__main__':
    main(sys.argv)
