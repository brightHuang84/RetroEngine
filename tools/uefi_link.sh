#!/bin/sh
# usage: uefi_link.sh objdir outfile obj.o ...
# Reads objdir/uefi.env (from uefi_probe.sh), links app.so, and writes a PE32+ EFI image.
# objcopy uses --output-target. binutils >= 2.45 treats --target as both the
# input and the output format, so --target=efi-app-x86_64 rejects the ELF .so
# with "file format not recognized".
set -eu

die() {
  printf '%s\n' "$*" >&2
  exit 1
}

[ "$#" -ge 3 ] || die "usage: uefi_link.sh objdir outfile obj.o ..."

objdir=$1
outfile=$2
shift 2

envfile=$objdir/uefi.env
[ -f "$envfile" ] || die "uefi: missing $envfile (uefi_probe.sh did not run)"
# shellcheck disable=SC1090
. "$envfile"

: "${LD:=ld}"
: "${OBJCOPY:=objcopy}"

for need in EFI_LDS EFI_CRT0 EFI_LIBDIR; do
  eval "val=\${$need:-}"
  [ -n "$val" ] || die "uefi: $envfile does not set $need"
done
[ -f "$EFI_LDS" ] || die "uefi: linker script not found: $EFI_LDS"
[ -f "$EFI_CRT0" ] || die "uefi: crt0 not found: $EFI_CRT0"
[ -f "$EFI_LIBDIR/libefi.a" ] || die "uefi: $EFI_LIBDIR/libefi.a not found"

so=$objdir/app.so
rm -f "$so" "$outfile"

# shellcheck disable=SC2086
"$LD" -nostdlib -znocombreloc -z norelro -shared -Bsymbolic \
  -T "$EFI_LDS" "$EFI_CRT0" "$@" -o "$so" \
  -L"$EFI_LIBDIR" -lefi ${EFI_GNUEFI:-} \
  || die "uefi: link failed ($so was not produced)"

if [ ! -s "$so" ]; then
  die "uefi: link produced no output ($so is missing or empty). Check that crt0 and libefi.a match this gcc."
fi

magic=$(od -An -t x1 -N 4 "$so" | tr -d ' \n')
case $magic in
  7f454c46|7F454C46) ;;
  *) die "uefi: $so is not an ELF file (magic $magic). The gnu-efi linker script or crt0 does not match this ld." ;;
esac

command -v readelf >/dev/null 2>&1 || die "uefi: readelf not found (install binutils); cannot choose objcopy sections"

# Section names from the linked image. A fixed -j list warns or drops data when
# gnu-efi moves .rodata out of .data (4.x) or adds .sbat.
sections=$(readelf -S "$so" | sed -n 's/^[[:space:]]*\[[[:space:]]*[0-9]*\][[:space:]]\+\([^[:space:]]\+\).*/\1/p')
[ -n "$sections" ] || die "uefi: readelf -S produced no section names for $so"

jargs=
seen_text=
for s in $sections; do
  keep=0
  case $s in
    .text|.sdata|.data|.rodata|.dynamic|.dynsym|.dynstr|.rel|.rela|.reloc|.areloc|.plt|.got|.got.plt)
      keep=1 ;;
    .sbat|.sbatlevel|.sbat.*)
      keep=1 ;;
    .rel.reloc|.rela.reloc)
      keep=0 ;;
    .rel.*|.rela.*)
      keep=1 ;;
  esac
  if [ "$keep" -eq 1 ]; then
    jargs="$jargs -j $s"
    [ "$s" = .text ] && seen_text=1
  fi
done

[ -n "$seen_text" ] || die "uefi: $so has no .text section; refusing to build an EFI image"

if ! "$OBJCOPY" $jargs --output-target=efi-app-x86_64 --subsystem=10 "$so" "$outfile"; then
  die "uefi: objcopy failed to write $outfile. Use --output-target=efi-app-x86_64 (binutils 2.45+ makes --target=efi-app-x86_64 the input format as well, and then reports \"file format not recognized\" on the ELF app.so)."
fi

if [ ! -s "$outfile" ]; then
  die "uefi: objcopy wrote no output ($outfile is missing or empty)"
fi

mz=$(od -An -t x1 -N 2 "$outfile" | tr -d ' \n')
case $mz in
  4d5a|4D5A) ;;
  *) die "uefi: $outfile does not start with MZ (magic $mz); objcopy did not produce a PE/COFF EFI application" ;;
esac

printf 'uefi: %s\n' "$outfile"
