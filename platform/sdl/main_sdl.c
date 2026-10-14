/* PC platform: SDL2 window (3x), keyboard -> pad, square-wave audio, fixed 60Hz.
   RETRO_TEST=<prefix>: deterministic test mode using game_autopilot(); saves
   <prefix>_a.bmp at frame RETRO_SHOT_A (default 60) and <prefix>_b.bmp at RETRO_SHOT_B (default 600), then quits. */
#include <SDL2/SDL.h>
#include "../../render/render_soft.h"
static uint32_t fb[SCREEN_W * SCREEN_H];
static double phase;
static void audio_cb(void *u, Uint8 *stream, int len){
  Sint16 *s = (Sint16*)stream; int i, n = len / 2;
  double f = soft_snd_vol ? 1789773.0 / (16.0 * (soft_snd_period + 1)) : 0;
  (void)u;
  for(i = 0; i < n; i++){
    phase += f / 44100.0; if(phase >= 1) phase -= 1;
    s[i] = (Sint16)(f ? ((phase < 0.5) ? 1 : -1) * soft_snd_vol * 300 : 0);
  }
}
static void save(const char *pre, const char *suf){
  char path[512]; SDL_Surface *s;
  SDL_snprintf(path, sizeof path, "%s_%s.bmp", pre, suf);
  s = SDL_CreateRGBSurfaceWithFormatFrom(fb, SCREEN_W, SCREEN_H, 32, SCREEN_W * 4, SDL_PIXELFORMAT_RGB888);
  SDL_SaveBMP(s, path); SDL_FreeSurface(s);
}
static u8 keys(void){
  const Uint8 *k = SDL_GetKeyboardState(NULL); u8 p = 0;
  if(k[SDL_SCANCODE_RIGHT] || k[SDL_SCANCODE_D]) p |= BTN_RIGHT;
  if(k[SDL_SCANCODE_LEFT]  || k[SDL_SCANCODE_A]) p |= BTN_LEFT;
  if(k[SDL_SCANCODE_UP]    || k[SDL_SCANCODE_W]) p |= BTN_UP;
  if(k[SDL_SCANCODE_DOWN]  || k[SDL_SCANCODE_S]) p |= BTN_DOWN;
  if(k[SDL_SCANCODE_Z] || k[SDL_SCANCODE_SPACE]) p |= BTN_A;
  if(k[SDL_SCANCODE_X]) p |= BTN_B;
  if(k[SDL_SCANCODE_RETURN]) p |= BTN_START;
  if(k[SDL_SCANCODE_RSHIFT] || k[SDL_SCANCODE_TAB]) p |= BTN_SELECT;
  return p;
}
int main(int argc, char **argv){
  const char *test = getenv("RETRO_TEST");
  int shot_a = getenv("RETRO_SHOT_A") ? atoi(getenv("RETRO_SHOT_A")) : 60;
  int shot_b = getenv("RETRO_SHOT_B") ? atoi(getenv("RETRO_SHOT_B")) : 600;
  SDL_Window *w; SDL_Renderer *r; SDL_Texture *t; SDL_AudioSpec want;
  Uint64 freq, prev, acc = 0, step; int run = 1, frames = 0;
  (void)argc; (void)argv;
  if(SDL_Init(SDL_INIT_VIDEO)){ SDL_Log("%s", SDL_GetError()); return 1; }
  if(SDL_InitSubSystem(SDL_INIT_AUDIO) == 0){
    SDL_zero(want); want.freq = 44100; want.format = AUDIO_S16SYS; want.channels = 1; want.samples = 512; want.callback = audio_cb;
    if(SDL_OpenAudio(&want, NULL) == 0) SDL_PauseAudio(0);
  }
  w = SDL_CreateWindow("retro_engine", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, SCREEN_W * 3, SCREEN_H * 3, 0);
  r = SDL_CreateRenderer(w, -1, SDL_RENDERER_PRESENTVSYNC); if(!r) r = SDL_CreateRenderer(w, -1, SDL_RENDERER_SOFTWARE);
  SDL_RenderSetLogicalSize(r, SCREEN_W, SCREEN_H);
  t = SDL_CreateTexture(r, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING, SCREEN_W, SCREEN_H);
  engine_init();
  freq = SDL_GetPerformanceFrequency(); step = freq / 60; prev = SDL_GetPerformanceCounter();
  while(run){
    SDL_Event e; Uint64 now;
    while(SDL_PollEvent(&e)){ if(e.type == SDL_QUIT) run = 0; if(e.type == SDL_KEYDOWN && e.key.keysym.sym == SDLK_ESCAPE) run = 0; }
    if(test){ engine_frame(game_autopilot()); }
    else {
      now = SDL_GetPerformanceCounter(); acc += now - prev; prev = now;
      if(acc > step * 10) acc = step * 10;
      while(acc >= step){ engine_frame(keys()); acc -= step; }
    }
    soft_compose(fb);
    SDL_UpdateTexture(t, NULL, fb, SCREEN_W * 4);
    SDL_RenderClear(r); SDL_RenderCopy(r, t, NULL, NULL); SDL_RenderPresent(r);
    if(!test) SDL_Delay(1);
    frames++;
    if(test && frames == shot_a) save(test, "a");
    if(test && frames == shot_b){ save(test, "b"); run = 0; }
  }
  SDL_Quit(); return 0;
}
