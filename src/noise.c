/* Noise generator effect (noise.h). Two independent noise streams (A, B) are made per sample, each colour from the same
 * white source, and mixed to left/right by the width (L = cA + sB, R = cA - sB, so the level stays put and full width
 * is uncorrelated). Then a low cut (always at least a 15 Hz subsonic filter) and a high cut, the level, the input
 * follower, and the input passed through. Every colour runs all the time, so a colour change crossfades without a
 * click; each is scaled so its output peak at Level 0 dB is ~full scale, so Level reads as the noise's PEAK in dBFS
 * (a peak meter shows the Level setting; see NORM). */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "noise.h"

enum { P_ON, P_COLOR, P_LEVEL, P_DRY, P_LOWCUT, P_HIGHCUT, P_WIDTH, P_FOLLOW, P_RELEASE, P_DENSITY, NPARAMS };

static const struct { const char *key; float min, max, def; } PARAMS[NPARAMS] = {
    {"on", 0, 1, 1},          {"color", 0, NCOLORS - 1, COLOR_PINK}, {"level", -60, 0, -24}, {"dry", -60, 6, 0},
    {"lowcut", 0, 100, 0},    {"highcut", 0, 100, 100},              {"width", 0, 100, 100},  {"follow", 0, 100, 0},
    {"release", 0, 100, 50},  {"density", 0, 100, 47},
};
static const char *COLOR_NAMES[NCOLORS] = {[COLOR_PINK] = "Pink", [COLOR_WHITE] = "White", [COLOR_BROWN] = "Brown",
    [COLOR_BLUE] = "Blue", [COLOR_VIOLET] = "Violet", [COLOR_GREY] = "Grey", [COLOR_CRACKLE] = "Crackle"};

/* Calibrated so a peak meter reads the Level setting (user, 2026-11-08, Studio-One-style gain-staging). Each colour
 * normalised to its ~100 ms window peak (the MPC meter's effective integration; median max|out| over 600 s, 44.1 kHz,
 * scratchpad/calib_peak3.c) so Level ~= metered peak in dBFS; Crackle uses its sparse pop peak (absmax) instead.
 * Was 1/RMS; trade-off: colours no longer match in loudness at the same Level (high-crest Pink/Brown quieter in RMS). */
static const float NORM[NCOLORS] = {[COLOR_PINK] = 0.1760f, [COLOR_WHITE] = 0.7018f, [COLOR_BROWN] = 0.0552f,
    [COLOR_BLUE] = 0.3105f, [COLOR_VIOLET] = 0.3876f, [COLOR_GREY] = 0.2989f, [COLOR_CRACKLE] = 1.5154f};

#define XFADE 1024   /* samples a colour change crossfades over */

typedef struct { float b0, b1, b2, a1, a2, z1, z2; } biquad_t;

static float bq_run(biquad_t *q, float x) {
    float y = q->b0 * x + q->z1;
    q->z1 = q->b1 * x - q->a1 * y + q->z2;
    q->z2 = q->b2 * x - q->a2 * y;
    return y;
}

