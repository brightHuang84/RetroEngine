/* Platformer demo on retro_engine: run/jump, tile collisions, several levels.
   Level 1 is the original 64-column map. A later level is wider than two
   screens; level_scroll streams columns and the camera follows the player.
   All coins or the goal opens the next level. The last level wins.
   Uses only engine.h. */
#include "../../engine/engine.h"
#include "assets.h"
#include "music.h"

#define T_HEAD 0xA0
#define T_LEG1 0xA1
#define T_LEG2 0xA2
#define T_COIN 0xB0
#define T_ENEMY 0xB8
#define T_GOAL 0x85
#define GRAVITY 3          /* 1/16 px per frame^2 */
#define JUMP_V  (-72)      /* -4.5 px/frame */
#define MAX_FALL 80
#define RUN_V   24         /* 1.5 px/frame */
#define ESLOTS 4

static fx px, py, pvx, pvy;
static u8 on_ground, facing_left, coins_got, lives, won, anim;
static u8 ncoins, coin_taken[ENT_MAX];
static s16 start_x, start_y;
static s16 exs[ESLOTS], eys[ESLOTS], elefts[ESLOTS], erights[ESLOTS];
static s8 edirs[ESLOTS];
static u8 ealive[ESLOTS], eslot[ESLOTS];
static u16 score, cam;
extern const Scene title_scene, play_scene, end_scene;

static void center_text(u8 y, const char *s){ u8 n = 0; while(s[n]) n++; bg_text((u8)((32 - n) / 2), y, s); }

/* ---------- title ---------- */
static void title_init(void){
  level_load(0);
  center_text(10, "TINY PLATFORMER");
  center_text(13, "COLLECT ALL COINS");
  center_text(16, "PRESS START");
  music_play(MUS_TITLE);
}
static void title_update(void){ if(pad_pressed & BTN_START){ sfx(SFX_BLIP); scene_go(&play_scene); } }
static void title_draw(void){ spr(120, 120, T_COIN, 1); }
const Scene title_scene = { title_init, title_update, title_draw };

/* ---------- play ---------- */
static u8 solid(s16 x, s16 y){ return (u8)(tm_flags_at(x, y) & TF_SOLID); }
static void enemies_clear(void){ u8 i; for(i = 0; i < ESLOTS; i++) ealive[i] = 0; }
static void load_spawns(void){
  u8 i, slot, n;
  const u8 *e, *ents;
  start_x = 16; start_y = 192; ncoins = 0;
  enemies_clear();
  ents = level_ents(); n = level_ent_n();
  for(i = 0; i < ENT_MAX; i++) coin_taken[i] = 0;
  slot = ent_find(ents, n, ENT_PLAYER);
  if(slot != 255){ e = ent_ptr(ents, slot); start_x = (s16)ent_x(e); start_y = ent_y(e); }
  for(i = 0; i < n; i++)
    if(ent_type(ent_ptr(ents, i)) == ENT_COIN) ncoins++;
}
static void respawn(void){ px = FX(start_x); py = FX(start_y); pvx = 0; pvy = 0; facing_left = 0; }
static u8 enemy_tracked(u8 slot){
  u8 i;
  for(i = 0; i < ESLOTS; i++) if(ealive[i] && eslot[i] == slot) return 1;
  return 0;
}
/* Keep up to four enemies whose spawn is near the camera. Level 1's enemy
   at x=280 is inside the window on the first frame, so its patrol phase matches. */
