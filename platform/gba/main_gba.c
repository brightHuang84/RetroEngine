/* One engine tick per vblank (~59.73 Hz, treated as the engine's 60 Hz).
   GBA_AUTOPILOT (test ROMs only) feeds game_autopilot(); the shipped ROM reads the keys. */
#include "gba.h"
#include "../../engine/backend.h"

#ifndef GBA_AUTOPILOT
static u8 pad_read(void){
  u16 k = (u16)~REG_KEYINPUT;
  u8 p = 0;
  if(k & 0x0010) p = (u8)(p | BTN_RIGHT);
  if(k & 0x0020) p = (u8)(p | BTN_LEFT);
  if(k & 0x0080) p = (u8)(p | BTN_DOWN);
  if(k & 0x0040) p = (u8)(p | BTN_UP);
  if(k & 0x0008) p = (u8)(p | BTN_START);
  if(k & 0x0004) p = (u8)(p | BTN_SELECT);
  if(k & 0x0002) p = (u8)(p | BTN_B);
  if(k & 0x0001) p = (u8)(p | BTN_A);
  return p;                              /* L and R are unused */
}
#endif
static void wait_vblank(void){
  while(REG_VCOUNT >= 160);
  while(REG_VCOUNT < 160);
}
int main(void){
  engine_init();
  for(;;){
    wait_vblank();
#ifdef GBA_AUTOPILOT
    engine_frame(game_autopilot());
#else
    engine_frame(pad_read());
#endif
    gba_present();
  }
  return 0;
}