/* RBJ cookbook designs; the state is kept, so a change mid-stream carries on. */
enum { BQ_LP, BQ_HP, BQ_PEAK, BQ_LOWSHELF, BQ_HIGHSHELF };
static void bq_design(biquad_t *q, int type, float sr, float f, float qv, float gain_db) {
    double w = 2 * M_PI * f / sr, cw = cos(w), sw = sin(w), A = pow(10, gain_db / 40), al = sw / (2 * qv);
    double b0, b1, b2, a0, a1, a2, sq = 2 * sqrt(A) * al;
    switch (type) {
    case BQ_LP: b0 = (1 - cw) / 2; b1 = 1 - cw; b2 = b0; a0 = 1 + al; a1 = -2 * cw; a2 = 1 - al; break;
    case BQ_HP: b0 = (1 + cw) / 2; b1 = -(1 + cw); b2 = b0; a0 = 1 + al; a1 = -2 * cw; a2 = 1 - al; break;
    case BQ_PEAK: b0 = 1 + al * A; b1 = -2 * cw; b2 = 1 - al * A; a0 = 1 + al / A; a1 = -2 * cw; a2 = 1 - al / A; break;
    case BQ_LOWSHELF:
        b0 = A * ((A + 1) - (A - 1) * cw + sq); b1 = 2 * A * ((A - 1) - (A + 1) * cw); b2 = A * ((A + 1) - (A - 1) * cw - sq);
        a0 = (A + 1) + (A - 1) * cw + sq; a1 = -2 * ((A - 1) + (A + 1) * cw); a2 = (A + 1) + (A - 1) * cw - sq;
        break;
    default:   /* BQ_HIGHSHELF */
        b0 = A * ((A + 1) + (A - 1) * cw + sq); b1 = -2 * A * ((A - 1) + (A + 1) * cw); b2 = A * ((A + 1) + (A - 1) * cw - sq);
        a0 = (A + 1) - (A - 1) * cw + sq; a1 = 2 * ((A - 1) - (A + 1) * cw); a2 = (A + 1) - (A - 1) * cw - sq;
        break;
    }
    q->b0 = b0 / a0; q->b1 = b1 / a0; q->b2 = b2 / a0; q->a1 = a1 / a0; q->a2 = a2 / a0;
}

/* One noise stream: every colour from one white source. */
typedef struct {
    uint32_t rng;
    float pk[7], pink_prev, white_prev, brown;
    biquad_t grey[3];
    float ck_env, ck_dec;          /* crackle: the current click's envelope and decay */
    biquad_t ck_hp;
    biquad_t sub[NCOLORS];         /* the 15 Hz filter calibration measures after: only the harness uses it */
} stream_t;

static uint32_t rnd(uint32_t *s) { uint32_t x = *s; x ^= x << 13; x ^= x >> 17; x ^= x << 5; return *s = x; }
static float rnd_bi(uint32_t *s) { return (int32_t)rnd(s) * (1.0f / 2147483648.0f); }   /* -1 .. 1 */
static float rnd_uni(uint32_t *s) { return (rnd(s) >> 8) * (1.0f / 16777216.0f); }       /* 0 .. 1 */

struct noise_s {
    float sr, p[NPARAMS];
    stream_t st[2];
    float brown_a, ck_p;
    int color, prev_color, xf;     /* xf: samples of crossfade from prev_color left */
    biquad_t hp[2], lp[2];
    float g_noise, g_dry, g_follow, env, theta;   /* smoothed */
    float theta_at, cs, sn;                       /* cos/sin of the width angle, for theta_at */
    float k_smooth, k_att, k_rel;
};

float noise_lowcut_hz(float pos) { return pos <= 0 ? 0 : 20 * powf(250, pos / 100); }
float noise_highcut_hz(float pos) { return pos >= 100 ? 0 : 200 * powf(100, pos / 100); }
float noise_release_ms(float pos) { return 5 * powf(400, pos / 100); }
float noise_density(float pos) { return 0.5f * powf(400, pos / 100); }

static void stream_init(stream_t *s, uint32_t seed, float sr) {
    memset(s, 0, sizeof *s);
    s->rng = seed;
    /* Grey: white shaped to roughly the inverse of an equal-loudness curve (lows up, a dip near 3.5 kHz, highs up a
     * little), so it sounds about as loud at every pitch. */
    bq_design(&s->grey[0], BQ_LOWSHELF, sr, 180, 0.5f, 18);
    bq_design(&s->grey[1], BQ_PEAK, sr, 3500, 1.0f, -6);
    bq_design(&s->grey[2], BQ_HIGHSHELF, sr, 9000, 0.7f, 7);
    bq_design(&s->ck_hp, BQ_HP, sr, 500, 0.7071f, 0);
    for (int c = 0; c < NCOLORS; c++) bq_design(&s->sub[c], BQ_HP, sr, 15, 0.7071f, 0);
}

