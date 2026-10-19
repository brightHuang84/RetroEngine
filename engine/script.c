/* Script bytecode VM. RAM is a handful of variables, two tasks, and four actors.
   Games without scripts still link the empty tables from scriptdata.c. */
#include "engine.h"

/* Bytecode numbers match tools/scriptc.py. */
#define OP_END 0
#define OP_SET 1
#define OP_ADD 2
#define OP_SFX 3
#define OP_MUS 4
#define OP_WAIT 5
#define OP_SHAKE 6
#define OP_DESPAWN 7
#define OP_SPAWN 8
#define OP_ANIM 9
#define OP_LEVEL 10
#define OP_WIN 11
#define OP_HURT 12
#define OP_LOSE 13
#define OP_TEXT 14
#define OP_JMP 15
#define OP_JEQ 16
#define OP_JNE 17
#define OP_JLT 18
#define OP_JGT 19
#define OP_JEQV 20
#define OP_RAND 21
#define OP_HOOK 22
#define OP_MOVE 23
#define OP_TIMER 24
#define OP_ACTOR 25
#define OP_JNHELD 26
#define OP_SCENE 27

#define TASKS 2
#define ACTORS 4
#define META 6

extern const unsigned char sdata[];
extern const unsigned short slen;
extern const unsigned char smeta[];
extern const unsigned char scount;
extern const unsigned short sginit[8];
extern const unsigned short slinit[8];
extern const char *const stext[];
extern const unsigned char sntext;
extern const unsigned char sregion[];
extern const unsigned char snregion;

static u16 gvar[8], lvar[8];
static u8 gone[4];
static u8 t_on[TASKS], t_id[TASKS], t_wait[TASKS];
static u16 t_pc[TASKS];
static u8 bind_slot, flags, active, level_id, shake_t, msg_t, rin;
static u8 goto_n, scene_n;
static const char *msg;
static u8 timer_left[2];
static u8 vlatch[4];
static void (*hooks[4])(u8);
static void script_update_vars(void);
static u8 a_on[ACTORS], a_type[ACTORS], a_y[ACTORS];
static u16 a_x[ACTORS];

static u16 var_get(u8 scope, u8 idx){
  if(idx >= 8) return 0;
  return scope ? lvar[idx] : gvar[idx];
}
static void var_set(u8 scope, u8 idx, u16 v){
  if(idx >= 8) return;
  if(scope) lvar[idx] = v; else gvar[idx] = v;
}
static void var_add(u8 scope, u8 idx, s16 d){
  var_set(scope, idx, (u16)((s16)var_get(scope, idx) + d));
}

void script_reset(void){
  u8 i;
  for(i = 0; i < 8; i++){ gvar[i] = sginit[i]; lvar[i] = slinit[i]; }
  for(i = 0; i < 4; i++) gone[i] = 0;
  for(i = 0; i < TASKS; i++) t_on[i] = 0;
  for(i = 0; i < ACTORS; i++) a_on[i] = 0;
  flags = 0; shake_t = 0; msg = 0; msg_t = 0; rin = 255;
  timer_left[0] = timer_left[1] = 0;
  vlatch[0] = vlatch[1] = vlatch[2] = vlatch[3] = 0;
}
void script_level_reset(void){
  u8 i;
  for(i = 0; i < 8; i++) lvar[i] = slinit[i];
  for(i = 0; i < 4; i++) gone[i] = 0;
  for(i = 0; i < TASKS; i++) t_on[i] = 0;
  msg = 0; msg_t = 0; rin = 255;
  timer_left[0] = timer_left[1] = 0;
  vlatch[0] = vlatch[1] = vlatch[2] = vlatch[3] = 0;
}
void script_enable(u8 on){ active = on ? 1 : 0; }
void script_set_level(u8 n){ level_id = n; }
void script_set(u8 scope, u8 idx, u16 v){ var_set(scope, idx, v); }
u16 script_get(u8 scope, u8 idx){ return var_get(scope, idx); }
void script_bind(u8 slot){ bind_slot = slot; }
void script_set_hook(u8 id, void (*fn)(u8)){ if(id < 4) hooks[id] = fn; }
u8 script_taken(u8 slot){ return (u8)((gone[slot >> 3] >> (slot & 7)) & 1); }
static void take(u8 slot){ gone[slot >> 3] = (u8)(gone[slot >> 3] | (u8)(1 << (slot & 7))); }
u8 script_pull(u8 mask){ u8 v = (u8)(flags & mask); flags = (u8)(flags & (u8)~mask); return v; }
s8 script_shake(void){ return shake_t ? (s8)((shake_t & 2) ? 2 : -2) : 0; }
u8 script_level_target(void){ return goto_n; }
u8 script_scene(void){ return scene_n; }

