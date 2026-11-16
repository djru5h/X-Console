/* X-Console desktop harness: numeric checks of every section against the FLANNEL figures and our own choices, click
 * checks for every switch, then demo WAVs.   harness [out_dir]
 * Exit status is the number of failed checks. */
#include "../src/xconsole.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int g_fail, g_pass;
#define CHECK(cond, ...) do { if (cond) { g_pass++; printf("ok   "); } else { g_fail++; printf("FAIL "); } printf(__VA_ARGS__); printf("\n"); } while (0)

static float SR = 44100.f;
static double g_alias_hz;   /* where the last harmonics() found its worst non-harmonic peak */

/* ---------------------------------------------------------------- helpers */
static int P(const char *k)
{
    int i = xc_param_index(k);
    if (i < 0) { fprintf(stderr, "unknown param %s\n", k); exit(99); }
    return i;
}
static void setv(XConsole *x, const char *k, float physical) { xc_set(x, P(k), xc_norm_of(P(k), physical)); }
static void setn(XConsole *x, const char *k, float n) { xc_set(x, P(k), n); }
static void seto(XConsole *x, const char *k, int opt) { xc_set(x, P(k), (float)opt); }
static void selm(XConsole *x, const char *k, int model) { seto(x, k, xc_model_opt(xc_model_section(P(k)), model)); }   /* pick a preset by model */

static XConsole *fresh(void) { return xc_create(SR); }

/* run a block-wise process over buffers */
static void run(XConsole *x, const float *il, const float *ir, float *ol, float *orr, int n)
{
    for (int i = 0; i < n; i += 128) {
        int m = n - i < 128 ? n - i : 128;
        xc_process(x, il + i, ir + i, ol + i, orr + i, m);
    }
}
static void settle(XConsole *x, float secs)
{
    int n = (int)(secs * SR);
    float *z = calloc(n, sizeof(float)), *o = calloc(n, sizeof(float)), *p = calloc(n, sizeof(float));
    run(x, z, z, o, p, n);
    free(z); free(o); free(p);
}
static double rms_db(const float *a, int from, int to)
{
    double s = 0;
    for (int i = from; i < to; i++) s += (double)a[i] * a[i];
    return 10 * log10(s / (to - from) + 1e-30);
}
/* output/input gain (dB) of a steady sine at hz, amplitude amp, measured over the last half of `secs` */
static double sine_gain(XConsole *x, float hz, float amp, float secs)
{
    int n = (int)(secs * SR);
    float *in = malloc(n * sizeof(float)), *ol = malloc(n * sizeof(float)), *orr = malloc(n * sizeof(float));
    for (int i = 0; i < n; i++) in[i] = amp * sinf(2 * (float)M_PI * hz * i / SR);
    run(x, in, in, ol, orr, n);
    double g = rms_db(ol, n / 2, n) - rms_db(in, n / 2, n);
    free(in); free(ol); free(orr);
    return g;
}
static double out_level(XConsole *x, float hz, float amp, float secs)
{
    return sine_gain(x, hz, amp, secs) + 20 * log10(amp / sqrt(2.0));
}

/* radix-2 FFT magnitude (dB re full-scale sine) with a Blackman-Harris window */
#define FN 16384
static void spectrum(const float *s, double *mag_db)
{
    static double re[FN], im[FN];
    double wsum = 0;
    for (int i = 0; i < FN; i++) {
        double w = 0.35875 - 0.48829 * cos(2 * M_PI * i / FN) + 0.14128 * cos(4 * M_PI * i / FN) - 0.01168 * cos(6 * M_PI * i / FN);
        re[i] = s[i] * w; im[i] = 0; wsum += w;
    }
    for (int i = 1, j = 0; i < FN; i++) {
        int bit = FN >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) { double t = re[i]; re[i] = re[j]; re[j] = t; }
    }
    for (int len = 2; len <= FN; len <<= 1) {
        double ang = -2 * M_PI / len;
        for (int i = 0; i < FN; i += len)
            for (int k = 0; k < len / 2; k++) {
                double wr = cos(ang * k), wi = sin(ang * k);
                double ur = re[i + k], ui = im[i + k];
                double vr = re[i + k + len / 2] * wr - im[i + k + len / 2] * wi, vi = re[i + k + len / 2] * wi + im[i + k + len / 2] * wr;
                re[i + k] = ur + vr; im[i + k] = ui + vi; re[i + k + len / 2] = ur - vr; im[i + k + len / 2] = ui - vi;
            }
    }
    for (int i = 0; i <= FN / 2; i++) mag_db[i] = 20 * log10(2 * sqrt(re[i] * re[i] + im[i] * im[i]) / wsum + 1e-15);
}
/* drive a bin-centred sine through x; report harmonic 2 and 3 (dB re the fundamental) and the worst non-harmonic peak */
static void harmonics(XConsole *x, int bin, float amp, double *h2, double *h3, double *worst_nh)
{
    int n = FN * 3;
    float hz = bin * SR / FN;
    float *in = malloc(n * sizeof(float)), *ol = malloc(n * sizeof(float)), *orr = malloc(n * sizeof(float));
    for (int i = 0; i < n; i++) in[i] = amp * sinf(2 * (float)M_PI * hz * i / SR);
    run(x, in, in, ol, orr, n);
    static double m[FN / 2 + 1];
    spectrum(ol + n - FN, m);
    double f0 = m[bin];
    *h2 = m[2 * bin] - f0; *h3 = m[3 * bin] - f0;
    double w = -300;
    int wbin = 0;
    int top = (int)(18000.f * FN / SR);                                  /* audible band: a fold-back above 18 kHz comes from the
                                                                             halfband's transition at Nyquist and isn't counted */
    for (int i = 8; i < top; i++) {
        int harm = 0;
        for (int h = 1; h * bin < FN / 2 + 8; h++) if (abs(i - h * bin) <= 6) harm = 1;
        if (!harm && m[i] - f0 > w) { w = m[i] - f0; wbin = i; }
    }
    *worst_nh = w;
    g_alias_hz = wbin * SR / FN;
    free(in); free(ol); free(orr);
}

/* ---------------------------------------------------------------- WAV */
static void wav(const char *path, const float *l, const float *r, int n)
{
    FILE *f = fopen(path, "wb");
    if (!f) { perror(path); return; }
    uint32_t sr = (uint32_t)SR, bytes = n * 4, v32;
    uint16_t v16;
    fwrite("RIFF", 1, 4, f); v32 = 36 + bytes; fwrite(&v32, 4, 1, f); fwrite("WAVEfmt ", 1, 8, f);
    v32 = 16; fwrite(&v32, 4, 1, f); v16 = 1; fwrite(&v16, 2, 1, f); v16 = 2; fwrite(&v16, 2, 1, f);
    fwrite(&sr, 4, 1, f); v32 = sr * 4; fwrite(&v32, 4, 1, f); v16 = 4; fwrite(&v16, 2, 1, f); v16 = 16; fwrite(&v16, 2, 1, f);
    fwrite("data", 1, 4, f); fwrite(&bytes, 4, 1, f);
    for (int i = 0; i < n; i++) {
        int16_t a = (int16_t)lrintf(fmaxf(-1.f, fminf(1.f, l[i])) * 32767.f), b = (int16_t)lrintf(fmaxf(-1.f, fminf(1.f, r[i])) * 32767.f);
        fwrite(&a, 2, 1, f); fwrite(&b, 2, 1, f);
    }
    fclose(f);
}

/* a 4-bar synthetic loop at 92 BPM: kick, snare, hats, a bass line, room noise under it (for the gate) */
static uint32_t rng = 12345;
static float noise(void) { rng = rng * 1664525u + 1013904223u; return (int32_t)rng * (1.f / 2147483648.f); }
static int make_loop(float **pl, float **pr)
{
    float bpm = 92, beat = 60.f / bpm;
    int n = (int)(16 * beat * SR);
    float *l = calloc(n, sizeof(float)), *r = calloc(n, sizeof(float));
    static const int bass_notes[16] = {36, 36, 39, 36, 41, 41, 39, 34, 36, 36, 39, 43, 41, 39, 36, 34};
    for (int step = 0; step < 64; step++) {
        int s0 = (int)(step * beat / 4 * SR);
        int pos = step % 16;
        if (pos == 0 || pos == 7 || pos == 10) {                         /* kick */
            float ph = 0;
            for (int i = 0; i < (int)(0.4f * SR) && s0 + i < n; i++) {
                float t = i / SR, f = 45 + 110 * expf(-t * 30);
                ph += 2 * (float)M_PI * f / SR;
                float v = 0.9f * sinf(ph) * expf(-t * 7);
                l[s0 + i] += v; r[s0 + i] += v;
            }
        }
        if (pos == 4 || pos == 12) {                                     /* snare */
            for (int i = 0; i < (int)(0.3f * SR) && s0 + i < n; i++) {
                float t = i / SR;
                float v = 0.45f * noise() * expf(-t * 14) + 0.35f * sinf(2 * (float)M_PI * 190 * t) * expf(-t * 25);
                l[s0 + i] += v; r[s0 + i] += 0.9f * v;
            }
        }
        {                                                                /* hats */
            float hp = 0, prev = 0, amp = (pos % 4 == 2) ? 0.16f : 0.08f;
            for (int i = 0; i < (int)(0.06f * SR) && s0 + i < n; i++) {
                float w = noise();
                hp = 0.7f * (hp + w - prev); prev = w;
                float v = amp * hp * expf(-(i / SR) * 70);
                l[s0 + i] += 0.7f * v; r[s0 + i] += v;
            }
        }
        if (pos % 2 == 0) {                                              /* bass, 8ths */
            float f = 440.f * powf(2.f, (bass_notes[step / 4 % 16] - 69) / 12.f);
            for (int i = 0; i < (int)(beat / 2 * 0.9f * SR) && s0 + i < n; i++) {
                float t = i / SR;
                float v = 0.30f * (sinf(2 * (float)M_PI * f * t) + 0.3f * sinf(4 * (float)M_PI * f * t) + 0.12f * sinf(6 * (float)M_PI * f * t)) * fminf(1.f, t * 200) * expf(-t * 2.5f);
                l[s0 + i] += v; r[s0 + i] += v;
            }
        }
    }
    for (int i = 0; i < n; i++) { float h = 0.004f * noise(); l[i] = 0.7f * l[i] + h; r[i] = 0.7f * r[i] + h; }   /* room noise around -50 dBFS */
    *pl = l; *pr = r;
    return n;
}

/* ---------------------------------------------------------------- checks */
static void check_null(float sr)
{
    SR = sr;
    XConsole *x = fresh();
    int n = (int)(sr);
    float *in = malloc(n * 4), *ol = malloc(n * 4), *orr = malloc(n * 4);
    for (int i = 0; i < n; i++) in[i] = 0.5f * sinf(2 * (float)M_PI * 997 * i / sr) + 0.1f * noise();
    run(x, in, in, ol, orr, n);
    float worst = 0;
    for (int i = 0; i < n; i++) worst = fmaxf(worst, fmaxf(fabsf(ol[i] - in[i]), fabsf(orr[i] - in[i])));
    CHECK(worst < 1e-6f, "defaults pass audio untouched at %.0f Hz (worst difference %.2g)", sr, worst);
    free(in); free(ol); free(orr);
    xc_destroy(x);
    SR = 44100.f;
}

static void check_input(void)
{
    XConsole *x = fresh();
    setv(x, "in_gain", 6.f); settle(x, 0.2f);
    double g = sine_gain(x, 1000, 0.1f, 0.3f);
    CHECK(fabs(g - 6.0) < 0.05, "input trim +6 dB gives %.2f dB", g);
    setv(x, "in_gain", -20.f); settle(x, 0.2f);
    g = sine_gain(x, 1000, 0.1f, 0.3f);
    CHECK(fabs(g + 20.0) < 0.05, "input trim -20 dB gives %.2f dB", g);
    xc_destroy(x);
    x = fresh();
    seto(x, "phase", 1); settle(x, 0.1f);
    float in[256], ol[256], orr[256];
    for (int i = 0; i < 256; i++) in[i] = 0.3f;
    xc_process(x, in, in, ol, orr, 256);
    CHECK(ol[255] < -0.299f && orr[255] < -0.299f, "polarity inverts (%.3f)", ol[255]);
    xc_destroy(x);
}

static void check_filters(void)
{
    static const int ORD[4] = {1, 2, 3, 4};
    for (int s = 0; s < 4; s++) {
        XConsole *x = fresh();
        setv(x, "lc_freq", 100.f); seto(x, "lc_slope", s); settle(x, 0.3f);
        double at = sine_gain(x, 100, 0.25f, 0.6f), half = sine_gain(x, 50, 0.25f, 0.8f), pass = sine_gain(x, 2000, 0.25f, 0.3f);
        double want_half = -10 * log10(1 + pow(2.0, 2 * ORD[s]));
        CHECK(fabs(at + 3.01) < 0.3 && fabs(half - want_half) < 0.6 && fabs(pass) < 0.1,
              "low cut 100 Hz at %d dB/oct: %.2f dB at 100 Hz, %.2f at 50 (Butterworth %.2f), %.2f at 2 kHz", 6 * ORD[s], at, half, want_half, pass);
        double curve = xc_filter_curve_db(x, 50);
        CHECK(fabs(curve - half) < 0.3, "  its drawn curve at 50 Hz %.2f dB matches the sound %.2f dB", curve, half);
        xc_destroy(x);
    }
    {
        XConsole *x = fresh();
        setv(x, "hc_freq", 5000.f); settle(x, 0.3f);              /* default slope 12 (the FLANNEL's) */
        double at = sine_gain(x, 5000, 0.25f, 0.3f), dbl = sine_gain(x, 10000, 0.25f, 0.3f);
        double r = tan(M_PI * 10000 / SR) / tan(M_PI * 5000 / SR), want = -10 * log10(1 + pow(r, 4));   /* the bilinear (prewarped) Butterworth */
        CHECK(fabs(at + 3.01) < 0.3 && fabs(dbl - want) < 0.3 && fabs(xc_filter_curve_db(x, 10000) - dbl) < 0.3,
              "high cut 5 kHz at 12 dB/oct: %.2f dB at 5k, %.2f at 10k (digital Butterworth %.2f; analog would be -12.3)", at, dbl, want);
        xc_destroy(x);
    }
    {
        XConsole *x = fresh();
        CHECK(xc_get(x, P("lc_slope")) == 2 && xc_get(x, P("hc_slope")) == 1, "FLANNEL defaults: low cut 18 dB/oct, high cut 12 dB/oct");
        char b[32];
        xc_display(x, P("lc_freq"), b, 32);
        char c[32];
        xc_display(x, P("hc_freq"), c, 32);
        CHECK(!strcmp(b, "Off") && !strcmp(c, "Off"), "both filters start Off (\"%s\", \"%s\")", b, c);
        xc_destroy(x);
    }
}

