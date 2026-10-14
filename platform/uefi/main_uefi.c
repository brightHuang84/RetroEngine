/* UEFI platform (gnu-efi): GOP framebuffer (integer scale, centered), SimpleTextInput,
   BootServices->Stall for ~60Hz. No key-up events: a key counts as held for HOLD frames.
   Audio is the PC speaker (PIT channel 2 + port 0x61): one note at a time.
   Priority is pulse2 (sound effects live there), then pulse1, then triangle.
   Noise has no pitch a beeper can play. QEMU: -audiodev <drv>,id=snd -machine pcspk-audiodev=snd */
#include <efi.h>
#include <efilib.h>
#include "../../render/render_soft.h"
#define HOLD 8
static uint32_t fb[SCREEN_W * SCREEN_H];
static EFI_GRAPHICS_OUTPUT_BLT_PIXEL row[SCREEN_W * 8];
static u8 hold[8];
static void press(int b){ hold[b] = (b >= 4) ? 4 : HOLD; }   /* bits: R L D U Start Select B A */
static unsigned char inb(unsigned short p){ unsigned char v; __asm__ volatile("inb %1, %0" : "=a"(v) : "d"(p)); return v; }
static void outb(unsigned short p, unsigned char v){ __asm__ volatile("outb %0, %1" : : "a"(v), "d"(p)); }
static unsigned last_div;
static void speaker_off(void){ outb(0x61, (unsigned char)(inb(0x61) & 0xFC)); last_div = 0; }
static void pcspk_update(void){
  static const int order[3] = { 1, 0, 2 };   /* pulse2, pulse1, triangle */
  int k, idx = -1; unsigned long long num; unsigned div; unsigned char sp;
  for(k = 0; k < 3; k++) if(soft_vol[order[k]]){ idx = order[k]; break; }
  if(idx < 0){ if(last_div) speaker_off(); return; }
  /* divisor = 1193182 / f, with f taken from the same NES timer the other backends use */
  num = (idx == 2 ? 38181824ULL : 19090912ULL) * ((unsigned long long)soft_period[idx] + 1ULL);
  div = (unsigned)(num / 1789773ULL);
  if(div < 1) div = 1;
  if(div > 65535) div = 65535;
  if(div == last_div) return;
  outb(0x43, 0xB6);
  outb(0x42, (unsigned char)div);
  outb(0x42, (unsigned char)(div >> 8));
  sp = inb(0x61); outb(0x61, (unsigned char)(sp | 0x03));
  last_div = div;
}
EFI_STATUS efi_main(EFI_HANDLE img, EFI_SYSTEM_TABLE *st){
  EFI_GUID gg = EFI_GRAPHICS_OUTPUT_PROTOCOL_GUID; EFI_GRAPHICS_OUTPUT_PROTOCOL *gop = NULL;
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL black = {0,0,0,0};
  UINT32 W, H, sc, ox, oy, x, y, r; EFI_INPUT_KEY k; u8 pad; int i;
  InitializeLib(img, st);
  uefi_call_wrapper(st->BootServices->SetWatchdogTimer, 4, 0, 0, 0, NULL);
  if(EFI_ERROR(uefi_call_wrapper(st->BootServices->LocateProtocol, 3, &gg, NULL, (void**)&gop))){ Print(L"No GOP\n"); return EFI_UNSUPPORTED; }
  W = gop->Mode->Info->HorizontalResolution; H = gop->Mode->Info->VerticalResolution;
  sc = W / SCREEN_W; if(H / SCREEN_H < sc) sc = H / SCREEN_H; if(sc < 1) sc = 1; if(sc > 8) sc = 8;
  ox = (W - SCREEN_W * sc) / 2; oy = (H - SCREEN_H * sc) / 2;
  uefi_call_wrapper(gop->Blt, 10, gop, &black, EfiBltVideoFill, 0, 0, 0, 0, W, H, 0);
  engine_init();
  for(;;){
    while(!EFI_ERROR(uefi_call_wrapper(st->ConIn->ReadKeyStroke, 2, st->ConIn, &k))){
      CHAR16 c = k.UnicodeChar;
      if(k.ScanCode == SCAN_RIGHT || c == 'd') press(0);
      else if(k.ScanCode == SCAN_LEFT || c == 'a') press(1);
      else if(k.ScanCode == SCAN_DOWN || c == 's') press(2);
      else if(k.ScanCode == SCAN_UP || c == 'w') press(3);
      else if(c == L'\r') press(4);
      else if(c == '\t') press(5);
      else if(c == 'x') press(6);
      else if(c == ' ' || c == 'z') press(7);
      else if(k.ScanCode == SCAN_ESC){ speaker_off(); return EFI_SUCCESS; }
    }
    pad = 0; for(i = 0; i < 8; i++) if(hold[i]){ pad |= (u8)(1 << i); hold[i]--; }
    engine_frame(pad);
    pcspk_update();
    soft_compose(fb);
    for(y = 0; y < SCREEN_H; y++){
      for(x = 0; x < SCREEN_W * sc; x++){ uint32_t c = fb[y * SCREEN_W + x / sc];
        row[x].Blue = c & 0xFF; row[x].Green = (c >> 8) & 0xFF; row[x].Red = (c >> 16) & 0xFF; row[x].Reserved = 0; }
      for(r = 0; r < sc; r++) uefi_call_wrapper(gop->Blt, 10, gop, row, EfiBltBufferToVideo, 0, 0, ox, oy + y * sc + r, SCREEN_W * sc, 1, 0);
    }
    uefi_call_wrapper(st->BootServices->Stall, 1, 16000);
  }
}