/* One sample of every colour, unscaled. */
static void stream_gen(noise_t *n, stream_t *s, float out[NCOLORS]) {
    float w = rnd_bi(&s->rng);
    out[COLOR_WHITE] = w;
    /* Pink: Paul Kellet's refined filter (within 0.05 dB of -3 dB/octave above 9 Hz at 44.1 kHz). */
    float *b = s->pk;
    b[0] = 0.99886f * b[0] + w * 0.0555179f;
    b[1] = 0.99332f * b[1] + w * 0.0750759f;
    b[2] = 0.96900f * b[2] + w * 0.1538520f;
    b[3] = 0.86650f * b[3] + w * 0.3104856f;
    b[4] = 0.55000f * b[4] + w * 0.5329522f;
    b[5] = -0.7616f * b[5] - w * 0.0168980f;
    float pink = b[0] + b[1] + b[2] + b[3] + b[4] + b[5] + b[6] + w * 0.5362f;
    b[6] = w * 0.115926f;
    out[COLOR_PINK] = pink;
    /* Brown: a leaky integrator (-6 dB/octave above 20 Hz). */
    s->brown = n->brown_a * s->brown + w;
    out[COLOR_BROWN] = s->brown;
    /* Blue and violet: pink and white differentiated (+6 dB/octave each: +3 and +6 dB/octave). */
    out[COLOR_BLUE] = pink - s->pink_prev;
    s->pink_prev = pink;
    out[COLOR_VIOLET] = w - s->white_prev;
    s->white_prev = w;
    out[COLOR_GREY] = bq_run(&s->grey[2], bq_run(&s->grey[1], bq_run(&s->grey[0], w)));
    /* Crackle: clicks at random times (density per second), each a burst of noise that dies away in 0.05-0.6 ms,
     * mostly faint ticks with the odd loud pop (amplitude u^4: one click in eight is within 6 dB of the loudest),
     * high-passed at 500 Hz (12 dB/octave) so they tick rather than thump. */
    if (rnd_uni(&s->rng) < n->ck_p) {
        float u = rnd_uni(&s->rng);
        s->ck_env = u * u * u * u;
        s->ck_dec = expf(-1 / ((0.00005f + 0.00055f * rnd_uni(&s->rng)) * n->sr));
    }
    float c = s->ck_env * rnd_bi(&s->rng);
    s->ck_env *= s->ck_dec;
    if (s->ck_env < 1e-6f) s->ck_env = 0;
    out[COLOR_CRACKLE] = bq_run(&s->ck_hp, c);
}

static void update_filters(noise_t *n) {
    float lo = noise_lowcut_hz(n->p[P_LOWCUT]), hi = noise_highcut_hz(n->p[P_HIGHCUT]);
    for (int ch = 0; ch < 2; ch++) {
        bq_design(&n->hp[ch], BQ_HP, n->sr, lo > 0 ? lo : 15, 0.7071f, 0);
        if (hi > 0) bq_design(&n->lp[ch], BQ_LP, n->sr, hi, 0.7071f, 0);
    }
}

static float clampf(float v, float lo, float hi) { return v < lo ? lo : v > hi ? hi : v; }

/* One step of a glide from g to t. A float glide stalls once its step is under half the float spacing at g: near 1 that
 * is 0.003% short, which left Follow's silence at -104 dB. So it snaps to t within 0.01% (-80 dB), and a glide to 0
 * snaps at 1e-9, out of denormals. */
static float smooth(float g, float t, float k) {
    g += (t - g) * k;
    return fabsf(g - t) <= 1e-4f * fabsf(t) + 1e-9f ? t : g;
}
static float db_gain(float db) { return powf(10, db / 20); }

