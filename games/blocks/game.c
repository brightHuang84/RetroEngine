/* Script-only demo. This file only places the actor and runs the VM.
   Walking, the coin, the message and the win flag live in scripts.json. */
#include "../../engine/engine.h"
#include "assets.h"
#include "music.h"
#include "scripts.h"
#include "anim.h"

#define T_COIN 0xB0

static void play_init(void){
  u8 n, slot;
  const u8 *ents, *e;
  gfx_palette(game_palette);
  level_load(0);
  bg_text(10, 6, "BLOCKS ONLY");
  music_play(level_music());
  script_reset();
  script_level_reset();
  script_set_level(0);
  script_enable(1);
  ents = level_ents();
  n = level_ent_n();
  slot = ent_find(ents, n, ENT_PLAYER);
  if(slot != 255){
    e = ent_ptr(ents, slot);
    script_actor_put(0, ENT_PLAYER, ent_x(e), ent_y(e));
  }
  anim_play(0, anim_for_type(ENT_PLAYER));
  script_emit(SEV_BOOT, 0);
  script_emit(SEV_LEVEL, 0);
}
static void play_update(void){
  script_update();
  if(script_actor_on(0))
    script_touch_map((s16)script_actor_x(0), script_actor_y(0), 8, 16);
  if(script_pull(SREQ_WIN)) script_enable(0);
}
static void play_draw(void){
  u8 i, n;
  const u8 *ents, *e;
  ents = level_ents();
  n = level_ent_n();
  anim_update();
  for(i = 0; i < n; i++){
    e = ent_ptr(ents, i);
    if(ent_type(e) == ENT_COIN && !script_taken(i))
      spr((s16)ent_x(e), ent_y(e), T_COIN, 1);
  }
  if(script_actor_on(0))
    anim_draw(0, (s16)script_actor_x(0), script_actor_y(0), 0);
  script_draw();
}
const Scene play_scene = { play_init, play_update, play_draw };
const Scene *game_boot(void){ return &play_scene; }
u8 game_autopilot(void){
  if(frame_count < 2) return 0;
  return BTN_RIGHT;
}
