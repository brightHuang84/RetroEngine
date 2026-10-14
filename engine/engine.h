/* retro_engine public API - C89, cc65-compatible, integers only, no malloc.
   Constraints follow the NES: 256x240 screen, 8x8 tiles, 64 sprites, 2KB RAM, NTSC 60Hz. */
#ifndef ENGINE_H
#define ENGINE_H

typedef unsigned char  u8;
typedef signed char    s8;
typedef unsigned short u16;
typedef signed short   s16;

#define SCREEN_W 256
#define SCREEN_H 240
#define BG_W 64            /* background is 2 screens wide (64x30 tiles) for horizontal scroll */
#define BG_H 30
#define MAX_SPRITES 64

/* ---------- video: palette & background ---------- */
void gfx_palette(const u8 *pal32);            /* 32 NES palette indices: 4 BG + 4 sprite palettes */
void bg_tile(u8 x, u8 y, u8 tile);            /* queued; x 0..63, y 0..29 */
void bg_tiles(u8 x, u8 y, const u8 *t, u8 n); /* horizontal run (one queue entry) */
void bg_fill(u8 x, u8 y, u8 w, u8 h, u8 tile);
void bg_attr(u8 x, u8 y, u8 pal);             /* palette 0..3 for the 16x16 block containing tile x,y */
void bg_text(u8 x, u8 y, const char *s);      /* tile index = ASCII */
void bg_number(u8 x, u8 y, u16 v, u8 digits); /* zero padded */
void bg_load(const u8 *map, u8 w, u8 h, const u8 *attr); /* bulk: use only in scene init. attr = 64 bytes per 32-wide page or 0 */
void bg_scroll(u16 x);                        /* horizontal scroll 0..511 */
/* Queued tile writes: on NES they are flushed during vblank (~96 bytes/frame); if the
   queue overflows the engine waits one frame (lag). During scene init writes are direct. */

/* ---------- sprites (8x8, cleared automatically before each draw) ---------- */
#define SPR_PAL(p) (p)
#define SPR_FLIPH  0x40
#define SPR_FLIPV  0x80
#define SPR_BEHIND 0x20
u8   spr(s16 x, s16 y, u8 tile, u8 attr);     /* returns 0 if clipped or 64 used */
void spr_meta(s16 x, s16 y, const s8 *m, u8 flip); /* m = {dx,dy,tile,attr,...,-128}; flip mirrors dx */
void spr_text(s16 x, s16 y, const char *s, u8 attr);
void spr_number(s16 x, s16 y, u16 v, u8 digits, u8 attr);

/* ---------- input ---------- */
#define BTN_RIGHT  0x01
#define BTN_LEFT   0x02
#define BTN_DOWN   0x04
#define BTN_UP     0x08
#define BTN_START  0x10
#define BTN_SELECT 0x20
#define BTN_B      0x40
#define BTN_A      0x80
extern u8 pad_held, pad_pressed, pad_released;

/* ---------- scenes ---------- */
typedef struct Scene { void (*init)(void); void (*update)(void); void (*draw)(void); } Scene;
void scene_go(const Scene *s);                /* switch at the start of the next frame */
const Scene *game_boot(void);                 /* provided by the game: first scene */
u8 game_autopilot(void);                      /* provided by the game: test-mode input (PC test mode) */
extern u8 frame_count;

/* ---------- audio: 4 NES APU channels (no DPCM) ---------- */
#define CH_PULSE1 0
#define CH_PULSE2 1
#define CH_TRI    2
#define CH_NOISE  3
/* A song is four independent note streams. NULL channel = silent.
   loop == 0xFFFF plays once; otherwise it is the byte offset to jump to at the end.
   Pulse/triangle events are note indices (1 = C1 .. 84 = B7, 0 = rest) plus a duration.
   Noise events use 1..16 for hardware period N0..N15. Streams end with 0xFF. */
typedef struct Track { const u8 *data; u16 loop; u8 duty; u8 vol; } Track;
typedef struct Song { const Track *ch[4]; } Song;
enum { SFX_NONE, SFX_BLIP, SFX_HIT, SFX_COIN, SFX_JUMP, SFX_LOSE, SFX_WIN };
void sfx(u8 id);                              /* steals pulse2 until the effect ends; ids unchanged */
void music_play(u8 id);                       /* game supplies music_lookup */
void music_stop(void);
void music_pause(u8 on);                      /* nonzero freezes the sequencer and holds current notes */
void music_volume(u8 vol);                    /* 0..15, music only; sound effects stay full */
const Song *music_lookup(u8 id);              /* provided by the game (generated from songs.txt) */

/* ---------- fixed point & physics ---------- */
typedef s16 fx;                 /* 12.4 fixed point: world up to +-2047 px */
#define FX_SHIFT 4
#define FX(n)    ((fx)((n) << FX_SHIFT))
#define FX_INT(v) ((s16)((v) >> FX_SHIFT))
u8 aabb(s16 ax, s16 ay, u8 aw, u8 ah, s16 bx, s16 by, u8 bw, u8 bh);
#define TF_SOLID 0x01
void tm_bind(const u8 *map, u8 w, u8 h, const u8 *flags256); /* collision map (usually same as bg_load) */
u8   tm_flags_at(s16 px, s16 py);             /* flags of tile at world pixel; outside map = solid */
u16  rnd(void);
#endif
