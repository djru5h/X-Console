/* Noise generator effect: adds coloured noise (pink, white, brown, blue, violet, grey, vinyl crackle) to the audio
 * passing through, with low/high cut, stereo width and an input follower. Float audio, any block length. */
#pragma once

typedef struct noise_s noise_t;

noise_t *noise_create(float sample_rate);
void noise_destroy(noise_t *n);
/* Keys are the parameter keys of vst/params.json; values are numbers as text (an option's index for option lists),
 * "state" restores what get "state" returned. */
void noise_set(noise_t *n, const char *key, const char *val);
/* A key's value, "<key>_display" (its text) or "state". > 0 on success. */
int noise_get(noise_t *n, const char *key, char *buf, int len);
/* In place: l and r hold the input on entry and the output on return. */
void noise_process(noise_t *n, float *l, float *r, int frames);

enum { COLOR_PINK, COLOR_WHITE, COLOR_BROWN, COLOR_BLUE, COLOR_VIOLET, COLOR_GREY, COLOR_CRACKLE, NCOLORS };

/* The knob positions (0..100) the frequency and time controls map from, shared with the harness. */
float noise_lowcut_hz(float pos);    /* 0 = off; else 20 Hz .. 5 kHz */
float noise_highcut_hz(float pos);   /* 100 = off; else 200 Hz .. 20 kHz */
float noise_release_ms(float pos);   /* 5 ms .. 2 s */
float noise_density(float pos);      /* crackles per second, 0.5 .. 200 */
