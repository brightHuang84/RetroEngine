#ifndef RENDER_SOFT_H
#define RENDER_SOFT_H
#include <stdint.h>
#include "../engine/backend.h"
void soft_compose(uint32_t *fb);              /* 256x240, 0x00RRGGBB */
extern volatile u16 soft_snd_period;          /* read by the SDL audio callback */
extern volatile u8  soft_snd_vol;
#endif
