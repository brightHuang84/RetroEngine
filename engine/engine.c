/* retro_engine core: shared by all platforms.
   The only platform split is the NES column decoder, which lives in
   platform/nes/upload.s so a 64-column upload does not stall for a second. */
#include "backend.h"

u8 pad_held, pad_pressed, pad_released, frame_count;
static const Scene *cur, *next;
static u8 attr[2][64];
static u8 *oam;
static u8 nspr;
static const u8 *tm_map, *tm_flags;
static u8 tm_w, tm_h;
static u8 lv_on, lv_id;
static u16 lv_right;
#ifdef __NES__
/* upload.s reads these. The column decoder there is a straight 6502 loop. */
const Level *lv;
u8 lv_col[30];
void lv_decode(u16 c);
#else
static const Level *lv;
static u8 lv_col[30];
#endif
u8 test_level = 255;
u16 test_cam = (u16)-1;
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

/* ---- audio: music on 4 APU channels, sfx borrows pulse2 ---- */
/* NTSC pulse timer, index 1 = C1 ... 84 = B7. t = CPU/(16*f)-1, f = 440*2^((midi-69)/12).
   Pulse hardware is 11-bit, so notes below A1 are clamped when written. Triangle keeps
   the full value and halves it, which is the right timer for the same pitch. */
static const u16 note_period[85] = {
  0,
  /* C1 */ 3419,3228,3046,2875,2714,2561,2418,2282,2154,2033,1919,1811,
  /* C2 */ 1709,1613,1523,1437,1356,1280,1208,1140,1076,1016,959,905,
  /* C3 */ 854,806,761,718,678,640,604,570,538,507,479,452,
  /* C4 */ 427,403,380,359,338,319,301,284,268,253,239,225,
  /* C5 */ 213,201,189,179,169,159,150,142,134,126,119,112,
  /* C6 */ 106,100,94,89,84,79,75,70,66,63,59,56,
  /* C7 */ 52,49,47,44,41,39,37,35,33,31,29,27
};
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
static const Track *tr[4];
static u16 mus_pos[4], mus_period[4];
static u8 mus_timer[4], mus_gate[4];
static u8 mus_paused, mus_master, mus_lock, mus_lock_id;
static u8 sfx_pos, sfx_left, sfx_on;
static u16 sfx_period;

void sfx(u8 id){
  if(id && id <= SFX_WIN){ sfx_pos = sfx_start[id]; sfx_left = 0; sfx_on = 1; }
}
void music_lock(u8 id){ mus_lock = 1; mus_lock_id = id; }
void music_play(u8 id){
  const Song *s; u8 i;
  if(mus_lock) id = mus_lock_id;
  s = music_lookup(id);
  mus_paused = 0;
  for(i = 0; i < 4; i++){
    tr[i] = (s && s->ch[i]) ? s->ch[i] : 0;
    mus_pos[i] = 0; mus_timer[i] = 0; mus_gate[i] = 0; mus_period[i] = 0;
  }
}
void music_stop(void){
  u8 i;
  for(i = 0; i < 4; i++){ tr[i] = 0; mus_gate[i] = 0; mus_timer[i] = 0; }
}
void music_pause(u8 on){ mus_paused = on ? 1 : 0; }
void music_volume(u8 v){ mus_master = (v > 15) ? 15 : v; }