void script_actor_put(u8 slot, u8 type, u16 x, u8 y){
  if(slot >= ACTORS) return;
  a_on[slot] = 1; a_type[slot] = type; a_x[slot] = x; a_y[slot] = y;
}
u8 script_actor_on(u8 slot){ return slot < ACTORS && a_on[slot]; }
u16 script_actor_x(u8 slot){ return slot < ACTORS ? a_x[slot] : 0; }
u8 script_actor_y(u8 slot){ return slot < ACTORS ? a_y[slot] : 0; }
u8 script_actor_type(u8 slot){ return slot < ACTORS ? a_type[slot] : 0; }

static u8 level_ok(u8 i){
  u8 lv = smeta[(u16)i * META + 2];
  return (u8)(lv == 255 || lv == level_id);
}
static u8 fetch(u8 t){
  u8 v;
  if(!t_on[t] || t_pc[t] >= slen){ t_on[t] = 0; return 0; }
  v = sdata[t_pc[t]];
  t_pc[t] = (u16)(t_pc[t] + 1);
  return v;
}
static u16 fetch16(u8 t){
  u8 lo = fetch(t), hi = fetch(t);
  return (u16)(lo | ((u16)hi << 8));
}

static void run_task(u8 t);

static u8 start_index(u8 index){
  u8 t;
  u16 entry;
  if(index >= scount) return 0;
  for(t = 0; t < TASKS; t++) if(t_on[t] && t_id[t] == index) return 0;
  for(t = 0; t < TASKS; t++) if(!t_on[t]){
    entry = (u16)(smeta[(u16)index * META + 4] | ((u16)smeta[(u16)index * META + 5] << 8));
    t_on[t] = 1; t_id[t] = index; t_pc[t] = entry; t_wait[t] = 0;
    run_task(t);
    return 1;
  }
  return 0;
}

u8 script_emit(u8 ev, u8 arg){
  u8 i, n = 0;
  for(i = 0; i < scount; i++){
    if(smeta[(u16)i * META] != ev) continue;
    if(ev != SEV_BOOT && ev != SEV_LEVEL && ev != SEV_FRAME && smeta[(u16)i * META + 1] != arg) continue;
    if(!level_ok(i)) continue;
    if(start_index(i)) n++;
  }
  return n;
}

u8 script_listening(u8 ev, u8 arg){
  u8 i;
  for(i = 0; i < scount; i++){
    if(smeta[(u16)i * META] == ev && smeta[(u16)i * META + 1] == arg && level_ok(i)) return 1;
  }
  return 0;
}

static void run_task(u8 t){
  u8 steps = 0, op, scope, idx, slot, id;
  u16 imm, dest, x;
  s16 delta;
  while(t_on[t] && !t_wait[t] && steps < 64){
    steps++;
    op = fetch(t);
    if(!t_on[t]) return;
    if(op == OP_END){ t_on[t] = 0; return; }
    if(op == OP_SET){ scope = fetch(t); idx = fetch(t); var_set(scope, idx, fetch16(t)); }
    else if(op == OP_ADD){ scope = fetch(t); idx = fetch(t); delta = (s16)fetch16(t); var_add(scope, idx, delta); }
    else if(op == OP_SFX) sfx(fetch(t));
    else if(op == OP_MUS){ id = fetch(t); if(id == 255) music_stop(); else music_play(id); }
    else if(op == OP_WAIT){ t_wait[t] = fetch(t); if(!t_wait[t]) t_wait[t] = 1; return; }
    else if(op == OP_SHAKE) shake_t = fetch(t);
    else if(op == OP_DESPAWN) take(bind_slot);
    else if(op == OP_SPAWN){
      id = fetch(t); x = fetch16(t); idx = fetch(t);
      for(slot = 0; slot < ACTORS; slot++) if(!a_on[slot]){
        script_actor_put(slot, id, x, (u8)idx); break;
      }
    }
    else if(op == OP_ANIM){ slot = fetch(t); id = fetch(t); anim_play(slot, id); }
    else if(op == OP_LEVEL){
      id = fetch(t);
      if(id == 254) flags = (u8)(flags | SREQ_ADVANCE);
      else { goto_n = id; flags = (u8)(flags | SREQ_LEVEL); }
    }
    else if(op == OP_WIN) flags = (u8)(flags | SREQ_WIN);
    else if(op == OP_HURT) flags = (u8)(flags | SREQ_HURT);
    else if(op == OP_LOSE) flags = (u8)(flags | SREQ_LOSE);
    else if(op == OP_TEXT){
      id = fetch(t); msg_t = fetch(t);
      msg = (id < sntext) ? stext[id] : 0;
      if(!msg_t) msg_t = 1;
    }
    else if(op == OP_JMP) t_pc[t] = fetch16(t);
    else if(op == OP_JEQ || op == OP_JNE || op == OP_JLT || op == OP_JGT){
      scope = fetch(t); idx = fetch(t); imm = fetch16(t); dest = fetch16(t);
      x = var_get(scope, idx);
      if((op == OP_JEQ && x == imm) || (op == OP_JNE && x != imm) ||
         (op == OP_JLT && x < imm) || (op == OP_JGT && x > imm)) t_pc[t] = dest;
    }
    else if(op == OP_JEQV){
      scope = fetch(t); idx = fetch(t); id = fetch(t); slot = fetch(t); dest = fetch16(t);
      if(var_get(scope, idx) == var_get(id, slot)) t_pc[t] = dest;
    }
    else if(op == OP_RAND){
      scope = fetch(t); idx = fetch(t); id = fetch(t);
      if(!id) id = 1;
      var_set(scope, idx, (u16)(rnd() % id));
    }
    else if(op == OP_HOOK){
      id = fetch(t); slot = fetch(t);
      if(id < 4 && hooks[id]) hooks[id](slot);
    }
    else if(op == OP_MOVE){
      slot = fetch(t); delta = (s8)fetch(t); idx = fetch(t);
      if(slot < ACTORS && a_on[slot]){
        a_x[slot] = (u16)((s16)a_x[slot] + delta);
        a_y[slot] = (u8)((s16)a_y[slot] + (s8)idx);
      }
    }
    else if(op == OP_TIMER){ id = fetch(t) & 1; timer_left[id] = fetch(t); }
    else if(op == OP_ACTOR){
      slot = fetch(t); id = fetch(t); x = fetch16(t); idx = fetch(t); scope = fetch(t);
      script_actor_put(slot, id, x, (u8)idx);
      if(scope != 255) anim_play(slot, scope);
    }
    else if(op == OP_JNHELD){
      id = fetch(t); dest = fetch16(t);
      if((pad_held & id) == 0) t_pc[t] = dest;
    }
    else if(op == OP_SCENE){ scene_n = fetch(t); flags = (u8)(flags | SREQ_SCENE); }
    else { t_on[t] = 0; return; }
  }
}

