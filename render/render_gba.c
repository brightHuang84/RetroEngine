/* GBA backend: mode 0, 4bpp, BG0 + OBJ. No platform code in the engine.
   The logical screen is 256x240. The GBA panel is 240x160, and affine BGs are
   8bpp, so this stays on regular tiles and crops instead of scaling.
   Horizontal: HOFS = scroll + 8, dropping 8px on each side.
   Vertical: an HBlank split pins map rows 0..1 (pixels 0..15) on the top 16
   scanlines, so a background HUD such as Breakout's SCORE/LIVES stays put.
   The remaining 144 lines show map y = view_y .. view_y+143. view_y follows
   sprites whose logical y is >= 24 (platformer draws its HUD as sprites at
   y = 8 and y = 20, and those stay pinned). view_y is clamped to 16..96,
   which is the range that still reaches both the brick rows and the paddle
   across successive frames. */
#include "../platform/gba/gba.h"
#include "../engine/backend.h"

extern const u8 gba_tiles[8192];

static u8 nt[30][64];
static u8 at[2][64];
static u8 oam[256];
static u16 hw[2][1024];          /* screenblocks 8 and 9, hardware order */
static u16 scroll_x;
static u16 view_y;
static u8 shown;
volatile u16 gba_vofs_play;

static const u32 nes_rgb[64] = {
 0x545454,0x001E74,0x081090,0x300088,0x440064,0x5C0030,0x540400,0x3C1800,0x202A00,0x083A00,0x004000,0x003C00,0x00323C,0,0,0,
 0x989698,0x084CC4,0x3032EC,0x5C1EE4,0x8814B0,0xA01464,0x982220,0x783C00,0x545A00,0x287200,0x087C00,0x007628,0x006678,0,0,0,
 0xECEEEC,0x4C9AEC,0x787CEC,0xB062EC,0xE454EC,0xEC58B4,0xEC6A64,0xD48820,0xA0AA00,0x74C400,0x4CD020,0x38CC6C,0x38B4CC,0x3C3C3C,0,0,
 0xECEEEC,0xA8CCEC,0xBCBCEC,0xD4B2EC,0xECAEEC,0xECAED4,0xECB4B0,0xE4C490,0xCCD278,0xB4DE78,0xA8E290,0x98E2B4,0xA0D6E4,0xA0A2A0,0,0 };

static u16 bgr555(u32 rgb){
  return (u16)(((rgb >> 19) & 0x1F) | (((rgb >> 11) & 0x1F) << 5) | (((rgb >> 3) & 0x1F) << 10));
}

static void copy32(volatile u32 *d, const u32 *s, u32 n){
  while(n--) *d++ = *s++;
}
static void hw_set(u8 x, u8 y, u8 tile, u8 pal){
  hw[x >> 5][(y << 5) + (x & 31)] = (u16)(tile | ((pal & 3) << 12));
}
static u8 pal_of(u8 x, u8 y){
  u8 page = (u8)(x >> 5), tx = (u8)(x & 31);
  u8 idx = (u8)((y >> 2) * 8 + (tx >> 2));
  u8 sh = (u8)(((y & 2) ? 4 : 0) + ((x & 2) ? 2 : 0));
  return (u8)((at[page][idx] >> sh) & 3);
}
static void poke(u8 x, u8 y){
  if(y < 30 && x < 64) hw_set(x, y, nt[y][x], pal_of(x, y));
}

/* Square: 131072/(2048-x) ~= 1789773/16/(nes+1). Wave: 65536/(2048-x) ~= 1789773/32/(nes+1). */
static u16 gb_square(u16 nes){
  u32 sub = (131072u * ((u32)nes + 1u)) / 111861u;
  if(sub >= 2048u) return 0;
  return (u16)(2048u - sub);
}
static u16 gb_wave(u16 nes){
  u32 sub = (65536u * ((u32)nes + 1u)) / 55930u;
  if(sub >= 2048u) return 0;
  return (u16)(2048u - sub);
}
/* Closest DMG polynomial byte for NES noise periods 0..15. Bit 3 (short mode) is added from duty. */
static const u8 noise_nr43[16] = {
  0x00,0x01,0x02,0x05, 0x15,0x17,0x25,0x26, 0x27,0x35,0x37,0x45, 0x47,0x55,0x65,0x75
};
static u16 prev_period[4];
static u8 prev_vol[4];
static u8 snd_init;