static void check_eq(void)
{
    static const char *G[4] = {"eq_lf_gain", "eq_lmf_gain", "eq_hmf_gain", "eq_hf_gain"};
    static const char *F[4] = {"eq_lf_freq", "eq_lmf_freq", "eq_hmf_freq", "eq_hf_freq"};
    static const float FR[4] = {60, 400, 2500, 10000};
    for (int style = 0; style < 2; style++)
        for (int b = 0; b < 4; b++) {
            XConsole *x = fresh();
            seto(x, "eq_on", 1); seto(x, "eq_style", style);
            if (style == 1 && (b == 0 || b == 3)) seto(x, b == 0 ? "eq_lf_type" : "eq_hf_type", 1);
            setv(x, G[b], 12.f); setv(x, F[b], FR[b]);
            settle(x, 0.4f);
            float probe = (b == 0 && !(style == 1)) ? 20.f : (b == 3 && !(style == 1)) ? 19000.f : FR[b];
            if (b == 0 && style == 0) probe = 25.f;
            double meas = sine_gain(x, probe, 0.05f, b == 0 ? 1.0f : 0.4f), curve = xc_eq_curve_db(x, probe);
            int bell = b == 1 || b == 2 || style == 1;
            double want = 12.0;
            CHECK(fabs(meas - curve) < 0.25 && (bell ? fabs(meas - want) < 0.3 : fabs(meas - want) < 1.5),
                  "%s style, %s +12 dB at %g Hz (%s): sound %.2f dB, drawn curve %.2f dB", style ? "E" : "G", G[b] + 3, FR[b],
                  bell ? "peak" : "shelf plateau", meas, curve);
            xc_destroy(x);
        }
    /* LF and HF: BELL in G too (extra), CUT as a 12 dB/oct Butterworth that ignores GAIN */
    {
        XConsole *x = fresh();
        seto(x, "eq_on", 1); seto(x, "eq_lf_type", 1); setv(x, "eq_lf_gain", 10.f); setv(x, "eq_lf_freq", 100.f);
        double pk = xc_eq_curve_db(x, 100.f);
        xc_destroy(x);
        x = fresh();
        seto(x, "eq_on", 1); seto(x, "eq_lf_type", 2); setv(x, "eq_lf_gain", 10.f); setv(x, "eq_lf_freq", 100.f); settle(x, 0.3f);
        double at = sine_gain(x, 100, 0.25f, 0.6f), half = sine_gain(x, 50, 0.25f, 0.8f), pass = sine_gain(x, 2000, 0.25f, 0.3f);
        CHECK(fabs(pk - 10) < 0.05 && fabs(at + 3.01) < 0.3 && fabs(half + 12.3) < 0.6 && fabs(pass) < 0.1 && fabs(xc_eq_curve_db(x, 50) - half) < 0.3,
              "LF BELL in G peaks %.2f dB; LF CUT at 100 Hz: %.2f dB there, %.2f at 50 (curve %.2f), %.2f at 2 kHz, GAIN ignored", pk, at, half, xc_eq_curve_db(x, 50), pass);
        xc_destroy(x);
        x = fresh();
        seto(x, "eq_on", 1); seto(x, "eq_hf_type", 2); setv(x, "eq_hf_freq", 5000.f); settle(x, 0.3f);
        double hc = sine_gain(x, 5000, 0.25f, 0.3f), lo = sine_gain(x, 500, 0.25f, 0.3f);
        CHECK(fabs(hc + 3.01) < 0.3 && fabs(lo) < 0.1, "HF CUT at 5 kHz: %.2f dB there, %.2f at 500 Hz", hc, lo);
        xc_destroy(x);
    }
    /* G shelves overshoot, E's don't */
    for (int style = 0; style < 2; style++) {
        XConsole *x = fresh();
        seto(x, "eq_on", 1); seto(x, "eq_style", style); setv(x, "eq_lf_gain", 12.f); setv(x, "eq_lf_freq", 100.f);
        settle(x, 0.1f);
        double lo = 1e9;
        for (float f = 100; f < 2000; f *= 1.02f) lo = fmin(lo, xc_eq_curve_db(x, f));
        if (style == 0) CHECK(lo < -0.3, "G low shelf dips below 0 dB above its corner (undershoot %.2f dB)", lo);
        else CHECK(lo > -0.05, "E low shelf has no undershoot (lowest %.2f dB)", lo);
        xc_destroy(x);
    }
    /* G's mids widen at small gains; E's keep their width */
    {
        double w[2];
        for (int style = 0; style < 2; style++) {
            XConsole *x = fresh();
            seto(x, "eq_style", style); setv(x, "eq_lmf_gain", 4.f); setv(x, "eq_lmf_freq", 1000.f); setv(x, "eq_lmf_q", 1.5f);
            w[style] = xc_eq_curve_db(x, 1500.f);
            xc_destroy(x);
        }
        CHECK(w[0] > w[1] + 0.3, "G mid bell is wider than E at +4 dB (%.2f vs %.2f dB half an octave off)", w[0], w[1]);
    }
    /* the FLANNEL ranges */
    {
        XConsole *x = fresh();
        char a[32], b[32], c[32], d[32];
        setn(x, "eq_lf_gain", 1.f); xc_display(x, P("eq_lf_gain"), a, 32);
        setn(x, "eq_lmf_freq", 0.f); xc_display(x, P("eq_lmf_freq"), b, 32);
        setn(x, "eq_hf_freq", 1.f); xc_display(x, P("eq_hf_freq"), c, 32);
        setn(x, "eq_hmf_q", 1.f); xc_display(x, P("eq_hmf_q"), d, 32);
        CHECK(!strcmp(a, "+19.0 dB") && !strcmp(b, "200 Hz") && !strcmp(c, "16.0 kHz") && !strcmp(d, "2.50"),
              "FLANNEL ranges read %s, %s, %s, Q %s", a, b, c, d);
        xc_destroy(x);
    }
}

static void check_comp(void)
{
    /* static curve, RMS: ratio 4, threshold -36 dBFS; -6 dBFS peak sine = -9 dBFS RMS: 27 dB over, beyond the 10 dB knee */
    {
        XConsole *x = fresh();
        seto(x, "cmp_on", 1); setv(x, "cmp_ratio", 4.f); setv(x, "cmp_thr", -36.f);
        double lv = out_level(x, 1000, 0.5f, 1.5f);
        double want = -9.03 - 27 * 0.75 + 20 * 0.75;                        /* auto make-up: (-16 - -36) x 0.75 */
        CHECK(fabs(lv - want) < 0.6, "RMS 4:1, threshold -36: -9 dBFS RMS in gives %.2f dBFS (want %.2f, auto make-up 15 dB)", lv, want);
        CHECK(fabs(xc_comp_gr_db(x) - 20.25) < 0.8, "  gain reduction reads %.2f dB (want 20.25)", xc_comp_gr_db(x));
        xc_destroy(x);
    }
    /* limit at the top of RATIO: louder in, same out */
    {
        XConsole *x = fresh();
        seto(x, "cmp_on", 1); setn(x, "cmp_ratio", 1.f); setv(x, "cmp_thr", -30.f); seto(x, "cmp_det", 1);
        double a = out_level(x, 1000, 0.1f, 1.0f), b = out_level(x, 1000, 0.8f, 1.0f);
        char t[32]; xc_display(x, P("cmp_ratio"), t, 32);
        CHECK(fabs(a - b) < 0.5 && !strcmp(t, "Limit"), "ratio \"%s\": 18 dB more in changes the output %.2f dB", t, b - a);
        xc_destroy(x);
    }
    /* ratio 1:1 at the bottom does nothing */
    {
        XConsole *x = fresh();
        seto(x, "cmp_on", 1); setn(x, "cmp_ratio", 0.f); setv(x, "cmp_thr", -46.f); settle(x, 0.5f);
        double g = sine_gain(x, 1000, 0.5f, 0.5f);
        CHECK(fabs(g) < 0.05, "ratio 1:1 is inactive (gain %.3f dB)", g);
        xc_destroy(x);
    }
    /* attack: fast vs program dependent (time to 90 % of the final reduction after a -40 -> -6 dBFS step) */
    for (int fast = 0; fast < 2; fast++) {
        XConsole *x = fresh();
        seto(x, "cmp_on", 1); setv(x, "cmp_ratio", 10.f); setv(x, "cmp_thr", -40.f); seto(x, "cmp_det", 1); seto(x, "cmp_fast", fast);
        int n = (int)(0.6f * SR) / 48 * 48;
        float *in = malloc(n * 4), *o1 = malloc(n * 4), *o2 = malloc(n * 4);
        for (int i = 0; i < n; i++) in[i] = (i < n / 3 ? 0.01f : 0.5f) * sinf(2 * (float)M_PI * 1000 * i / SR);
        float gr[4000]; int k = 0;
        for (int i = 0; i < n; i += 16) { xc_process(x, in + i, in + i, o1 + i, o2 + i, 16); if (i >= n / 3 && k < 4000) gr[k++] = xc_comp_gr_db(x); }
        float fin = gr[k - 1]; int t90 = -1;
        for (int j = 0; j < k; j++) if (gr[j] >= 0.9f * fin) { t90 = j; break; }
        double ms = t90 * 16 * 1000.0 / SR;
        if (fast) CHECK(ms < 4.5, "fast attack: 90%% of %.1f dB reduction in %.1f ms (FLANNEL: 3 ms for 20 dB)", fin, ms);
        else CHECK(ms >= 2.0 && ms < 30, "program-dependent attack: 90%% of %.1f dB in %.1f ms (FLANNEL: 3..30 ms)", fin, ms);
        free(in); free(o1); free(o2);
        xc_destroy(x);
    }
    /* release about as set */
    {
        XConsole *x = fresh();
        seto(x, "cmp_on", 1); setv(x, "cmp_ratio", 10.f); setv(x, "cmp_thr", -40.f); setv(x, "cmp_rel", 1000.f);
        int n = (int)(3.0f * SR) / 48 * 48;
        float *in = malloc(n * 4), *o1 = malloc(n * 4), *o2 = malloc(n * 4);
        for (int i = 0; i < n; i++) in[i] = (i < n / 3 ? 0.5f : 0.0f) * sinf(2 * (float)M_PI * 1000 * i / SR);
        float g0 = 0; int t10 = -1;
        for (int i = 0; i < n; i += 16) {
            xc_process(x, in + i, in + i, o1 + i, o2 + i, 16);
            if (i == n / 3) g0 = xc_comp_gr_db(x);
            if (i > n / 3 && t10 < 0 && xc_comp_gr_db(x) < 0.1f * g0) t10 = i - n / 3;
        }
        double ms = t10 * 1000.0 / SR;
        CHECK(ms > 600 && ms < 1400, "release 1 s: back to 10%% of %.1f dB in %.0f ms", g0, ms);
        free(in); free(o1); free(o2);
        xc_destroy(x);
    }
    /* soft knee in RMS, hard in PK: 2 dB below threshold */
    {
        double gr[2];
        for (int det = 0; det < 2; det++) {
            XConsole *x = fresh();
            seto(x, "cmp_on", 1); setv(x, "cmp_ratio", 4.f); setv(x, "cmp_thr", -20.f); seto(x, "cmp_det", det);
            float amp = det ? powf(10.f, -22.f / 20.f) : powf(10.f, -22.f / 20.f) * 1.41421f;   /* 2 dB under, by each detector */
            out_level(x, 1000, amp, 1.0f);
            gr[det] = xc_comp_gr_db(x);
            xc_destroy(x);
        }
        CHECK(gr[0] > 0.3 && gr[1] < 0.05, "2 dB under threshold: RMS soft knee already reduces %.2f dB, PK hard knee %.2f dB", gr[0], gr[1]);
    }
    /* extras: wet/dry 0 = dry, make-up adds */
    {
        XConsole *x = fresh();
        seto(x, "cmp_on", 1); setv(x, "cmp_ratio", 8.f); setv(x, "cmp_thr", -40.f); setv(x, "cmp_mix", 0.f);
        double g = sine_gain(x, 1000, 0.5f, 0.5f);
        CHECK(fabs(g) < 0.05, "wet/dry 0%% passes the dry signal (%.3f dB)", g);
        xc_destroy(x);
    }
}

static void check_gate(void)
{
    /* gate: threshold -30, range 40; a -50 dBFS tone sinks by 40 dB, a -20 dBFS tone passes */
    {
        XConsole *x = fresh();
        seto(x, "sh_on", 1); setv(x, "gate_thr", -30.f); setv(x, "gate_range", 40.f); setv(x, "gate_rel", 100.f);
        double lo = sine_gain(x, 1000, powf(10.f, -50.f / 20.f), 1.0f), hi = sine_gain(x, 1000, powf(10.f, -20.f / 20.f), 0.5f);
        CHECK(fabs(lo + 40) < 1.0 && fabs(hi) < 0.1, "gate, range 40: below threshold %.1f dB, above %.2f dB", lo, hi);
        xc_destroy(x);
    }
    /* opening: 40 dB in 1.5 ms (fast: 0.1 ms), linear */
    for (int fast = 0; fast < 2; fast++) {
        XConsole *x = fresh();
        seto(x, "sh_on", 1); setv(x, "gate_thr", -30.f); setv(x, "gate_range", 40.f); seto(x, "gate_fast", fast);
        int n = (int)(1.0f * SR) / 48 * 48;
        float *in = malloc(n * 4), *o1 = malloc(n * 4), *o2 = malloc(n * 4);
        for (int i = 0; i < n; i++) in[i] = (i < n / 2 ? 0.f : 0.3f);
        int open_at = -1;
        for (int i = 0; i < n; i += 4) { xc_process(x, in + i, in + i, o1 + i, o2 + i, 4); if (i >= n / 2 && open_at < 0 && xc_gate_gr_db(x) < 0.5f) open_at = i - n / 2; }
        double ms = open_at * 1000.0 / SR;
        CHECK(fast ? ms < 0.3 : (ms > 1.0 && ms < 2.0), "gate %s attack: open in %.2f ms (FLANNEL: %s)", fast ? "fast" : "normal", ms, fast ? "100 us / 40 dB" : "1.5 ms / 40 dB");
        free(in); free(o1); free(o2);
        xc_destroy(x);
    }
    /* hold: stays open as long as set after the signal drops */
    {
        XConsole *x = fresh();
        seto(x, "sh_on", 1); setv(x, "gate_thr", -30.f); setv(x, "gate_range", 40.f); setv(x, "gate_hold", 200.f); setv(x, "gate_rel", 100.f);
        int n = (int)(1.0f * SR) / 48 * 48;
        float *in = malloc(n * 4), *o1 = malloc(n * 4), *o2 = malloc(n * 4);
        for (int i = 0; i < n; i++) in[i] = (i < n / 2 ? 0.3f : 0.001f) * sinf(2 * (float)M_PI * 500 * i / SR);
        int close_at = -1;
        for (int i = 0; i < n; i += 16) { xc_process(x, in + i, in + i, o1 + i, o2 + i, 16); if (i >= n / 2 && close_at < 0 && xc_gate_gr_db(x) > 1.f) close_at = i - n / 2; }
        double ms = close_at * 1000.0 / SR;
        CHECK(ms > 200 && ms < 260, "hold 200 ms: starts closing %.0f ms after the drop (plus the detector's 12 ms hold and fall)", ms);
        free(in); free(o1); free(o2);
        xc_destroy(x);
    }
    /* expander 2:1: 10 dB under threshold -> 10 dB down */
    {
        XConsole *x = fresh();
        seto(x, "sh_on", 1); seto(x, "gate_mode", 1); setv(x, "gate_thr", -30.f); setv(x, "gate_range", 40.f);
        double g = sine_gain(x, 1000, powf(10.f, -40.f / 20.f), 1.0f);   /* peak -40: the gate reads peaks */
        CHECK(fabs(g + 10) < 1.0, "expander 2:1 (the FLANNEL's): 10 dB under threshold gives %.2f dB", g);
        xc_destroy(x);
    }
    /* range 0 = inactive */
    {
        XConsole *x = fresh();
        seto(x, "sh_on", 1); setv(x, "gate_thr", -10.f);
        double g = sine_gain(x, 1000, 0.01f, 0.5f);
        CHECK(fabs(g) < 0.05, "range 0 (the default) leaves the gate inactive (%.3f dB)", g);
        xc_destroy(x);
    }
}