static void enemies_spawn(void){
  u8 i, k, n, free;
  const u8 *ents, *e;
  s16 wx;
  n = level_ent_n(); ents = level_ents();
  for(i = 0; i < ESLOTS; i++){
    if(!ealive[i]) continue;
    if(exs[i] < (s16)cam - 64 || exs[i] > (s16)cam + 320) ealive[i] = 0;
  }
  if(!ents) return;
  for(i = 0; i < n; i++){
    e = ent_ptr(ents, i);
    if(ent_type(e) != ENT_ENEMY) continue;
    wx = (s16)ent_x(e);
    if(wx < (s16)cam - 32 || wx > (s16)cam + 320) continue;
    if(enemy_tracked(i)) continue;
    free = 255;
    for(k = 0; k < ESLOTS; k++) if(!ealive[k]){ free = k; break; }
    if(free == 255) continue;
    ealive[free] = 1; eslot[free] = i;
    exs[free] = wx; eys[free] = ent_y(e);
    elefts[free] = (s16)ent_prop(e, 0); erights[free] = (s16)ent_prop(e, 1);
    edirs[free] = 1;
  }
}
static void begin_level(u8 n){
  level_load(n);
  load_spawns();
  coins_got = 0; cam = 0;
  respawn();
  enemies_spawn();
  level_scroll(cam);
  music_play(level_music());
}
static void play_init(void){
  u8 n = 0;
  long pix, lim, maxc;
  score = 0; lives = 3;
  if(test_level != 255 && test_level < level_count()) n = test_level;
  begin_level(n);
  if(test_cam != (u16)-1){
    pix = (long)test_cam + 120L;
    lim = ((long)level_cols() << 3) - 8L;
    maxc = (level_cols() > 32) ? (((long)level_cols() - 32L) << 3) : 0L;
    if(pix > lim) pix = lim;
    if(pix > 2047L) pix = 2047L;
    px = (fx)(pix << FX_SHIFT);
    cam = test_cam;
    if((long)cam > maxc) cam = (u16)maxc;
    enemies_clear();
    enemies_spawn();
    level_scroll(cam);
  }
}
static void lose_life(void){
  sfx(SFX_LOSE);
  if(--lives == 0){ won = 0; scene_go(&end_scene); } else respawn();
}
static void move_player(void){
  s16 x, y, nx, ny; s16 t;
  long v, lim;
  if(pad_held & BTN_RIGHT){ pvx = RUN_V; facing_left = 0; }
  else if(pad_held & BTN_LEFT){ pvx = -RUN_V; facing_left = 1; }
  else pvx = 0;
  if((pad_pressed & BTN_A) && on_ground){ pvy = JUMP_V; sfx(SFX_JUMP); }
  if(!(pad_held & BTN_A) && pvy < -24) pvy = -24;     /* variable jump height */
  /* Maps wider than 2048 px would overflow fx. Clamp with a long so a
     256-column level (2048 px) stays in range. Narrow levels use s16 add. */
  if(level_cols() > 64){
    v = (long)px + (long)pvx;
    lim = (((long)level_cols() << 3) - 8L) << FX_SHIFT;
    if(v > lim) v = lim;
    if(v > 32767L) v = 32767L;
    if(v < -32768L) v = -32768L;
    px = (fx)v;
  } else px += pvx;
  x = FX_INT(px); y = FX_INT(py);
  if(pvx > 0 && (solid(x + 7, y) || solid(x + 7, y + 8) || solid(x + 7, y + 15))){ t = (s16)((x + 7) & ~7); px = FX(t - 8); }
  if(pvx < 0 && (solid(x, y) || solid(x, y + 8) || solid(x, y + 15))){ t = (s16)((x & ~7) + 8); px = FX(t); }
  pvy += GRAVITY; if(pvy > MAX_FALL) pvy = MAX_FALL;
  py += pvy; nx = FX_INT(px); ny = FX_INT(py);
  on_ground = 0;
  if(pvy > 0 && ny < 232 && (solid(nx + 1, ny + 16) || solid(nx + 6, ny + 16))){
    py = FX(((ny + 16) & ~7) - 16); pvy = 0; on_ground = 1;
  } else if(pvy < 0 && (solid(nx + 1, ny) || solid(nx + 6, ny))){
    py = FX((ny & ~7) + 8); pvy = 0;
  }
  if(FX_INT(py) > 240) lose_life();
}
static void advance(void){
  u8 n = (u8)(level_current() + 1);
  if(n >= level_count()){ won = 1; sfx(SFX_WIN); scene_go(&end_scene); return; }
  sfx(SFX_BLIP);
  begin_level(n);
}
static u8 hit_goal(s16 x, s16 y){
  u8 i, n;
  const u8 *ents = level_ents();
  n = level_ent_n();
  if(!ents) return 0;
  for(i = 0; i < n; i++){
    const u8 *e = ent_ptr(ents, i);
    if(ent_type(e) == ENT_GOAL && aabb(x, y, 8, 16, (s16)ent_x(e), ent_y(e), 16, 16)) return 1;
  }
  return 0;
}
static void play_update(void){
  u8 i, n, s;
  s16 x, y;
  const u8 *ents, *e;
  long cx, maxc;
  move_player();
  x = FX_INT(px); y = FX_INT(py);
  if(pvx) anim++;
  ents = level_ents(); n = level_ent_n();
  for(i = 0; i < n; i++){
    e = ent_ptr(ents, i);
    if(ent_type(e) != ENT_COIN || coin_taken[i]) continue;
    if(aabb(x, y, 8, 16, (s16)ent_x(e), ent_y(e), 8, 8)){
      coin_taken[i] = 1; ++coins_got; score += 100; sfx(SFX_COIN);
    }
  }
  if(hit_goal(x, y) || (ncoins && coins_got == ncoins)){ advance(); return; }
  enemies_spawn();
  for(s = 0; s < ESLOTS; s++){
    if(!ealive[s]) continue;
    if(frame_count & 1){
      exs[s] += edirs[s];
      if(exs[s] < elefts[s] || exs[s] > erights[s]) edirs[s] = (s8)-edirs[s];
    }
    if(aabb(x, y, 8, 16, exs[s], eys[s], 8, 8)){
      if(pvy > 0 && y + 12 < eys[s]){ ealive[s] = 0; score += 50; pvy = JUMP_V / 2; sfx(SFX_HIT); }
      else lose_life();
    }
  }
  cx = (long)FX_INT(px) - 120L;
  if(cx < 0) cx = 0;
  maxc = (level_cols() > 32) ? (((long)level_cols() - 32L) << 3) : 0L;
  if(cx > maxc) cx = maxc;
  cam = (u16)cx;
  level_scroll(cam);
}
static void draw_goal(s16 x, s16 y){
  spr(x, y, T_GOAL, 3); spr((s16)(x + 8), y, T_GOAL, 3);
  spr(x, (s16)(y + 8), T_GOAL, 3); spr((s16)(x + 8), (s16)(y + 8), T_GOAL, 3);
}
static void play_draw(void){
  u8 i, a, n, s;
  s16 x = FX_INT(px) - (s16)cam, y = FX_INT(py);
  const u8 *ents, *e;
  a = facing_left ? SPR_FLIPH : 0;
  spr(x, y, T_HEAD, a);
  spr(x, y + 8, (on_ground && pvx && (anim & 8)) ? T_LEG2 : T_LEG1, a);
  /* HUD as sprites (background scrolls) - max 8 sprites per scanline on NES */
  spr_number(8, 8, score, 5, 3);
  spr(8, 20, T_COIN, 1); spr_number(20, 20, coins_got, 1, 3); spr(28, 20, '/', 3); spr_number(36, 20, ncoins, 1, 3);
  spr(216, 20, T_HEAD, 0); spr(226, 20, 'X', 3); spr_number(236, 20, lives, 1, 3);
  ents = level_ents(); n = level_ent_n();
  for(i = 0; i < n; i++){
    e = ent_ptr(ents, i);
    if(ent_type(e) == ENT_COIN && !coin_taken[i]) spr((s16)ent_x(e) - (s16)cam, ent_y(e), T_COIN, 1);
    if(ent_type(e) == ENT_GOAL) draw_goal((s16)ent_x(e) - (s16)cam, ent_y(e));
  }
  for(s = 0; s < ESLOTS; s++)
    if(ealive[s]) spr(exs[s] - (s16)cam, eys[s], T_ENEMY, (u8)(2 | ((frame_count & 16) ? SPR_FLIPH : 0)));
}
const Scene play_scene = { play_init, play_update, play_draw };

