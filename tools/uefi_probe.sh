#!/bin/sh
# Locate gnu-efi for the x86_64 UEFI build and print shell assignments.
# stdout is only KEY=value lines. Errors go to stderr and exit 1.
#
# Search order for elf_x86_64_efi.lds, crt0-efi-x86_64.o, libefi.a:
#   $UEFI_LIBDIRS (colon-separated; when set, these are the only lib dirs)
#   otherwise: pkg-config gnu-efi, then the usual system directories.
# Headers: $UEFI_INCDIR, otherwise pkg-config, then /usr/include/efi.
set -eu

die() {
  printf '%s\n' "$*" >&2
  exit 1
}

# Accumulate directories in $dirs (newline-separated, no duplicates).
dirs=

add_dir() {
  d=$1
  [ -n "$d" ] && [ -d "$d" ] || return 0
  case "
$dirs" in
    *"
$d
"*) return 0 ;;
  esac
  dirs="${dirs}${d}
"
}

split_add() {
  old=$IFS
  IFS=:
  # shellcheck disable=SC2086
  for d in $1; do
    add_dir "$d"
  done
  IFS=$old
}

pc_var() {
  # $1 = variable name from a .pc file, with ${prefix} / ${exec_prefix} expanded.
  file=$1
  var=$2
  prefix=$(sed -n 's/^prefix=//p' "$file" | head -n 1)
  exec_prefix=$(sed -n 's/^exec_prefix=//p' "$file" | head -n 1)
  exec_prefix=$(printf '%s' "$exec_prefix" | sed "s|\${prefix}|$prefix|g")
  val=$(sed -n "s/^${var}=//p" "$file" | head -n 1)
  val=$(printf '%s' "$val" | sed "s|\${prefix}|$prefix|g; s|\${exec_prefix}|$exec_prefix|g")
  printf '%s' "$val"
}

if [ -n "${UEFI_LIBDIRS:-}" ]; then
  split_add "$UEFI_LIBDIRS"
else
  if command -v pkg-config >/dev/null 2>&1; then
    libdir=$(pkg-config --variable=libdir gnu-efi 2>/dev/null || true)
    add_dir "$libdir"
  fi
  for pc in /usr/lib/pkgconfig/gnu-efi.pc \
            /usr/lib/x86_64-linux-gnu/pkgconfig/gnu-efi.pc \
            /usr/lib64/pkgconfig/gnu-efi.pc \
            /usr/share/pkgconfig/gnu-efi.pc \
            /usr/local/lib/pkgconfig/gnu-efi.pc \
            /usr/local/lib/x86_64-linux-gnu/pkgconfig/gnu-efi.pc; do
    if [ -f "$pc" ]; then
      add_dir "$(pc_var "$pc" libdir)"
    fi
  done
  add_dir /usr/lib
  add_dir /usr/lib/x86_64-linux-gnu
  add_dir /usr/lib64
  add_dir /usr/local/lib
  add_dir /usr/local/lib/x86_64-linux-gnu
  add_dir /usr/lib/gnuefi
fi

# Expand $dirs into a positional list, plus a gnuefi/ subdirectory when present.
set --
old=$IFS
IFS='
'
for d in $dirs; do
  [ -n "$d" ] || continue
  set -- "$@" "$d"
  if [ -d "$d/gnuefi" ]; then
    set -- "$@" "$d/gnuefi"
  fi
done
IFS=$old

if [ "$#" -eq 0 ]; then
  die "gnu-efi: no library directories to search. Install gnu-efi, or set UEFI_LIBDIRS to the directory that contains elf_x86_64_efi.lds, crt0-efi-x86_64.o and libefi.a."
fi

find_file() {
  name=$1
  shift
  for d in "$@"; do
    if [ -f "$d/$name" ]; then
      printf '%s\n' "$d/$name"
      return 0
    fi
  done
  return 1
}

looked="$*"
EFI_LDS=$(find_file elf_x86_64_efi.lds "$@") || \
  die "gnu-efi: elf_x86_64_efi.lds not found (looked in: $looked). Install gnu-efi, or set UEFI_LIBDIRS."
