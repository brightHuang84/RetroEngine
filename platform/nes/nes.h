#ifndef NES_H
#define NES_H
#include "../../engine/engine.h"
#define PPUCTRL   (*(volatile u8*)0x2000)
#define PPUMASK   (*(volatile u8*)0x2001)
#define PPUADDR   (*(volatile u8*)0x2006)
#define PPUDATA   (*(volatile u8*)0x2007)
#define JOY1      (*(volatile u8*)0x4016)
#define APU(a)    (*(volatile u8*)(a))
extern volatile u8 nmi_count, vram_len, scroll_x, ppu_ctrl;
#pragma zpsym("nmi_count")
#pragma zpsym("vram_len")
#pragma zpsym("scroll_x")
#pragma zpsym("ppu_ctrl")
extern u8 vram_buf[];
void wait_vblank(void);
#endif