static void check_transient(void)
{
    /* hits: a 200 Hz tone, instant attack, 150 ms decay, every 0.5 s */
    int n = (int)(2.0f * SR);
    float *in = calloc(n, 4), *o1 = malloc(n * 4), *o2 = malloc(n * 4), *d1 = malloc(n * 4), *d2 = malloc(n * 4);
    for (int h = 0; h < 4; h++)
        for (int i = 0; i < (int)(0.5f * SR); i++) {
            int k = h * (int)(0.5f * SR) + i;
            in[k] = 0.4f * sinf(2 * (float)M_PI * 200 * i / SR) * expf(-(i / SR) / 0.15f);
        }
    int h0 = 3 * (int)(0.5f * SR), early = (int)(0.008f * SR), late0 = (int)(0.15f * SR), late1 = (int)(0.35f * SR);
    double ref_e, ref_l;
    {
        XConsole *x = fresh(); seto(x, "sh_on", 1);
        run(x, in, in, d1, d2, n);
        ref_e = rms_db(d1, h0, h0 + early); ref_l = rms_db(d1, h0 + late0, h0 + late1);
        xc_destroy(x);
    }
    {
        XConsole *x = fresh(); seto(x, "sh_on", 1); setv(x, "sh_punch", 100.f);
        run(x, in, in, o1, o2, n);
        double e = rms_db(o1, h0, h0 + early) - ref_e, l = rms_db(o1, h0 + late0, h0 + late1) - ref_l;
        CHECK(e > 3.0 && e > l + 3.0, "punch +100: first 8 ms %+.1f dB, tail %+.1f dB", e, l);
        xc_destroy(x);
    }
    {
        XConsole *x = fresh(); seto(x, "sh_on", 1); setv(x, "sh_sustain", 100.f);
        run(x, in, in, o1, o2, n);
        double e = rms_db(o1, h0, h0 + early) - ref_e, l = rms_db(o1, h0 + late0, h0 + late1) - ref_l;
        CHECK(l > 3.0 && l > e + 3.0, "sustain +100: tail %+.1f dB, first 8 ms %+.1f dB", l, e);
        xc_destroy(x);
    }
    {
        XConsole *x = fresh(); seto(x, "sh_on", 1); setv(x, "sh_punch", -100.f);
        run(x, in, in, o1, o2, n);
        double e = rms_db(o1, h0, h0 + early) - ref_e;
        CHECK(e < -3.0, "punch -100 softens the attack (%+.1f dB)", e);
        xc_destroy(x);
    }
    free(in); free(o1); free(o2); free(d1); free(d2);
}

static void check_saturation(void)
{
    double h2, h3, nh;
    /* oversampler alone: drive on at 0 % and a quiet tone, flat to 18 kHz */
    {
        XConsole *x = fresh(); seto(x, "drv_on", 1);
        double a = sine_gain(x, 1000, 0.01f, 0.3f), b = sine_gain(x, 18000, 0.01f, 0.3f);
        CHECK(fabs(a) < 0.3 && fabs(b) < 0.6, "drive stage at 0 %% is near clear: %.2f dB at 1 kHz, %.2f dB at 18 kHz (4x oversampling, ADAA)", a, b);
        xc_destroy(x);
    }
    /* VHD-style character: 2nd vs 3rd */
    {
        XConsole *x = fresh(); seto(x, "drv_on", 1); setv(x, "drv_amt", 60.f); setv(x, "drv_char", 0.f);
        harmonics(x, 372, 0.3f, &h2, &h3, &nh);
        CHECK(h2 > h3 + 6, "drive 60%%, character 2nd: H2 %.1f dB, H3 %.1f dB", h2, h3);
        xc_destroy(x);
        x = fresh(); seto(x, "drv_on", 1); setv(x, "drv_amt", 60.f); setv(x, "drv_char", 100.f);
        harmonics(x, 372, 0.3f, &h2, &h3, &nh);
        CHECK(h3 > h2 + 20, "drive 60%%, character 3rd: H3 %.1f dB, H2 %.1f dB", h3, h2);
        xc_destroy(x);
    }
    /* auto-gain: a -12 dBFS tone keeps its level across the knob, both sides */
    {
        double lo = 1e9, hi = -1e9;
        for (int c = 0; c <= 100; c += 50)
            for (int d = 0; d <= 100; d += 25) {
                XConsole *x = fresh(); seto(x, "drv_on", 1); setv(x, "drv_amt", (float)d); setv(x, "drv_char", (float)c);
                double g = sine_gain(x, 1000, 0.25f, 0.3f);
                lo = fmin(lo, g); hi = fmax(hi, g);
                xc_destroy(x);
            }
        CHECK(lo > -1.0 && hi < 1.0, "drive auto-gain: a -12 dBFS tone stays within %.2f..%+.2f dB across DRIVE and CHARACTER", lo, hi);
    }
    /* aliasing: a 4.5 kHz tone driven hard; nothing off the harmonics above -60 dB */
    {
        XConsole *x = fresh(); seto(x, "drv_on", 1); setv(x, "drv_amt", 100.f); setv(x, "drv_char", 100.f);
        harmonics(x, 1672, 0.5f, &h2, &h3, &nh);
        CHECK(nh < -60, "drive 100%% on a 4.5 kHz tone: worst alias below 18 kHz %.1f dB under the tone (at %.0f Hz)", nh, g_alias_hz);
        xc_destroy(x);
    }
    /* preamp types: each colours, none wrecks the level */
    static const char *TY[3] = {"TAPE", "TUBE", "IRON"};
    for (int t = 0; t < 3; t++) {
        XConsole *x = fresh(); seto(x, "pre_on", 1); seto(x, "pre_type", t); setv(x, "pre_color", 100.f);
        double g = sine_gain(x, 1000, 0.5f, 0.4f);
        xc_destroy(x);
        x = fresh(); seto(x, "pre_on", 1); seto(x, "pre_type", t); setv(x, "pre_color", 100.f);
        harmonics(x, t == 2 ? 30 : 372, 0.5f, &h2, &h3, &nh);
        CHECK(fabs(g) < 6 && fmax(h2, h3) > -50 && nh < -60, "preamp %s at 100%%: level %+.1f dB, H2 %.1f, H3 %.1f, worst alias %.1f dB", TY[t], g, h2, h3, nh);
        xc_destroy(x);
    }
}

static void check_output(void)
{
    XConsole *x = fresh();
    int n = 4096;
    float *l = malloc(n * 4), *r = malloc(n * 4), *ol = malloc(n * 4), *orr = malloc(n * 4);
    for (int i = 0; i < n; i++) { l[i] = 0.5f; r[i] = 0.f; }
    setv(x, "out_width", 0.f); settle(x, 0.1f);
    run(x, l, r, ol, orr, n);
    CHECK(fabsf(ol[n - 1] - 0.25f) < 1e-3f && fabsf(orr[n - 1] - 0.25f) < 1e-3f, "width 0%% folds to mono (%.3f / %.3f)", ol[n - 1], orr[n - 1]);
    setv(x, "out_width", 100.f); setv(x, "out_pan", -100.f); settle(x, 0.1f);
    for (int i = 0; i < n; i++) r[i] = 0.5f;
    run(x, l, r, ol, orr, n);
    CHECK(fabsf(ol[n - 1] - 0.5f) < 1e-3f && fabsf(orr[n - 1]) < 1e-3f, "pan hard left: left %.3f, right %.3f", ol[n - 1], orr[n - 1]);
    setv(x, "out_pan", 0.f); setn(x, "out_vol", 0.f); settle(x, 0.1f);
    run(x, l, r, ol, orr, n);
    char b[16]; xc_display(x, P("out_vol"), b, 16);
    CHECK(ol[n - 1] == 0.f && !strcmp(b, "Off"), "volume at the bottom is \"%s\" and silent", b);
    seto(x, "bypass", 1); settle(x, 0.1f);
    run(x, l, r, ol, orr, n);
    CHECK(ol[n - 1] == 0.5f, "bypass passes the input (%.3f)", ol[n - 1]);
    free(l); free(r); free(ol); free(orr);
    xc_destroy(x);
}

static void check_presets(void)
{
    XConsole *x = fresh();
    setv(x, "lc_freq", 200.f); seto(x, "phase", 1); seto(x, "flt_on", 0); setv(x, "in_gain", 5.f);
    setv(x, "cmp_ratio", 10.f); setv(x, "drv_amt", 50.f); seto(x, "drv_on", 1); seto(x, "cmp_on", 1);
    setv(x, "eq_lf_gain", 6.f); setv(x, "gate_range", 20.f);
    unsigned rev = xc_display_rev(x);
    xc_apply_preset(x, SEC_INPUT, MODEL_FLANNEL);
    CHECK(xc_get(x, P("lc_freq")) == 0.f && xc_get(x, P("phase")) == 0.f && xc_get(x, P("flt_on")) == 0.f && fabsf(xc_get(x, P("in_gain")) - xc_norm_of(P("in_gain"), 5.f)) < 1e-6f
          && xc_display_rev(x) == rev + 1,
          "picking the INPUT preset resets low cut and polarity, leaves the filter ON button and input gain, and bumps the display");
    CHECK(xc_get(x, P("eq_lf_gain")) != 0.5f && xc_get(x, P("gate_range")) != 0.f, "  and leaves the other sections alone");
    xc_apply_preset(x, SEC_COMP, MODEL_FLANNEL);
    CHECK(fabsf(xc_get(x, P("cmp_ratio")) - xc_norm_of(P("cmp_ratio"), 4.f)) < 1e-4f && xc_get(x, P("drv_amt")) == 0.f && xc_get(x, P("drv_on")) == 0.f && xc_get(x, P("cmp_on")) == 1.f,
          "picking the COMP preset resets the compressor and DRIVE (drive ON too), not the compressor ON button");
    /* restoring a project: the preset value is recorded, nothing jumps */
    setv(x, "eq_lf_gain", 6.f);
    float before = xc_get(x, P("eq_lf_gain"));
    xc_set_restoring(x, 1);
    selm(x, "eq_model", MODEL_FLANNEL);
    xc_set_restoring(x, 0);
    CHECK(xc_get(x, P("eq_lf_gain")) == before, "restoring saved state doesn't reset the EQ");
    xc_destroy(x);
}

/* the second preset: GRANITE (Waves SSL E-Channel figures; bx_console SSL 4000 E) */
static void setm(XConsole *x, const char *k, float physical) { xc_set(x, P(k), xc_norm_for(x, P(k), physical)); }
static XConsole *fresh4000(void)
{
    XConsole *x = fresh();
    selm(x, "in_model", MODEL_GRANITE); selm(x, "sh_model", MODEL_GRANITE); selm(x, "eq_model", MODEL_GRANITE); selm(x, "cmp_model", MODEL_GRANITE);
    return x;
}
static void check_granite(void)
{
    XConsole *x = fresh4000();
    char a[32], b[32], c[32], d[32], e[32], f[32];
    setn(x, "in_gain", 1.f); xc_display(x, P("in_gain"), a, 32);
    setm(x, "lc_freq", 17.f); xc_display(x, P("lc_freq"), b, 32);   /* its bottom (16 Hz) is Off */
    setn(x, "cmp_thr", 0.f); xc_display(x, P("cmp_thr"), c, 32);
    setn(x, "eq_lmf_q", 0.f); xc_display(x, P("eq_lmf_q"), d, 32);
    setn(x, "eq_hmf_q", 1.f); xc_display(x, P("eq_hmf_q"), e, 32);
    setm(x, "hc_freq", 21000.f); xc_display(x, P("hc_freq"), f, 32);
    CHECK(!strcmp(a, "+18.0 dB") && !strcmp(b, "17 Hz") && !strcmp(c, "-40.0 dB") && !strcmp(d, "0.10") && !strcmp(e, "3.50") && !strcmp(f, "21.0 kHz"),
          "GRANITE ranges: trim %s, low cut %s, threshold %s, Q %s..%s, high cut up to %s", a, b, c, d, e, f);
    CHECK(xc_get(x, P("gate_mode")) == 1.f && xc_get(x, P("cmp_thr")) != 1.f, "GRANITE preset: the gate/expander starts as the expander");
    xc_destroy(x);

    /* the 242's gains: mids +-15 at Q 0.1 to +-18 at Q 3.5; LF shelf +-16.5, bell +-18; constant Q even with STYLE on G */
    x = fresh4000();
    seto(x, "eq_on", 1); setm(x, "eq_lmf_freq", 1000.f); setn(x, "eq_lmf_gain", 1.f);
    setn(x, "eq_lmf_q", 1.f); double g35 = xc_eq_curve_db(x, 1000.f);
    setn(x, "eq_lmf_q", 0.f); double g01 = xc_eq_curve_db(x, 1000.f);
    char t[32]; xc_display(x, P("eq_lmf_gain"), t, 32);
    CHECK(fabs(g35 - 18) < 0.05 && fabs(g01 - 15) < 0.05 && !strcmp(t, "+15.0 dB"), "GRANITE LMF full boost: %+.2f dB at Q 3.5, %+.2f dB at Q 0.1 (reads \"%s\")", g35, g01, t);
    setn(x, "eq_lmf_gain", 0.5f);
    setn(x, "eq_lf_gain", 1.f); setm(x, "eq_lf_freq", 100.f);
    double shelf = xc_eq_curve_db(x, 25.f);
    seto(x, "eq_lf_type", 1); double bell = xc_eq_curve_db(x, 100.f);
    CHECK(fabs(shelf - 16.5) < 0.5 && fabs(bell - 18) < 0.05, "GRANITE LF full boost: shelf plateau %+.2f dB (+16.5), bell peak %+.2f dB (+18)", shelf, bell);
    xc_destroy(x);
    double w[2];
    for (int st = 0; st < 2; st++) {
        x = fresh4000();
        seto(x, "eq_style", st); setm(x, "eq_lmf_gain", 4.f); setm(x, "eq_lmf_freq", 1000.f); setm(x, "eq_lmf_q", 1.5f);
        w[st] = xc_eq_curve_db(x, 1500.f);
        xc_destroy(x);
    }
    CHECK(fabs(w[0] - w[1]) < 1e-4, "GRANITE EQ is E only: STYLE G and E draw the same bell (%.3f / %.3f dB)", w[0], w[1]);
    x = fresh4000();
    seto(x, "eq_on", 1); setm(x, "eq_hmf_freq", 2500.f); setn(x, "eq_hmf_gain", 1.f); setn(x, "eq_hmf_q", 0.6f); settle(x, 0.3f);
    double meas = sine_gain(x, 2500, 0.03f, 0.4f), cv = xc_eq_curve_db(x, 2500);
    CHECK(fabs(meas - cv) < 0.25, "GRANITE HMF: the sound %.2f dB matches the drawn curve %.2f dB", meas, cv);
    xc_destroy(x);

    /* fast attacks: 1 ms on both dynamics */
    x = fresh4000();
    seto(x, "cmp_on", 1); setm(x, "cmp_ratio", 10.f); setm(x, "cmp_thr", -40.f); seto(x, "cmp_det", 1); seto(x, "cmp_fast", 1);
    int n = (int)(0.6f * SR) / 48 * 48;
    float *in = malloc(n * 4), *o1 = malloc(n * 4), *o2 = malloc(n * 4);
    for (int i = 0; i < n; i++) in[i] = (i < n / 3 ? 0.01f : 0.5f) * sinf(2 * (float)M_PI * 1000 * i / SR);
    float gr[4000]; int k = 0;
    for (int i = 0; i < n; i += 16) { xc_process(x, in + i, in + i, o1 + i, o2 + i, 16); if (i >= n / 3 && k < 4000) gr[k++] = xc_comp_gr_db(x); }
    int t90 = -1;
    for (int j = 0; j < k; j++) if (gr[j] >= 0.9f * gr[k - 1]) { t90 = j; break; }
    double ms = t90 * 16 * 1000.0 / SR;
    CHECK(ms < 2.0, "GRANITE compressor fast attack: 90%% of %.1f dB in %.1f ms (GRANITE: 1 ms)", gr[k - 1], ms);
    xc_destroy(x);
    x = fresh4000();
    seto(x, "sh_on", 1); seto(x, "gate_mode", 0); setm(x, "gate_thr", -30.f); setm(x, "gate_range", 40.f); seto(x, "gate_fast", 1);
    for (int i = 0; i < n; i++) in[i] = (i < n / 2 ? 0.f : 0.3f);
    int open_at = -1;
    for (int i = 0; i < n; i += 4) { xc_process(x, in + i, in + i, o1 + i, o2 + i, 4); if (i >= n / 2 && open_at < 0 && xc_gate_gr_db(x) < 0.5f) open_at = i - n / 2; }
    CHECK(open_at * 1000.0 / SR > 0.7 && open_at * 1000.0 / SR < 1.3, "GRANITE gate fast attack: open in %.2f ms (GRANITE: 1 ms)", open_at * 1000.0 / SR);
    free(in); free(o1); free(o2);
    xc_destroy(x);

    /* and back: the FLANNEL's ranges return with its preset */
    x = fresh4000();
    selm(x, "eq_model", MODEL_FLANNEL);
    setn(x, "eq_lmf_q", 1.f); xc_display(x, P("eq_lmf_q"), a, 32);
    CHECK(!strcmp(a, "2.50") && xc_get(x, P("eq_lmf_q")) == 1.f, "picking the FLANNEL again brings back its ranges (Q top %s)", a);
    xc_destroy(x);
}

