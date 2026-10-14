/* retro_engine core: shared by all platforms, no platform #ifdefs. */
#include "backend.h"

u8 pad_held, pad_pressed, pad_released, frame_count;
static const Scene *cur, *next;
static u8 attr[2][64];
static u8 *oam;
static u8 nspr;
static const u8 *tm_map, *tm_flags;
static u8 tm_w, tm_h;
static u16 seed = 0x1234;
static char numbuf[6];

/* ---- background ---- */
void gfx_palette(const u8 *p){ r_palette(p); }
void bg_tiles(u8 x, u8 y, const u8 *t, u8 n){
  u8 k;
  while(n){
    k = (u8)(32 - (x & 31)); if(k > n) k = n;   /* split at page boundary */
    r_tiles(x, y, t, k); x += k; t += k; n -= k;
  }
}
void bg_tile(u8 x, u8 y, u8 tile){ r_tiles(x, y, &tile, 1); }
void bg_fill(u8 x, u8 y, u8 w, u8 h, u8 tile){
  static u8 row[32]; u8 i;
  if(w > 32) w = 32;
  for(i = 0; i < w; i++) row[i] = tile;
  while(h--){ bg_tiles(x, y++, row, w); }
}
void bg_attr(u8 x, u8 y, u8 pal){
  u8 pg = (u8)(x >> 5), idx = (u8)((y >> 2) * 8 + ((x & 31) >> 2));
  u8 sh = (u8)(((y & 2) ? 4 : 0) + ((x & 2) ? 2 : 0));
  u8 v = (u8)((attr[pg][idx] & ~(3 << sh)) | ((pal & 3) << sh));
  if(v != attr[pg][idx]){ attr[pg][idx] = v; r_attr(pg, idx, v); }
}
void bg_text(u8 x, u8 y, const char *s){ u8 n = 0; while(s[n]) n++; bg_tiles(x, y, (const u8*)s, n); }
static char *fmt(u16 v, u8 d){ s8 i; if(d > 5) d = 5; numbuf[d] = 0;
  for(i = (s8)(d - 1); i >= 0; i--){ numbuf[i] = (char)('0' + v % 10); v /= 10; } return numbuf; }
void bg_number(u8 x, u8 y, u16 v, u8 d){ bg_text(x, y, fmt(v, d)); }
void bg_load(const u8 *map, u8 w, u8 h, const u8 *at){
  u8 y, i, pg;
  for(y = 0; y < h && y < BG_H; y++) bg_tiles(0, y, map + (u16)y * w, w);
  for(pg = 0; pg < 2; pg++) for(i = 0; i < 64; i++){
    attr[pg][i] = (at && (u8)(pg * 32) < w) ? at[pg * 64 + i] : 0;
    r_attr(pg, i, attr[pg][i]);
  }
}
void bg_scroll(u16 x){ r_scroll(x & 511); }

/* ---- sprites ---- */
u8 spr(s16 x, s16 y, u8 tile, u8 a){
  u8 *p;
  if(nspr >= MAX_SPRITES || x < 0 || x > 255 || y < 0 || y > 231) return 0;
  p = oam + (nspr << 2); p[0] = (u8)(y - 1); p[1] = tile; p[2] = a; p[3] = (u8)x; ++nspr;
  return 1;
}
void spr_meta(s16 x, s16 y, const s8 *m, u8 flip){
  while(m[0] != -128){
    if(flip) spr(x + 8 - 8 - m[0], y + m[1], (u8)m[2], (u8)(m[3] ^ SPR_FLIPH));
    else     spr(x + m[0], y + m[1], (u8)m[2], (u8)m[3]);
    m += 4;
  }
}
void spr_text(s16 x, s16 y, const char *s, u8 a){ while(*s){ if(*s != ' ') spr(x, y, (u8)*s, a); x += 8; s++; } }
void spr_number(s16 x, s16 y, u16 v, u8 d, u8 a){ spr_text(x, y, fmt(v, d), a); }

/* ---- scenes ---- */
void scene_go(const Scene *s){ next = s; }

/* ---- sound: tiny sequencer, one pulse channel ---- */
static const u16 sfx_data[] = {   /* (period, frames) pairs, 0 terminated; index table below */
  0,
  0x0FD, 3, 0,                          /* BLIP */
  0x1FC, 2, 0x17C, 3, 0,                /* HIT  */
  0x0D5, 4, 0x09F, 8, 0,                /* COIN */
  0x2A0, 2, 0x1C0, 2, 0x150, 3, 0,      /* JUMP */
  0x350, 8, 0x470, 8, 0x5F0, 14, 0,     /* LOSE */
  0x1AB, 6, 0x153, 6, 0x11D, 6, 0x0D5, 16, 0 /* WIN */
};
static const u8 sfx_start[] = { 0, 1, 4, 9, 14, 21, 28 };
static u8 sfx_pos, sfx_timer;
void sfx(u8 id){ if(id && id <= SFX_WIN){ sfx_pos = sfx_start[id]; sfx_timer = 0; } }
static void sfx_tick(void){
  if(!sfx_pos) return;
  if(sfx_timer){ if(--sfx_timer) return; }
  if(sfx_data[sfx_pos] == 0){ sfx_pos = 0; snd_hw(0, 0); return; }
  snd_hw(sfx_data[sfx_pos], 10); sfx_timer = (u8)sfx_data[sfx_pos + 1]; sfx_pos += 2;
}

/* ---- physics helpers ---- */
u8 aabb(s16 ax, s16 ay, u8 aw, u8 ah, s16 bx, s16 by, u8 bw, u8 bh){
  return (u8)(ax < bx + bw && bx < ax + aw && ay < by + bh && by < ay + ah);
}
void tm_bind(const u8 *map, u8 w, u8 h, const u8 *flags){ tm_map = map; tm_w = w; tm_h = h; tm_flags = flags; }
u8 tm_flags_at(s16 px, s16 py){
  s16 tx, ty;
  if(!tm_map) return 0;
  if(px < 0 || py < 0) return TF_SOLID;
  tx = px >> 3; ty = py >> 3;
  if(tx >= tm_w) return TF_SOLID;
  if(ty >= tm_h) return 0;
  return tm_flags[tm_map[(u16)ty * tm_w + tx]];
}
u16 rnd(void){ seed ^= seed << 7; seed ^= seed >> 9; seed ^= seed << 8; return seed; }

/* ---- main loop ---- */
void engine_init(void){ r_init(); oam = r_oam(); next = game_boot(); }
void engine_frame(u8 raw){
  u8 i;
  pad_pressed = (u8)(raw & ~pad_held); pad_released = (u8)(pad_held & ~raw); pad_held = raw;
  if(next){
    cur = next; next = 0;
    r_bulk_begin();
    for(i = 0; i < 64; i++){ attr[0][i] = attr[1][i] = 0; }
    tm_map = 0; r_scroll(0);
    cur->init();
    r_bulk_end();
    pad_pressed = 0;
  }
  cur->update();
  nspr = 0;
  cur->draw();
  for(i = nspr; i < MAX_SPRITES; i++) oam[i << 2] = 0xF0;   /* hide unused */
  sfx_tick();
  ++frame_count; seed += raw;
}
