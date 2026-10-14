/* UEFI platform (gnu-efi): GOP framebuffer (integer scale, centered), SimpleTextInput,
   BootServices->Stall for ~60Hz. No key-up events: a key counts as held for HOLD frames. Silent. */
#include <efi.h>
#include <efilib.h>
#include "../../render/render_soft.h"
#define HOLD 8
static uint32_t fb[SCREEN_W * SCREEN_H];
static EFI_GRAPHICS_OUTPUT_BLT_PIXEL row[SCREEN_W * 8];
static u8 hold[8];
static void press(int b){ hold[b] = (b >= 4) ? 4 : HOLD; }   /* bits: R L D U Start Select B A */
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
      else if(k.ScanCode == SCAN_ESC) return EFI_SUCCESS;
    }
    pad = 0; for(i = 0; i < 8; i++) if(hold[i]){ pad |= (u8)(1 << i); hold[i]--; }
    engine_frame(pad);
    soft_compose(fb);
    for(y = 0; y < SCREEN_H; y++){
      for(x = 0; x < SCREEN_W * sc; x++){ uint32_t c = fb[y * SCREEN_W + x / sc];
        row[x].Blue = c & 0xFF; row[x].Green = (c >> 8) & 0xFF; row[x].Red = (c >> 16) & 0xFF; row[x].Reserved = 0; }
      for(r = 0; r < sc; r++) uefi_call_wrapper(gop->Blt, 10, gop, row, EfiBltBufferToVideo, 0, 0, ox, oy + y * sc + r, SCREEN_W * sc, 1, 0);
    }
    uefi_call_wrapper(st->BootServices->Stall, 1, 16000);
  }
}