static void mus_step(u8 i){
  const Track *t; u8 n, d, guard; u16 p, half;
  if(mus_paused) return;
  t = tr[i];
  if(!t || !t->data){ mus_gate[i] = 0; return; }
  if(mus_timer[i]){ mus_timer[i]--; return; }
  guard = 0;
  for(;;){
    if(guard++ > 4){ tr[i] = 0; mus_gate[i] = 0; return; }
    n = t->data[mus_pos[i]];
    if(n == 255){
      if(t->loop != 0xFFFF){ mus_pos[i] = t->loop; continue; }
      tr[i] = 0; mus_gate[i] = 0; return;
    }
    d = t->data[(u16)(mus_pos[i] + 1)];
    mus_pos[i] = (u16)(mus_pos[i] + 2);
    if(n == 0){ mus_gate[i] = 0; mus_period[i] = 0; }
    else if(i == CH_NOISE){ mus_gate[i] = 1; mus_period[i] = (u16)((n - 1) & 15); }
    else {
      p = (n < 85) ? note_period[n] : note_period[84];
      if(i == CH_TRI){ half = (u16)((p + 1) >> 1); p = half ? (u16)(half - 1) : 0; }
      else if(p > 0x7FF) p = 0x7FF;
      mus_gate[i] = 1; mus_period[i] = p;
    }
    if(d < 1) d = 1;
    mus_timer[i] = (u8)(d - 1);
    return;
  }
}
static void sfx_step(void){
  u8 d;
  if(!sfx_on) return;
  if(sfx_left){ sfx_left--; return; }
  if(sfx_data[sfx_pos] == 0){ sfx_on = 0; return; }
  sfx_period = sfx_data[sfx_pos];
  d = (u8)sfx_data[sfx_pos + 1];
  sfx_pos = (u8)(sfx_pos + 2);
  if(d < 1) d = 1;
  sfx_left = (u8)(d - 1);
}
static void audio_tick(void){
  SndCh o[4]; u8 i, v;
  for(i = 0; i < 4; i++){
    mus_step(i);
    v = (tr[i] && mus_gate[i]) ? tr[i]->vol : 0;
    o[i].period = mus_period[i];
    o[i].vol = (u8)(((u16)v * mus_master) / 15);
    o[i].duty = tr[i] ? tr[i]->duty : 2;
  }
  sfx_step();
  if(sfx_on){ o[CH_PULSE2].period = sfx_period; o[CH_PULSE2].vol = 14; o[CH_PULSE2].duty = 2; }
  snd_hw(o);
}

/* ---- physics helpers ---- */
u8 aabb(s16 ax, s16 ay, u8 aw, u8 ah, s16 bx, s16 by, u8 bw, u8 bh){
  return (u8)(ax < bx + bw && bx < ax + aw && ay < by + bh && by < ay + ah);
}
void tm_bind(const u8 *map, u8 w, u8 h, const u8 *flags){
  lv_on = 0; tm_map = map; tm_w = w; tm_h = h; tm_flags = flags;
}
/* One column of the packed level. Packets are the format in tools/mappack.py. */
static u8 lv_tile(u16 tx, u8 ty){
  const u8 *p = lv->pack + lv->index[tx];
  const u8 *end = lv->pack + lv->index[(u16)(tx + 1)];
  u8 row = 0;
  while(p < end && row <= ty){
    u8 cmd = *p++, n = (u8)(cmd & 127);
    if(!n) continue;
    if(cmd & 128){
      u8 t = *p++;
      if(ty < (u8)(row + n)) return t;
      row = (u8)(row + n);
    } else {
      if(ty < (u8)(row + n)) return p[(u8)(ty - row)];
      p += n; row = (u8)(row + n);
    }
  }
  return 0;
}
/* Walk the column once. A per-row walk restarts the RLE and, on 6502,
   makes a 64-column load take more than a second with the screen off. */
