/* NES platform layer: read pad, run one engine tick, wait for vblank. */
#include "nes.h"
#include "../../engine/backend.h"
void wait_vblank(void){ u8 c = nmi_count; while(c == nmi_count); vram_len = 0; }
static u8 pad_read(void){ u8 i, v = 0; JOY1 = 1; JOY1 = 0; for(i = 0; i < 8; i++) v = (u8)((v << 1) | (JOY1 & 1)); return v; }
void main(void){
  ppu_ctrl = 0x80; PPUCTRL = 0x80;          /* NMI on */
  engine_init();
  for(;;){ engine_frame(pad_read()); wait_vblank(); }
}