/* ---------- end ---------- */
static void end_init(void){
  music_stop();
  bg_fill(0, 0, 32, 30, ' ');
  center_text(11, won ? "YOU WIN!" : "GAME OVER");
  bg_text(11, 14, "SCORE:"); bg_number(17, 14, score, 5);
  center_text(18, "PRESS START");
  { u8 c, r; for(r = 10; r < 20; r++) for(c = 0; c < 32; c += 2) bg_attr(c, r, 3); }
}
static void end_update(void){ if(pad_pressed & BTN_START) scene_go(&title_scene); }
static void end_draw(void){}
const Scene end_scene = { end_init, end_update, end_draw };

const Scene *game_boot(void){ gfx_palette(game_palette); return &title_scene; }

/* PC test mode: press start, run right, jump regularly.
   RETRO_LEVEL holds still after start when RETRO_CAM is set, so a screenshot
   stays on that camera. Unset, the original route is unchanged. */
u8 game_autopilot(void){
  u8 f = frame_count;
  if(test_level != 255){
    /* Frame 0 is swallowed by the title scene switch, so the start edge has to come later. */
    if(f < 2) return 0;
    if(f < 8) return BTN_START;
    if(test_cam != (u16)-1) return 0;
  }
  if(f < 60) return 0;
  if(f < 70) return BTN_START;
  if(f < 110) return 0;
  if(f < 150) return BTN_RIGHT;                       /* walk into coin 1 */
  if(f < 165) return BTN_RIGHT | BTN_A;               /* jump onto platform 1 */
  return BTN_RIGHT | (((f >> 4) & 3) == 0 ? BTN_A : 0);
}