#ifndef __NES__
static void lv_decode(u16 c){
  const u8 *p = lv->pack + lv->index[c];
  const u8 *end = lv->pack + lv->index[(u16)(c + 1)];
  u8 row = 0, rows = lv->rows, cmd, n, k, t;
  if(rows > BG_H) rows = BG_H;
  while(p < end && row < rows){
    cmd = *p++; n = (u8)(cmd & 127);
    if(!n) continue;
    if(cmd & 128){
      t = *p++;
      for(k = 0; k < n && row < rows; k++) lv_col[row++] = t;
    } else {
      for(k = 0; k < n && row < rows; k++) lv_col[row++] = *p++;
    }
  }
  while(row < rows) lv_col[row++] = 0;
}
#endif
static void lv_paint(u16 c){
  u8 ay, nt, idx, b;
  u16 base;
  lv_decode(c);
  r_column((u8)(c & 63), lv_col, lv->rows);
  nt = (u8)((c & 63) >> 5);
  base = (u16)((c >> 5) * 64);
  for(ay = 0; ay < 8; ay++){
    idx = (u8)(ay * 8 + ((c & 31) >> 2));
    b = lv->attr[base + idx];
    attr[nt][idx] = b;
    r_attr(nt, idx, b);
  }
}
u8 level_count(void){ return game_level_count(); }
u8 level_current(void){ return lv_id; }
u16 level_cols(void){ return (lv_on && lv) ? lv->cols : 0; }
u8 level_music(void){ return (lv_on && lv) ? lv->music : 0; }
const u8 *level_ents(void){ return (lv_on && lv) ? lv->ents : 0; }
u8 level_ent_n(void){ return (lv_on && lv) ? lv->ent_n : 0; }
void level_load(u8 n){
  u16 c, last, i;
  u8 nested;
  if(!game_level_count()) return;
  if(n >= game_level_count()) n = 0;
  lv = game_level(n);
  lv_on = 1; lv_id = n;
  tm_map = 0;
  nested = r_in_bulk();
  if(!nested) r_bulk_begin();
  for(i = 0; i < 64; i++){ attr[0][i] = 0; attr[1][i] = 0; }
  last = lv->cols ? (u16)(lv->cols - 1) : 0;
  if(last > 63) last = 63;
  for(c = 0; c <= last; c++) lv_paint(c);
  if(lv->cols <= 32) for(i = 0; i < 64; i++){ attr[1][i] = 0; r_attr(1, i, 0); }
  lv_right = last;
  if(!nested) r_bulk_end();
}
void level_scroll(u16 cam){
  u16 cols, maxc, need_l, need_r, win_l, start, c;
  u8 nested;
  if(!lv_on || !lv || !lv->cols){ r_scroll(0); return; }
  cols = lv->cols;
  maxc = (cols > 32) ? (u16)((cols - 32) << 3) : 0;
  if(cam > maxc) cam = maxc;
  if(cols <= 32){ r_scroll(0); return; }
  need_l = (u16)(cam >> 3);
  need_r = (u16)((cam + 255) >> 3);
  if(need_r >= cols) need_r = (u16)(cols - 1);
  win_l = (lv_right >= 63) ? (u16)(lv_right - 63) : 0;
  if(need_l >= win_l && need_r <= lv_right){
    r_scroll((u16)(cam & 511));
    return;
  }
  if(need_r > lv_right && (u16)(need_r - lv_right) <= 2){
    while(lv_right < need_r){ lv_right++; lv_paint(lv_right); }
  } else if(lv_right > (u16)(need_l + 63) && (u16)(lv_right - (need_l + 63)) <= 2){
    while((u16)(need_l + 63) < lv_right){ lv_paint((u16)(lv_right - 64)); lv_right--; }
  } else {
    nested = r_in_bulk();
    if(!nested) r_bulk_begin();
    start = (need_r >= 63) ? (u16)(need_r - 63) : 0;
    for(c = start; c <= need_r; c++) lv_paint(c);
    lv_right = need_r;
    if(!nested) r_bulk_end();
  }
  r_scroll((u16)(cam & 511));
}
u8 tm_flags_at(s16 px, s16 py){
  s16 tx, ty;
  if(lv_on && lv){
    if(px < 0 || py < 0) return TF_SOLID;
    tx = (s16)(px >> 3); ty = (s16)(py >> 3);
    if(tx >= (s16)lv->cols) return TF_SOLID;
    if(ty >= (s16)lv->rows) return 0;
    return lv->flags[lv_tile((u16)tx, (u8)ty)];
  }
  if(!tm_map) return 0;
  if(px < 0 || py < 0) return TF_SOLID;
  tx = px >> 3; ty = py >> 3;
  if(tx >= tm_w) return TF_SOLID;
  if(ty >= tm_h) return 0;
  return tm_flags[tm_map[(u16)ty * tm_w + tx]];
}
u16 rnd(void){ seed ^= seed << 7; seed ^= seed >> 9; seed ^= seed << 8; return seed; }

u8 ent_find(const u8 *ents, u8 n, u8 type){
  u8 i;
  if(!ents) return 255;
  for(i = 0; i < n; i++)
    if(ents[(u16)i * ENT_BYTES] == type) return i;
  return 255;
}

/* ---- main loop ---- */
void engine_init(void){ mus_master = 12; r_init(); oam = r_oam(); next = game_boot(); }
void engine_frame(u8 raw){
  u8 i;
  pad_pressed = (u8)(raw & ~pad_held); pad_released = (u8)(pad_held & ~raw); pad_held = raw;
  if(next){
    cur = next; next = 0;
    r_bulk_begin();
    for(i = 0; i < 64; i++){ attr[0][i] = attr[1][i] = 0; }
    tm_map = 0; lv_on = 0; r_scroll(0);
    cur->init();
    r_bulk_end();
    pad_pressed = 0;
  }
  cur->update();
  nspr = 0;
  cur->draw();
  for(i = nspr; i < MAX_SPRITES; i++) oam[i << 2] = 0xF0;   /* hide unused */
  audio_tick();
  ++frame_count; seed += raw;
}