/* the SETUP drop-downs list the presets alphabetically; a new strip still starts on the FLANNEL */
/* the third preset: HEARTS (Weiss EQ1-MK2 and DS1-MK3 manuals) */
static XConsole *freshW(void)
{
    XConsole *x = fresh();
    selm(x, "in_model", MODEL_HEARTS); selm(x, "sh_model", MODEL_HEARTS); selm(x, "eq_model", MODEL_HEARTS); selm(x, "cmp_model", MODEL_HEARTS);
    return x;
}
/* the peak of the output (dB) for a steady sine, over the last half of `secs` */
static double sine_peak_db(XConsole *x, float hz, float amp, float phase, float secs)
{
    int n = (int)(secs * SR);
    float *in = malloc(n * sizeof(float)), *ol = malloc(n * sizeof(float)), *orr = malloc(n * sizeof(float));
    for (int i = 0; i < n; i++) in[i] = amp * sinf(2 * (float)M_PI * hz * i / SR + phase);
    run(x, in, in, ol, orr, n);
    float pk = 0;
    for (int i = n / 2; i < n; i++) pk = fmaxf(pk, fmaxf(fabsf(ol[i]), fabsf(orr[i])));
    free(in); free(ol); free(orr);
    return 20 * log10(pk + 1e-12);
}
static void check_hearts(void)
{
    XConsole *x = freshW();
    char t[10][32];
    int dflt = xc_get(x, P("gate_mode")) == 1.f && xc_get(x, P("lc_slope")) == 1.f && xc_get(x, P("hc_slope")) == 0.f
               && xc_get(x, P("cmp_det")) == 1.f && fabsf(xc_get(x, P("eq_lmf_gain")) - 0.5f) < 1e-6f && xc_get(x, P("pre_on")) == 0.f;
    CHECK(dflt, "HEARTS defaults: expander, 12 dB/oct low cut, 6 dB/oct high cut (the Gambit strip), peak detector, EQ gain 0 at the knob's centre, preamp colour off");
    setn(x, "eq_lmf_gain", 0.f); xc_display(x, P("eq_lmf_gain"), t[0], 32);
    setn(x, "eq_lmf_gain", 0.5f); xc_display(x, P("eq_lmf_gain"), t[1], 32);
    setn(x, "eq_lmf_gain", 1.f); xc_display(x, P("eq_lmf_gain"), t[2], 32);
    setn(x, "eq_lmf_q", 1.f); xc_display(x, P("eq_lmf_q"), t[3], 32);
    setn(x, "cmp_ratio", 0.f); xc_display(x, P("cmp_ratio"), t[4], 32);
    setn(x, "cmp_att", 0.f); xc_display(x, P("cmp_att"), t[5], 32);
    setn(x, "cmp_thr", 0.f); xc_display(x, P("cmp_thr"), t[6], 32);
    setm(x, "drv_char", 90.f); xc_display(x, P("drv_char"), t[7], 32);
    setm(x, "drv_amt", 6.f); xc_display(x, P("drv_amt"), t[8], 32);
    setn(x, "cmp_knee", 1.f); xc_display(x, P("cmp_knee"), t[9], 32);
    CHECK(!strcmp(t[0], "-39.0 dB") && !strcmp(t[1], "+0.0 dB") && !strcmp(t[2], "+18.0 dB") && !strcmp(t[3], "650.00") && !strcmp(t[4], "1:5.00")
          && !strcmp(t[5], "20 us") && !strcmp(t[6], "-60.0 dB") && !strcmp(t[7], "TYPE 2 (TP)") && !strcmp(t[8], "+6.0 dB") && !strcmp(t[9], "1.00"),
          "HEARTS ranges: EQ gain %s / %s / %s, Q to %s, ratio from %s, attack from %s, threshold to %s, limiter %s, pre-limiter %s, knee %s",
          t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], t[8], t[9]);
    xc_destroy(x);

    /* EQ1: a -39 dB notch at 1 kHz, Q 10, sound and drawn curve */
    x = freshW();
    seto(x, "eq_on", 1); setm(x, "eq_lmf_freq", 1000.f); setm(x, "eq_lmf_q", 10.f); setn(x, "eq_lmf_gain", 0.f);
    settle(x, 0.2f);
    double g = sine_gain(x, 1000.f, 0.25f, 0.6f), cv = xc_eq_curve_db(x, 1000.f);
    CHECK(fabs(g + 39) < 1.5 && fabs(cv + 39) < 0.5, "HEARTS EQ1 -39 dB notch at 1 kHz: the sound %.1f dB, the curve %.1f dB", g, cv);
    xc_destroy(x);

    /* DS1: ratio 1:2 above a -30 dB threshold expands upward: a -12 dBFS (peak) tone comes out about 18 dB louder */
    x = freshW();
    seto(x, "cmp_on", 1); setm(x, "cmp_thr", -30.f); setm(x, "cmp_ratio", 0.5f);
    g = sine_gain(x, 1000.f, 0.25f, 1.0f);
    CHECK(fabs(g - 18) < 1.5, "HEARTS upward expansion (1:2 over -30 dB): a -12 dBFS tone gains %+.1f dB (+18)", g);
    xc_destroy(x);

    /* DS1 soft-knee 1.0: from 0 dBFS down to twice the threshold; at the threshold, ratio 4: 3.75 dB of reduction */
    x = freshW();
    seto(x, "cmp_on", 1); seto(x, "cmp_det", 0); setm(x, "cmp_thr", -20.f); setm(x, "cmp_ratio", 4.f); setn(x, "cmp_knee", 1.f);
    g = sine_gain(x, 1000.f, 0.1f * sqrtf(2.f), 1.0f);
    double g0;
    setn(x, "cmp_knee", 0.f);
    g0 = sine_gain(x, 1000.f, 0.1f * sqrtf(2.f), 1.0f);
    CHECK(fabs(g + 3.75) < 0.75 && fabs(g0) < 0.3, "HEARTS knee 1.0 at a -20 dB threshold: %+.2f dB at the threshold (-3.75), hard knee %+.2f dB", g, g0);
    xc_destroy(x);

    /* the safety limiter: +12 dB into it, nothing over -0.1 dBFS; TYPE 2 also holds the peaks between samples down */
    double pk[3];
    for (int ty = 0; ty < 3; ty++) {
        x = freshW();
        seto(x, "drv_on", 1); setm(x, "drv_amt", 12.f); setm(x, "drv_char", ty == 0 ? 0.f : ty == 1 ? 50.f : 100.f);
        pk[ty] = sine_peak_db(x, ty == 2 ? 11025.f : 1000.f, 0.5f, ty == 2 ? (float)M_PI / 4 : 0.f, 0.5f);
        xc_destroy(x);
    }
    x = freshW();
    seto(x, "drv_on", 1); setm(x, "drv_amt", 12.f); setm(x, "drv_char", 50.f);
    double t1 = sine_peak_db(x, 11025.f, 0.5f, (float)M_PI / 4, 0.5f);
    xc_destroy(x);
    CHECK(pk[0] <= -0.09 && pk[1] <= -0.09 && pk[0] > -1.0 && pk[1] > -1.0 && pk[2] < t1 - 1.0,
          "HEARTS limiter, +12 dB into a -6 dBFS tone: ORIGINAL peaks %.2f, TYPE 1 %.2f dBFS (ceiling -0.1); at fs/4, TYPE 2 %.2f vs TYPE 1 %.2f (inter-sample peaks)",
          pk[0], pk[1], pk[2], t1);

    /* DRIVE is the limiter only under HEARTS: back on the FLANNEL it saturates again */
    x = freshW();
    seto(x, "drv_on", 1);
    selm(x, "cmp_model", MODEL_FLANNEL);
    seto(x, "drv_on", 1); setv(x, "drv_amt", 60.f);
    double h2, h3, nh;
    harmonics(x, 372, 0.3f, &h2, &h3, &nh);
    CHECK(h2 > -60 || h3 > -60, "back on the FLANNEL, DRIVE saturates again (h2 %.0f, h3 %.0f dB)", h2, h3);
    xc_destroy(x);

    /* the spectrum's look: HEARTS is looks 4 and 5 */
    x = fresh();
    selm(x, "eq_model", MODEL_HEARTS);
    int ok = xc_get(x, P("m_eqlook")) == 4.f;
    seto(x, "sp_view", 1); ok &= xc_get(x, P("m_eqlook")) == 5.f;
    CHECK(ok && xc_model_opt(SEC_INPUT, MODEL_HEARTS) == 4, "HEARTS: fifth in the lists, its spectrum looks 4 (line) and 5 (bars)");
    xc_destroy(x);
}

/* 0.8.0: the static transfer curves (the GRANITE's SHAPE and COMP graphs) and the SHAPE gain meter */
/* the fourth preset: SUEDE (1073-style EQ and preamp, 2254-style compressor, stepped switches) (0.9.0) */
static XConsole *freshN(void)
{
    XConsole *x = fresh();
    selm(x, "in_model", MODEL_SUEDE); selm(x, "sh_model", MODEL_SUEDE); selm(x, "eq_model", MODEL_SUEDE); selm(x, "cmp_model", MODEL_SUEDE);
    return x;
}
static void check_suede(void)
{
    XConsole *x = freshN();
    char t[12][32];
    setn(x, "in_gain", 1.f); xc_display(x, P("in_gain"), t[0], 32);
    setn(x, "lc_freq", 0.f); xc_display(x, P("lc_freq"), t[1], 32);
    setn(x, "lc_freq", 0.41f); xc_display(x, P("lc_freq"), t[2], 32);
    setn(x, "lc_freq", 0.59f); xc_display(x, P("lc_freq"), t[3], 32);
    setn(x, "eq_hf_freq", 1.f); xc_display(x, P("eq_hf_freq"), t[4], 32);
    setn(x, "cmp_ratio", 1.f); xc_display(x, P("cmp_ratio"), t[5], 32);
    setn(x, "cmp_rel", 1.f); xc_display(x, P("cmp_rel"), t[6], 32);
    setn(x, "eq_lmf_q", 1.f); xc_display(x, P("eq_lmf_q"), t[7], 32);
    setn(x, "cmp_att", 0.f); xc_display(x, P("cmp_att"), t[8], 32);
    setn(x, "eq_lmf_freq", 0.5f); xc_display(x, P("eq_lmf_freq"), t[9], 32);
    setn(x, "cmp_thr", 0.f); xc_display(x, P("cmp_thr"), t[10], 32);
    setn(x, "cmp_ratio", 0.f); xc_display(x, P("cmp_ratio"), t[11], 32);
    CHECK(!strcmp(t[0], "+20.0 dB") && !strcmp(t[1], "Off") && !strcmp(t[2], "80 Hz") && !strcmp(t[3], "80 Hz") && !strcmp(t[4], "Off")
          && !strcmp(t[5], "Limit") && !strcmp(t[6], "AUTO") && !strcmp(t[7], "HI Q") && !strcmp(t[8], "5.0 ms") && !strcmp(t[9], "700 Hz")
          && !strcmp(t[10], "-40.0 dB") && !strcmp(t[11], "1.5:1"),
          "SUEDE steps: trim %s, HPF %s / %s / %s (one position across its zone), HF %s, ratio %s..%s, recovery %s, %s, attack %s, LMF %s, threshold %s",
          t[0], t[1], t[2], t[3], t[4], t[11], t[5], t[6], t[7], t[8], t[9], t[10]);
    xc_destroy(x);
    x = freshN();
    int dflt = xc_get(x, P("pre_type")) == 2.f && xc_get(x, P("gate_mode")) == 0.f && xc_get(x, P("lc_slope")) == 2.f && xc_get(x, P("lc_freq")) < 0.2f;
    char d1[32], d2[32], d3[32];
    xc_display(x, P("cmp_ratio"), d1, 32); xc_display(x, P("eq_hf_freq"), d2, 32); xc_display(x, P("cmp_rel"), d3, 32);
    CHECK(dflt && !strcmp(d1, "3.0:1") && !strcmp(d2, "12.0 kHz") && !strcmp(d3, "400 ms"),
          "SUEDE defaults: IRON preamp type, GATE mode, HPF Off at 18 dB/oct, ratio %s, HF %s, recovery %s", d1, d2, d3);
    /* the EQ: sound = curve on a mid boost; an OFF position bypasses the band */
    seto(x, "eq_on", 1); setm(x, "eq_lmf_freq", 1600.f); setm(x, "eq_lmf_gain", 12.f);
    double g = sine_gain(x, 1600.f, 0.1f, 0.5f), cv = xc_eq_curve_db(x, 1600.f);
    setn(x, "eq_lmf_q", 1.f);
    double gq = sine_gain(x, 1131.f, 0.1f, 0.5f);   /* half an octave down: narrower with HI Q */
    setn(x, "eq_lmf_q", 0.f);
    double gn = sine_gain(x, 1131.f, 0.1f, 0.5f);
    setn(x, "eq_lmf_freq", 0.f);
    double off = sine_gain(x, 1600.f, 0.1f, 0.5f), cvo = xc_eq_curve_db(x, 1600.f);
    CHECK(fabs(g - 12) < 0.3 && fabs(g - cv) < 0.25 && gn > gq + 2 && fabs(off) < 0.05 && fabs(cvo) < 0.01,
          "SUEDE LMF +12 at 1.6 kHz: sound %+.2f, curve %+.2f; half an octave off NORMAL %+.1f vs HI Q %+.1f; OFF position %+.2f dB (curve %+.2f)", g, cv, gn, gq, off, cvo);
    setm(x, "eq_lf_freq", 60.f); setm(x, "eq_lf_gain", 12.f);
    double lf = xc_eq_curve_db(x, 25.f);
    float over = 0.f;
    for (float hz = 60.f; hz < 1000.f; hz *= 1.05f) over = fminf(over, xc_eq_curve_db(x, hz) - xc_eq_curve_db(x, 2000.f));
    CHECK(lf > 11.0 && over < -0.3, "SUEDE LF shelf at 60 Hz: %+.1f dB at 25 Hz, the 1073-style dip above it %.2f dB", lf, over);
    xc_destroy(x);
    /* the 2254: no auto make-up; -10 dBFS RMS over a -20 threshold at 4:1 comes out at -17.5 */
    x = freshN();
    seto(x, "cmp_on", 1); setm(x, "cmp_thr", -20.f); setm(x, "cmp_ratio", 4.f);
    double lv = out_level(x, 1000.f, powf(10.f, -10.f / 20.f) * 1.41421356f, 1.5f), cc = xc_comp_curve_db(x, -10.f);
    CHECK(fabs(lv + 17.5) < 0.6 && fabs(cc + 17.5) < 0.05, "SUEDE 4:1 over -20: -10 dBFS RMS in gives %.2f dBFS (curve %.2f; no auto make-up)", lv, cc);
    /* AUTO recovery: fast after a short burst, slow after a long one */
    float rec[2];
    for (int k = 0; k < 2; k++) {
        XConsole *y = freshN();
        seto(y, "cmp_on", 1); setm(y, "cmp_thr", -30.f); setm(y, "cmp_ratio", 6.f); setn(y, "cmp_rel", 1.f);
        int nb = (int)((k ? 2.0f : 0.03f) * SR), nq = (int)(0.15f * SR);
        float *in = malloc((nb + nq) * sizeof(float)), *o1 = malloc((nb + nq) * sizeof(float)), *o2 = malloc((nb + nq) * sizeof(float));
        for (int i = 0; i < nb + nq; i++) in[i] = (i < nb ? 0.7f : 0.01f) * sinf(2 * (float)M_PI * 1000.f * i / SR);
        run(y, in, in, o1, o2, nb);
        float g0 = xc_comp_gr_db(y);
        run(y, in + nb, in + nb, o1 + nb, o2 + nb, nq);
        rec[k] = xc_comp_gr_db(y) / g0;
        free(in); free(o1); free(o2);
        xc_destroy(y);
    }
    CHECK(rec[0] < 0.1f && rec[1] > 0.4f, "SUEDE AUTO recovery, 150 ms after: %.0f%% of the reduction left after a 30 ms burst, %.0f%% after 2 s", 100 * rec[0], 100 * rec[1]);
    /* the spectrum's look and the list place */
    int ok = xc_get(x, P("m_eqlook")) == 6.f;
    seto(x, "sp_view", 1); ok &= xc_get(x, P("m_eqlook")) == 7.f;
    CHECK(ok && xc_model_opt(SEC_INPUT, MODEL_SUEDE) == 5, "SUEDE: sixth in the lists, its spectrum looks 6 (line) and 7 (bars)");
    /* back on the FLANNEL its continuous ranges return */
    selm(x, "eq_model", MODEL_FLANNEL); setn(x, "eq_lmf_freq", 0.5f);
    char c9[32]; xc_display(x, P("eq_lmf_freq"), c9, 32);
    CHECK(strcmp(c9, "700 Hz") && strcmp(c9, "Off"), "picking the FLANNEL again: LMF sweeps freely (%s at the middle)", c9);
    xc_destroy(x);
}