void script_update(void){
  u8 i, t, ev;
  if(shake_t) shake_t--;
  if(msg_t){ msg_t--; if(!msg_t) msg = 0; }
  for(i = 0; i < 2; i++) if(timer_left[i]){
    timer_left[i]--;
    if(!timer_left[i]) script_emit(SEV_TIMER, i);
  }
  for(t = 0; t < TASKS; t++) if(t_on[t] && t_wait[t]){
    t_wait[t]--;
    if(!t_wait[t]) run_task(t);
  }
  if(!active) return;
  for(i = 0; i < scount; i++){
    ev = smeta[(u16)i * META];
    if(!level_ok(i)) continue;
    if(ev == SEV_FRAME) start_index(i);
    else if(ev == SEV_BUTTON && (pad_pressed & smeta[(u16)i * META + 1])) start_index(i);
  }
  script_update_vars();
}

void script_region_at(s16 x, s16 y){
  u8 i, id, found = 0;
  u16 rx;
  if(!active) return;
  for(i = 0; i < snregion; i++){
    id = sregion[(u16)i * 7];
    rx = (u16)(sregion[(u16)i * 7 + 2] | ((u16)sregion[(u16)i * 7 + 3] << 8));
    if(x >= (s16)rx && x < (s16)(rx + sregion[(u16)i * 7 + 5]) &&
       y >= sregion[(u16)i * 7 + 4] && y < (s16)(sregion[(u16)i * 7 + 4] + sregion[(u16)i * 7 + 6])){
      found = 1;
      if(rin != id){ script_emit(SEV_REGION, id); rin = id; }
    }
  }
  if(!found) rin = 255;
}

void script_touch_map(s16 x, s16 y, u8 w, u8 h){
  u8 i, n;
  const u8 *ents, *e;
  ents = level_ents();
  n = level_ent_n();
  if(!ents) return;
  for(i = 0; i < n; i++){
    if(script_taken(i)) continue;
    e = ent_ptr(ents, i);
    if(aabb(x, y, w, h, (s16)ent_x(e), ent_y(e), 8, 8)){
      bind_slot = i;
      script_emit(SEV_TOUCH, ent_type(e));
    }
  }
}

void script_draw(void){
  if(msg && msg_t) spr_text(48, 72, msg, 3);
}

static void script_update_vars(void){
  u8 i, arg, scope, idx, extra, bit, on;
  for(i = 0; i < scount; i++){
    if(smeta[(u16)i * META] != SEV_VAR || !level_ok(i)) continue;
    arg = smeta[(u16)i * META + 1];
    scope = (u8)(arg >> 7); idx = (u8)(arg & 7);
    extra = smeta[(u16)i * META + 3];
    on = (u8)((var_get(scope, idx) & 255) == extra);
    bit = (u8)(1 << (i & 7));
    if(on && !(vlatch[i >> 3] & bit)) start_index(i);
    if(on) vlatch[i >> 3] = (u8)(vlatch[i >> 3] | bit);
    else vlatch[i >> 3] = (u8)(vlatch[i >> 3] & (u8)~bit);
  }
}
