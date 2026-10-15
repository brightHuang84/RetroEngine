/* Platformer demo on retro_engine: run/jump with gravity, tile collisions,
   2-screen scrolling level, 6 coins, one enemy. Uses only engine.h. */
#include "../../engine/engine.h"
#include "assets.h"
#include "music.h"

#define T_HEAD 0xA0
#define T_LEG1 0xA1
#define T_LEG2 0xA2
#define T_COIN 0xB0
#define T_ENEMY 0xB8
#define NCOINS 6
#define START_X 16
#define START_Y 192
#define GRAVITY 3          /* 1/16 px per frame^2 */
#define JUMP_V  (-72)      /* -4.5 px/frame */
#define MAX_FALL 80
#define RUN_V   24         /* 1.5 px/frame */

static const s16 coin_x[NCOINS] = { 56, 96, 160, 232, 376, 440 };
static const s16 coin_y[NCOINS] = { 196, 156, 124, 156, 148, 116 };

static fx px, py, pvx, pvy;
static u8 on_ground, facing_left, coins_got, lives, won, anim;
static u8 coin_taken[NCOINS];
static s16 ex; static s8 edir; static u8 enemy_alive;
static u16 score, cam;
extern const Scene title_scene, play_scene, end_scene;

static void center_text(u8 y, const char *s){ u8 n = 0; while(s[n]) n++; bg_text((u8)((32 - n) / 2), y, s); }

/* ---------- title ---------- */
static void title_init(void){
  bg_load(map_level, MAP_LEVEL_W, MAP_LEVEL_H, map_level_attr);
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
static void respawn(void){ px = FX(START_X); py = FX(START_Y); pvx = 0; pvy = 0; facing_left = 0; }
static void play_init(void){
  u8 i;
  bg_load(map_level, MAP_LEVEL_W, MAP_LEVEL_H, map_level_attr);
  tm_bind(map_level, MAP_LEVEL_W, MAP_LEVEL_H, map_level_flags);
  for(i = 0; i < NCOINS; i++) coin_taken[i] = 0;
  coins_got = 0; score = 0; lives = 3; ex = 280; edir = 1; enemy_alive = 1; cam = 0;
  respawn();
  music_play(MUS_PLAY);
}
static void lose_life(void){
  sfx(SFX_LOSE);
  if(--lives == 0){ won = 0; scene_go(&end_scene); } else respawn();
}
static void move_player(void){
  s16 x, y, nx, ny; s16 t;
  /* horizontal */
  if(pad_held & BTN_RIGHT){ pvx = RUN_V; facing_left = 0; }
  else if(pad_held & BTN_LEFT){ pvx = -RUN_V; facing_left = 1; }
  else pvx = 0;
  if((pad_pressed & BTN_A) && on_ground){ pvy = JUMP_V; sfx(SFX_JUMP); }
  if(!(pad_held & BTN_A) && pvy < -24) pvy = -24;     /* variable jump height */
  px += pvx; x = FX_INT(px); y = FX_INT(py);
  if(pvx > 0 && (solid(x + 7, y) || solid(x + 7, y + 8) || solid(x + 7, y + 15))){ t = (s16)((x + 7) & ~7); px = FX(t - 8); }
  if(pvx < 0 && (solid(x, y) || solid(x, y + 8) || solid(x, y + 15))){ t = (s16)((x & ~7) + 8); px = FX(t); }
  /* vertical */
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
static void play_update(void){
  u8 i; s16 x, y;
  move_player();
  x = FX_INT(px); y = FX_INT(py);
  if(pvx) anim++;
  for(i = 0; i < NCOINS; i++)
    if(!coin_taken[i] && aabb(x, y, 8, 16, coin_x[i], coin_y[i], 8, 8)){
      coin_taken[i] = 1; ++coins_got; score += 100; sfx(SFX_COIN);
      if(coins_got == NCOINS){ won = 1; sfx(SFX_WIN); scene_go(&end_scene); }
    }
  if(enemy_alive){
    if(frame_count & 1){ ex += edir; if(ex < 264 || ex > 312) edir = (s8)-edir; }
    if(aabb(x, y, 8, 16, ex, 200, 8, 8)){
      if(pvy > 0 && y + 12 < 200){ enemy_alive = 0; score += 50; pvy = JUMP_V / 2; sfx(SFX_HIT); }
      else lose_life();
    }
  }
  /* camera follows player, 2 screens wide */
  x -= 120; if(x < 0) x = 0; if(x > 256) x = 256;
  cam = (u16)x; bg_scroll(cam);
}
static void play_draw(void){
  u8 i, a; s16 x = FX_INT(px) - (s16)cam, y = FX_INT(py);
  a = facing_left ? SPR_FLIPH : 0;
  spr(x, y, T_HEAD, a);
  spr(x, y + 8, (on_ground && pvx && (anim & 8)) ? T_LEG2 : T_LEG1, a);
  /* HUD as sprites (background scrolls) - max 8 sprites per scanline on NES */
  spr_number(8, 8, score, 5, 3);
  spr(8, 20, T_COIN, 1); spr_number(20, 20, coins_got, 1, 3); spr(28, 20, '/', 3); spr_number(36, 20, NCOINS, 1, 3);
  spr(216, 20, T_HEAD, 0); spr(226, 20, 'X', 3); spr_number(236, 20, lives, 1, 3);
  for(i = 0; i < NCOINS; i++) if(!coin_taken[i]) spr(coin_x[i] - (s16)cam, coin_y[i], T_COIN, 1);
  if(enemy_alive) spr(ex - (s16)cam, 200, T_ENEMY, (u8)(2 | ((frame_count & 16) ? SPR_FLIPH : 0)));
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

/* PC test mode: press start, run right, jump regularly */
u8 game_autopilot(void){
  u8 f = frame_count;
  if(f < 60) return 0;
  if(f < 70) return BTN_START;
  if(f < 110) return 0;
  if(f < 150) return BTN_RIGHT;                       /* walk into coin 1 */
  if(f < 165) return BTN_RIGHT | BTN_A;               /* jump onto platform 1 */
  return BTN_RIGHT | (((f >> 4) & 3) == 0 ? BTN_A : 0);
}