/* the fifth preset: SANDSTONE (EQF-100 EQ, TLA-100A compressor, the BCA gate) (0.10.0) */
static XConsole *freshS(void)
{
    XConsole *x = fresh();
    selm(x, "in_model", MODEL_SANDSTONE); selm(x, "sh_model", MODEL_SANDSTONE); selm(x, "eq_model", MODEL_SANDSTONE); selm(x, "cmp_model", MODEL_SANDSTONE);
    return x;
}
static void check_sandstone(void)
{
    XConsole *x = freshS();
    char t[10][32];
    xc_display(x, P("eq_lf_freq"), t[0], 32); xc_display(x, P("eq_lmf_freq"), t[1], 32);
    xc_display(x, P("eq_hmf_freq"), t[2], 32); xc_display(x, P("eq_hf_freq"), t[3], 32);
    xc_display(x, P("eq_lmf_q"), t[4], 32); xc_display(x, P("cmp_att"), t[5], 32); xc_display(x, P("cmp_rel"), t[6], 32);
    setn(x, "lc_freq", 1.f); xc_display(x, P("lc_freq"), t[7], 32);
    setn(x, "hc_freq", 0.f); xc_display(x, P("hc_freq"), t[8], 32);
    setn(x, "eq_hf_freq", 1.f); xc_display(x, P("eq_hf_freq"), t[9], 32);
    int dflt = xc_get(x, P("pre_type")) == 1.f && xc_get(x, P("eq_lf_type")) == 1.f && xc_get(x, P("eq_hf_type")) == 1.f && xc_get(x, P("lc_slope")) == 1.f;
    CHECK(dflt && !strcmp(t[0], "180 Hz") && !strcmp(t[1], "560 Hz") && !strcmp(t[2], "2.20 kHz") && !strcmp(t[3], "8.20 kHz") && !strcmp(t[4], "BW 10.0")
          && !strcmp(t[5], "SLOW") && !strcmp(t[6], "MEDIUM") && !strcmp(t[7], "82 Hz") && !strcmp(t[8], "8.20 kHz") && !strcmp(t[9], "15.0 kHz"),
          "SANDSTONE defaults as the Grand Channel's: LF %s, LMF %s, HMF %s, HF %s, %s, attack %s, release %s, both bells, TUBE; low filter top %s, high filter bottom %s, HF top %s",
          t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], t[8], t[9]);
    setn(x, "eq_lmf_q", 1.f); xc_display(x, P("eq_lmf_q"), t[0], 32);
    setn(x, "cmp_att", 0.f); xc_display(x, P("cmp_att"), t[1], 32);
    setn(x, "cmp_rel", 1.f); xc_display(x, P("cmp_rel"), t[2], 32);
    CHECK(!strcmp(t[0], "BW 0.0") && !strcmp(t[1], "FAST") && !strcmp(t[2], "SLOW"), "SANDSTONE switches: narrowest %s, attack %s, release %s", t[0], t[1], t[2]);
    xc_destroy(x);
    /* the EQ: sound = curve; a narrower BANDWIDTH is narrower */
    x = freshS();
    seto(x, "eq_on", 1); setm(x, "eq_hmf_freq", 2200.f); setm(x, "eq_hmf_gain", 12.f);
    double g = sine_gain(x, 2200.f, 0.1f, 0.5f), cv = xc_eq_curve_db(x, 2200.f);
    double gw = sine_gain(x, 1100.f, 0.1f, 0.5f);
    setn(x, "eq_hmf_q", 1.f);
    double gn = sine_gain(x, 1100.f, 0.1f, 0.5f);
    CHECK(fabs(g - 12) < 0.3 && fabs(g - cv) < 0.25 && gw > gn + 3, "SANDSTONE HMF +12 at 2.2 kHz: sound %+.2f, curve %+.2f; an octave down BW 10 %+.1f vs BW 0 %+.1f", g, cv, gw, gn);
    xc_destroy(x);
    /* the TLA-100A: no auto make-up; soft knee */
    x = freshS();
    seto(x, "cmp_on", 1); setm(x, "cmp_thr", -30.f); setm(x, "cmp_ratio", 4.f);
    double c1 = xc_comp_curve_db(x, -10.f), c0 = xc_comp_curve_db(x, -30.f);
    CHECK(fabs(c1 + 25.0) < 0.05 && c0 < -30.2 && c0 > -32.0, "SANDSTONE 4:1 over -30: -10 in gives %.2f (no auto make-up), at the threshold %.2f (soft knee)", c1, c0);
    /* program-dependent release: back faster after a short burst than after a long one */
    float rec[2];
    for (int k = 0; k < 2; k++) {
        XConsole *y = freshS();
        seto(y, "cmp_on", 1); setm(y, "cmp_thr", -30.f); setm(y, "cmp_ratio", 6.f); setn(y, "cmp_rel", 1.f);   /* SLOW */
        int nb = (int)((k ? 2.0f : 0.03f) * SR), nq = (int)(0.15f * SR);
        float *in = malloc((nb + nq) * sizeof(float)), *o1 = malloc((nb + nq) * sizeof(float)), *o2 = malloc((nb + nq) * sizeof(float));
        for (int i = 0; i < nb + nq; i++) in[i] = (i < nb ? 0.7f : 0.01f) * sinf(2 * (float)M_PI * 1000.f * i / SR);
        run(y, in, in, o1, o2, nb);
        float g0 = xc_comp_gr_db(y);
        run(y, in + nb, in + nb, o1 + nb, o2 + nb, nq);
        rec[k] = xc_comp_gr_db(y) / g0;
        free(in); free(o1); free(o2);
        xc_destroy(y);
    }
    CHECK(rec[0] < rec[1] - 0.2f, "SANDSTONE SLOW release, 150 ms after: %.0f%% of the reduction left after a 30 ms burst, %.0f%% after 2 s", 100 * rec[0], 100 * rec[1]);
    int ok = xc_get(x, P("m_eqlook")) == 8.f;
    seto(x, "sp_view", 1); ok &= xc_get(x, P("m_eqlook")) == 9.f;
    CHECK(ok && xc_model_opt(SEC_INPUT, MODEL_SANDSTONE) == 8 && xc_model_opt(SEC_INPUT, MODEL_FLANNEL) == 7, "SANDSTONE: last in the lists, spectrum looks 8 and 9");
    xc_destroy(x);
}

/* the sixth preset: HEXX (550B EQ with proportional Q, 2500/527-style compressor) (0.11.0) */
static XConsole *freshA(void)
{
    XConsole *x = fresh();
    selm(x, "in_model", MODEL_HEXX); selm(x, "sh_model", MODEL_HEXX); selm(x, "eq_model", MODEL_HEXX); selm(x, "cmp_model", MODEL_HEXX);
    return x;
}
static void check_hexx(void)
{
    XConsole *x = freshA();
    char t[10][32];
    xc_display(x, P("eq_lf_freq"), t[0], 32); xc_display(x, P("eq_lmf_freq"), t[1], 32);
    xc_display(x, P("eq_hmf_freq"), t[2], 32); xc_display(x, P("eq_hf_freq"), t[3], 32);
    xc_display(x, P("eq_lmf_q"), t[4], 32); xc_display(x, P("cmp_att"), t[5], 32); xc_display(x, P("cmp_rel"), t[6], 32);
    xc_display(x, P("cmp_ratio"), t[7], 32); xc_display(x, P("gate_rel"), t[8], 32);
    setn(x, "eq_hf_freq", 1.f); xc_display(x, P("eq_hf_freq"), t[9], 32);
    int dflt = xc_get(x, P("pre_type")) == 2.f && xc_get(x, P("eq_lf_type")) == 1.f && xc_get(x, P("eq_hf_type")) == 1.f;
    CHECK(dflt && !strcmp(t[0], "100 Hz") && !strcmp(t[1], "240 Hz") && !strcmp(t[2], "5.00 kHz") && !strcmp(t[3], "10.0 kHz") && !strcmp(t[4], "1.00x")
          && !strcmp(t[5], "25 ms") && !strcmp(t[6], "1.30 s") && !strcmp(t[7], "1.5:1") && !strcmp(t[8], "1.33 s") && !strcmp(t[9], "20.0 kHz"),
          "HEXX defaults as the screenshot's: LF %s, LMF %s, HMF %s, HF %s, Q %s, attack %s, release %s, ratio %s, gate release %s, both bells, IRON; HF top %s",
          t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], t[8], t[9]);
    xc_destroy(x);
    /* the EQ: sound = curve; proportional Q: an octave away, +3 dB is relatively wider than +12 */
    x = freshA();
    seto(x, "eq_on", 1); setm(x, "eq_hmf_freq", 3000.f); setm(x, "eq_hmf_gain", 12.f);
    double g = sine_gain(x, 3000.f, 0.1f, 0.5f), cv = xc_eq_curve_db(x, 3000.f), w12 = sine_gain(x, 1500.f, 0.1f, 0.5f) / 12.0;
    setm(x, "eq_hmf_gain", 3.f);
    double w3 = sine_gain(x, 1500.f, 0.1f, 0.5f) / 3.0, cv3 = xc_eq_curve_db(x, 1500.f) / 3.0;
    CHECK(fabs(g - 12) < 0.3 && fabs(g - cv) < 0.25 && w3 > w12 + 0.15 && fabs(w3 - cv3) < 0.1,
          "HEXX HMF +12 at 3 kHz: sound %+.2f, curve %+.2f; an octave down %.0f%% of the gain at +3 vs %.0f%% at +12 (proportional Q)", g, cv, 100 * w3, 100 * w12);
    xc_destroy(x);
    /* the compressor: no auto make-up, AUTO knee 4 dB */
    x = freshA();
    seto(x, "cmp_on", 1); setm(x, "cmp_thr", -30.f); setm(x, "cmp_ratio", 4.f);
    double c1 = xc_comp_curve_db(x, -10.f), c0 = xc_comp_curve_db(x, -30.f);
    CHECK(fabs(c1 + 25.0) < 0.05 && c0 < -30.2 && c0 > -31.0, "HEXX 4:1 over -30: -10 in gives %.2f (no auto make-up), at the threshold %.2f (4 dB knee)", c1, c0);
    int ok = xc_get(x, P("m_eqlook")) == 10.f;
    seto(x, "sp_view", 1); ok &= xc_get(x, P("m_eqlook")) == 11.f;
    CHECK(ok && xc_model_opt(SEC_INPUT, MODEL_HEXX) == 1, "HEXX: second in the lists, spectrum looks 10 and 11");
    xc_destroy(x);
}

