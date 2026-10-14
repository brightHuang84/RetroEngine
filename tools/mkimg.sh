#!/bin/sh
# usage: mkimg.sh BOOTX64.EFI out.img  -> 16MB FAT16 image with EFI/BOOT/BOOTX64.EFI (no root needed)
set -e
EFI=$1; IMG=$2
rm -f "$IMG"; dd if=/dev/zero of="$IMG" bs=1M count=16 status=none
/sbin/mkfs.fat -F 16 -n BREAKOUT "$IMG" >/dev/null
mmd -i "$IMG" ::/EFI ::/EFI/BOOT
mcopy -i "$IMG" "$EFI" ::/EFI/BOOT/BOOTX64.EFI
echo "created $IMG"
