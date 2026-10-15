# retro_engine: make GAME=<breakout|platformer> pc|uefi|img|nes|gba|all ; make clean
# Outputs: build/<game>/{pc,uefi,nes}/ . Up-to-date outputs are skipped (make clean to force).
GAME ?= breakout
G    := games/$(GAME)
B    := build/$(GAME)
GEN  := $(B)/gen
ENGINE_SRC := engine/engine.c
GAME_SRC   := $(G)/game.c
HDRS := engine/engine.h engine/backend.h $(GEN)/assets.h $(GEN)/music.h
ASSET_SRC := $(G)/tiles.png $(wildcard $(G)/*.txt $(G)/*.csv $(G)/*.legend) tools/png2chr.py tools/png2gba.py tools/map2c.py tools/build_assets.py
MUS_SRC := $(GEN)/music.c

# `all` tries every optional target. A missing toolchain prints "skip <target>"
# and the rest still build. A real compile or link error still stops `all`.
# Invoking pc/uefi/img/nes directly fails with a reason when the tool is absent.
all:
	@$(MAKE) --no-print-directory all-pc
	@$(MAKE) --no-print-directory all-uefi
	@$(MAKE) --no-print-directory all-img
	@$(MAKE) --no-print-directory all-nes
games-all:
	$(MAKE) GAME=breakout all
	$(MAKE) GAME=platformer all

all-pc:
	@if command -v sdl2-config >/dev/null 2>&1; then $(MAKE) --no-print-directory pc; \
	else echo "skip pc: sdl2-config not found (install libsdl2-dev)"; fi
all-uefi:
	@mkdir -p $(B)
	@if tools/uefi_probe.sh >/dev/null 2>$(B)/uefi-probe.err; then \
	  rm -f $(B)/uefi-probe.err; \
	  $(MAKE) --no-print-directory uefi; \
	else \
	  printf 'skip uefi:'; \
	  while IFS= read -r line; do printf ' %s' "$$line"; done < $(B)/uefi-probe.err; \
	  printf '\n'; \
	  rm -f $(B)/uefi-probe.err; \
	  true; \
	fi
all-img:
	@mkdir -p $(B)
	@if ! tools/uefi_probe.sh >/dev/null 2>$(B)/uefi-probe.err; then \
	  printf 'skip img:'; \
	  while IFS= read -r line; do printf ' %s' "$$line"; done < $(B)/uefi-probe.err; \
	  printf '\n'; \
	  rm -f $(B)/uefi-probe.err; \
	  true; \
	elif ! command -v mcopy >/dev/null 2>&1 || ! command -v mkfs.fat >/dev/null 2>&1; then \
	  echo "skip img: mcopy or mkfs.fat not found (install mtools and dosfstools)"; \
	else rm -f $(B)/uefi-probe.err; $(MAKE) --no-print-directory img; fi
all-nes:
	@if command -v cc65 >/dev/null 2>&1 && command -v ca65 >/dev/null 2>&1 && command -v ld65 >/dev/null 2>&1; then \
	  $(MAKE) --no-print-directory nes; \
	else echo "skip nes: cc65, ca65, or ld65 not found (install cc65)"; fi

$(GEN)/assets.h $(GEN)/tiles.c $(GEN)/tiles_gba.c $(GEN)/maps.c $(GEN)/game.chr: $(ASSET_SRC)
	python3 tools/build_assets.py $(G) $(GEN)
assets: $(GEN)/assets.h

$(GEN)/music.c $(GEN)/music.h: $(G)/songs.txt tools/txt2mus.py
	@mkdir -p $(GEN)
	python3 tools/txt2mus.py $(G)/songs.txt $(GEN)

# ---------------- PC / SDL2 ----------------
PC_SRC := $(ENGINE_SRC) $(GAME_SRC) render/render_soft.c platform/sdl/main_sdl.c $(GEN)/tiles.c $(GEN)/maps.c $(MUS_SRC)
pc: $(B)/pc/$(GAME)
$(B)/pc/$(GAME): $(PC_SRC) $(HDRS) render/render_soft.h
	@command -v sdl2-config >/dev/null 2>&1 || { echo "pc: sdl2-config not found (install libsdl2-dev)"; exit 1; }
	@mkdir -p $(@D)
	gcc -O2 -std=c99 -Wall -Wextra -I. -I$(GEN) -o $@ $(PC_SRC) `sdl2-config --cflags --libs`

# ---------------- UEFI (gnu-efi) ----------------
# Paths come from tools/uefi_probe.sh (pkg-config gnu-efi, then /usr/lib and
# the multiarch dirs). tools/uefi_link.sh uses objcopy --output-target and
# copies the sections that are actually present (.rodata, .sbat, ...).
# Override with UEFI_LIBDIRS=/path (colon-separated) and UEFI_INCDIR=/path.
EFI_CFLAGS := -O2 -std=c99 -Wall -ffreestanding -fno-builtin -fno-tree-loop-distribute-patterns \
  -I. -I$(GEN) -fpic -fshort-wchar -fno-stack-protector -fno-strict-aliasing \
  -mno-red-zone -maccumulate-outgoing-args -mno-sse -mno-mmx -DEFI_FUNCTION_WRAPPER -DGNU_EFI_USE_MS_ABI
EFI_SRC := $(ENGINE_SRC) $(GAME_SRC) render/render_soft.c platform/uefi/main_uefi.c $(GEN)/tiles.c $(GEN)/maps.c $(MUS_SRC)
EFI_OBJ := $(addprefix $(B)/uefi/obj/,$(notdir $(EFI_SRC:.c=.o)))
uefi: $(B)/uefi/BOOTX64.EFI
$(B)/uefi/BOOTX64.EFI: $(EFI_SRC) $(HDRS) render/render_soft.h tools/uefi_probe.sh tools/uefi_link.sh
	@mkdir -p $(B)/uefi/obj
	tools/uefi_probe.sh > $(B)/uefi/obj/uefi.env
	. $(B)/uefi/obj/uefi.env && \
	for f in $(EFI_SRC); do \
	  gcc $(EFI_CFLAGS) -I$$EFI_INC $${EFI_INC_ARCH:+-I$$EFI_INC_ARCH} -c $$f -o $(B)/uefi/obj/`basename $$f .c`.o || exit 1; \
	done && \
	tools/uefi_link.sh $(B)/uefi/obj $@ $(EFI_OBJ)
img: $(B)/uefi/$(GAME).img
$(B)/uefi/$(GAME).img: $(B)/uefi/BOOTX64.EFI tools/mkimg.sh
	@command -v mcopy >/dev/null 2>&1 && command -v mkfs.fat >/dev/null 2>&1 || { echo "img: mcopy and mkfs.fat not found (install mtools and dosfstools)"; exit 1; }
	tools/mkimg.sh $< $@

# ---------------- NES (cc65, NROM) ----------------
NO := $(B)/nes/obj
NES_C := $(ENGINE_SRC) $(GAME_SRC) render/render_nes.c platform/nes/main.c $(GEN)/maps.c $(MUS_SRC)
nes: $(B)/nes/$(GAME).nes
$(B)/nes/$(GAME).nes: $(NES_C) $(HDRS) platform/nes/nes.h platform/nes/crt0.s platform/nes/nes.cfg $(GEN)/game.chr
	@command -v cc65 >/dev/null 2>&1 && command -v ca65 >/dev/null 2>&1 && command -v ld65 >/dev/null 2>&1 || { echo "nes: cc65, ca65, and ld65 not found (install cc65)"; exit 1; }
	@mkdir -p $(NO)
	for f in $(NES_C); do n=`basename $$f .c`; cc65 -t nes -Oirs -I. -I$(GEN) $$f -o $(NO)/$$n.s || exit 1; \
	  ca65 -t nes $(NO)/$$n.s -o $(NO)/$$n.o || exit 1; done
	ca65 -t nes --bin-include-dir $(GEN) platform/nes/crt0.s -o $(NO)/crt0.o
	ld65 -C platform/nes/nes.cfg -o $@ -m $(B)/nes/$(GAME).map $(NO)/crt0.o \
	  $(addprefix $(NO)/,$(notdir $(NES_C:.c=.o))) lib/none.lib

# ---------------- GBA (arm-none-eabi-gcc; not part of `all`) ----------------
# devkitARM/libtonc are not Ubuntu packages. gcc-arm-none-eabi plus platform/gba
# is enough. gbafix from devkitARM is used when it is on PATH; otherwise
# tools/gbafix.py writes the title and complement (no Nintendo logo).
GBA_CFLAGS := -marm -mcpu=arm7tdmi -ffreestanding -fno-builtin -fno-unwind-tables \
  -fno-asynchronous-unwind-tables -O2 -std=c99 -Wall -Wextra -fno-strict-aliasing -I. -I$(GEN)
GBA_SRC := $(ENGINE_SRC) $(GAME_SRC) render/render_gba.c platform/gba/main_gba.c $(GEN)/tiles_gba.c $(GEN)/maps.c $(MUS_SRC)
GBA_DEPS := $(GBA_SRC) $(HDRS) platform/gba/crt0.s platform/gba/gba.ld platform/gba/gba.h tools/gbafix.py

define build_gba
	@mkdir -p $(dir $(1))
	arm-none-eabi-gcc $(GBA_CFLAGS) $(2) -T platform/gba/gba.ld -nostdlib \
	  -o $(1:.gba=.elf) platform/gba/crt0.s $(GBA_SRC) -lgcc -Wl,-Map,$(1:.gba=.map)
	arm-none-eabi-objcopy -O binary $(1:.gba=.elf) $(1)
	@if command -v gbafix >/dev/null 2>&1; then gbafix $(1) -t$(shell printf '%s' $(GAME) | tr a-z A-Z | cut -c1-12); \
	else python3 tools/gbafix.py $(1) $(GAME); fi
endef

gba: $(B)/gba/$(GAME).gba
$(B)/gba/$(GAME).gba: $(GBA_DEPS)
	$(call build_gba,$@,)
gba-auto: $(B)/gba/$(GAME)-auto.gba
$(B)/gba/$(GAME)-auto.gba: $(GBA_DEPS)
	$(call build_gba,$@,-DGBA_AUTOPILOT)

clean:
	rm -rf build
.PHONY: all all-pc all-uefi all-img all-nes games-all assets pc uefi img nes gba gba-auto clean