/* the seventh preset: MOLTEN (Curve Bender EQ, Zener Limiter) (0.12.0) */
static XConsole *freshC(void)
{
    XConsole *x = fresh();
    selm(x, "in_model", MODEL_MOLTEN); selm(x, "sh_model", MODEL_MOLTEN); selm(x, "eq_model", MODEL_MOLTEN); selm(x, "cmp_model", MODEL_MOLTEN);
    return x;
}
static void check_molten(void)
{
    XConsole *x = freshC();
    char t[14][32];
    const char *K[12] = {"eq_lf_freq", "eq_lmf_freq", "eq_hmf_freq", "eq_hf_freq", "eq_lmf_q", "cmp_ratio", "cmp_att", "cmp_rel", "cmp_makeup", "lc_freq", "hc_freq", "gate_rel"};
    for (int i = 0; i < 12; i++) xc_display(x, P(K[i]), t[i], 32);
    setm(x, "cmp_ratio", 3.f); xc_display(x, P("cmp_ratio"), t[12], 32); xc_display(x, P("cmp_att"), t[13], 32);
    int dflt = xc_get(x, P("pre_type")) == 2.f && xc_get(x, P("eq_lf_type")) == 1.f && xc_get(x, P("eq_hf_type")) == 1.f
               && xc_get(x, P("lc_slope")) == 0.f && xc_get(x, P("hc_slope")) == 0.f;
    CHECK(dflt && !strcmp(t[0], "91 Hz") && !strcmp(t[1], "1.20 kHz") && !strcmp(t[2], "3.60 kHz") && !strcmp(t[3], "10.0 kHz") && !strcmp(t[4], "1.00x")
          && !strcmp(t[5], "COMP 1") && !strcmp(t[6], "2 (38 ms)") && !strcmp(t[7], "11 (775 ms)") && !strcmp(t[8], "+0.0 dB")
          && !strcmp(t[9], "Off") && !strcmp(t[10], "Off") && !strcmp(t[11], "1.33 s") && !strcmp(t[12], "LIMIT") && !strcmp(t[13], "2 (6.7 ms)"),
          "MOLTEN defaults: LF %s, LMF %s, HMF %s, HF %s, Q %s, mode %s, attack %s, release %s, output %s, filters %s / %s 6 dB/oct, gate release %s, bells, IRON; LIMIT: %s, attack %s",
          t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], t[8], t[9], t[10], t[11], t[12], t[13]);
    xc_destroy(x);
    /* the EQ: sound = curve; the band narrows with gain: an octave away, +3 dB keeps relatively more than +15 */
    x = freshC();
    seto(x, "eq_on", 1); setm(x, "eq_hmf_freq", 3600.f); setm(x, "eq_hmf_gain", 15.f);
    double g = sine_gain(x, 3600.f, 0.1f, 0.5f), cv = xc_eq_curve_db(x, 3600.f), w15 = sine_gain(x, 1800.f, 0.1f, 0.5f) / 15.0;
    setm(x, "eq_hmf_gain", 3.f);
    double w3 = sine_gain(x, 1800.f, 0.1f, 0.5f) / 3.0, cv3 = xc_eq_curve_db(x, 1800.f) / 3.0;
    CHECK(fabs(g - 15) < 0.4 && fabs(g - cv) < 0.25 && w3 > w15 + 0.1 && fabs(w3 - cv3) < 0.1,
          "MOLTEN HMF +15 at 3.6 kHz: sound %+.2f, curve %+.2f; an octave down %.0f%% of the gain at +3 vs %.0f%% at +15", g, cv, 100 * w3, 100 * w15);
    xc_destroy(x);
    /* the compressor: COMP 1 2:1, LIMIT 8:1, no auto make-up, OUTPUT steps */
    x = freshC();
    seto(x, "cmp_on", 1); setm(x, "cmp_thr", -30.f);
    double c1 = xc_comp_curve_db(x, -10.f);
    setm(x, "cmp_ratio", 3.f);
    double cl = xc_comp_curve_db(x, -10.f);
    setm(x, "cmp_makeup", -4.f);
    double cm = xc_comp_curve_db(x, -10.f);
    CHECK(fabs(c1 + 20.0) < 0.05 && fabs(cl + 27.5) < 0.05 && fabs(cm + 31.5) < 0.05,
          "MOLTEN over -30: -10 in gives %.2f in COMP 1 (2:1), %.2f in LIMIT (8:1), %.2f with OUTPUT -4 (no auto make-up)", c1, cl, cm);
    int ok = xc_get(x, P("m_eqlook")) == 12.f;
    seto(x, "sp_view", 1); ok &= xc_get(x, P("m_eqlook")) == 13.f;
    CHECK(ok && xc_model_opt(SEC_INPUT, MODEL_MOLTEN) == 3, "MOLTEN: fourth in the lists, spectrum looks 12 and 13");
    xc_destroy(x);
}

/* the eighth preset: SPADES (VT-737sp) (0.13.0) */
static XConsole *freshV(void)
{
    XConsole *x = fresh();
    selm(x, "in_model", MODEL_SPADES); selm(x, "sh_model", MODEL_SPADES); selm(x, "eq_model", MODEL_SPADES); selm(x, "cmp_model", MODEL_SPADES);
    return x;
}
static void check_spades(void)
{
    XConsole *x = freshV();
    char t[9][32];
    const char *K[9] = {"eq_lf_freq", "eq_lmf_freq", "eq_hmf_freq", "eq_hf_freq", "eq_lmf_q", "lc_freq", "cmp_att", "cmp_rel", "cmp_ratio"};
    for (int i = 0; i < 9; i++) xc_display(x, P(K[i]), t[i], 32);
    int dflt = xc_get(x, P("pre_type")) == 1.f && xc_get(x, P("eq_lf_type")) == 0.f && xc_get(x, P("eq_hf_type")) == 0.f && xc_get(x, P("lc_slope")) == 0.f;
    CHECK(dflt && !strcmp(t[0], "60 Hz") && !strcmp(t[1], "300 Hz") && !strcmp(t[2], "2.00 kHz") && !strcmp(t[3], "15.0 kHz") && !strcmp(t[4], "LO Q")
          && !strcmp(t[5], "Off"),
          "SPADES defaults: LF %s, LMF %s, HMF %s, HF %s, Q %s, HPF %s 6 dB/oct, attack %s, release %s, ratio %s, shelves, TUBE",
          t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], t[8]);
    setm(x, "eq_lmf_q", 2.f); xc_display(x, P("eq_lmf_q"), t[0], 32);
    CHECK(!strcmp(t[0], "HI Q"), "SPADES Q switch: %s", t[0]);
    xc_destroy(x);
    /* the EQ: sound = curve on a mid and the bass shelf */
    x = freshV();
    seto(x, "eq_on", 1); setm(x, "eq_lmf_freq", 1000.f); setm(x, "eq_lmf_gain", 12.f); setm(x, "eq_lf_gain", 10.f);
    double g = sine_gain(x, 1000.f, 0.1f, 0.5f), cv = xc_eq_curve_db(x, 1000.f), gl = sine_gain(x, 30.f, 0.1f, 0.8f), cl = xc_eq_curve_db(x, 30.f);
    CHECK(fabs(g - cv) < 0.3 && fabs(gl - cl) < 0.4 && cl > 8.0,
          "SPADES LMF +12 at 1 kHz: sound %+.2f, curve %+.2f; bass shelf +10 at 60 Hz, at 30 Hz: sound %+.2f, curve %+.2f", g, cv, gl, cl);
    xc_destroy(x);
    /* the compressor: manual make-up, ratio as set */
    x = freshV();
    seto(x, "cmp_on", 1); setm(x, "cmp_thr", -30.f); setm(x, "cmp_ratio", 4.f);
    double c4 = xc_comp_curve_db(x, -10.f);
    setm(x, "cmp_makeup", 5.f);
    double cm = xc_comp_curve_db(x, -10.f);
    CHECK(fabs(c4 + 25.0) < 0.05 && fabs(cm + 20.0) < 0.05,
          "SPADES over -30: -10 in gives %.2f at 4:1 (no auto make-up), %.2f with GAIN +5", c4, cm);
    int ok = xc_get(x, P("m_eqlook")) == 14.f;
    seto(x, "sp_view", 1); ok &= xc_get(x, P("m_eqlook")) == 15.f;
    CHECK(ok && xc_model_opt(SEC_INPUT, MODEL_SPADES) == 2, "SPADES: third in the lists, spectrum looks 14 and 15");
    xc_destroy(x);
}

/* the ninth preset: MOCHA (UA LA-6176: 610-B + 1176LN) (0.14.0) */
static XConsole *freshL(void)
{
    XConsole *x = fresh();
    selm(x, "in_model", MODEL_MOCHA); selm(x, "sh_model", MODEL_MOCHA); selm(x, "eq_model", MODEL_MOCHA); selm(x, "cmp_model", MODEL_MOCHA);
    return x;
}
static void check_mocha(void)
{
    XConsole *x = freshL();
    char t[5][32];
    const char *K[5] = {"eq_lf_freq", "eq_hf_freq", "cmp_ratio", "cmp_att", "cmp_rel"};
    for (int i = 0; i < 5; i++) xc_display(x, P(K[i]), t[i], 32);
    int dflt = xc_get(x, P("pre_type")) == 1.f && xc_get(x, P("eq_lf_type")) == 0.f && xc_get(x, P("eq_hf_type")) == 0.f;
    CHECK(dflt && !strcmp(t[0], "100 Hz") && !strcmp(t[1], "10.0 kHz"),
          "MOCHA defaults: LF %s, HF %s, ratio %s, attack %s, release %s, shelves, TUBE", t[0], t[1], t[2], t[3], t[4]);
    setn(x, "cmp_ratio", 1.f); xc_display(x, P("cmp_ratio"), t[0], 32);
    CHECK(!strcmp(t[0], "Limit"), "MOCHA ratio top (all buttons): %s", t[0]);
    xc_destroy(x);
    /* the EQ: sound = curve on the low shelf */
    x = freshL();
    seto(x, "eq_on", 1); setm(x, "eq_lf_gain", 9.f);
    double gl = sine_gain(x, 40.f, 0.1f, 0.8f), cl = xc_eq_curve_db(x, 40.f);
    CHECK(fabs(gl - cl) < 0.4 && cl > 6.0, "MOCHA low shelf +9 at 100 Hz, at 40 Hz: sound %+.2f, curve %+.2f", gl, cl);
    xc_destroy(x);
    /* the compressor: 4:1, manual OUTPUT */
    x = freshL();
    seto(x, "cmp_on", 1); setm(x, "cmp_thr", -30.f);
    double c4 = xc_comp_curve_db(x, -10.f);
    setm(x, "cmp_makeup", 5.f);
    double cm = xc_comp_curve_db(x, -10.f);
    CHECK(fabs(c4 + 25.0) < 0.05 && fabs(cm + 20.0) < 0.05,
          "MOCHA over -30: -10 in gives %.2f at 4:1 (no auto make-up), %.2f with OUTPUT +5", c4, cm);
    int ok = xc_get(x, P("m_eqlook")) == 16.f;
    seto(x, "sp_view", 1); ok &= xc_get(x, P("m_eqlook")) == 17.f;
    CHECK(ok && xc_model_opt(SEC_INPUT, MODEL_MOCHA) == 0, "MOCHA: first in the lists, spectrum looks 16 and 17");
    xc_destroy(x);
}

static XConsole *freshT(void)
{
    XConsole *x = fresh();
    selm(x, "in_model", MODEL_TITANIUM); selm(x, "sh_model", MODEL_TITANIUM); selm(x, "eq_model", MODEL_TITANIUM); selm(x, "cmp_model", MODEL_TITANIUM);
    return x;
}

/* 0.16.0: TITANIUM (strip), TITANIUM EQ (SHAPE + EQ), TITANIUM DRIVE (COMP + DRIVE) */
static void check_empirical(void)
{
    int ok = 1;
    for (int s = SEC_INPUT; s <= SEC_COMP; s++) ok &= xc_model_in(s, MODEL_TITANIUM);
    ok &= !xc_model_in(SEC_INPUT, MODEL_TITANIUM_EQ) && xc_model_in(SEC_SHAPE, MODEL_TITANIUM_EQ) && xc_model_in(SEC_EQ, MODEL_TITANIUM_EQ) && !xc_model_in(SEC_COMP, MODEL_TITANIUM_EQ);
    ok &= !xc_model_in(SEC_INPUT, MODEL_TITANIUM_DRIVE) && !xc_model_in(SEC_SHAPE, MODEL_TITANIUM_DRIVE) && !xc_model_in(SEC_EQ, MODEL_TITANIUM_DRIVE) && xc_model_in(SEC_COMP, MODEL_TITANIUM_DRIVE);
    XConsole *x = fresh();
    xc_apply_preset(x, SEC_INPUT, MODEL_TITANIUM_DRIVE);
    xc_apply_preset(x, SEC_EQ, MODEL_TITANIUM_DRIVE);
    ok &= xc_get(x, P("in_model")) == (float)xc_model_opt(SEC_INPUT, MODEL_FLANNEL) && xc_get(x, P("eq_model")) == (float)xc_model_opt(SEC_EQ, MODEL_FLANNEL);
    xc_destroy(x);
    CHECK(ok, "TITANIUM in all four lists, TITANIUM EQ in SHAPE and EQ only, TITANIUM DRIVE in COMPRESSOR only (a pick outside its lists is ignored)");

    x = freshT();
    char t[6][32];
    const char *K[6] = {"gate_thr", "gate_hold", "eq_lmf_q", "cmp_ratio", "cmp_att", "drv_amt"};
    for (int i = 0; i < 6; i++) xc_display(x, P(K[i]), t[i], 32);
    int dflt = xc_get(x, P("drv_on")) == 1.f && xc_get(x, P("lc_slope")) == 2.f && xc_get(x, P("hc_slope")) == 2.f && xc_get(x, P("gate_fast")) == 0.f;
    CHECK(dflt && !strcmp(t[0], "-20.0 dB") && !strcmp(t[1], "6.00 kHz") && !strcmp(t[2], "0.70") && !strcmp(t[3], "4.0:1") && !strcmp(t[4], "8.0 ms") && !strcmp(t[5], "3.0"),
          "TITANIUM defaults: DS %s at %s, mid Q %s, ratio %s, attack %s, DRIVE %s (on); filters 18 dB/oct, de-esser", t[0], t[1], t[2], t[3], t[4], t[5]);
    setn(x, "cmp_ratio", 1.f); xc_display(x, P("cmp_ratio"), t[0], 32);
    setn(x, "eq_lf_freq", 0.9f); xc_display(x, P("eq_lf_freq"), t[1], 32);
    seto(x, "eq_hf_type", 1); setn(x, "eq_hf_freq", 1.f); xc_display(x, P("eq_hf_freq"), t[2], 32);
    const char *n1 = xc_param_alt_name(x, P("gate_hold")), *n2 = xc_param_alt_name(x, P("cmp_thr"));
    XConsole *y = fresh();
    const char *n0 = xc_param_alt_name(y, P("gate_hold"));
    xc_destroy(y);
    CHECK(!strcmp(t[0], "NUKE") && !strcmp(t[1], "120 Hz") && !strcmp(t[2], "20.5 kHz") && n1 && !strcmp(n1, "De-Ess Frequency") && !n2 && !n0,
          "TITANIUM: ratio top %s, LF shelf fixed at %s, HF bell up to %s; SHAPE knob named \"%s\" for MPC (FLANNEL: its own)", t[0], t[1], t[2], n1 ? n1 : "?");
    xc_destroy(x);

    /* the de-esser: level independent; HF LIMITER: level dependent */
    x = freshT(); seto(x, "sh_on", 1); settle(x, 0.05f);
    double hi = sine_gain(x, 8000.f, 0.25f, 0.5f), hiq = sine_gain(x, 8000.f, 0.008f, 0.5f), lo = sine_gain(x, 200.f, 0.25f, 0.5f);
    CHECK(hi < -2.0 && fabs(hi - hiq) < 1.0 && lo > -0.3,
          "TITANIUM EQ de-esser at 6 kHz: 8 kHz at -12 dBFS %+.2f dB, at -42 dBFS %+.2f dB (level independent); 200 Hz %+.2f dB", hi, hiq, lo);
    seto(x, "gate_fast", 1); settle(x, 0.05f);
    double lh = sine_gain(x, 8000.f, 0.5f, 0.5f), ll = sine_gain(x, 8000.f, 0.005f, 0.5f);
    float c = xc_gate_curve_db(x, -10.f);
    CHECK(lh < -6.0 && ll > -0.3 && fabsf(c + 19.f) < 0.05f,
          "TITANIUM EQ HF LIMITER (threshold -20): 8 kHz at -6 dBFS %+.2f dB, at -46 dBFS %+.2f dB; curve -10 -> %.2f", lh, ll, c);
    xc_destroy(x);

    /* the EQ: the fixed LF shelf, +-10 dB, sound = curve */
    x = freshT(); seto(x, "eq_on", 1); seto(x, "drv_on", 0); setm(x, "eq_lf_gain", 14.f);   /* the EQ alone (DRIVE is on under TITANIUM) */
    double s40 = sine_gain(x, 40.f, 0.1f, 0.8f), c40 = xc_eq_curve_db(x, 40.f), c20 = xc_eq_curve_db(x, 20.f);
    setn(x, "eq_lf_freq", 0.95f);
    double c20b = xc_eq_curve_db(x, 20.f);
    CHECK(fabs(s40 - c40) < 0.4 && c20 > 8.5 && c20 < 10.2 && fabs(c20 - c20b) < 0.01,
          "TITANIUM EQ LF shelf at full gain: 20 Hz %+.2f dB (FREQ moved: %+.2f), 40 Hz sound %+.2f / curve %+.2f", c20, c20b, s40, c40);
    xc_destroy(x);

    /* TITANIUM's cuts have a bump; the FLANNEL's don't */
    x = freshT(); y = fresh();
    setm(x, "lc_freq", 100.f); setm(y, "lc_freq", 100.f);
    float bx = -99.f, by = -99.f;
    for (float hz = 100.f; hz < 1000.f; hz *= 1.05f) { bx = fmaxf(bx, xc_filter_curve_db(x, hz)); by = fmaxf(by, xc_filter_curve_db(y, hz)); }
    CHECK(bx > 0.8f && by < 0.1f, "TITANIUM low cut at 100 Hz: a bump of %+.2f dB over it (FLANNEL %+.2f)", bx, by);
    xc_destroy(x); xc_destroy(y);

    /* the Mike-E: 2:1 with a 20 dB knee, manual GAIN; DRIVE on, near unity */
    x = fresh(); selm(x, "cmp_model", MODEL_TITANIUM_DRIVE); seto(x, "cmp_on", 1);
    setm(x, "cmp_thr", -30.f); setm(x, "cmp_ratio", 2.f);
    float k1 = xc_comp_curve_db(x, -10.f), k2 = xc_comp_curve_db(x, -30.f);
    double dg = sine_gain(x, 1000.f, 0.25f, 0.5f);
    seto(x, "cmp_on", 0);
    double dg0 = sine_gain(x, 1000.f, 0.25f, 0.5f);
    ok = xc_get(x, P("m_eqlook")) == 0.f;
    selm(x, "eq_model", MODEL_TITANIUM_EQ); ok &= xc_get(x, P("m_eqlook")) == 20.f;
    selm(x, "eq_model", MODEL_TITANIUM); ok &= xc_get(x, P("m_eqlook")) == 18.f;
    CHECK(fabsf(k1 + 20.f) < 0.05f && fabsf(k2 + 31.25f) < 0.05f && dg < dg0 - 1.0 && fabs(dg0) < 2.0 && ok,
          "TITANIUM DRIVE 2:1 over -30: -10 -> %.2f, -30 -> %.2f (20 dB knee); a -12 dBFS tone %+.2f dB compressed, %+.2f with DRIVE alone; looks 18 / 20", k1, k2, dg, dg0);
    xc_destroy(x);
}

