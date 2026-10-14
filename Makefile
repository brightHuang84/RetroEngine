# retro_engine: make GAME=<breakout|platformer> pc|uefi|img|nes|all ; make clean
# Outputs: build/<game>/{pc,uefi,nes}/ . Up-to-date outputs are skipped (make clean to force).
GAME ?= breakout
G    := games/$(GAME)
B    := build/$(GAME)
GEN  := $(B)/gen
ENGINE_SRC := engine/engine.c
GAME_SRC   := $(G)/game.c
HDRS := engine/engine.h engine/backend.h $(GEN)/assets.h
ASSET_SRC := $(G)/tiles.png $(wildcard $(G)/*.txt $(G)/*.csv $(G)/*.legend) tools/png2chr.py tools/map2c.py tools/build_assets.py

all: pc uefi img nes
games-all:
	$(MAKE) GAME=breakout all
	$(MAKE) GAME=platformer all

$(GEN)/assets.h $(GEN)/tiles.c $(GEN)/maps.c $(GEN)/game.chr: $(ASSET_SRC)
	python3 tools/build_assets.py $(G) $(GEN)
assets: $(GEN)/assets.h

# ---------------- PC / SDL2 ----------------
PC_SRC := $(ENGINE_SRC) $(GAME_SRC) render/render_soft.c platform/sdl/main_sdl.c $(GEN)/tiles.c $(GEN)/maps.c
pc: $(B)/pc/$(GAME)
$(B)/pc/$(GAME): $(PC_SRC) $(HDRS) render/render_soft.h
	@mkdir -p $(@D)
	gcc -O2 -std=c99 -Wall -Wextra -I$(GEN) -o $@ $(PC_SRC) `sdl2-config --cflags --libs`

# ---------------- UEFI (gnu-efi) ----------------
EFIINC := /usr/include/efi
EFILIB := /usr/lib
EFI_CFLAGS := -O2 -std=c99 -Wall -ffreestanding -fno-builtin -fno-tree-loop-distribute-patterns \
  -I$(EFIINC) -I$(EFIINC)/x86_64 -I$(GEN) -fpic -fshort-wchar -fno-stack-protector -fno-strict-aliasing \
  -mno-red-zone -maccumulate-outgoing-args -mno-sse -mno-mmx -DEFI_FUNCTION_WRAPPER -DGNU_EFI_USE_MS_ABI
EFI_SRC := $(ENGINE_SRC) $(GAME_SRC) render/render_soft.c platform/uefi/main_uefi.c $(GEN)/tiles.c $(GEN)/maps.c
EFI_OBJ := $(addprefix $(B)/uefi/obj/,$(notdir $(EFI_SRC:.c=.o)))
uefi: $(B)/uefi/BOOTX64.EFI
$(B)/uefi/BOOTX64.EFI: $(EFI_SRC) $(HDRS) render/render_soft.h
	@mkdir -p $(B)/uefi/obj
	for f in $(EFI_SRC); do gcc $(EFI_CFLAGS) -c $$f -o $(B)/uefi/obj/`basename $$f .c`.o || exit 1; done
	ld -nostdlib -znocombreloc -shared -Bsymbolic -T $(EFILIB)/elf_x86_64_efi.lds $(EFILIB)/crt0-efi-x86_64.o \
	  $(EFI_OBJ) -o $(B)/uefi/obj/app.so -L$(EFILIB) -lefi -lgnuefi
	objcopy -j .text -j .rodata -j .sdata -j .data -j .dynamic -j .dynsym -j .rel -j .rela -j .rel.* -j .rela.* -j .reloc \
	  --target efi-app-x86_64 --subsystem=10 $(B)/uefi/obj/app.so $@
img: $(B)/uefi/$(GAME).img
$(B)/uefi/$(GAME).img: $(B)/uefi/BOOTX64.EFI tools/mkimg.sh
	tools/mkimg.sh $< $@

# ---------------- NES (cc65, NROM) ----------------
NO := $(B)/nes/obj
NES_C := $(ENGINE_SRC) $(GAME_SRC) render/render_nes.c platform/nes/main.c $(GEN)/maps.c
nes: $(B)/nes/$(GAME).nes
$(B)/nes/$(GAME).nes: $(NES_C) $(HDRS) platform/nes/nes.h platform/nes/crt0.s platform/nes/nes.cfg $(GEN)/game.chr
	@mkdir -p $(NO)
	for f in $(NES_C); do n=`basename $$f .c`; cc65 -t nes -Oirs -I$(GEN) $$f -o $(NO)/$$n.s || exit 1; \
	  ca65 -t nes $(NO)/$$n.s -o $(NO)/$$n.o || exit 1; done
	ca65 -t nes --bin-include-dir $(GEN) platform/nes/crt0.s -o $(NO)/crt0.o
	ld65 -C platform/nes/nes.cfg -o $@ -m $(B)/nes/$(GAME).map $(NO)/crt0.o \
	  $(addprefix $(NO)/,$(notdir $(NES_C:.c=.o))) lib/none.lib

clean:
	rm -rf build
.PHONY: all games-all assets pc uefi img nes clean