EFI_CRT0=$(find_file crt0-efi-x86_64.o "$@") || \
  die "gnu-efi: crt0-efi-x86_64.o not found (looked in: $looked). Install gnu-efi, or set UEFI_LIBDIRS."
libefi=$(find_file libefi.a "$@") || \
  die "gnu-efi: libefi.a not found (looked in: $looked). Install gnu-efi, or set UEFI_LIBDIRS."
EFI_LIBDIR=$(dirname "$libefi")

if find_file libgnuefi.a "$@" >/dev/null 2>&1; then
  EFI_GNUEFI=-lgnuefi
else
  EFI_GNUEFI=
fi

EFI_INC=
if [ -n "${UEFI_INCDIR:-}" ]; then
  if [ -f "$UEFI_INCDIR/efi.h" ]; then
    EFI_INC=$UEFI_INCDIR
  elif [ -f "$UEFI_INCDIR/efi/efi.h" ]; then
    EFI_INC=$UEFI_INCDIR/efi
  else
    die "gnu-efi: UEFI_INCDIR=$UEFI_INCDIR does not contain efi.h"
  fi
else
  if command -v pkg-config >/dev/null 2>&1; then
    cflags=$(pkg-config --cflags-only-I gnu-efi 2>/dev/null || true)
    for tok in $cflags; do
      case $tok in
        -I*)
          idir=${tok#-I}
          if [ -f "$idir/efi.h" ]; then EFI_INC=$idir; break; fi
          if [ -f "$idir/efi/efi.h" ]; then EFI_INC=$idir/efi; break; fi
          ;;
      esac
    done
  fi
  if [ -z "$EFI_INC" ]; then
    for pc in /usr/lib/pkgconfig/gnu-efi.pc \
              /usr/lib/x86_64-linux-gnu/pkgconfig/gnu-efi.pc \
              /usr/lib64/pkgconfig/gnu-efi.pc \
              /usr/share/pkgconfig/gnu-efi.pc; do
      if [ -f "$pc" ]; then
        includedir=$(pc_var "$pc" includedir)
        cflags=$(sed -n 's/^Cflags:[[:space:]]*//p' "$pc" | head -n 1)
        cflags=$(printf '%s' "$cflags" | sed "s|\${includedir}|$includedir|g; s|\${prefix}|$(pc_var "$pc" prefix)|g")
        for tok in $cflags; do
          case $tok in
            -I*)
              idir=${tok#-I}
              if [ -f "$idir/efi.h" ]; then EFI_INC=$idir; break; fi
              if [ -f "$idir/efi/efi.h" ]; then EFI_INC=$idir/efi; break; fi
              ;;
          esac
        done
      fi
      [ -n "$EFI_INC" ] && break
    done
  fi
  if [ -z "$EFI_INC" ]; then
    if [ -f /usr/include/efi/efi.h ]; then
      EFI_INC=/usr/include/efi
    elif [ -f /usr/local/include/efi/efi.h ]; then
      EFI_INC=/usr/local/include/efi
    fi
  fi
fi

[ -n "$EFI_INC" ] || \
  die "gnu-efi: efi.h not found. Install gnu-efi, or set UEFI_INCDIR to the directory that contains efi.h."

if [ -d "$EFI_INC/x86_64" ]; then
  EFI_INC_ARCH=$EFI_INC/x86_64
else
  EFI_INC_ARCH=
fi

# Single-quote so the assignments can be sourced.
q() {
  printf '%s' "$1" | sed "s/'/'\\\\''/g"
}

printf "EFI_LDS='%s'\n" "$(q "$EFI_LDS")"
printf "EFI_CRT0='%s'\n" "$(q "$EFI_CRT0")"
printf "EFI_LIBDIR='%s'\n" "$(q "$EFI_LIBDIR")"
printf "EFI_INC='%s'\n" "$(q "$EFI_INC")"
printf "EFI_INC_ARCH='%s'\n" "$(q "$EFI_INC_ARCH")"
printf "EFI_GNUEFI='%s'\n" "$(q "$EFI_GNUEFI")"
