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
/* Write $4003/$400B/$400F only when the timer high byte changes or a note starts.
   Those registers restart the sequencer and would buzz if written every frame. */
static u16 apu_period[4];
static u8 apu_vol[4], apu_init;
static void pulse_out(u16 reg, const SndCh *c, u8 idx){
  APU(reg) = (u8)(((c->duty & 3) << 6) | 0x30 | (c->vol & 15));
  APU((u16)(reg + 2)) = (u8)c->period;
  if(!apu_vol[idx] && c->vol) APU((u16)(reg + 3)) = (u8)((c->period >> 8) & 7);
  else if(c->vol && ((c->period ^ apu_period[idx]) & 0x700)) APU((u16)(reg + 3)) = (u8)((c->period >> 8) & 7);
  apu_period[idx] = c->period; apu_vol[idx] = c->vol;
}
void snd_hw(const SndCh *ch){
  if(!apu_init){ APU(0x4015) = 0x0F; APU(0x4001) = 0x08; APU(0x4005) = 0x08; apu_init = 1; }
  pulse_out(0x4000, &ch[0], 0);
  pulse_out(0x4004, &ch[1], 1);
  APU(0x4008) = ch[2].vol ? 0xFF : 0x80;
  APU(0x400A) = (u8)ch[2].period;
  if(ch[2].vol && (!apu_vol[2] || ((ch[2].period ^ apu_period[2]) & 0x700)))
    APU(0x400B) = (u8)((ch[2].period >> 8) & 7);
  apu_period[2] = ch[2].period; apu_vol[2] = ch[2].vol;
  APU(0x400C) = (u8)(0x30 | (ch[3].vol & 15));
  APU(0x400E) = (u8)((ch[3].period & 15) | ((ch[3].duty & 1) << 7));
  if(ch[3].vol && !apu_vol[3]) APU(0x400F) = 0x00;
  apu_period[3] = ch[3].period; apu_vol[3] = ch[3].vol;
}
