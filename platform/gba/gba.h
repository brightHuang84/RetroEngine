/* GBA I/O for the platform layer. Game code never includes this. */
#ifndef GBA_H
#define GBA_H
#include "../../engine/engine.h"

typedef unsigned int u32;

#define REG_DISPCNT  (*(volatile u16 *)0x04000000)
#define REG_DISPSTAT (*(volatile u16 *)0x04000004)
#define REG_VCOUNT   (*(volatile u16 *)0x04000006)
#define REG_BG0CNT   (*(volatile u16 *)0x04000008)
#define REG_BG0HOFS  (*(volatile u16 *)0x04000010)
#define REG_BG0VOFS  (*(volatile u16 *)0x04000012)
#define REG_KEYINPUT (*(volatile u16 *)0x04000130)
#define REG_IE       (*(volatile u16 *)0x04000200)
#define REG_IF       (*(volatile u16 *)0x04000202)
#define REG_IME      (*(volatile u16 *)0x04000208)

#define REG_SND1CNT_L (*(volatile u16 *)0x04000060)
#define REG_SND1CNT_H (*(volatile u16 *)0x04000062)
#define REG_SND1CNT_X (*(volatile u16 *)0x04000064)
#define REG_SND2CNT_L (*(volatile u16 *)0x04000068)
#define REG_SND2CNT_H (*(volatile u16 *)0x0400006C)
#define REG_SND3CNT_L (*(volatile u16 *)0x04000070)
#define REG_SND3CNT_H (*(volatile u16 *)0x04000072)
#define REG_SND3CNT_X (*(volatile u16 *)0x04000074)
#define REG_SND4CNT_L (*(volatile u16 *)0x04000078)
#define REG_SND4CNT_H (*(volatile u16 *)0x0400007C)
#define REG_SNDCNT_L  (*(volatile u16 *)0x04000080)
#define REG_SNDCNT_H  (*(volatile u16 *)0x04000082)
#define REG_SNDCNT_X  (*(volatile u16 *)0x04000084)
#define WAVE_RAM      ((volatile u16 *)0x04000090)

#define PAL_BG  ((volatile u16 *)0x05000000)
#define PAL_OBJ ((volatile u16 *)0x05000200)
#define VRAM_BG ((volatile u32 *)0x06000000)
#define VRAM_OBJ ((volatile u32 *)0x06010000)
#define MAP_BASE ((volatile u32 *)0x06004000) /* screenblocks 8 and 9, 512x256 */
#define OAM_MEM ((volatile u32 *)0x07000000)

/* Playfield vertical scroll, latched by the HBlank handler on line 15. */
extern volatile u16 gba_vofs_play;
void gba_present(void);
#endif
