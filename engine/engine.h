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
void bg_scroll(u16 x);                        /* horizontal scroll 0..511, nametable window only */
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

/* ---------- audio: NES APU plus two optional MMC5 pulses (no DPCM) ---------- */
#define CH_PULSE1 0
#define CH_PULSE2 1
#define CH_TRI    2
#define CH_NOISE  3
#define CH_PULSE3 4
#define CH_PULSE4 5
#define MUS_CHANS 6
/* A song is six note streams. NULL channel = silent. Channels 4 and 5 are the
   MMC5 expansion pulses. Other targets mix them in software or ignore a silent
   track, so a song that leaves them NULL sounds the same everywhere.
   loop == 0xFFFF plays once; otherwise it is the byte offset to jump to at the end.
   Pulse/triangle events are note indices (1 = C1 .. 84 = B7, 0 = rest) plus a duration.
   Noise events use 1..16 for hardware period N0..N15. Streams end with 0xFF. */
typedef struct Track { const u8 *data; u16 loop; u8 duty; u8 vol; } Track;
typedef struct Song { const Track *ch[MUS_CHANS]; } Song;
enum { SFX_NONE, SFX_BLIP, SFX_HIT, SFX_COIN, SFX_JUMP, SFX_LOSE, SFX_WIN };
void sfx(u8 id);                              /* steals pulse2 until the effect ends; ids unchanged */
void music_play(u8 id);                       /* game supplies music_lookup */
void music_lock(u8 id);                       /* later music_play calls use this id */
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
void tm_bind(const u8 *map, u8 w, u8 h, const u8 *flags256); /* raw collision map (width fits in u8) */
u8   tm_flags_at(s16 px, s16 py);             /* flags of tile at world pixel; outside left/right/above = solid */
u16  rnd(void);

/* ---------- levels ----------
   games/<game>/maps/order.txt is the level list. Each map is column-RLE in ROM
   (see tools/mappack.py). level_load uploads the 64-column nametable window.
   level_scroll streams columns as the camera moves. tm_flags_at then reads one
   column from the blob, so the whole map is not decompressed into RAM.
   test_level 255 and test_cam 65535 mean "not set" (SDL: RETRO_LEVEL, RETRO_CAM). */
typedef struct Level {
  const u8 *pack;
  const u16 *index;
  const u8 *attr;
  const u8 *flags;
  const u8 *ents;
  u16 cols;
  u8 rows;
  u8 ent_n;
  u8 music;
  u8 chr_page;                  /* 8KB CHR page. 0 is the original 256-tile sheet */
  u8 prg;                       /* MMC5 8KB bank at $8000 holding pack/index/attr/flags/ents */
  const u8 *xpal;               /* 32*30 per-tile palettes, or 0. Valid only while this PRG bank is mapped */
} Level;
u8 game_level_count(void);                   /* provided by generated maps.c */
u8 game_exattr(void);                         /* 1 when nes.txt says exattr 1 */
const Level *game_level(u8 n);                /* switches the PRG bank, then returns the row.
                                                 Pointers inside stay valid until the next game_level/level_load. */
void level_load(u8 n);                       /* scene init, or mid-game (blanks while uploading) */
u8   level_count(void);
u8   level_current(void);
u16  level_cols(void);
u8   level_music(void);
const u8 *level_ents(void);
u8   level_ent_n(void);
void level_scroll(u16 cam_px);               /* keep the 2-screen window on this camera */
extern u8 test_level;
extern u16 test_cam;

/* ---------- cartridge (no effect on NROM / ignored where the hardware lacks it) ---------- */
void prg_bank(u8 bank);                       /* 8KB PRG window at $8000. Level loads do this. */
void chr_bank(u8 page);                       /* 8KB pattern page. Level loads do this. */
void wram_bank(u8 bank);                      /* 8KB WRAM window at $6000 */
u8   wram_banks(void);                        /* how many 8KB WRAM banks this target has */
u8  *wram_page(void);                         /* pointer to the current window, or 0 */
u16  mul8(u8 a, u8 b);                        /* 8x8 -> 16 multiply (MMC5 $5205, else software) */
void video_split(u8 scanline);                /* 0 off. Nonzero: pin scroll 0 until this scanline, then the real scroll */
void video_exattr(u8 on);                     /* per-8x8 palette via MMC5 ExRAM. Off keeps 16x16 attributes */

/* ---------- entities (ROM tables from entities.txt + the map) ----------
   One record is ENT_BYTES bytes: type, x lo/hi, y, then 4 little-endian u16 props.
   A map holds at most ENT_MAX records. 255 from ent_find means "not found". */
#define ENT_MAX  32
#define ENT_BYTES 12
#define ent_ptr(base, i) ((const u8 *)((base) + (u16)(i) * (u16)ENT_BYTES))
#define ent_type(p) ((p)[0])
#define ent_x(p) ((u16)((p)[1] | ((u16)(p)[2] << 8)))
#define ent_y(p) ((p)[3])
#define ent_prop(p, n) ((u16)((p)[4 + (u16)(n) * 2] | ((u16)(p)[5 + (u16)(n) * 2] << 8)))
u8 ent_find(const u8 *ents, u8 n, u8 type);

/* ---------- scripts (bytecode from scripts.json; empty tables if the file is absent) ---------- */
#define SEV_BOOT 1
#define SEV_LEVEL 2
#define SEV_FRAME 3
#define SEV_BUTTON 4
#define SEV_TOUCH 5
#define SEV_TILE 6
#define SEV_ENTITY 7
#define SEV_TIMER 8
#define SEV_VAR 9
#define SEV_REGION 10
#define SREQ_ADVANCE 1
#define SREQ_HURT 2
#define SREQ_WIN 4
#define SREQ_LOSE 8
#define SREQ_LEVEL 16
#define SREQ_SCENE 32
#define SCRIPT_GLOBAL 0
#define SCRIPT_LEVEL 1
void script_reset(void);
void script_level_reset(void);
void script_enable(u8 on);
void script_set_level(u8 n);
void script_set(u8 scope, u8 idx, u16 v);
u16  script_get(u8 scope, u8 idx);
void script_bind(u8 slot);
void script_set_hook(u8 id, void (*fn)(u8));
u8   script_taken(u8 slot);
u8   script_emit(u8 ev, u8 arg);              /* returns how many scripts started */
u8   script_listening(u8 ev, u8 arg);
void script_update(void);                     /* waits, timers, per-frame and button scripts */
void script_region_at(s16 x, s16 y);
void script_touch_map(s16 x, s16 y, u8 w, u8 h);
void script_draw(void);                       /* sprite text while a message is up */
u8   script_pull(u8 mask);                    /* read and clear request flags */
s8   script_shake(void);
u8   script_level_target(void);
u8   script_scene(void);
void script_actor_put(u8 slot, u8 type, u16 x, u8 y);
u8   script_actor_on(u8 slot);
u16  script_actor_x(u8 slot);
u8   script_actor_y(u8 slot);
u8   script_actor_type(u8 slot);

/* ---------- sprite animation (anims.json). Slot 255 / ANIM_NONE means stopped. ---------- */
void anim_reset(void);
void anim_play(u8 slot, u8 id);               /* same id keeps the current frame */
void anim_restart(u8 slot);
u8   anim_current(u8 slot);
void anim_update(void);
void anim_draw(u8 slot, s16 x, s16 y, u8 flip);
u8   anim_for_type(u8 type);                  /* default from anims.json, or 255 */
#endif
