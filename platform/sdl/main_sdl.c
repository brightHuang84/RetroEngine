/* PC platform: SDL2 window (3x), keyboard -> pad, 4-channel NES-style mix, fixed 60Hz.
   RETRO_TEST=<prefix>: deterministic test mode using game_autopilot(); saves
   <prefix>_a.bmp at frame RETRO_SHOT_A (default 60) and <prefix>_b.bmp at RETRO_SHOT_B (default 600), then quits.
   RETRO_WAV=<path>: write one 60Hz frame of mixed audio (44100 Hz mono s16) per engine tick.
   RETRO_MUS=<id>: lock playback to that song id (music_play from the game is redirected).
   RETRO_FRAMES=<n>: exit after n engine frames.
   RETRO_LEVEL=<n>: play scene loads level n (255 or unset = level 0).
   RETRO_CAM=<px>: play scene places the camera at this pixel (65535 or unset = follow).
   With RETRO_WAV set, the audio device is left closed so the file is the only consumer of the mixer. */
#include <SDL2/SDL.h>
#include <stdio.h>
#include "../../render/render_soft.h"
static uint32_t fb[SCREEN_W * SCREEN_H];

/* CPU cycles advanced per output sample, 16.16. 1789773 * 65536 / 44100. */
static const unsigned CYC_Q16 = (unsigned)(((unsigned long long)1789773 << 16) / 44100ull);
static const unsigned noise_timer[16] = {
  4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068
};
/* NES duty sequences, bit 0 is the first step. */
static const unsigned char DUTY_SEQ[4] = { 0x02, 0x06, 0x1E, 0xF9 };
static unsigned pulse_acc[2], tri_acc, noise_acc;
static unsigned char pulse_step[2], tri_step;
static unsigned short lfsr = 1;

static int pulse_bit(int idx, unsigned period, unsigned duty){
  unsigned thr;
  if(period < 8) period = 8;
  thr = (2u * (period + 1u)) << 16;
  pulse_acc[idx] += CYC_Q16;
  while(pulse_acc[idx] >= thr){
    pulse_acc[idx] -= thr;
    pulse_step[idx] = (unsigned char)((pulse_step[idx] + 1) & 7);
  }
  return (DUTY_SEQ[duty & 3] >> pulse_step[idx]) & 1;
}
static int tri_sample(unsigned period){
  unsigned thr, v;
  if(period < 1) period = 1;
  thr = (period + 1u) << 16;
  tri_acc += CYC_Q16;
  while(tri_acc >= thr){
    tri_acc -= thr;
    tri_step = (unsigned char)((tri_step + 1) & 31);
  }
  v = tri_step;
  if(v < 16) return (int)(15 - v) - 8;
  return (int)(v - 16) - 8;
}
static int noise_bit(unsigned idx, unsigned mode){
  unsigned thr, fb;
  if(idx > 15) idx = 15;
  thr = noise_timer[idx] << 16;
  noise_acc += CYC_Q16;
  while(noise_acc >= thr){
    noise_acc -= thr;
    fb = mode ? ((lfsr ^ (lfsr >> 6)) & 1) : ((lfsr ^ (lfsr >> 1)) & 1);
    lfsr = (unsigned short)((lfsr >> 1) | (fb << 14));
    if(!lfsr) lfsr = 1;
  }
  return (lfsr & 1) ? 0 : 1;
}
static void mix_n(Sint16 *dst, int n){
  unsigned per[4], vol[4], duty[4];
  int i, s;
  for(i = 0; i < 4; i++){
    per[i] = soft_period[i]; vol[i] = soft_vol[i]; duty[i] = soft_duty[i];
  }
  for(s = 0; s < n; s++){
    int mix = 0, bit;
    if(vol[0]){ bit = pulse_bit(0, per[0], duty[0]); mix += (bit ? (int)vol[0] : -(int)vol[0]) * 320; }
    if(vol[1]){ bit = pulse_bit(1, per[1], duty[1]); mix += (bit ? (int)vol[1] : -(int)vol[1]) * 320; }
    if(vol[2]) mix += tri_sample(per[2]) * (int)vol[2] * 22;
    if(vol[3]){
      bit = noise_bit(per[3], duty[3] & 1);
      mix += (bit ? (int)vol[3] : -(int)vol[3]) * 200;
    }
    if(mix > 32767) mix = 32767;
    if(mix < -32768) mix = -32768;
    dst[s] = (Sint16)mix;
  }
}
static void audio_cb(void *u, Uint8 *stream, int len){
  (void)u;
  mix_n((Sint16*)stream, len / 2);
}

