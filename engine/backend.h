/* Interface every render/platform backend implements (engine internal). */
#ifndef BACKEND_H
#define BACKEND_H
#include "engine.h"
void r_init(void);
void r_palette(const u8 *pal32);
void r_tiles(u8 x, u8 y, const u8 *t, u8 n);  /* x+n must stay within one 32-wide page */
void r_column(u8 x, const u8 *t, u8 rows);    /* vertical run at nametable x 0..63; rows <= 30 */
void r_attr(u8 page, u8 idx, u8 val);         /* attribute byte */
void r_scroll(u16 x);
void r_bulk_begin(void);                      /* scene switch: NES turns rendering off */
void r_bulk_end(void);
u8   r_in_bulk(void);                         /* nonzero while NES rendering is off */
u8  *r_oam(void);                             /* 256 bytes OAM in NES format (y-1, tile, attr, x) */
/* Mapper services. NROM ignores banking. PC/UEFI/GBA keep one CHR page index
   and an 8-bank WRAM image so game code can call these without #ifdefs. */
void r_prg_bank(u8 bank);                     /* map an 8KB PRG bank at CPU $8000 */
void r_chr_bank(u8 page);                     /* 8KB CHR page (pattern table 0) */
void r_wram_bank(u8 bank);                    /* 8KB WRAM bank at CPU $6000 */
u8   r_wram_banks(void);                      /* 0 on NROM, 8 on MMC5 and on soft/GBA */
u8  *r_wram_page(void);                       /* current 8KB window, or NULL */
u16  r_mul8(u8 a, u8 b);                      /* MMC5 $5205, otherwise a software product */
void r_split(u8 scanline);                    /* 0 disables the fixed-HUD scanline IRQ */
void r_exattr(u8 on);                         /* MMC5 ExRAM per-tile palettes; 0 = 16x16 attrs */
/* src[y * 32] is the palette of this column in a 32-wide row-major table.
   chr_bits is the low 4KB-bank field (level page << 1). No-op unless exattr is on. */
void r_excol(u8 x, const u8 *src, u8 rows, u8 chr_bits);
/* Channels already converted to NES timer values:
   [0] pulse1 [1] pulse2: period = timer (freq CPU/16/(p+1)), duty 0..3, vol 0..15
   [2] triangle: period = timer (freq CPU/32/(p+1)), vol 0 = off, else on
   [3] noise: period = period index 0..15, duty bit0 = short LFSR mode
   [4] [5] MMC5 expansion pulses (same encoding as pulse1). Silent extras stay
   silent: soft mix adds them only when vol != 0, GBA ignores them. */
typedef struct SndCh { u16 period; u8 vol; u8 duty; } SndCh;
void snd_hw(const SndCh *ch);
/* engine entry points called by platforms */
void engine_init(void);
void engine_frame(u8 raw_pad);                /* one 1/60 s tick */
#endif
