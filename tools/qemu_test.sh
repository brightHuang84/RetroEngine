#!/bin/sh
# usage: qemu_test.sh <game> <out_prefix>  - boots build/<game>/uefi/<game>.img in QEMU+OVMF headless,
# sends keys via the monitor and saves <prefix>_a.png (title) and <prefix>_b.png (gameplay)
G=$1; P=$2
cp /usr/share/OVMF/OVMF_VARS_4M.fd /tmp/vars_$G.fd
{
  sleep 20; echo "screendump /tmp/${G}_a.ppm"
  echo "sendkey ret"; sleep 2
  if [ "$G" = breakout ]; then
    echo "sendkey spc"; sleep 1
    i=0; while [ $i -lt 40 ]; do echo "sendkey left"; sleep 0.1; i=$((i+1)); done
    sleep 3
  else
    i=0; while [ $i -lt 60 ]; do echo "sendkey right"; [ $((i % 12)) -eq 6 ] && echo "sendkey spc"; sleep 0.08; i=$((i+1)); done
  fi
  echo "screendump /tmp/${G}_b.ppm"; sleep 1; echo quit
} | timeout 90 qemu-system-x86_64 -m 256 -net none -display none -monitor stdio \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
  -drive if=pflash,format=raw,file=/tmp/vars_$G.fd -drive format=raw,file=build/$G/uefi/$G.img >/dev/null 2>&1
convert /tmp/${G}_a.ppm ${P}_a.png && convert /tmp/${G}_b.ppm ${P}_b.png
