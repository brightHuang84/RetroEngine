#ifndef RENDER_SOFT_H
#define RENDER_SOFT_H
#include <stdint.h>
#include "../engine/backend.h"
void soft_compose(uint32_t *fb);              /* 256x240, 0x00RRGGBB */
/* Latest APU register image, written every frame. SDL mixes it; UEFI reads one channel for the PC speaker. */
extern volatile u16 soft_period[6];
extern volatile u8  soft_vol[6];
extern volatile u8  soft_duty[6];
#endif
