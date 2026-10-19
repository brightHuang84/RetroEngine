/* Sprite animation playback. Pictures and timings live in generated animdata.c.
   Six slots cover the player plus a few enemies without growing the RAM budget. */
#include "engine.h"

#define ANIM_SLOTS 6

extern unsigned char anim_length(unsigned char id);
extern unsigned char anim_looping(unsigned char id);
extern unsigned char anim_step(unsigned char id, unsigned char frame);
extern const signed char *anim_picture(unsigned char id, unsigned char frame);

static u8 a_id[ANIM_SLOTS];
static u8 a_fr[ANIM_SLOTS];
static u8 a_tm[ANIM_SLOTS];

void anim_reset(void){
  u8 i;
  for(i = 0; i < ANIM_SLOTS; i++){ a_id[i] = 255; a_fr[i] = 0; a_tm[i] = 0; }
}
void anim_play(u8 slot, u8 id){
  if(slot >= ANIM_SLOTS) return;
  if(a_id[slot] == id) return;
  a_id[slot] = id; a_fr[slot] = 0; a_tm[slot] = 0;
}
void anim_restart(u8 slot){
  if(slot >= ANIM_SLOTS) return;
  a_fr[slot] = 0; a_tm[slot] = 0;
}
u8 anim_current(u8 slot){ return slot < ANIM_SLOTS ? a_id[slot] : 255; }
void anim_update(void){
  u8 i, dur, len;
  for(i = 0; i < ANIM_SLOTS; i++){
    if(a_id[i] == 255) continue;
    len = anim_length(a_id[i]);
    if(!len) continue;
    dur = anim_step(a_id[i], a_fr[i]);
    if(!dur) dur = 1;
    a_tm[i]++;
    if(a_tm[i] < dur) continue;
    a_tm[i] = 0;
    if((u8)(a_fr[i] + 1) < len) a_fr[i]++;
    else if(anim_looping(a_id[i])) a_fr[i] = 0;
  }
}
void anim_draw(u8 slot, s16 x, s16 y, u8 flip){
  const s8 *pic;
  if(slot >= ANIM_SLOTS || a_id[slot] == 255) return;
  pic = anim_picture(a_id[slot], a_fr[slot]);
  if(pic) spr_meta(x, y, pic, flip);
}