static void check_curves(void)
{
    XConsole *x = fresh4000();
    setm(x, "gate_thr", -30.f); setm(x, "gate_range", 20.f); setm(x, "gate_ratio", 2.f); seto(x, "gate_mode", 1);
    float a = xc_gate_curve_db(x, -10.f), b = xc_gate_curve_db(x, -35.f), c = xc_gate_curve_db(x, -55.f);
    seto(x, "gate_mode", 0);
    float d = xc_gate_curve_db(x, -35.f);
    CHECK(fabsf(a + 10.f) < 0.01f && fabsf(b + 40.f) < 0.05f && fabsf(c + 75.f) < 0.05f && fabsf(d + 55.f) < 0.05f,
          "gate curve (thr -30, range 20, EXP 2:1): -10 -> %.1f, -35 -> %.1f, -55 -> %.1f (capped by range); GATE: -35 -> %.1f", a, b, c, d);
    setm(x, "cmp_thr", -20.f); setm(x, "cmp_ratio", 4.f); seto(x, "cmp_det", 1);   /* PEAK: hard knee (AUTO) */
    float mk = (-10.f - -20.f) * 0.75f;                                                  /* the GRANITE's auto make-up */
    float e1 = xc_comp_curve_db(x, -30.f), e2 = xc_comp_curve_db(x, -10.f);
    CHECK(fabsf(e1 - (-30.f + mk)) < 0.05f && fabsf(e2 - (-10.f - 7.5f + mk)) < 0.05f,
          "comp curve (thr -20, 4:1, make-up %.1f): -30 -> %.1f, -10 -> %.1f", mk, e1, e2);
    xc_destroy(x);
    /* the SHAPE gain meter: an expander working on a quiet tone reads below the middle */
    x = fresh4000();
    seto(x, "sh_on", 1); setm(x, "gate_thr", -20.f); setm(x, "gate_range", 20.f); setm(x, "gate_ratio", 4.f); seto(x, "gate_mode", 1);
    sine_gain(x, 1000.f, 0.01f, 0.5f);                                                    /* -40 dBFS */
    float m = xc_get(x, P("m_shape")) * 40.f - 20.f;
    CHECK(m < -15.f, "SHAPE gain meter under an expander at -40 dBFS: %.1f dB (the gate's -20)", m);
    xc_destroy(x);
}

/* 0.15.0: each SETUP drop-down its own list. All nine presets are channel strips, so every list has all nine, in the
 * same order; a place maps to a model and back; only the four preset parameters have a section. */
static void check_section_lists(void)
{
    const char *k[4] = {"in_model", "sh_model", "eq_model", "cmp_model"};
    int ok = xc_model_section(P("eq_lf_gain")) == 0 && xc_model_section(P("order")) == 0;
    for (int s = SEC_INPUT; s <= SEC_COMP; s++) {
        int i = P(k[s - 1]), n = xc_param_options(i);
        static const int NL[5] = {0, 10, 11, 11, 11};   /* nine strips + TITANIUM; + TITANIUM EQ (SHAPE, EQ); + TITANIUM DRIVE (COMP) */
        ok &= xc_model_section(i) == s && n == NL[s];
        for (int o = 0; o < n; o++) {
            int m = xc_opt_model(s, o);
            ok &= xc_model_in(s, m) && xc_model_opt(s, m) == o;
        }
    }
    XConsole *x = fresh();
    selm(x, "cmp_model", MODEL_HEXX);
    int hexx = xc_get(x, P("cmp_model")) == (float)xc_model_opt(SEC_COMP, MODEL_HEXX);
    xc_apply_preset(x, SEC_COMP, 99);   /* no such model: nothing changes */
    ok &= hexx && xc_get(x, P("cmp_model")) == (float)xc_model_opt(SEC_COMP, MODEL_HEXX) && xc_get(x, P("eq_model")) == (float)xc_model_opt(SEC_EQ, MODEL_FLANNEL);
    CHECK(ok, "SETUP lists: one per section (PREAMP 10, SHAPE / EQ / COMP 11); places map to models and back; an unknown model is ignored");
    xc_destroy(x);
}

/* 0.17.0: CHANNEL STRIP sets all four; each section's list is STRIP + its units */
static void check_strip_selector(void)
{
    const char *k[4] = {"in_model", "sh_model", "eq_model", "cmp_model"}, *u[4] = {"in_unit", "sh_unit", "eq_unit", "cmp_unit"};
    int ok = xc_param_options(P("strip_sel")) == 10 && xc_param_options(P("in_unit")) == 1 && xc_param_options(P("sh_unit")) == 2
          && xc_param_options(P("eq_unit")) == 2 && xc_param_options(P("cmp_unit")) == 2;
    for (int o = 0; o < 10; o++) ok &= xc_is_strip(xc_strip_model_at(o)) && xc_strip_opt(xc_strip_model_at(o)) == o;
    ok &= !xc_is_strip(MODEL_TITANIUM_EQ) && !xc_is_strip(MODEL_TITANIUM_DRIVE) && xc_strip_model_at(9) == MODEL_TITANIUM;
    XConsole *x = fresh();
    ok &= xc_get(x, P("strip_sel")) == (float)xc_strip_opt(MODEL_FLANNEL);
    for (int i = 0; i < 4; i++) ok &= xc_get(x, P(u[i])) == 0.f;
    seto(x, "strip_sel", xc_strip_opt(MODEL_TITANIUM));
    for (int i = 0; i < 4; i++) ok &= xc_get(x, P(k[i])) == (float)xc_model_opt(i + 1, MODEL_TITANIUM) && xc_get(x, P(u[i])) == 0.f;
    int a = ok;
    seto(x, "eq_unit", 1); seto(x, "cmp_unit", 1);
    ok &= xc_get(x, P("eq_model")) == (float)xc_model_opt(SEC_EQ, MODEL_TITANIUM_EQ) && xc_get(x, P("cmp_model")) == (float)xc_model_opt(SEC_COMP, MODEL_TITANIUM_DRIVE)
       && xc_get(x, P("sh_model")) == (float)xc_model_opt(SEC_SHAPE, MODEL_TITANIUM) && xc_get(x, P("eq_unit")) == 1.f && xc_get(x, P("m_eqlook")) == 20.f;
    int b = ok;
    seto(x, "eq_unit", 0);
    ok &= xc_get(x, P("eq_model")) == (float)xc_model_opt(SEC_EQ, MODEL_TITANIUM) && xc_get(x, P("cmp_model")) == (float)xc_model_opt(SEC_COMP, MODEL_TITANIUM_DRIVE);
    seto(x, "strip_sel", xc_strip_opt(MODEL_HEXX));
    for (int i = 0; i < 4; i++) ok &= xc_get(x, P(k[i])) == (float)xc_model_opt(i + 1, MODEL_HEXX) && xc_get(x, P(u[i])) == 0.f;
    int c = ok;
    selm(x, "sh_model", MODEL_TITANIUM_EQ); ok &= xc_get(x, P("sh_unit")) == 1.f;   /* the old preset parameter, set directly */
    xc_set_restoring(x, 1); seto(x, "strip_sel", xc_strip_opt(MODEL_SUEDE)); seto(x, "eq_unit", 1); xc_set_restoring(x, 0);
    ok &= xc_get(x, P("eq_model")) == (float)xc_model_opt(SEC_EQ, MODEL_HEXX);   /* a project load sets them without picking */
    xc_sync_selectors(x, 1); ok &= xc_get(x, P("eq_unit")) == 0.f && xc_get(x, P("strip_sel")) == (float)xc_strip_opt(MODEL_SUEDE);
    xc_sync_selectors(x, 0); ok &= xc_get(x, P("strip_sel")) == (float)xc_strip_opt(MODEL_HEXX);
    CHECK(ok, "CHANNEL STRIP (10 strips) sets all four sections (%d); a unit replaces one section (%d), STRIP goes back to the strip, a new strip clears the units (%d); loads only record", a, b, c);
    xc_destroy(x);
}

static void check_model_order(void)
{
    XConsole *x = fresh();
    int ok = xc_model_opt(SEC_INPUT, MODEL_MOCHA) == 0 && xc_model_opt(SEC_INPUT, MODEL_HEXX) == 1 && xc_model_opt(SEC_INPUT, MODEL_SPADES) == 2 && xc_model_opt(SEC_INPUT, MODEL_MOLTEN) == 3 && xc_model_opt(SEC_INPUT, MODEL_HEARTS) == 4 && xc_model_opt(SEC_INPUT, MODEL_SUEDE) == 5 && xc_model_opt(SEC_INPUT, MODEL_GRANITE) == 6 && xc_model_opt(SEC_INPUT, MODEL_FLANNEL) == 7;
    const char *k[4] = {"in_model", "sh_model", "eq_model", "cmp_model"};
    for (int i = 0; i < 4; i++) ok &= xc_get(x, P(k[i])) == (float)xc_model_opt(i + 1, MODEL_FLANNEL);
    char a[32];
    selm(x, "eq_model", MODEL_GRANITE); setn(x, "eq_lmf_q", 1.f); xc_display(x, P("eq_lmf_q"), a, 32);
    CHECK(ok && !strcmp(a, "3.50"), "presets in alphabetical order (MOCHA, HEXX, SPADES, MOLTEN, HEARTS, SUEDE, GRANITE (its Q top %s), FLANNEL); a new strip starts on the FLANNEL", a);
    xc_destroy(x);
}

static void check_look(void)
{
    XConsole *x = fresh();
    int ok = xc_get(x, P("m_eqlook")) == 0.f;
    seto(x, "sp_view", 1); ok &= xc_get(x, P("m_eqlook")) == 1.f;
    unsigned rev = xc_display_rev(x);
    selm(x, "eq_model", MODEL_GRANITE); ok &= xc_get(x, P("m_eqlook")) == 3.f && xc_display_rev(x) > rev;
    seto(x, "sp_view", 0); ok &= xc_get(x, P("m_eqlook")) == 2.f;
    xc_set(x, P("m_eqlook"), 0.f); ok &= xc_get(x, P("m_eqlook")) == 2.f;
    xc_set_restoring(x, 1); selm(x, "eq_model", MODEL_FLANNEL); xc_set_restoring(x, 0); ok &= xc_get(x, P("m_eqlook")) == 0.f;
    CHECK(ok, "the spectrum's look follows EQ preset x VIEW (green/brown x line/bars), also on a project load; the host can't set it");
    xc_destroy(x);
}

static void check_display(void)
{
    XConsole *x = fresh();
    char a[32], b[32], c[32], d[32], e[32];
    xc_display(x, P("cmp_att"), a, 32);
    xc_display(x, P("cmp_knee"), b, 32);
    setv(x, "gate_hold", 1200.f); xc_display(x, P("gate_hold"), c, 32);
    xc_display(x, P("drv_char"), d, 32);
    setv(x, "out_pan", -40.f); xc_display(x, P("out_pan"), e, 32);
    CHECK(!strcmp(a, "AUTO") && !strcmp(b, "AUTO") && !strcmp(c, "1.20 s") && !strcmp(d, "2nd 50 / 3rd 50") && !strcmp(e, "L 40"),
          "display: attack \"%s\", knee \"%s\", hold \"%s\", character \"%s\", pan \"%s\"", a, b, c, d, e);
    xc_destroy(x);
}

