/* See spectrum.h. Hann window; a column sums the power of the bins whose centres fall in it, calibrated by the window's
 * coherent gain and noise bandwidth, so a sine inside a column reads its own level. A column narrower than a bin (the
 * low end) reads the power interpolated between its two nearest bins. */
#include "spectrum.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

#define N 2048
#define LOG2N 11
#define PASSES_PER_FEED 3
#define MAXC 128

struct Spectrum {
    float sr;
    int ncols;
    float ring[N]; int pos;
    float re[N], im[N];
    float win[N], cs[N / 2], sn[N / 2];
    unsigned short rev[N];
    int stage;                 /* -1 idle; 0..LOG2N-1 the next pass; LOG2N the columns */
    int ready;
    int b0[MAXC], b1[MAXC];
    float fc_bin[MAXC];
    float col[MAXC];
};

Spectrum *sp_create(float sr, int ncols, float f_lo, float f_hi)
{
    if (ncols > MAXC) ncols = MAXC;
    Spectrum *s = calloc(1, sizeof *s);
    if (!s) return NULL;
    s->sr = sr; s->ncols = ncols; s->stage = -1;
    for (int i = 0; i < N; i++) {
        s->win[i] = 0.5f - 0.5f * cosf(2.f * (float)M_PI * i / N);
        unsigned r = 0;
        for (int b = 0; b < LOG2N; b++) if (i & (1 << b)) r |= 1u << (LOG2N - 1 - b);
        s->rev[i] = (unsigned short)r;
    }
    for (int k = 0; k < N / 2; k++) { s->cs[k] = cosf(2.f * (float)M_PI * k / N); s->sn[k] = -sinf(2.f * (float)M_PI * k / N); }
    float df = sr / N, ratio = f_hi / f_lo;
    for (int c = 0; c < ncols; c++) {
        float fa = f_lo * powf(ratio, (float)c / ncols), fb = f_lo * powf(ratio, (float)(c + 1) / ncols), fc = f_lo * powf(ratio, (c + 0.5f) / ncols);
        s->b0[c] = (int)ceilf(fa / df);
        s->b1[c] = (int)ceilf(fb / df);
        if (s->b1[c] > N / 2) s->b1[c] = N / 2;
        s->fc_bin[c] = fc / df;
    }
    return s;
}

void sp_destroy(Spectrum *s) { free(s); }

int sp_start(Spectrum *s)
{
    if (s->stage >= 0) return 0;
    for (int i = 0; i < N; i++) {                    /* the last N samples, oldest first, windowed, in bit-reversed order */
        float v = s->ring[(s->pos + i) & (N - 1)] * s->win[i];
        s->re[s->rev[i]] = v;
        s->im[s->rev[i]] = 0.f;
    }
    s->stage = 0;
    return 1;
}

static void pass(Spectrum *s, int p)
{
    int len = 2 << p, half = len >> 1, step = N / len;
    for (int i = 0; i < N; i += len)
        for (int k = 0; k < half; k++) {
            float wr = s->cs[k * step], wi = s->sn[k * step];
            float *ar = &s->re[i + k], *ai = &s->im[i + k], *br = &s->re[i + k + half], *bi = &s->im[i + k + half];
            float tr = *br * wr - *bi * wi, ti = *br * wi + *bi * wr;
            *br = *ar - tr; *bi = *ai - ti;
            *ar += tr; *ai += ti;
        }
}

static void columns(Spectrum *s)
{
    const float peak = (float)(N / 4) * (N / 4);    /* a full-scale sine's peak bin power with Hann (coherent gain 0.5) */
    const float band = peak * 1.5f;                  /* its power summed over the bins (noise bandwidth 1.5 bins) */
    for (int c = 0; c < s->ncols; c++) {
        float db;
        if (s->b1[c] > s->b0[c]) {
            float sum = 0.f;
            for (int k = s->b0[c]; k < s->b1[c]; k++) sum += s->re[k] * s->re[k] + s->im[k] * s->im[k];
            db = 10.f * log10f(sum / band + 1e-12f);
        } else {
            int k = (int)s->fc_bin[c];
            float t = s->fc_bin[c] - k;
            if (k >= N / 2) k = N / 2 - 1;
            float p0 = s->re[k] * s->re[k] + s->im[k] * s->im[k], p1 = s->re[k + 1] * s->re[k + 1] + s->im[k + 1] * s->im[k + 1];
            db = 10.f * log10f((p0 + t * (p1 - p0)) / peak + 1e-12f);
        }
        s->col[c] = db;
    }
}

void sp_feed(Spectrum *s, const float *l, const float *r, int n)
{
    for (int i = 0; i < n; i++) { s->ring[s->pos] = 0.5f * (l[i] + r[i]); s->pos = (s->pos + 1) & (N - 1); }
    if (s->stage < 0) return;
    if (s->stage == LOG2N) { columns(s); s->ready = 1; s->stage = -1; return; }
    for (int k = 0; k < PASSES_PER_FEED && s->stage < LOG2N; k++) pass(s, s->stage++);
}

int sp_ready(const Spectrum *s) { return s->ready; }

void sp_read(Spectrum *s, float *out)
{
    memcpy(out, s->col, sizeof(float) * s->ncols);
    s->ready = 0;
}
