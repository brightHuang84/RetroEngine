/* Software renderer emulating the NES PPU model (2 nametables 64x30, attributes,
   64 sprites with flip). No libc/malloc: used by SDL and UEFI. */
#include "render_soft.h"
extern const u8 chr_tiles[];                 /* generated per game by tools/png2chr.py; one page is 4096 bytes */
static u8 nt[BG_H][BG_W];
static u8 at[2][64];
static u8 pal[32];
static u8 oam[256];
static u16 scroll;
static u8 chr_page, ex_on;
static u8 ex_pal[30][32];
static u8 wram_mem[8 * 8192];
static u8 wram_cur;
volatile u16 soft_period[6]; volatile u8 soft_vol[6]; volatile u8 soft_duty[6];
static const uint32_t nes_rgb[64] = {
 0x545454,0x001E74,0x081090,0x300088,0x440064,0x5C0030,0x540400,0x3C1800,0x202A00,0x083A00,0x004000,0x003C00,0x00323C,0,0,0,
 0x989698,0x084CC4,0x3032EC,0x5C1EE4,0x8814B0,0xA01464,0x982220,0x783C00,0x545A00,0x287200,0x087C00,0x007628,0x006678,0,0,0,
 0xECEEEC,0x4C9AEC,0x787CEC,0xB062EC,0xE454EC,0xEC58B4,0xEC6A64,0xD48820,0xA0AA00,0x74C400,0x4CD020,0x38CC6C,0x38B4CC,0x3C3C3C,0,0,
 0xECEEEC,0xA8CCEC,0xBCBCEC,0xD4B2EC,0xECAEEC,0xECAED4,0xECB4B0,0xE4C490,0xCCD278,0xB4DE78,0xA8E290,0x98E2B4,0xA0D6E4,0xA0A2A0,0,0 };
void r_init(void){ int x, y; for(y = 0; y < BG_H; y++) for(x = 0; x < BG_W; x++) nt[y][x] = ' '; for(x = 0; x < 256; x++) oam[x] = 0xF0; }
void r_palette(const u8 *p){ int i; for(i = 0; i < 32; i++) pal[i] = p[i] & 63; }
void r_tiles(u8 x, u8 y, const u8 *t, u8 n){ while(n--){ if(x < BG_W && y < BG_H) nt[y][x] = *t; x++; t++; } }
void r_column(u8 x, const u8 *t, u8 rows){
  u8 y;
  if(x >= BG_W) return;
  for(y = 0; y < rows && y < BG_H; y++) nt[y][x] = t[y];
}
void r_attr(u8 page, u8 idx, u8 v){ at[page & 1][idx & 63] = v; }
void r_scroll(u16 x){ scroll = x & 511; }
void r_bulk_begin(void){}
void r_bulk_end(void){}
u8 r_in_bulk(void){ return 0; }
u8 *r_oam(void){ return oam; }
void r_prg_bank(u8 bank){ (void)bank; }
void r_chr_bank(u8 page){ chr_page = page; }
void r_wram_bank(u8 bank){ wram_cur = (u8)(bank & 7); }
u8 r_wram_banks(void){ return 8; }
u8 *r_wram_page(void){ return wram_mem + (unsigned)wram_cur * 8192u; }
u16 r_mul8(u8 a, u8 b){ return (u16)((u16)a * (u16)b); }
void r_split(u8 line){ (void)line; }
void r_exattr(u8 on){ ex_on = on ? 1 : 0; }
void r_excol(u8 x, const u8 *src, u8 rows, u8 chr_bits){
  u8 y;
  (void)chr_bits;
  if(!src || x >= 32) return;
  for(y = 0; y < rows && y < 30; y++) ex_pal[y][x] = (u8)(src[(u16)y * 32] & 3);
}
void snd_hw(const SndCh *ch){
  u8 i;
  for(i = 0; i < 6; i++){ soft_period[i] = ch[i].period; soft_vol[i] = ch[i].vol; soft_duty[i] = ch[i].duty; }
}

static int px_of(u8 tile, int r, int c){
  const u8 *t = &chr_tiles[(unsigned)chr_page * 4096u + (unsigned)tile * 16u];
  return ((t[r] >> (7 - c)) & 1) | (((t[r + 8] >> (7 - c)) & 1) << 1);
}
void soft_compose(uint32_t *fb){
  int x, y, i;
  for(y = 0; y < SCREEN_H; y++){
    int ty = y >> 3, r = y & 7;
    for(x = 0; x < SCREEN_W; x++){
      int wx = (x + scroll) & 511, tx = wx >> 3, pg = tx >> 5, lx = tx & 31;
      int a = at[pg][(ty >> 2) * 8 + (lx >> 2)];
      int p = ex_on ? ex_pal[ty][lx] : ((a >> (((ty & 2) ? 4 : 0) + ((lx & 2) ? 2 : 0))) & 3);
      int v = px_of(nt[ty][tx], r, wx & 7);
      fb[y * SCREEN_W + x] = nes_rgb[v ? pal[p * 4 + v] : pal[0]];
    }
  }
  for(i = 63; i >= 0; i--){                   /* lower index = higher priority */
    const u8 *s = &oam[i * 4]; int sy = s[0] + 1, sx = s[3], rr, cc;
    if(s[0] >= 0xEF) continue;
    for(rr = 0; rr < 8; rr++) for(cc = 0; cc < 8; cc++){
      int r = (s[2] & 0x80) ? 7 - rr : rr, c = (s[2] & 0x40) ? 7 - cc : cc;
      int v = px_of(s[1], r, c);
      if(!v || sy + rr >= SCREEN_H || sx + cc >= SCREEN_W) continue;
      fb[(sy + rr) * SCREEN_W + sx + cc] = nes_rgb[pal[16 + (s[2] & 3) * 4 + v]];
    }
  }
}
