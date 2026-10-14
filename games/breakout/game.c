/* Breakout on retro_engine. Uses only engine.h - no platform code. */
#include "../../engine/engine.h"
#include "assets.h"
#include "music.h"

#define BR_COLS 14
#define BR_ROWS 6
#define BR_TX 2
#define BR_TY 4
#define PAD_W 32
#define PAD_Y 200
#define T_BRICK_L 0x80
#define T_BRICK_R 0x81
#define T_BALL 0x90

static const u8 palette[32] = {
  0x0F,0x16,0x26,0x06, 0x0F,0x27,0x37,0x17, 0x0F,0x2A,0x3A,0x1A, 0x0F,0x10,0x00,0x30,
  0x0F,0x30,0x30,0x10, 0x0F,0x21,0x31,0x11, 0x0F,0x30,0x30,0x30, 0x0F,0x30,0x30,0x30 };
static const s8 paddle_meta[] = { 0,0,0x91,1, 8,0,0x92,1, 16,0,0x92,1, 24,0,0x93,1, -128 };

static u8 bricks[BR_ROWS][BR_COLS];
static u8 padx, bx, by, serving, lives, left, won;
static s8 vx, vy;
static u16 score;
extern const Scene title_scene, play_scene, end_scene;

static void draw_brick(u8 r, u8 c, u8 on){
  static u8 t[2];
  t[0] = on ? T_BRICK_L : ' '; t[1] = on ? T_BRICK_R : ' ';
  bg_tiles((u8)(BR_TX + c * 2), (u8)(BR_TY + r), t, 2);
}
static void hud(void){ bg_number(8, 1, score, 5); bg_number(29, 1, lives, 1); }

/* ---------- title ---------- */
static void title_init(void){
  u8 r, c;
  gfx_palette(palette);
  bg_fill(0, 0, 32, 30, ' ');
  for(r = 0; r < 4; r++) for(c = 0; c < 16; c++){ bg_tile((u8)(c * 2), (u8)(6 + r), T_BRICK_L); bg_tile((u8)(c * 2 + 1), (u8)(6 + r), T_BRICK_R); bg_attr((u8)(c * 2), (u8)(6 + r), (u8)(r >> 1)); }
  bg_text(12, 13, "BREAKOUT");
  bg_text(10, 17, "PRESS START");
  bg_text(5, 25, "RETRO ENGINE DEMO 2026");
  for(c = 0; c < 32; c += 2){ bg_attr(c, 13, 3); bg_attr(c, 17, 3); bg_attr(c, 25, 3); }
  music_play(MUS_TITLE);
}
static void title_update(void){ if(pad_pressed & (BTN_START | BTN_A)){ sfx(SFX_BLIP); scene_go(&play_scene); } }
static void title_draw(void){ if(frame_count & 32) spr(124, 140, T_BALL, 0); }
const Scene title_scene = { title_init, title_update, title_draw };

/* ---------- play ---------- */
static void serve(void){ serving = 1; vx = 0; vy = 0; bg_text(8, 16, "PRESS A TO LAUNCH"); }
static void play_init(void){
  u8 r, c;
  bg_load(map_play, MAP_PLAY_W, MAP_PLAY_H, map_play_attr);
  bg_text(2, 1, "SCORE:"); bg_text(23, 1, "LIVES:");
  for(r = 0; r < BR_ROWS; r++) for(c = 0; c < BR_COLS; c++){
    bricks[r][c] = 1; draw_brick(r, c, 1); bg_attr((u8)(BR_TX + c * 2), (u8)(BR_TY + r), (u8)(r >> 1));
  }
  left = BR_ROWS * BR_COLS; score = 0; lives = 3; padx = (SCREEN_W - PAD_W) / 2;
  serve(); hud();
  music_play(MUS_PLAY);
}
static void play_update(void){
  u8 cx, cy, r, c, oy; s8 off;
  if((pad_held & BTN_LEFT) && padx > 10) padx -= 3;
  if((pad_held & BTN_RIGHT) && padx < 248 - PAD_W - 2) padx += 3;
  if(serving){
    bx = (u8)(padx + PAD_W / 2 - 4); by = PAD_Y - 8;
    if(pad_pressed & (BTN_A | BTN_START)){ serving = 0; vx = (frame_count & 1) ? 1 : -1; vy = -2; bg_text(8, 16, "                 "); sfx(SFX_BLIP); }
    return;
  }
  oy = by; bx = (u8)(bx + vx); by = (u8)(by + vy);
  if(vx < 0 && bx < 8){ bx = 8; vx = -vx; sfx(SFX_BLIP); }
  if(vx > 0 && bx > 240){ bx = 240; vx = -vx; sfx(SFX_BLIP); }
  if(vy < 0 && by < 24){ by = 24; vy = -vy; sfx(SFX_BLIP); }
  if(vy > 0 && aabb(bx, by, 8, 8, padx, PAD_Y, PAD_W, 6)){
    off = (s8)((bx + 4) - (padx + PAD_W / 2));
    vx = (s8)(off / 6); if(vx == 0) vx = (off < 0) ? -1 : 1;
    vy = -2; by = PAD_Y - 8; sfx(SFX_BLIP);
  }
  if(by >= 232 && vy > 0){
    sfx(SFX_LOSE);
    if(--lives == 0){ won = 0; scene_go(&end_scene); } else serve();
    hud(); return;
  }
  cx = (u8)((bx + 4) >> 3); cy = (u8)((by + 4) >> 3);
  if(cy >= BR_TY && cy < BR_TY + BR_ROWS && cx >= BR_TX && cx < BR_TX + BR_COLS * 2){
    r = (u8)(cy - BR_TY); c = (u8)((cx - BR_TX) >> 1);
    if(bricks[r][c]){
      bricks[r][c] = 0; --left; score += 10 * (BR_ROWS - r);
      draw_brick(r, c, 0); hud(); sfx(SFX_HIT);
      if(((u8)((oy + 4) >> 3)) != cy) vy = (s8)-vy; else vx = (s8)-vx;
      if(left == 0){ won = 1; sfx(SFX_WIN); scene_go(&end_scene); }
    }
  }
}
static void play_draw(void){
  spr(bx, by, T_BALL, 0);                 /* sprite 0 = ball (test scripts rely on it) */
  spr_meta(padx, PAD_Y, paddle_meta, 0);  /* sprite 1 = paddle */
}
const Scene play_scene = { play_init, play_update, play_draw };

/* ---------- end ---------- */
static void end_init(void){
  music_stop();
  bg_fill(0, 0, 32, 30, ' ');
  bg_text(won ? 12 : 11, 12, won ? "YOU WIN!" : "GAME OVER");
  bg_text(11, 15, "SCORE:"); bg_number(17, 15, score, 5);
  bg_text(10, 19, "PRESS START");
  { u8 c; for(c = 0; c < 32; c += 2){ bg_attr(c, 12, 3); bg_attr(c, 15, 3); bg_attr(c, 19, 3); } }
}
static void end_update(void){ if(pad_pressed & BTN_START) scene_go(&title_scene); }
static void end_draw(void){}
const Scene end_scene = { end_init, end_update, end_draw };

const Scene *game_boot(void){ gfx_palette(palette); return &title_scene; }

/* test-mode input (PC RETRO_TEST): start game, then follow the ball */
u8 game_autopilot(void){
  u8 p = 0;
  if(frame_count < 90) return 0;
  if((frame_count & 31) == 0) p |= BTN_START;
  if(padx + 16 < bx) p |= BTN_RIGHT; else if(padx + 12 > bx) p |= BTN_LEFT;
  return p;
}
