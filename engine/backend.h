/* Interface every render/platform backend implements (engine internal). */
#ifndef BACKEND_H
#define BACKEND_H
#include "engine.h"
void r_init(void);
void r_palette(const u8 *pal32);
void r_tiles(u8 x, u8 y, const u8 *t, u8 n);  /* x+n must stay within one 32-wide page */
void r_attr(u8 page, u8 idx, u8 val);         /* attribute byte */
void r_scroll(u16 x);
void r_bulk_begin(void);                      /* scene switch: NES turns rendering off */
void r_bulk_end(void);
u8  *r_oam(void);                             /* 256 bytes OAM in NES format (y-1, tile, attr, x) */
void snd_hw(u16 period, u8 vol);              /* NES pulse period (CPU/16/(p+1) Hz), vol 0..15; 0 = off */
/* engine entry points called by platforms */
void engine_init(void);
void engine_frame(u8 raw_pad);                /* one 1/60 s tick */
#endif