static FILE *wav;
static unsigned long wav_bytes;
static void wav_open(const char *path){
  unsigned char h[44];
  unsigned long rate = 44100, bytes = rate * 2;
  int i;
  for(i = 0; i < 44; i++) h[i] = 0;
  h[0] = 'R'; h[1] = 'I'; h[2] = 'F'; h[3] = 'F';
  h[8] = 'W'; h[9] = 'A'; h[10] = 'V'; h[11] = 'E';
  h[12] = 'f'; h[13] = 'm'; h[14] = 't'; h[15] = ' ';
  h[16] = 16; h[20] = 1; h[22] = 1;
  h[24] = (unsigned char)rate; h[25] = (unsigned char)(rate >> 8); h[26] = (unsigned char)(rate >> 16);
  h[28] = (unsigned char)bytes; h[29] = (unsigned char)(bytes >> 8); h[30] = (unsigned char)(bytes >> 16);
  h[32] = 2; h[34] = 16;
  h[36] = 'd'; h[37] = 'a'; h[38] = 't'; h[39] = 'a';
  wav = fopen(path, "wb");
  if(!wav){ SDL_Log("RETRO_WAV: %s", path); return; }
  fwrite(h, 1, 44, wav);
  wav_bytes = 0;
}
static void wav_u32(long pos, unsigned long v){
  unsigned char b[4];
  b[0] = (unsigned char)v; b[1] = (unsigned char)(v >> 8);
  b[2] = (unsigned char)(v >> 16); b[3] = (unsigned char)(v >> 24);
  fseek(wav, pos, SEEK_SET); fwrite(b, 1, 4, wav);
}
static void step_audio(void){
  Sint16 buf[735];
  if(!wav) return;
  mix_n(buf, 735);
  fwrite(buf, 2, 735, wav);
  wav_bytes += 735u * 2u;
}
static void wav_close(void){
  if(!wav) return;
  wav_u32(4, 36 + wav_bytes);
  wav_u32(40, wav_bytes);
  fclose(wav); wav = 0;
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
  const char *wav_path = getenv("RETRO_WAV");
  const char *mus = getenv("RETRO_MUS");
  int shot_a = getenv("RETRO_SHOT_A") ? atoi(getenv("RETRO_SHOT_A")) : 60;
  int shot_b = getenv("RETRO_SHOT_B") ? atoi(getenv("RETRO_SHOT_B")) : 600;
  int max_frames = getenv("RETRO_FRAMES") ? atoi(getenv("RETRO_FRAMES")) : 0;
  int audio_frames = 0;
  SDL_Window *w; SDL_Renderer *r; SDL_Texture *t; SDL_AudioSpec want;
  Uint64 freq, prev, acc = 0, step; int run = 1, frames = 0;
  (void)argc; (void)argv;
  if(SDL_Init(SDL_INIT_VIDEO)){ SDL_Log("%s", SDL_GetError()); return 1; }
  if(wav_path) wav_open(wav_path);
  if(!wav_path && SDL_InitSubSystem(SDL_INIT_AUDIO) == 0){
    SDL_zero(want); want.freq = 44100; want.format = AUDIO_S16SYS; want.channels = 1; want.samples = 512; want.callback = audio_cb;
    if(SDL_OpenAudio(&want, NULL) == 0) SDL_PauseAudio(0);
  }
  w = SDL_CreateWindow("retro_engine", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, SCREEN_W * 3, SCREEN_H * 3, 0);
  r = SDL_CreateRenderer(w, -1, SDL_RENDERER_PRESENTVSYNC); if(!r) r = SDL_CreateRenderer(w, -1, SDL_RENDERER_SOFTWARE);
  SDL_RenderSetLogicalSize(r, SCREEN_W, SCREEN_H);
  t = SDL_CreateTexture(r, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING, SCREEN_W, SCREEN_H);
  if(mus) music_lock((u8)atoi(mus));
  if(getenv("RETRO_LEVEL")) test_level = (u8)atoi(getenv("RETRO_LEVEL"));
  if(getenv("RETRO_CAM")) test_cam = (u16)atoi(getenv("RETRO_CAM"));
  engine_init();
  freq = SDL_GetPerformanceFrequency(); step = freq / 60; prev = SDL_GetPerformanceCounter();
  while(run){
    SDL_Event e; Uint64 now;
    while(SDL_PollEvent(&e)){ if(e.type == SDL_QUIT) run = 0; if(e.type == SDL_KEYDOWN && e.key.keysym.sym == SDLK_ESCAPE) run = 0; }
    if(test){ engine_frame(game_autopilot()); step_audio(); audio_frames++; }
    else {
      now = SDL_GetPerformanceCounter(); acc += now - prev; prev = now;
      if(acc > step * 10) acc = step * 10;
      while(acc >= step){
        engine_frame(keys()); step_audio(); audio_frames++; acc -= step;
        if(max_frames && audio_frames >= max_frames) break;
      }
    }
    soft_compose(fb);
    SDL_UpdateTexture(t, NULL, fb, SCREEN_W * 4);
    SDL_RenderClear(r); SDL_RenderCopy(r, t, NULL, NULL); SDL_RenderPresent(r);
    if(!test) SDL_Delay(1);
    frames++;
    if(test && frames == shot_a) save(test, "a");
    if(test && frames == shot_b){ save(test, "b"); run = 0; }
    if(max_frames && audio_frames >= max_frames) run = 0;
  }
  wav_close();
  SDL_Quit(); return 0;
}