static void sound_init(void){
  static const u16 wave[8] = { 0xCDEF,0x89AB,0x4567,0x0123, 0x3210,0x7654,0xBA98,0xFEDC };
  u8 i;
  *(volatile u16 *)0x04000088 = 0x0200;  /* SOUNDBIAS, normally set by the BIOS */
  REG_SNDCNT_X = 0x0080;                 /* master */
  REG_SNDCNT_H = 0x0002;                 /* DMG at 100% */
  REG_SNDCNT_L = 0x0077;                 /* max volume, channels muted until a note */
  REG_SND1CNT_L = 0x0008;                /* sweep off */
  REG_SND3CNT_L = 0;
  for(i = 0; i < 8; i++) WAVE_RAM[i] = wave[i];
  for(i = 0; i < 4; i++){ prev_period[i] = 0xFFFF; prev_vol[i] = 0; }
  snd_init = 1;
}
static void mix_enable(const SndCh *ch){
  u16 en = 0x0077;
  u8 i;
  for(i = 0; i < 4; i++) if(ch[i].vol) en = (u16)(en | (0x1100 << i));
  REG_SNDCNT_L = en;
}
static void square_out(volatile u16 *cnt, volatile u16 *freq, const SndCh *c, u8 idx){
  u16 rate = gb_square(c->period);
  u16 x = rate;
  *cnt = (u16)(((c->duty & 3) << 6) | ((c->vol & 15) << 12));
  if(c->vol && (!prev_vol[idx] || c->period != prev_period[idx])) x = (u16)(x | 0x8000);
  *freq = x;
  prev_period[idx] = c->period;
  prev_vol[idx] = c->vol;
}

void r_init(void){
  u8 x, y;
  REG_DISPCNT = 0x0080;                  /* forced blank while VRAM is filled */
  copy32(VRAM_BG, (const u32 *)gba_tiles, 2048);
  copy32(VRAM_OBJ, (const u32 *)gba_tiles, 2048);
  for(y = 0; y < 30; y++) for(x = 0; x < 64; x++) nt[y][x] = ' ';
  for(y = 0; y < 2; y++) for(x = 0; x < 64; x++) at[y][x] = 0;
  for(y = 0; y < 32; y++) for(x = 0; x < 64; x++) hw_set(x, y, (u8)(y < 30 ? ' ' : 0), 0);
  for(x = 0; x < 64; x++) oam[x << 2] = 0xF0;
  scroll_x = 0;
  view_y = 16;
  gba_vofs_play = 0;
  shown = 0;
  REG_BG0CNT = 0x4800;                   /* charblock 0, screenblock 8, 512x256, 4bpp */
  REG_BG0HOFS = 8;
  REG_BG0VOFS = 0;
  sound_init();
}
void r_palette(const u8 *p){
  u8 i;
  u16 bg = bgr555(nes_rgb[p[0] & 63]);
  for(i = 0; i < 4; i++){
    PAL_BG[i * 16] = bg;
    PAL_BG[i * 16 + 1] = bgr555(nes_rgb[p[i * 4 + 1] & 63]);
    PAL_BG[i * 16 + 2] = bgr555(nes_rgb[p[i * 4 + 2] & 63]);
    PAL_BG[i * 16 + 3] = bgr555(nes_rgb[p[i * 4 + 3] & 63]);
    PAL_OBJ[i * 16] = 0;
    PAL_OBJ[i * 16 + 1] = bgr555(nes_rgb[p[16 + i * 4 + 1] & 63]);
    PAL_OBJ[i * 16 + 2] = bgr555(nes_rgb[p[16 + i * 4 + 2] & 63]);
    PAL_OBJ[i * 16 + 3] = bgr555(nes_rgb[p[16 + i * 4 + 3] & 63]);
  }
}
void r_tiles(u8 x, u8 y, const u8 *t, u8 n){
  while(n--){
    if(x < 64 && y < 30){ nt[y][x] = *t; poke(x, y); }
    x++; t++;
  }
}
void r_column(u8 x, const u8 *t, u8 rows){
  u8 y;
  if(x >= 64) return;
  for(y = 0; y < rows && y < 30; y++){ nt[y][x] = t[y]; poke(x, y); }
}
void r_attr(u8 page, u8 idx, u8 v){
  u8 tx, ty, x, y;
  page = (u8)(page & 1);
  idx = (u8)(idx & 63);
  at[page][idx] = v;
  ty = (u8)((idx >> 3) << 2);
  tx = (u8)((idx & 7) << 2);
  for(y = ty; y < (u8)(ty + 4) && y < 30; y++)
    for(x = tx; x < (u8)(tx + 4); x++) poke((u8)(x + (page ? 32 : 0)), y);
}
void r_scroll(u16 x){ scroll_x = (u16)(x & 511); }
void r_bulk_begin(void){}
void r_bulk_end(void){}
u8 r_in_bulk(void){ return 0; }
u8 *r_oam(void){ return oam; }

