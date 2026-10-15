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
/* Four hardware channels, already converted to NES timer values:
   [0] pulse1 [1] pulse2: period = timer (freq CPU/16/(p+1)), duty 0..3 (12.5/25/50/75%), vol 0..15
   [2] triangle: period = timer (freq CPU/32/(p+1)), vol 0 = off, else on (NES has no volume)
   [3] noise: period = period index 0..15, duty bit0 = short LFSR mode */
typedef struct SndCh { u16 period; u8 vol; u8 duty; } SndCh;
void snd_hw(const SndCh *ch);
/* engine entry points called by platforms */
void engine_init(void);
void engine_frame(u8 raw_pad);                /* one 1/60 s tick */
#endif