/* every switch flipped mid-tone: no step larger than the tone's own movement can explain */
static void check_clicks(void)
{
    static const struct { const char *k; int a, b; } SW[] = {
        {"phase", 0, 1}, {"pre_on", 0, 1}, {"pre_type", 0, 2}, {"flt_on", 1, 0}, {"lc_slope", 2, 3}, {"hc_slope", 1, 3}, {"flt_sc", 0, 1},
        {"sh_on", 0, 1}, {"gate_mode", 0, 1}, {"gate_fast", 0, 1}, {"eq_on", 0, 1}, {"eq_style", 0, 1}, {"eq_lf_type", 0, 2}, {"eq_hf_type", 0, 1},
        {"cmp_on", 0, 1}, {"cmp_det", 0, 1}, {"cmp_fast", 0, 1}, {"drv_on", 0, 1}, {"drv_pos", 0, 1}, {"order", 1, 4}, {"bypass", 0, 1}};
    int nsw = sizeof SW / sizeof SW[0];
    int worst_i = -1; float worst = 0;
    for (int s = 0; s < nsw; s++) {
        XConsole *x = fresh();
        /* settings that make each section audible */
        setv(x, "lc_freq", 60.f); setv(x, "hc_freq", 9000.f); seto(x, "eq_style", 1);
        setv(x, "eq_lf_gain", 8.f); setv(x, "eq_hmf_gain", -6.f); setv(x, "eq_hf_gain", 6.f);
        setv(x, "cmp_ratio", 4.f); setv(x, "cmp_thr", -30.f); setv(x, "drv_amt", 40.f); setv(x, "pre_color", 60.f);
        setv(x, "gate_range", 20.f); setv(x, "gate_thr", -40.f);
        if (strcmp(SW[s].k, "sh_on")) seto(x, "sh_on", 1);
        if (strcmp(SW[s].k, "eq_on")) seto(x, "eq_on", 1);
        if (strcmp(SW[s].k, "cmp_on")) seto(x, "cmp_on", 1);
        seto(x, SW[s].k, SW[s].a);
        int n = (int)(0.6f * SR);
        float *in = malloc(n * 4), *o1 = malloc(n * 4), *o2 = malloc(n * 4);
        for (int i = 0; i < n; i++) in[i] = 0.25f * sinf(2 * (float)M_PI * 220 * i / SR);
        int half = n / 2 / 128 * 128 + 37;
        run(x, in, in, o1, o2, half);
        seto(x, SW[s].k, SW[s].b);
        run(x, in + half, in + half, o1 + half, o2 + half, n - half);
        float m = 0;
        for (int i = half - 2000; i < n; i++) {
            float d2 = fabsf(o1[i] - 2 * o1[i - 1] + o1[i - 2]);
            if (d2 > m) m = d2;
        }
        float ref = 0;
        for (int i = 2000; i < half - 2000; i++) { float d2 = fabsf(o1[i] - 2 * o1[i - 1] + o1[i - 2]); if (d2 > ref) ref = d2; }
        float ratio = m / (ref + 1e-9f);
        if (ratio > worst) { worst = ratio; worst_i = s; }
        if (ratio > 4.f) printf("     click on %s: %.1fx the steady curvature\n", SW[s].k, ratio);
        free(in); free(o1); free(o2);
        xc_destroy(x);
    }
    CHECK(worst < 4.f, "%d switches flipped mid-tone, no click (worst %s at %.2fx the tone's own curvature)", nsw, worst_i >= 0 ? SW[worst_i].k : "-", worst);
    /* a knob swept hard: frequency of a boosted band across its range in 50 ms */
    {
        XConsole *x = fresh();
        seto(x, "eq_on", 1); setv(x, "eq_lmf_gain", 15.f);
        int n = (int)(1.0f * SR);
        float *in = malloc(n * 4), *o1 = malloc(n * 4), *o2 = malloc(n * 4);
        for (int i = 0; i < n; i++) in[i] = 0.1f * sinf(2 * (float)M_PI * 300 * i / SR);
        for (int i = 0; i < n; i += 128) {
            float t = (float)i / n;
            setn(x, "eq_lmf_freq", t < 0.5f ? 0.f : 1.f);
            xc_process(x, in + i, in + i, o1 + i, o2 + i, n - i < 128 ? n - i : 128);
        }
        int ok = 1;
        for (int i = 0; i < n; i++) if (!isfinite(o1[i]) || fabsf(o1[i]) > 1.5f) ok = 0;
        CHECK(ok, "LMF frequency slammed end to end with +15 dB: output finite and bounded");
        free(in); free(o1); free(o2);
        xc_destroy(x);
    }
}

/* 0.19.0: the noise generator on the PREAMP page (P-Valley PNG's): off by default; on, LEVEL is the noise's RMS; it
 * joins after INPUT (INPUT doesn't move it) and before the strip (the low cut takes brown noise down), so OUTPUT and
 * BYPASS act on it; every waveform runs finite and bounded; its text */
static void check_noise(void)
{
    int n = (int)SR;
    float *z = calloc(n, 4), *o1 = malloc(n * 4), *o2 = malloc(n * 4), *tone = malloc(n * 4);
    for (int i = 0; i < n; i++) tone[i] = 0.25f * sinf(2 * (float)M_PI * 440 * i / SR);
    XConsole *x = fresh();
    run(x, z, z, o1, o2, n);
    double off = rms_db(o1, 0, n);
    seto(x, "nz_on", 1);
    run(x, z, z, o1, o2, n);
    double pl = rms_db(o1, n / 2, n), pr = rms_db(o2, n / 2, n);
    CHECK(off < -200 && fabs(pl + 24) < 1.0 && fabs(pr + 24) < 1.0,
          "NOISE: off by default (%.0f dB); on, pink at Level -24 measures %.2f / %.2f dBFS", off, pl, pr);
    setv(x, "nz_level", -12.f); settle(x, 0.2f);
    run(x, z, z, o1, o2, n);
    double l12 = rms_db(o1, n / 2, n);
    setv(x, "in_gain", 6.f); settle(x, 0.2f);
    run(x, z, z, o1, o2, n);
    double in6 = rms_db(o1, n / 2, n);
    setv(x, "in_gain", 0.f); setv(x, "out_vol", -6.f); settle(x, 0.2f);
    run(x, z, z, o1, o2, n);
    double v6 = rms_db(o1, n / 2, n);
    seto(x, "bypass", 1); settle(x, 0.2f);
    run(x, z, z, o1, o2, n);
    double byp = rms_db(o1, n / 2, n);
    CHECK(fabs(l12 + 12) < 1.0 && fabs(in6 - l12) < 0.3 && fabs(v6 + 18) < 1.0 && byp < -150,
          "NOISE: Level -12 gives %.2f dBFS; INPUT +6 leaves it at %.2f (after INPUT); OUTPUT -6 dB: %.2f; BYPASS silences it (%.0f dB)", l12, in6, v6, byp);
    xc_destroy(x);
    x = fresh();
    seto(x, "nz_on", 1); seto(x, "nz_color", 2);   /* brown: most of it low */
    run(x, z, z, o1, o2, n);
    double br = rms_db(o1, n / 2, n);
    seto(x, "flt_on", 1); setv(x, "lc_freq", 400.f); settle(x, 0.3f);
    run(x, z, z, o1, o2, n);
    double brc = rms_db(o1, n / 2, n);
    CHECK(br - brc > 6, "NOISE: through the strip: brown %.2f dBFS, %.2f with LOW CUT 400 Hz", br, brc);
    xc_destroy(x);
    int ok = 1;
    for (int c = 0; c < 7; c++) {
        x = fresh();
        seto(x, "nz_on", 1); seto(x, "nz_color", c);
        run(x, tone, tone, o1, o2, n / 2);
        if (c == 3) seto(x, "nz_color", 6);   /* a change while running crossfades */
        run(x, tone + n / 2, tone + n / 2, o1 + n / 2, o2 + n / 2, n - n / 2);
        float pk = 0;
        for (int i = 0; i < n; i++) { if (!isfinite(o1[i]) || !isfinite(o2[i])) ok = 0; pk = fmaxf(pk, fmaxf(fabsf(o1[i]), fabsf(o2[i]))); }
        double r = rms_db(o1, n / 2, n) - rms_db(tone, n / 2, n);
        if (pk > 1.f || fabs(r) > 3.0) { ok = 0; printf("     colour %d: peak %.2f, level change %.2f dB\n", c, pk, r); }
        xc_destroy(x);
    }
    CHECK(ok, "NOISE: all 7 waveforms over a tone (a change mid-run): finite, peaks under 0 dBFS, tone on top");
    x = fresh();
    char a[32];
    xc_display(x, P("nz_level"), a, 32);
    CHECK(!strcmp(a, "-24.0 dB"), "NOISE: LEVEL text \"%s\"", a);
    xc_destroy(x);
    free(z); free(o1); free(o2); free(tone);
}

static void check_tail(void)
{
    XConsole *x = fresh();
    seto(x, "pre_on", 1); seto(x, "sh_on", 1); seto(x, "eq_on", 1); seto(x, "cmp_on", 1); seto(x, "drv_on", 1);
    setv(x, "lc_freq", 40.f); setv(x, "eq_lf_gain", 10.f); setv(x, "cmp_ratio", 4.f); setv(x, "gate_range", 30.f); setv(x, "sh_sustain", 50.f);
    int n = (int)(SR * 6);
    float *in = calloc(n, 4), *o1 = malloc(n * 4), *o2 = malloc(n * 4);
    for (int i = 0; i < (int)SR; i++) in[i] = 0.9f * noise();
    run(x, in, in, o1, o2, n);
    int ok = 1;
    for (int i = 0; i < n; i++) if (!isfinite(o1[i]) || !isfinite(o2[i])) ok = 0;
    CHECK(ok && fabsf(o1[n - 1]) < 1e-6f, "loud noise then 5 s of silence through everything: finite, decays to %.2g", o1[n - 1]);
    free(in); free(o1); free(o2);
    xc_destroy(x);
}

/* ---------------------------------------------------------------- demos */
typedef void (*Setup)(XConsole *);
static void d_dry(XConsole *x) { (void)x; }
static void d_comp(XConsole *x) { seto(x, "cmp_on", 1); setv(x, "cmp_ratio", 4.f); setv(x, "cmp_thr", -34.f); setv(x, "cmp_rel", 200.f); }
static void d_comp_fast_pk(XConsole *x) { d_comp(x); seto(x, "cmp_fast", 1); seto(x, "cmp_det", 1); setn(x, "cmp_ratio", 1.f); setv(x, "cmp_thr", -30.f); }
static void d_gate(XConsole *x) { seto(x, "sh_on", 1); setv(x, "gate_thr", -36.f); setv(x, "gate_range", 40.f); setv(x, "gate_rel", 150.f); setv(x, "gate_hold", 30.f); }
static void d_punch(XConsole *x) { seto(x, "sh_on", 1); setv(x, "sh_punch", 80.f); setv(x, "sh_sustain", -40.f); }
static void d_sustain(XConsole *x) { seto(x, "sh_on", 1); setv(x, "sh_sustain", 80.f); }
static void d_eq_g(XConsole *x) { seto(x, "eq_on", 1); setv(x, "eq_lf_gain", 6.f); setv(x, "eq_lf_freq", 80.f); setv(x, "eq_lmf_gain", -5.f); setv(x, "eq_lmf_freq", 350.f); setv(x, "eq_hmf_gain", 4.f); setv(x, "eq_hmf_freq", 3000.f); setv(x, "eq_hf_gain", 5.f); setv(x, "eq_hf_freq", 10000.f); }
static void d_eq_e(XConsole *x) { d_eq_g(x); seto(x, "eq_style", 1); }
static void d_filters(XConsole *x) { setv(x, "lc_freq", 150.f); setv(x, "hc_freq", 4000.f); }
static void d_drive2(XConsole *x) { seto(x, "drv_on", 1); setv(x, "drv_amt", 70.f); setv(x, "drv_char", 0.f); }
static void d_drive3(XConsole *x) { seto(x, "drv_on", 1); setv(x, "drv_amt", 70.f); setv(x, "drv_char", 100.f); }
static void d_tape(XConsole *x) { seto(x, "pre_on", 1); seto(x, "pre_type", 0); setv(x, "pre_color", 80.f); setv(x, "in_gain", 6.f); }
static void d_tube(XConsole *x) { seto(x, "pre_on", 1); seto(x, "pre_type", 1); setv(x, "pre_color", 80.f); setv(x, "in_gain", 6.f); }
static void d_iron(XConsole *x) { seto(x, "pre_on", 1); seto(x, "pre_type", 2); setv(x, "pre_color", 100.f); setv(x, "in_gain", 6.f); }
static void d_strip(XConsole *x) { setv(x, "lc_freq", 30.f); d_gate(x); setv(x, "sh_punch", 40.f); d_eq_g(x); d_comp(x); seto(x, "drv_on", 1); setv(x, "drv_amt", 35.f); setv(x, "drv_char", 30.f); }

static void demos(const char *dir)
{
    float *l, *r;
    int n = make_loop(&l, &r);
    static const struct { const char *name; Setup f; } D[] = {
        {"01-dry", d_dry}, {"02-comp-flannel-4to1", d_comp}, {"03-comp-limit-fast-peak", d_comp_fast_pk}, {"04-gate", d_gate},
        {"05-punch", d_punch}, {"06-sustain", d_sustain}, {"07-eq-g-style", d_eq_g}, {"08-eq-e-style", d_eq_e}, {"09-filters", d_filters},
        {"10-drive-2nd", d_drive2}, {"11-drive-3rd", d_drive3}, {"12-preamp-tape", d_tape}, {"13-preamp-tube", d_tube}, {"14-preamp-iron", d_iron},
        {"15-whole-strip", d_strip}};
    float *ol = malloc(n * 4), *orr = malloc(n * 4);
    for (unsigned d = 0; d < sizeof D / sizeof D[0]; d++) {
        XConsole *x = fresh();
        D[d].f(x);
        settle(x, 0.1f);
        run(x, l, r, ol, orr, n);
        char path[512];
        snprintf(path, sizeof path, "%s/%s.wav", dir, D[d].name);
        float pk = 0;
        for (int i = 0; i < n; i++) pk = fmaxf(pk, fmaxf(fabsf(ol[i]), fabsf(orr[i])));
        if (pk > 0.891f) {                                               /* the plugin runs in float; only the 16-bit file would clip */
            float k = 0.891f / pk;
            for (int i = 0; i < n; i++) { ol[i] *= k; orr[i] *= k; }
            printf("  %s turned down %.1f dB for the file (peak %+.1f dBFS)\n", D[d].name, -20 * log10f(k), 20 * log10f(pk));
        }
        wav(path, ol, orr, n);
        xc_destroy(x);
    }
    printf("demos: %u WAVs in %s (%.1f s each)\n", (unsigned)(sizeof D / sizeof D[0]), dir, n / SR);
    free(l); free(r); free(ol); free(orr);
}

int main(int argc, char **argv)
{
    check_null(44100.f); check_null(48000.f); check_null(96000.f);
    check_input();
    check_filters();
    check_eq();
    check_comp();
    check_gate();
    check_transient();
    check_saturation();
    check_output();
    check_presets();
    check_display();
    check_granite();
    check_hearts();
    check_suede();
    check_sandstone();
    check_hexx();
    check_molten();
    check_spades();
    check_mocha();
    check_empirical();
    check_curves();
    check_model_order();
    check_section_lists();
    check_strip_selector();
    check_look();
    check_clicks();
    check_noise();
    check_tail();
    printf("%d passed, %d failed\n", g_pass, g_fail);
    if (argc > 1) demos(argv[1]);
    return g_fail;
}
