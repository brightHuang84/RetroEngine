/* NES backend: tile updates go into a VRAM buffer at $0300 that the NMI copies
   during vblank; OAM shadow at $0200 is DMA'd every NMI. */
#include "../engine/backend.h"
#include "../platform/nes/nes.h"
static u8 direct;
#define VRAM_BUDGET 96    /* ~15 CPU cycles per byte; vblank is ~2270 cycles incl. OAM DMA */
static void put(u16 addr, const u8 *d, u8 n){
  u8 i;
  if(direct){ PPUADDR = (u8)(addr >> 8); PPUADDR = (u8)addr; while(n--) PPUDATA = *d++; return; }
  if(vram_len + 3 + n > VRAM_BUDGET) wait_vblank();   /* over budget: lag one frame */
  i = vram_len;
  vram_buf[i++] = (u8)(addr >> 8); vram_buf[i++] = (u8)addr; vram_buf[i++] = n;
  while(n--) vram_buf[i++] = *d++;
  vram_len = i;
}
void r_init(void){ u8 i; for(i = 0; i < 64; i++) ((u8*)0x200)[i << 2] = 0xF0; }
void r_palette(const u8 *p){ put(0x3F00, p, 32); }
void r_tiles(u8 x, u8 y, const u8 *t, u8 n){
  put((u16)((x & 32) ? 0x2400 : 0x2000) + ((u16)y << 5) + (x & 31), t, n);
}
void r_attr(u8 page, u8 idx, u8 v){ put((u16)(page ? 0x27C0 : 0x23C0) + idx, &v, 1); }
void r_scroll(u16 x){ scroll_x = (u8)x; ppu_ctrl = (u8)(0x80 | ((x >> 8) & 1)); }
void r_bulk_begin(void){ wait_vblank(); PPUMASK = 0; PPUCTRL = 0; direct = 1; } /* NMI off: direct writes are not interrupted */
void r_bulk_end(void){ direct = 0; PPUCTRL = ppu_ctrl; wait_vblank(); PPUMASK = 0x1E; }
u8 *r_oam(void){ return (u8*)0x200; }
void snd_hw(u16 period, u8 vol){
  if(!vol){ APU(0x4000) = 0x30; return; }
  APU(0x4015) = 0x01;
  APU(0x4000) = (u8)(0xB0 | vol);   /* duty 50%, length halt, constant volume */
  APU(0x4001) = 0x08;               /* sweep off */
  APU(0x4002) = (u8)period;
  APU(0x4003) = (u8)((period >> 8) & 7);
}