noise_t *noise_create(float sr) {
    noise_t *n = calloc(1, sizeof *n);
    if (!n) return NULL;
    n->sr = sr;
    for (int i = 0; i < NPARAMS; i++) n->p[i] = PARAMS[i].def;
    stream_init(&n->st[0], 0x9e3779b9u, sr);
    stream_init(&n->st[1], 0x7f4a7c15u, sr);
    n->brown_a = expf(-2 * (float)M_PI * 20 / sr);
    n->ck_p = noise_density(n->p[P_DENSITY]) / sr;
    n->color = n->prev_color = (int)n->p[P_COLOR];
    n->k_smooth = 1 - expf(-1 / (0.02f * sr));
    n->k_att = 1 - expf(-1 / (0.001f * sr));
    n->k_rel = 1 - expf(-1 / (noise_release_ms(n->p[P_RELEASE]) * 0.001f * sr));
    n->g_dry = 1;
    n->theta = n->theta_at = n->p[P_WIDTH] / 100 * (float)M_PI / 4;
    n->cs = cosf(n->theta);
    n->sn = sinf(n->theta);
    update_filters(n);
    return n;
}

void noise_destroy(noise_t *n) { free(n); }

static int find_param(const char *key) {
    for (int i = 0; i < NPARAMS; i++)
        if (!strcmp(key, PARAMS[i].key)) return i;
    return -1;
}

void noise_set(noise_t *n, const char *key, const char *val) {
    if (!strcmp(key, "state")) {   /* "key=value;key=value;..." from get "state" */
        char buf[512], *save = NULL;
        snprintf(buf, sizeof buf, "%s", val);
        for (char *t = strtok_r(buf, ";", &save); t; t = strtok_r(NULL, ";", &save)) {
            char *eq = strchr(t, '=');
            if (eq) *eq = 0, noise_set(n, t, eq + 1);
        }
        return;
    }
    int i = find_param(key);
    if (i < 0) return;
    float v = clampf(strtof(val, NULL), PARAMS[i].min, PARAMS[i].max);
    if (i == P_ON || i == P_COLOR) v = roundf(v);
    n->p[i] = v;
    switch (i) {
    case P_COLOR:
        if ((int)v != n->color) {
            n->prev_color = n->color;   /* a change during a crossfade starts a new one from the current colour */
            n->color = (int)v;
            n->xf = XFADE;
        }
        break;
    case P_LOWCUT: case P_HIGHCUT: update_filters(n); break;
    case P_RELEASE: n->k_rel = 1 - expf(-1 / (noise_release_ms(v) * 0.001f * n->sr)); break;
    case P_DENSITY: n->ck_p = noise_density(v) / n->sr; break;
    }
}

static int fmt_hz(char *buf, int len, float hz) {
    return hz >= 1000 ? snprintf(buf, len, "%.1f kHz", hz / 1000) : snprintf(buf, len, "%.0f Hz", hz);
}

int noise_get(noise_t *n, const char *key, char *buf, int len) {
    if (!strcmp(key, "state")) {
        int o = 0;
        for (int i = 0; i < NPARAMS && o < len; i++) o += snprintf(buf + o, len - o, "%s%s=%g", i ? ";" : "", PARAMS[i].key, n->p[i]);
        return o < len ? o : -1;
    }
    int i = find_param(key);
    if (i >= 0) return snprintf(buf, len, "%g", n->p[i]);
    size_t kl = strlen(key);
    if (kl < 9 || strcmp(key + kl - 8, "_display")) return 0;
    char k[32];
    snprintf(k, sizeof k, "%.*s", (int)(kl - 8), key);
    if ((i = find_param(k)) < 0) return 0;
    float v = n->p[i];
    switch (i) {
    case P_ON: return snprintf(buf, len, "%s", v > 0.5f ? "On" : "Off");
    case P_COLOR: return snprintf(buf, len, "%s", COLOR_NAMES[(int)v]);
    case P_LEVEL: return snprintf(buf, len, "%.1f dB", v);
    case P_DRY: return v <= PARAMS[P_DRY].min ? snprintf(buf, len, "Off") : snprintf(buf, len, "%.1f dB", v);
    case P_LOWCUT: return v <= 0 ? snprintf(buf, len, "Off") : fmt_hz(buf, len, noise_lowcut_hz(v));
    case P_HIGHCUT: return v >= 100 ? snprintf(buf, len, "Off") : fmt_hz(buf, len, noise_highcut_hz(v));
    case P_WIDTH: return v <= 0 ? snprintf(buf, len, "Mono") : snprintf(buf, len, "%.0f%%", v);
    case P_FOLLOW: return v <= 0 ? snprintf(buf, len, "Off") : snprintf(buf, len, "%.0f%%", v);
    case P_RELEASE: {
        float ms = noise_release_ms(v);
        return ms >= 1000 ? snprintf(buf, len, "%.2f s", ms / 1000) : snprintf(buf, len, "%.0f ms", ms);
    }
    case P_DENSITY: {
        float d = noise_density(v);
        return d < 10 ? snprintf(buf, len, "%.1f /s", d) : snprintf(buf, len, "%.0f /s", d);
    }
    }
    return 0;
}

