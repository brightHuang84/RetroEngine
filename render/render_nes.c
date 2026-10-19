/* NES backend: tile updates go into a VRAM buffer at $0300 that the NMI copies
   during vblank; OAM shadow at $0200 is DMA'd every NMI. */
#include "../engine/backend.h"
#include "../platform/nes/nes.h"
/* Non-static so platform/nes/upload.s can see it. */
u8 ppu_direct;
#define VRAM_BUDGET 96    /* ~15 CPU cycles per byte; vblank is ~2270 cycles incl. OAM DMA */
static void put(u16 addr, const u8 *d, u8 n){
  u8 i;
  if(ppu_direct){ PPUADDR = (u8)(addr >> 8); PPUADDR = (u8)addr; while(n--) PPUDATA = *d++; return; }
  if(vram_len + 3 + n > VRAM_BUDGET) wait_vblank();   /* over budget: lag one frame */
  i = vram_len;
  vram_buf[i++] = (u8)(addr >> 8); vram_buf[i++] = (u8)addr; vram_buf[i++] = n;
  while(n--) vram_buf[i++] = *d++;
  vram_len = i;
}
void r_init(void){ u8 i; for(i = 0; i < 64; i++) ((u8*)0x200)[i << 2] = 0xF0; }
#ifdef MMC5
static void mmc5(u16 addr, u8 v){ *(volatile u8*)addr = v; }
void r_prg_bank(u8 bank){ if(bank > 12) bank = 12; mmc5(0x5114, (u8)(0x80 | bank)); }
void r_chr_bank(u8 page){ mmc5(0x5127, page); }
void r_wram_bank(u8 bank){ mmc5(0x5113, (u8)(bank & 7)); }
u8 r_wram_banks(void){ return 8; }
u8 *r_wram_page(void){ return (u8*)0x6000; }
u16 r_mul8(u8 a, u8 b){
  mmc5(0x5205, a); mmc5(0x5206, b);
  return (u16)(*(volatile u8*)0x5205) | ((u16)(*(volatile u8*)0x5206) << 8);
}
void r_split(u8 line){
  split_line = line;
  if(!line){ mmc5(0x5204, 0); __asm__("sei"); }
  else __asm__("cli");
}
void r_exattr(u8 on){ ex_on = on ? 1 : 0; mmc5(0x5104, ex_on ? 1 : 0); }
void r_excol(u8 x, const u8 *src, u8 rows, u8 chr_bits){
  volatile u8 *ex; u8 y;
  if(!ex_on || !src || x >= 32) return;
  mmc5(0x5104, 2);                 /* RAM mode so a write during vblank sticks */
  ex = (volatile u8*)0x5C00;
  for(y = 0; y < rows && y < 30; y++)
    ex[(u16)y * 32 + x] = (u8)(((src[(u16)y * 32] & 3) << 6) | (chr_bits & 0x3E));
  mmc5(0x5104, 1);
}
#else
void r_prg_bank(u8 bank){ (void)bank; }
void r_chr_bank(u8 page){ (void)page; }
void r_wram_bank(u8 bank){ (void)bank; }
u8 r_wram_banks(void){ return 0; }
u8 *r_wram_page(void){ return 0; }
u16 r_mul8(u8 a, u8 b){ return (u16)((u16)a * (u16)b); }
void r_split(u8 line){ (void)line; }
void r_exattr(u8 on){ (void)on; }
void r_excol(u8 x, const u8 *src, u8 rows, u8 chr_bits){
  (void)x; (void)src; (void)rows; (void)chr_bits;
}
#endif
void r_palette(const u8 *p){ put(0x3F00, p, 32); }
void r_tiles(u8 x, u8 y, const u8 *t, u8 n){
  put((u16)((x & 32) ? 0x2400 : 0x2000) + ((u16)y << 5) + (x & 31), t, n);
}
/* r_column and r_attr are in platform/nes/upload.s. The C versions compiled
   to a stack-heavy loop and a 64-column load missed vblank for about a second. */
void r_scroll(u16 x){ scroll_x = (u8)x; ppu_ctrl = (u8)(0x80 | ((x >> 8) & 1)); }
void r_bulk_begin(void){ wait_vblank(); PPUMASK = 0; PPUCTRL = 0; ppu_direct = 1; } /* NMI off: direct writes are not interrupted */
void r_bulk_end(void){ ppu_direct = 0; PPUCTRL = ppu_ctrl; wait_vblank(); PPUMASK = 0x1E; }
u8 r_in_bulk(void){ return ppu_direct; }
u8 *r_oam(void){ return (u8*)0x200; }
/* Write $4003/$400B/$400F only when the timer high byte changes or a note starts.
   Those registers restart the sequencer and would buzz if written every frame. */
static u16 apu_period[4];
static u8 apu_vol[4], apu_init;
#ifdef MMC5
static u16 mmc_period[2];
static u8 mmc_vol[2], mmc_on;
static void mmc_pulse(u16 reg, const SndCh *c, u8 idx){
  APU(reg) = (u8)(((c->duty & 3) << 6) | 0x30 | (c->vol & 15));
  APU((u16)(reg + 2)) = (u8)c->period;
  if(!mmc_vol[idx] && c->vol) APU((u16)(reg + 3)) = (u8)((c->period >> 8) & 7);
  else if(c->vol && ((c->period ^ mmc_period[idx]) & 0x700)) APU((u16)(reg + 3)) = (u8)((c->period >> 8) & 7);
  mmc_period[idx] = c->period; mmc_vol[idx] = c->vol;
}
#endif
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
#ifdef MMC5
  /* Expansion pulses stay silent until a song actually uses them. */
  if(ch[4].vol || ch[5].vol || mmc_on){
    if(!mmc_on){ APU(0x5015) = 0x03; mmc_on = 1; }
    mmc_pulse(0x5000, &ch[4], 0);
    mmc_pulse(0x5004, &ch[5], 1);
  }
#endif
}