static void pick_view(void){
  int i, n = 0, miny = 240, maxy = 0, focus, y;
  for(i = 0; i < 64; i++){
    u8 yb = oam[i << 2];
    if(yb >= 0xEF) continue;
    y = (int)yb + 1;
    if(y < 24) continue;                 /* HUD sprites stay on the glass */
    if(y < miny) miny = y;
    if(y > maxy) maxy = y;
    n++;
  }
  if(!n) focus = 140;
  else if(maxy - miny <= 130) focus = (miny + maxy) / 2;
  else if(miny < 120) focus = miny + 60;
  else focus = maxy;
  focus -= 72;
  if(focus < 16) focus = 16;
  if(focus > 96) focus = 96;
  view_y = (u16)focus;
  gba_vofs_play = (u16)(view_y - 16);
}

void gba_present(void){
  u32 spr[64 * 2];
  int i;
  pick_view();
  REG_BG0VOFS = 0;                       /* line 0..15: HUD strip; IRQ takes over at line 15 */
  REG_BG0HOFS = (u16)((scroll_x + 8) & 511);
  for(i = 0; i < 64; i++){
    u8 yb = oam[i << 2];
    u8 tile = oam[(i << 2) + 1];
    u8 a = oam[(i << 2) + 2];
    int x = (int)oam[(i << 2) + 3];
    int y, gx, gy;
    u16 a0, a1, a2;
    if(yb >= 0xEF){ spr[i * 2] = 160; spr[i * 2 + 1] = 0; continue; }
    y = (int)yb + 1;
    gx = x - 8;
    if(y < 24) gy = y;
    else gy = y - (int)view_y + 16;
    if(gy < 0 || gy >= 160 || gx <= -8 || gx >= 240){
      spr[i * 2] = 160; spr[i * 2 + 1] = 0; continue;
    }
    a0 = (u16)gy;
    a1 = (u16)(gx & 0x1FF);
    if(a & 0x40) a1 = (u16)(a1 | 0x1000);
    if(a & 0x80) a1 = (u16)(a1 | 0x2000);
    a2 = (u16)(tile | ((a & 3) << 12));
    if(a & 0x20) a2 = (u16)(a2 | (3 << 10));
    spr[i * 2] = (u32)a0 | ((u32)a1 << 16);
    spr[i * 2 + 1] = (u32)a2;
  }
  copy32(MAP_BASE, (const u32 *)hw, 1024);
  copy32(OAM_MEM, spr, 128);
  if(!shown){
    REG_DISPSTAT = 0x0010;               /* HBlank IRQ */
    REG_IE = 0x0002;
    REG_IME = 1;
    REG_DISPCNT = 0x1140;                /* mode 0, 1D OBJ, BG0, OBJ */
    shown = 1;
  }
}

void snd_hw(const SndCh *ch){
  u16 rate, x, vs;
  const SndCh *w = &ch[2], *nz = &ch[3];
  int trig;
  if(!snd_init) sound_init();
  mix_enable(ch);
  square_out(&REG_SND1CNT_H, &REG_SND1CNT_X, &ch[0], 0);
  square_out(&REG_SND2CNT_L, &REG_SND2CNT_H, &ch[1], 1);
  rate = gb_wave(w->period);
  if(w->vol == 0) vs = 0;
  else if(w->vol < 6) vs = 3;
  else if(w->vol < 11) vs = 2;
  else vs = 1;
  REG_SND3CNT_H = (u16)(vs << 13);
  REG_SND3CNT_L = w->vol ? 0x0080 : 0;
  x = rate;
  trig = w->vol && (!prev_vol[2] || w->period != prev_period[2]);
  if(trig) x = (u16)(x | 0x8000);
  REG_SND3CNT_X = x;
  prev_period[2] = w->period;
  prev_vol[2] = w->vol;
  REG_SND4CNT_L = (u16)((nz->vol & 15) << 12);
  x = (u16)(noise_nr43[nz->period & 15] | ((nz->duty & 1) << 3));
  trig = nz->vol && (!prev_vol[3] || nz->period != prev_period[3]);
  if(trig) x = (u16)(x | 0x8000);
  REG_SND4CNT_H = x;
  prev_period[3] = nz->period;
  prev_vol[3] = nz->vol;
}