void noise_process(noise_t *n, float *l, float *r, int frames) {
    float t_noise = n->p[P_ON] > 0.5f ? db_gain(n->p[P_LEVEL]) : 0;
    float t_dry = n->p[P_DRY] <= PARAMS[P_DRY].min ? 0 : db_gain(n->p[P_DRY]);
    float t_follow = n->p[P_FOLLOW] / 100, t_theta = n->p[P_WIDTH] / 100 * (float)M_PI / 4;
    int hicut = n->p[P_HIGHCUT] < 100;
    /* Off and faded out: pass the input through and skip making noise. */
    int silent = t_noise == 0 && n->g_noise == 0;
    for (int i = 0; i < frames; i++) {
        float k = n->k_smooth;
        n->g_noise = smooth(n->g_noise, t_noise, k);
        n->g_dry = smooth(n->g_dry, t_dry, k);
        n->g_follow = smooth(n->g_follow, t_follow, k);
        n->theta = smooth(n->theta, t_theta, k);

        float in_l = l[i], in_r = r[i], peak = fmaxf(fabsf(in_l), fabsf(in_r));
        n->env += (peak - n->env) * (peak > n->env ? n->k_att : n->k_rel);
        if (n->env < 1e-9f) n->env = 0;
        if (silent) { l[i] = in_l * n->g_dry; r[i] = in_r * n->g_dry; continue; }

        float ab[2];
        float f = n->xf > 0 ? (float)(XFADE - n->xf) / XFADE : 1;
        for (int s = 0; s < 2; s++) {
            float c[NCOLORS];
            stream_gen(n, &n->st[s], c);
            ab[s] = c[n->color] * NORM[n->color] * f;
            if (f < 1) ab[s] += c[n->prev_color] * NORM[n->prev_color] * (1 - f);
        }
        if (n->xf > 0) n->xf--;
        if (n->theta != n->theta_at) n->theta_at = n->theta, n->cs = cosf(n->theta), n->sn = sinf(n->theta);
        float nl = n->cs * ab[0] + n->sn * ab[1], nr = n->cs * ab[0] - n->sn * ab[1];
        nl = bq_run(&n->hp[0], nl);
        nr = bq_run(&n->hp[1], nr);
        if (hicut) { nl = bq_run(&n->lp[0], nl); nr = bq_run(&n->lp[1], nr); }
        float g = n->g_noise * ((1 - n->g_follow) + n->g_follow * n->env);
        l[i] = in_l * n->g_dry + nl * g;
        r[i] = in_r * n->g_dry + nr * g;
    }
}

/* Harness only: raw RMS of each colour after the 15 Hz filter, for NORM[]. */
void noise_calibrate(float seconds, double rms[NCOLORS]) {
    noise_t *n = noise_create(44100);
    double sum[NCOLORS] = {0};
    long count = (long)(seconds * 44100), skip = 44100;   /* let the filters settle for a second */
    for (long i = 0; i < count + skip; i++) {
        float c[NCOLORS];
        stream_gen(n, &n->st[0], c);
        for (int k = 0; k < NCOLORS; k++) {
            float v = bq_run(&n->st[0].sub[k], c[k]);
            if (i >= skip) sum[k] += (double)v * v;
        }
    }
    for (int k = 0; k < NCOLORS; k++) rms[k] = sqrt(sum[k] / count);
    noise_destroy(n);
}
