/* X-Console channel strip DSP. See xconsole.h. All-new code (2026-11-02); figures for the FLANNEL preset come from
 * SSL's Super 9000 User Guide and the bx_console 9000 J manual (~/mpc-dev/refdocs). "choice:" marks what those
 * documents don't settle. The HEARTS preset (model 2, HEARTS in 0.7.0) follows Weiss's EQ1-MK2 and DS1-MK3 manuals
 * (~/mpc-dev/refdocs/hearts/); its DRIVE is the DS1's safety limiter. SUEDE (model 3, 0.9.0) is a 1073-style strip with a
 * 2254-style compressor, its switches stepped (T_STEPS): figures from AMS Neve's 2254/R and 1073 published specs and
 * Softube's British Class A manual (its added attack/release steps, the gate's DEPTH, OFF positions on the EQ bands).
 * HEXX (model 5, 0.11.0): an HEXX console strip after Softube's American Class A: the 550B's switched frequencies and
 * proportional Q, a 2500/527-style compressor with manual output gain.
 * MOCHA (model 8, 0.14.0): UA's LA-6176: a 610-B tube preamp with low/high shelves into a 1176LN (stepped ratios,
 * all-buttons as Limit, 20-800 us attack, 50 ms-1.1 s release, manual OUTPUT).
 * SPADES (model 7, 0.13.0): the Avalon VT-737sp: Class A tube preamp, 6 dB/oct HPF, switched bass and treble shelves,
 * swept mids with LO/HI Q, an opto compressor (program-dependent release), after UA's Avalon VT-737 and Avalon's specs.
 * MOLTEN (model 6, 0.12.0): Chandler Limited's Curve Bender EQ (switched frequencies, bands that narrow as the gain
 * goes up, 6 dB/oct filters) and Zener Limiter (COMP 1 / COMP 2 / LIMIT, switched attack and release, stepped output),
 * after Softube's Zener-Bender for Console 1 and Softube's Curve Bender and Zener Limiter manuals.
 * TITANIUM (model 9), TITANIUM EQ (10), TITANIUM DRIVE (11), 0.16.0: Empirical Labs, after Softube's Trak Pak for Console 1 and the
 * Lil FrEQ / Mike-E manuals: the Lil FrEQ's filters (with a bump), DS section (de-esser / HF limiter, in SHAPE) and EQ (fixed
 * shelves), the Mike-E's compressor (2:1 .. NUKE) and Warm/Toasty saturation (a germanium stage after the drive curve).
 * SANDSTONE (model 4, 0.10.0): Summit Audio's EQF-100 (switched frequencies, bandwidth 0-10) and TLA-100A (FAST / MEDIUM /
 * SLOW attack and program-dependent release, soft knee, manual gain), after Softube's Summit Audio Grand Channel.
 *
 * Signal flow:  input trim + polarity -> [preamp extra, 2x] -> filters (or into the dynamics side chains with TO S/C)
 *               -> [drive PRE] -> shape / EQ / comp in the ORDER chosen -> [drive POST] -> width, pan, volume -> bypass.
 *               The noise generator (P-Valley PNG's, src/noise.c; on the PREAMP page since 0.19.0) joins after the
 *               input trim, before the preamp: a gain-staging signal through the whole strip.
 * Controls glide (20 ms) and are turned into coefficients every CTRL samples. Switches that change the structure
 * (polarity, slopes, order, positions, types) dip the output for 5 + 10 + 5 ms while they change; section ON
 * buttons and filter Off positions crossfade over 10 ms; bypass crossfades over 10 ms. */
#include "xconsole.h"
#include "noise.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CTRL 16
#define PI_F 3.14159265358979f
#define DB2LIN(d) expf((d) * 0.11512925465f)
#define LIN2DB(l) (8.68588963807f * logf(l))
#define HB_NC 10                 /* oversampling halfband: allpass coefficients (5 per path) */
#define HB_TBW 0.04              /* its transition band, as a fraction of the 2x rate */

typedef struct { const char *key; float def, lo, hi; int taper, sec, nopt, kind; const float *st; int nst; } PInfo;   /* kind 0 continuous, 1 option, 2 meter; st: T_STEPS values */
static const PInfo PT[P_COUNT] = {
#define N(k, d, lo, hi, t, s) {#k, d, lo, hi, t, s, 0, 0, 0, 0},
#define O(k, d, n, s) {#k, (float)(d), 0, 0, 0, s, n, 1, 0, 0},
#define M(k) {#k, 0, 0, 0, 0, 0, 0, 2, 0, 0},
#define MR(m, k, d, lo, hi, t)
#define MO(m, k, d)
#define MS(m, k, d, n, ...)
#include "param_table.h"
#undef N
#undef O
#undef M
#undef MR
#undef MO
#undef MS
};
enum { T_LIN, T_LOG, T_OFFLOG, T_TOPOFF, T_LIMLOG, T_AUTOLOG, T_AUTOLIN, T_SPLIT, T_STEPS };   /* SPLIT: lo..0 left half, 0..hi right; STEPS: a switch's positions */
/* T_STEPS (SUEDE, 0.9.0): the knob's travel in equal zones, one per position; a position may be Off, AUTO or Limit */
#define ST_OFF -1e6f
#define ST_AUTO -2e6f
#define ST_LIMIT 1e6f
static int st_real(float v) { return fabsf(v) < 5e5f; }
static void st_range(PInfo *p)                                     /* lo / hi: the lowest and highest real positions */
{
    int first = 1;
    for (int i = 0; i < p->nst; i++)
        if (st_real(p->st[i])) { if (first || p->st[i] < p->lo) p->lo = p->st[i]; if (first || p->st[i] > p->hi) p->hi = p->st[i]; first = 0; }
}
/* Each model's table: the FLANNEL's (PT), with a later model's ranges and defaults laid over it (MR / MO / MS in param_table.h) */
static PInfo PTM[MODEL_COUNT][P_COUNT];
static void ptm_init(void)
{
    static int done;
    if (done) return;
    for (int m = 0; m < MODEL_COUNT; m++) memcpy(PTM[m], PT, sizeof PT);
#define N(k, d, lo, hi, t, s)
#define O(k, d, n, s)
#define M(k)
#define MR(m, k, d, l, h, t) { PTM[m][P_##k].def = d; PTM[m][P_##k].lo = l; PTM[m][P_##k].hi = h; PTM[m][P_##k].taper = t; }
#define MO(m, k, d) PTM[m][P_##k].def = (float)(d);
#define MS(m, k, d, n, ...) { static const float v_[n] = {__VA_ARGS__}; PInfo *p_ = &PTM[m][P_##k]; p_->def = d; p_->taper = T_STEPS; p_->st = v_; p_->nst = n; st_range(p_); }
#include "param_table.h"
#undef N
#undef O
#undef M
#undef MR
#undef MO
#undef MS
    done = 1;
}
enum { SP_NONE, SP_OFF, SP_AUTO, SP_LIMIT };
#define EDGE 0.004f              /* the knob's last 1/250 at an Off / Auto / Limit end */

static const int MODEL_KEYS[SEC_COUNT] = {-1, P_in_model, P_sh_model, P_eq_model, P_cmp_model};
/* A preset parameter's value is the model's place in its own SETUP drop-down, which lists that section's presets
 * alphabetically (0.15.0: each section its own list; a channel strip is in all four, a single unit only in its section's).
 * The model numbers (MODEL_FLANNEL, ...) and their tables keep the order the models were added in. */
static const int MBO_IN[] = {MODEL_BY_OPT_IN}, MBO_SH[] = {MODEL_BY_OPT_SH}, MBO_EQ[] = {MODEL_BY_OPT_EQ}, MBO_CMP[] = {MODEL_BY_OPT_CMP};
#define NOF(a) ((int)(sizeof(a) / sizeof((a)[0])))
static const int *const MODEL_BY_OPT[SEC_COUNT] = {MBO_IN, MBO_IN, MBO_SH, MBO_EQ, MBO_CMP};
static const int MODEL_NOPT[SEC_COUNT] = {NOF(MBO_IN), NOF(MBO_IN), NOF(MBO_SH), NOF(MBO_EQ), NOF(MBO_CMP)};
static int sec_ok(int sec) { return sec > SEC_NONE && sec < SEC_COUNT ? sec : SEC_INPUT; }
static int model_at(int sec, int opt)
{
    sec = sec_ok(sec);
    int n = MODEL_NOPT[sec];
    return MODEL_BY_OPT[sec][opt < 0 ? 0 : opt >= n ? n - 1 : opt];
}
static int list_place(int sec, int model)   /* -1 when the model isn't in that section's list */
{
    sec = sec_ok(sec);
    for (int o = 0; o < MODEL_NOPT[sec]; o++) if (MODEL_BY_OPT[sec][o] == model) return o;
    return -1;
}
int xc_opt_model(int sec, int opt) { return model_at(sec, opt); }
int xc_model_in(int sec, int model) { return list_place(sec, model) >= 0; }
int xc_model_opt(int sec, int model)
{
    int o = list_place(sec, model);
    if (o < 0) o = list_place(sec, MODEL_FLANNEL);   /* not in this list: the FLANNEL (a channel strip, in every list) */
    return o < 0 ? 0 : o;
}
int xc_model_section(int i)
{
    for (int s = SEC_INPUT; s < SEC_COUNT; s++) if (MODEL_KEYS[s] == i) return s;
    return 0;
}
/* 0.17.0: the CHANNEL STRIP drop-down (strips only) and each section's (STRIP, then that section's single units). They pick
 * the model; the preset parameters above stay the model each section runs. */
static const int STRIPS[] = {STRIP_BY_OPT};
static const int UBO_IN[] = {UNIT_BY_OPT_IN}, UBO_SH[] = {UNIT_BY_OPT_SH}, UBO_EQ[] = {UNIT_BY_OPT_EQ}, UBO_CMP[] = {UNIT_BY_OPT_CMP};
static const int *const UNIT_BY_OPT[SEC_COUNT] = {UBO_IN, UBO_IN, UBO_SH, UBO_EQ, UBO_CMP};
static const int UNIT_NOPT[SEC_COUNT] = {NOF(UBO_IN), NOF(UBO_IN), NOF(UBO_SH), NOF(UBO_EQ), NOF(UBO_CMP)};
static const int UNIT_KEYS[SEC_COUNT] = {-1, P_in_unit, P_sh_unit, P_eq_unit, P_cmp_unit};
int xc_strip_model_at(int opt) { return STRIPS[opt < 0 ? 0 : opt >= NOF(STRIPS) ? NOF(STRIPS) - 1 : opt]; }
int xc_is_strip(int model)
{
    for (int o = 0; o < NOF(STRIPS); o++) if (STRIPS[o] == model) return 1;
    return 0;
}
int xc_strip_opt(int model)
{
    for (int o = 0; o < NOF(STRIPS); o++) if (STRIPS[o] == model) return o;
    return xc_strip_opt(MODEL_FLANNEL);   /* not a strip: the FLANNEL (always one) */
}
static int unit_place(int sec, int model)   /* the section drop-down's place for a model: its unit's, else 0 (STRIP) */
{
    sec = sec_ok(sec);
    for (int o = 1; o < UNIT_NOPT[sec]; o++) if (UNIT_BY_OPT[sec][o] == model) return o;
    return 0;
}

/* Parameters whose change re-plumbs the strip: applied at the bottom of an output dip. */
static const int STRUCT_KEYS[] = {P_phase, P_pre_type, P_lc_slope, P_hc_slope, P_flt_sc, P_gate_mode, P_eq_style,
                                  P_eq_lf_type, P_eq_hf_type, P_cmp_det, P_drv_pos, P_order};
#define N_STRUCT ((int)(sizeof(STRUCT_KEYS) / sizeof(STRUCT_KEYS[0])))

/* ---------------------------------------------------------------- building blocks */
typedef struct { float s; } OnePole;                               /* TPT one-pole; G = g / (1 + g) */
static inline float op_lp(OnePole *o, float x, float G) { float v = (x - o->s) * G, y = v + o->s; o->s = y + v; return y; }

typedef struct { float ic1, ic2; } Svf;                            /* Simper's trapezoidal SVF */
typedef struct { float g, k, a1, a2, a3, m0, m1, m2; } SvfC;
static void svf_set(SvfC *c, float g, float k, float m0, float m1, float m2)
{
    c->g = g; c->k = k;
    c->a1 = 1.f / (1.f + g * (g + k)); c->a2 = g * c->a1; c->a3 = g * c->a2;
    c->m0 = m0; c->m1 = m1; c->m2 = m2;
}
static inline float svf_tick(Svf *s, const SvfC *c, float v0)
{
    float v3 = v0 - s->ic2;
    float v1 = c->a1 * s->ic1 + c->a2 * v3;
    float v2 = s->ic2 + c->a2 * s->ic1 + c->a3 * v3;
    s->ic1 = 2.f * v1 - s->ic1; s->ic2 = 2.f * v2 - s->ic2;
    return c->m0 * v0 + c->m1 * v1 + c->m2 * v2;
}
/* |H| in dB of an SVF at hz: it is the bilinear image of m0 + m1 s/(s^2+ks+1) + m2/(s^2+ks+1), s = j tan(pi f/fs) / g */
static float svf_db(const SvfC *c, float hz, float sr)
{
    double w = tan(M_PI * fmin(hz, 0.4999 * sr) / sr) / c->g;
    double dr = 1 - w * w, di = c->k * w;                 /* s^2 + ks + 1 at s = jw */
    double d2 = dr * dr + di * di;
    double v1r = (w * di) / d2, v1i = (w * dr) / d2;      /* jw / D */
    double v2r = dr / d2, v2i = -di / d2;                 /* 1 / D */
    double hr = c->m0 + c->m1 * v1r + c->m2 * v2r, hi = c->m1 * v1i + c->m2 * v2i;
    return (float)(10 * log10(hr * hr + hi * hi + 1e-30));
}

static float tanh_f(float x);
static float tanh_slope(float v)                                    /* d/dv of tanh_f: the small-signal gain at a bias */
{
    if (fabsf(v) >= 3.f) return 0.f;
    float v2 = v * v, d = 27.f + 9.f * v2;
    return ((27.f + 3.f * v2) * d - v * (27.f + v2) * 18.f * v) / (d * d);
}
static inline float tanh_f(float x)                                /* rational tanh, exact limit at +-3 */
{
    if (x > 3.f) return 1.f;
    if (x < -3.f) return -1.f;
    float x2 = x * x;
    return x * (27.f + x2) / (27.f + 9.f * x2);
}

/* 2x polyphase IIR halfband (two allpass paths), coefficients from the elliptic design used by L. de Soras' hiir. */
typedef struct { double g, ge, c, nE, nO; } DrvK;   /* drive curve settings and its auto-gain */
typedef struct { float x[HB_NC], y[HB_NC]; } Hb;   /* one 2x stage; drive cascades two for 4x */
static void hb_design(float *coef, int n, double tbw)
{
    double k = tan((1 - tbw * 2) * M_PI / 4); k *= k;
    double kk = pow(1 - k * k, 0.25), e = 0.5 * (1 - kk) / (1 + kk), e2 = e * e, e4 = e2 * e2;
    double q = e * (1 + e4 * (2 + e4 * (15 + 150 * e4)));
    int order = n * 2 + 1;
    for (int idx = 0; idx < n; idx++) {
        int c = idx + 1;
        double num = 0, den = 0, t;
        int i = 0, j = 1;
        do { t = pow(q, i * (i + 1)) * sin((i * 2 + 1) * c * M_PI / order) * j; num += t; j = -j; i++; } while (fabs(t) > 1e-100);
        i = 1; j = -1;
        do { t = pow(q, i * i) * cos(i * 2 * c * M_PI / order) * j; den += t; j = -j; i++; } while (fabs(t) > 1e-100);
        num *= pow(q, 0.25); den += 0.5;
        double ww = num / den, wwsq = ww * ww;
        double x = sqrt((1 - wwsq * k) * (1 - wwsq / k)) / (1 + wwsq);
        coef[idx] = (float)((1 - x) / (1 + x));
    }
}
static inline void hb_pair(Hb *h, const float *c, float *s0, float *s1)
{
    for (int i = 0; i < HB_NC; i += 2) {
        float t0 = h->x[i], t1 = h->x[i + 1];
        h->x[i] = *s0; h->x[i + 1] = *s1;
        *s0 = (*s0 - h->y[i]) * c[i] + t0;
        *s1 = (*s1 - h->y[i + 1]) * c[i + 1] + t1;
        h->y[i] = *s0; h->y[i + 1] = *s1;
    }
}
static inline void hb_up(Hb *h, const float *c, float in, float *o0, float *o1) { float a = in, b = in; hb_pair(h, c, &a, &b); *o0 = a; *o1 = b; }
static inline float hb_down(Hb *h, const float *c, float i0, float i1) { float a = i1, b = i0; hb_pair(h, c, &a, &b); return 0.5f * (a + b); }

/* Butterworth high or low cut, 6..24 dB/oct: a one-pole for odd orders, then SVF sections. */
typedef struct { OnePole op; Svf sv[2]; } FiltSt;
typedef struct { float G; SvfC c[2]; int order, nsv; } FiltC;
static const float BW_Q[5][2] = {{0, 0}, {0, 0}, {0.70710678f, 0}, {1.0f, 0}, {0.54119610f, 1.30656296f}};
static void filt_set(FiltC *f, float g, int order, int hp, float qm)   /* qm: the sections' Q x (TITANIUM's bump) */
{
    f->order = order; f->G = g / (1.f + g);
    f->nsv = order / 2;
    for (int i = 0; i < f->nsv; i++) {
        float k = 1.f / (BW_Q[order][i] * qm);
        if (hp) svf_set(&f->c[i], g, k, 1.f, -k, -1.f);
        else svf_set(&f->c[i], g, k, 0.f, 0.f, 1.f);
    }
}
static inline float filt_tick(FiltSt *s, const FiltC *f, float x, int hp)
{
    if (f->order & 1) { float lp = op_lp(&s->op, x, f->G); x = hp ? x - lp : lp; }
    for (int i = 0; i < f->nsv; i++) x = svf_tick(&s->sv[i], &f->c[i], x);
    return x;
}
static float filt_db(const FiltC *f, float hz, float sr, int hp)
{
    float db = 0;
    if (f->order & 1) {
        double w = tan(M_PI * fmin(hz, 0.4999 * sr) / sr) / (f->G / (1 - f->G));
        db += (float)(hp ? 10 * log10(w * w / (1 + w * w)) : 10 * log10(1 / (1 + w * w)));
    }
    for (int i = 0; i < f->nsv; i++) db += svf_db(&f->c[i], hz, sr);
    return db;
}

typedef struct { FiltSt lc, hc; } FiltPair;

/* ---------------------------------------------------------------- the strip */
struct XConsole {
    float sr, ctrl_a;
    float val[P_COUNT], sm[P_COUNT];
    int act[P_COUNT];                    /* applied values of the structural switches */
    int restoring, pending;
    unsigned rev;
    int ctrl_left;
    float hbc[HB_NC];

    /* glides and fades, per sample */
    float fade_step;
    float w_pre, w_lc, w_hc, w_sh, w_eq, w_cmp, w_drv, w_byp;
    float dip; int dip_state, dip_hold;
    float g_in, g_in_t, g_out, g_out_t, pan_l, pan_l_t, pan_r, pan_r_t, width, width_t;
    float pol;

    /* input and filters */
    Hb pre_up[2], pre_dn[2];
    OnePole pre_lo[2], pre_hf[2], pre_dc[2];
    Svf pre_bump[2]; SvfC pre_bump_c;
    float pre_g, pre_bias, pre_norm, pre_hf_G, pre_lo_G, pre_dc_G, pre_glo;
    FiltC lc_c, hc_c;
    FiltPair f_audio[2], f_sc_sh[2], f_sc_cmp[2];

    /* shape */
    float e_fa, e_sa, e_fr, e_sr, sh_db, a_sm_dn;
    float a_fast, r_fast, a_slow, r_slow, r_long, r_mid, a_sm;
    float punch, sustain;
    float gate_pk, gate_hold_n, gate_gr; int gate_open; int gate_hold_left;
    float gate_thr, gate_hyst, gate_range, gate_att, gate_rel, gate_ratio, gate_pk_rel; int gate_hold_samples;

    /* TITANIUM EQ's DS section (SHAPE under TITANIUM / TITANIUM EQ): reduction in gate_gr */
    int ds_on, ds_lim; float ds_thr, ds_rel_thr, ds_a, ds_r, ds_hf, ds_full; Svf ds_lp[2]; SvfC ds_c;

    /* EQ */
    Svf eq[4][2]; SvfC eqc[4];

    /* compressor */
    Svf cmp_hp[2]; SvfC cmp_hp_c; float cmp_hp_w, cmp_hp_on;
    float cmp_ms, cmp_gr;
    float cmp_fast_tau;
    float cmp_thr, cmp_slope, cmp_knee, cmp_rel_a, cmp_att_tau, cmp_makeup, cmp_mix, cmp_ms_a; int cmp_auto_att;
    int cmp_hearts; float cmp_rel_fast_a;   /* HEARTS: program-dependent release (fast after short peaks) */
    int cmp_nauto; float cmp_gr_f, cmp_gr_s, cmp_sa_a;   /* SUEDE AUTO recovery: a fast and a slow reduction, the larger wins */

    /* drive */
    Hb drv_up[2], drv_dn[2], drv_up2[2], drv_dn2[2]; OnePole drv_dc[2];
    double drv_x1[2], drv_F1[2], drv_key[2][3];   /* the last input, its F, and the curve settings that F was for */
    DrvK drv_k;
    float drv_g, drv_ge, drv_char, drv_dc_G;
    /* HEARTS: DRIVE is the DS1 safety limiter */
    int drv_mke; float drv_th;   /* TITANIUM DRIVE: the germanium stage's ceiling */
    int drv_hearts, lim_type; float lim_pre, lim_ceil, lim_g, lim_avg, lim_avg_a, lim_rel_a[3], lim_d[2], lim_d2[2];

    /* meters */
    float lev[4], lev_pk[4], gr_show, gate_show, fall;

    noise_t *nz;   /* the NOISE page (0.18.0) */
};

static float clampf(float x, float a, float b) { return x < a ? a : x > b ? b : x; }

static int OPT(const XConsole *x, int i);
static int model_sel(const XConsole *x, int key) { return model_at(xc_model_section(key), OPT(x, key)); }   /* a preset parameter's model */
/* the model a control's range follows: its section's preset (INPUT gain follows the PREAMP preset, though a preset pick
 * doesn't reset it) */
static int model_of(const XConsole *x, int i)
{
    int sec = PT[i].sec ? PT[i].sec : (i == P_in_gain ? SEC_INPUT : 0);
    if (!sec) return 0;
    return model_sel(x, MODEL_KEYS[sec]);
}
static const PInfo *pinfo(const XConsole *x, int i) { return &PTM[model_of(x, i)][i]; }
static int st_idx(const PInfo *p, float n) { int i = (int)(n * p->nst); return i < 0 ? 0 : i >= p->nst ? p->nst - 1 : i; }
static float st_val(const PInfo *p, float n)                       /* a position's value; Off / AUTO / Limit: the nearest real one */
{
    int i = st_idx(p, n);
    for (int d = 0; d < p->nst; d++) {
        if (i + d < p->nst && st_real(p->st[i + d])) return p->st[i + d];
        if (i - d >= 0 && st_real(p->st[i - d])) return p->st[i - d];
    }
    return 0.f;
}

/* the physical value of continuous parameter i at 0..1 position n, in x's preset for it */
static float map_n(const XConsole *x, int i, float n)
{
    const PInfo *p = pinfo(x, i);
    n = clampf(n, 0.f, 1.f);
    if (p->taper == T_STEPS) return st_val(p, n);
    if (p->taper == T_LIN || p->taper == T_AUTOLIN) return p->lo + n * (p->hi - p->lo);
    if (p->taper == T_SPLIT) return n < 0.5f ? p->lo * (1.f - 2.f * n) : p->hi * (2.f * n - 1.f);
    return p->lo * powf(p->hi / p->lo, n);
}
static float norm_in(const PInfo *p, float v)
{
    float n;
    if (p->taper == T_STEPS) {                                          /* the middle of the nearest real position's zone */
        int best = -1;
        for (int i = 0; i < p->nst; i++)
            if (st_real(p->st[i]) && (best < 0 || fabsf(p->st[i] - v) < fabsf(p->st[best] - v))) best = i;
        return best < 0 ? 0.f : (best + 0.5f) / p->nst;
    }
    if (p->taper == T_SPLIT) n = v < 0.f ? 0.5f * (1.f - v / p->lo) : 0.5f + 0.5f * v / p->hi;
    else if (p->taper == T_LIN || p->taper == T_AUTOLIN) n = (v - p->lo) / (p->hi - p->lo);
    else n = logf(v / p->lo) / logf(p->hi / p->lo);
    return clampf(n, 0.f, 1.f);
}
float xc_norm_for(const XConsole *x, int i, float v)
{
    if (i < 0 || i >= P_COUNT || PT[i].kind != 0) return 0.f;
    return norm_in(pinfo(x, i), v);
}
float xc_norm_of(int i, float v)
{
    if (i < 0 || i >= P_COUNT || PT[i].kind != 0) return 0.f;
    const PInfo *p = &PT[i];
    float n;
    if (p->taper == T_SPLIT) n = v < 0.f ? 0.5f * (1.f - v / p->lo) : 0.5f + 0.5f * v / p->hi;
    else if (p->taper == T_LIN || p->taper == T_AUTOLIN) n = (v - p->lo) / (p->hi - p->lo);
    else n = logf(v / p->lo) / logf(p->hi / p->lo);
    return clampf(n, 0.f, 1.f);
}

static int special(const XConsole *x, int i, float n)
{
    const PInfo *p = pinfo(x, i);
    switch (p->taper) {
    case T_STEPS: { float v = p->st[st_idx(p, n)]; return v == ST_OFF ? SP_OFF : v == ST_AUTO ? SP_AUTO : v == ST_LIMIT ? SP_LIMIT : SP_NONE; }
    case T_OFFLOG: return n < EDGE ? SP_OFF : SP_NONE;
    case T_TOPOFF: return n > 1.f - EDGE ? SP_OFF : SP_NONE;
    case T_LIMLOG: return n > 1.f - EDGE ? SP_LIMIT : SP_NONE;
    case T_AUTOLOG: case T_AUTOLIN: return n < EDGE ? SP_AUTO : SP_NONE;
    }
    if (i == P_out_vol && n < EDGE) return SP_OFF;
    return SP_NONE;
}
static float V(const XConsole *x, int i) { return map_n(x, i, x->sm[i]); }     /* glided physical value */
static int OPT(const XConsole *x, int i) { return (int)(x->val[i] + 0.5f); }

/* the defaults a model gives its section's controls */
static float model_default(int model, int i) { return PTM[model][i].def; }

int xc_param_index(const char *key)
{
    for (int i = 0; i < P_COUNT; i++) if (!strcmp(PT[i].key, key)) return i;
    return -1;
}
const char *xc_param_key(int i) { return (i >= 0 && i < P_COUNT) ? PT[i].key : ""; }
int xc_param_is_option(int i) { return i >= 0 && i < P_COUNT && PT[i].kind == 1; }
int xc_param_is_meter(int i) { return i >= 0 && i < P_COUNT && PT[i].kind == 2; }
int xc_param_options(int i) { return (i >= 0 && i < P_COUNT) ? PT[i].nopt : 0; }
unsigned xc_display_rev(const XConsole *x) { return x->rev; }
void xc_set_restoring(XConsole *x, int on) { x->restoring = on; }

static int is_struct(int i)
{
    for (int k = 0; k < N_STRUCT; k++) if (STRUCT_KEYS[k] == i) return 1;
    return 0;
}

static void set_raw(XConsole *x, int i, float v)
{
    if (PT[i].kind == 2) return;                                  /* meters belong to the engine */
    if (PT[i].kind == 1) {
        int n = (int)(v + 0.5f);
        if (n < 0) n = 0;
        if (n >= PT[i].nopt) n = PT[i].nopt - 1;
        v = (float)n;
    } else v = clampf(v, 0.f, 1.f);
    x->val[i] = v;
    if (is_struct(i) && (int)v != x->act[i]) x->pending = 1;
}

/* m_eqlook: which of the spectrum's four looks the skin shows (EQ preset x 2 + VIEW). The engine keeps it, as a skin
 * line takes one condition only; bumping rev makes the wrapper report it, so MPC switches the pictures. */
static void update_look(XConsole *x)
{
    float look = (float)(model_sel(x, P_eq_model) * 2 + OPT(x, P_sp_view));
    if (x->val[P_m_eqlook] != look) { x->val[P_m_eqlook] = look; x->rev++; }
}

static void sync_units(XConsole *x)   /* each section's drop-down shows its model: its unit, or STRIP */
{
    for (int s = SEC_INPUT; s < SEC_COUNT; s++) {
        float u = (float)unit_place(s, model_sel(x, MODEL_KEYS[s]));
        if (x->val[UNIT_KEYS[s]] != u) { x->val[UNIT_KEYS[s]] = u; x->rev++; }
    }
}

void xc_apply_preset(XConsole *x, int sec, int model)
{
    if (sec <= SEC_NONE || sec >= SEC_COUNT) return;
    int o = list_place(sec, model);   /* an unknown model isn't in any list */
    if (o < 0) return;   /* not in this section's list (a single unit of another section): nothing changes */
    x->val[MODEL_KEYS[sec]] = (float)o;
    for (int i = 0; i < P_COUNT; i++)
        if (PT[i].sec == sec) set_raw(x, i, model_default(model, i));
    x->rev++;
    update_look(x);
    sync_units(x);
}

void xc_sync_selectors(XConsole *x, int strip_known)
{
    if (!strip_known) x->val[P_strip_sel] = (float)xc_strip_opt(model_sel(x, P_in_model));   /* an older save: PREAMP's strip */
    sync_units(x);
    x->rev++;
}

/* 0.18.0: the NOISE page's parameters -> noise.c's keys; noise.c takes the physical value as text */
static const struct { int p; const char *key; } NZ[] = {   /* 0.19.0: ON, WAVEFORM, LEVEL only; the rest noise.c's defaults */
    {P_nz_on, "on"}, {P_nz_color, "color"}, {P_nz_level, "level"}};
static void nz_push(XConsole *x, int i)
{
    if (!x->nz) return;
    for (int k = 0; k < NOF(NZ); k++)
        if (NZ[k].p == i) {
            char v[32];
            if (PT[i].kind == 1) snprintf(v, sizeof v, "%d", OPT(x, i));
            else snprintf(v, sizeof v, "%.4f", map_n(x, i, x->val[i]));   /* 4 places: 0 dB is exactly 0 */
            noise_set(x->nz, NZ[k].key, v);
            return;
        }
}

void xc_set(XConsole *x, int i, float v)
{
    if (i < 0 || i >= P_COUNT || i == P_m_eqlook) return;   /* m_eqlook is the engine's own */
    if (i == P_strip_sel) {                                  /* CHANNEL STRIP: all four sections to that strip */
        int o = (int)(v + 0.5f);
        if (!x->restoring && o != OPT(x, i) && o >= 0 && o < NOF(STRIPS)) {
            x->val[i] = (float)o;
            for (int s = SEC_INPUT; s < SEC_COUNT; s++) xc_apply_preset(x, s, STRIPS[o]);
            return;
        }
        set_raw(x, i, v);
        return;
    }
    for (int s = 1; s < SEC_COUNT; s++)
        if (UNIT_KEYS[s] == i) {                             /* a section: STRIP (the channel strip's) or one of its units */
            int o = (int)(v + 0.5f);
            if (!x->restoring && o != OPT(x, i) && o >= 0 && o < UNIT_NOPT[s]) {
                xc_apply_preset(x, s, o == 0 ? xc_strip_model_at(OPT(x, P_strip_sel)) : UNIT_BY_OPT[s][o]);
                return;
            }
            set_raw(x, i, v);
            return;
        }
    for (int s = 1; s < SEC_COUNT; s++)
        if (MODEL_KEYS[s] == i) {
            int m = (int)(v + 0.5f);
            if (!x->restoring && m != OPT(x, i)) { xc_apply_preset(x, s, model_at(s, m)); return; }
            break;
        }
    set_raw(x, i, v);
    if (i == P_eq_model || i == P_sp_view) update_look(x);
    nz_push(x, i);
}

float xc_get(const XConsole *x, int i) { return (i >= 0 && i < P_COUNT) ? x->val[i] : 0.f; }

/* Empirical Labs (0.16.0): the Lil FrEQ's sections under TITANIUM and TITANIUM EQ, the Mike-E's under TITANIUM and TITANIUM DRIVE */
static int is_lil(int m) { return m == MODEL_TITANIUM || m == MODEL_TITANIUM_EQ; }
static int is_mke(int m) { return m == MODEL_TITANIUM || m == MODEL_TITANIUM_DRIVE; }
#define LIL_LF_HZ 120.f   /* the Lil FrEQ's fixed shelves: "around 120Hz, and 4KHz", 6 dB/oct, +-10 dB (EL-Q manual) */
#define LIL_HF_HZ 4000.f
/* the Mike-E's knee by ratio: 2:1 has "a long 20dB knee", 4:1 and 8:1 "long knees" (EL-9 manual; choice 14 and 10 dB),
 * NUKE "very steep (limiter like)" (choice 3 dB); 1:1 none */
static float mke_knee(float r, int nuke) { return nuke ? 3.f : r < 1.05f ? 0.f : r < 3.f ? 20.f : r < 6.f ? 14.f : 10.f; }
static float flt_q(const XConsole *x) { return model_sel(x, P_in_model) == MODEL_TITANIUM ? 1.3f : 1.f; }   /* TITANIUM's cuts: "that nice bump" (choice: Q x 1.3) */
/* the DS section's HF limiter: level sensitive, soft knee. choices: 10:1, a 10 dB knee, at most 24 dB */
static float ds_lim_db(float over)
{
    const float W = 10.f, s = 0.9f;
    float gt = 2.f * over <= -W ? 0.f : 2.f * fabsf(over) < W ? s * (over + W * 0.5f) * (over + W * 0.5f) / (2.f * W) : s * over;
    return fminf(gt, 24.f);
}

/* the share of a gain knob's +-18 dB the GRANITE's 242 EQ gives at the current Q or type (1 for the FLANNEL) */
static float eq_gain_scale(const XConsole *x, int band, float q, int type)
{
    if (is_lil(model_sel(x, P_eq_model))) return ((band == 0 || band == 3) && type == 0) ? 10.f / 14.f : 1.f;   /* TITANIUM EQ: shelves +-10 of +-14 */
    if (model_sel(x, P_eq_model) != MODEL_GRANITE) return 1.f;
    if (band == 1 || band == 2) return (15.f + 3.f * logf(fmaxf(q, 0.1f) / 0.1f) / logf(35.f)) / 18.f;
    return type == 0 ? 16.5f / 18.f : 1.f;
}

/* MOLTEN (0.12.0). The Curve Bender's bands narrow as the gain goes up (its +-15 dB range "also decreases the width").
 * choice: Q 0.6 at small gains to 1.5 at 15 dB. */
static float cb_q(float gdb) { return 0.6f + 0.9f * fminf(fabsf(gdb) / 15.f, 1.f); }
/* The Zener Limiter's MODE (the RATIO knob: 1 COMP 1, 2 COMP 2, 3 LIMIT) and its switched times, ATTACK 1-11 and RELEASE
 * 1-21 spread log over each mode's range (a third-party manual's figures: attack COMP 1 28-570 ms, COMP 2 10-200 ms,
 * LIMIT 5-100 ms; release 60 ms-10 s, 20 ms-4 s, 10 ms-2 s). COMP 1 and 2 are 2:1; choice: LIMIT 8:1. */
static int zl_mode(float r) { int m = (int)lroundf(r); return m < 1 ? 1 : m > 3 ? 3 : m; }
static float zl_ms(int mode, int rel, float pos)
{
    static const float AT[4][2] = {{28, 570}, {28, 570}, {10, 200}, {5, 100}}, RT[4][2] = {{60, 10000}, {60, 10000}, {20, 4000}, {10, 2000}};
    const float *t = rel ? RT[mode] : AT[mode];
    float u = (pos - 1.f) / (rel ? 20.f : 10.f);
    u = u < 0.f ? 0.f : u > 1.f ? 1.f : u;
    return t[0] * powf(t[1] / t[0], u);
}
static float zl_slope(int mode) { return mode == 3 ? 1.f - 1.f / 8.f : 0.5f; }

static void fmt_hz(char *b, int len, float hz)
{
    if (hz >= 1000.f) snprintf(b, len, hz >= 9995.f ? "%.1f kHz" : "%.2f kHz", hz / 1000.f);
    else snprintf(b, len, "%.0f Hz", hz);
}
static void fmt_ms(char *b, int len, float ms)
{
    if (ms >= 1000.f) snprintf(b, len, "%.2f s", ms / 1000.f);
    else if (ms < 1.f) snprintf(b, len, "%.0f us", ms * 1000.f);   /* HEARTS: the DS1's attack goes down to 20 us */
    else if (ms >= 10.f) snprintf(b, len, "%.0f ms", ms);
    else snprintf(b, len, "%.1f ms", ms);
}

void xc_display(const XConsole *x, int i, char *b, int len)
{
    if (len <= 0) return;
    b[0] = 0;
    if (i < 0 || i >= P_COUNT || PT[i].kind != 0) return;
    for (int k = 0; k < NOF(NZ); k++)   /* the NOISE page: noise.c's own texts ("-24.0 dB", "Off", "1.2 kHz", "Mono") */
        if (NZ[k].p == i) {
            char key[40];
            snprintf(key, sizeof key, "%s_display", NZ[k].key);
            if (!x->nz || noise_get(x->nz, key, b, len) <= 0) b[0] = 0;
            return;
        }
    float n = x->val[i], v = map_n(x, i, n);
    int sp = special(x, i, n);
    if (sp == SP_OFF) { snprintf(b, len, "Off"); return; }
    if (sp == SP_AUTO) { snprintf(b, len, "AUTO"); return; }
    if (sp == SP_LIMIT) { snprintf(b, len, i == P_cmp_ratio && is_mke(model_of(x, i)) ? "NUKE" : "Limit"); return; }
    switch (i) {
    case P_lc_freq: case P_hc_freq: case P_cmp_sc_hpf: case P_eq_lf_freq: case P_eq_lmf_freq: case P_eq_hmf_freq: case P_eq_hf_freq:
        if ((i == P_eq_lf_freq || i == P_eq_hf_freq) && is_lil(model_of(x, i)) && OPT(x, i == P_eq_lf_freq ? P_eq_lf_type : P_eq_hf_type) == 0)
            v = i == P_eq_lf_freq ? LIL_LF_HZ : LIL_HF_HZ;               /* TITANIUM EQ: the shelf's fixed frequency */
        fmt_hz(b, len, v); return;
    case P_gate_hold: case P_gate_rel: case P_cmp_rel: case P_cmp_att:
        if (i == P_gate_hold && is_lil(model_of(x, i))) { fmt_hz(b, len, v); return; }   /* the DS section's FREQUENCY */
        if ((i == P_cmp_att || i == P_cmp_rel) && model_of(x, i) == MODEL_MOLTEN) {   /* the Zener's positions and their time */
            char t[16];
            fmt_ms(t, sizeof t, zl_ms(zl_mode(map_n(x, P_cmp_ratio, x->val[P_cmp_ratio])), i == P_cmp_rel, v));
            snprintf(b, len, "%d (%s)", (int)lroundf(v), t);
            return;
        }
        if ((i == P_cmp_att || i == P_cmp_rel) && model_of(x, i) == MODEL_SANDSTONE) {   /* the TLA-100A's three-way switches */
            int k = i == P_cmp_att ? (v < 1.f ? 0 : v < 10.f ? 1 : 2) : (v < 100.f ? 0 : v < 1000.f ? 1 : 2);
            static const char *FMS[3] = {"FAST", "MEDIUM", "SLOW"};
            snprintf(b, len, "%s", FMS[k]);
            return;
        }
        fmt_ms(b, len, v); return;
    case P_eq_lmf_q: case P_eq_hmf_q:
        if (model_of(x, i) == MODEL_SUEDE) { snprintf(b, len, v > 1.2f ? "HI Q" : "NORMAL"); return; }   /* British Class A's Hi Q switch */
        if (model_of(x, i) == MODEL_SPADES) { snprintf(b, len, v > 1.2f ? "HI Q" : "LO Q"); return; }    /* the 737's hi/lo Q switch */
        if (model_of(x, i) == MODEL_HEXX || model_of(x, i) == MODEL_MOLTEN) { snprintf(b, len, "%.2fx", v); return; }   /* HEXX, MOLTEN: a scale on their gain-dependent Q */
        if (model_of(x, i) == MODEL_SANDSTONE) {                        /* the EQF-100's BANDWIDTH: 0 narrow (Q 5) .. 10 wide (Q 0.5) */
            const PInfo *p = pinfo(x, i);
            snprintf(b, len, "BW %.1f", 10.f * logf(p->hi / v) / logf(p->hi / p->lo));
            return;
        }
        snprintf(b, len, "%.2f", v); return;
    case P_gate_ratio: case P_cmp_ratio:
        if (i == P_cmp_ratio && model_of(x, i) == MODEL_MOLTEN) {   /* the Zener's MODE */
            static const char *ZM[4] = {"", "COMP 1", "COMP 2", "LIMIT"};
            snprintf(b, len, "%s", ZM[zl_mode(v)]);
            return;
        }
        if (v < 0.995f) snprintf(b, len, "1:%.2f", 1.f / v);       /* HEARTS: the DS1 writes upward expansion as 1:x */
        else snprintf(b, len, "%.1f:1", v);
        return;
    case P_out_pan: {
        int p = (int)lroundf(v);
        if (p == 0) snprintf(b, len, "C");
        else snprintf(b, len, "%c %d", p < 0 ? 'L' : 'R', abs(p));
        return;
    }
    case P_drv_char: {
        if (model_of(x, i) == MODEL_HEARTS) {                         /* the DS1-MK3's safety limiter types */
            static const char *LT[3] = {"ORIGINAL", "TYPE 1", "TYPE 2 (TP)"};
            snprintf(b, len, "%s", LT[v < 33.4f ? 0 : v < 66.7f ? 1 : 2]);
            return;
        }
        int t = (int)lroundf(v);
        snprintf(b, len, "2nd %d / 3rd %d", 100 - t, t);
        return;
    }
    case P_sh_punch: case P_sh_sustain:
        snprintf(b, len, "%+d%%", (int)lroundf(v)); return;
    case P_drv_amt:
        if (model_of(x, i) == MODEL_HEARTS) { snprintf(b, len, "+%.1f dB", v); return; }   /* pre-limiter gain */
        if (is_mke(model_of(x, i))) { snprintf(b, len, "%.1f", v / 10.f); return; }         /* the Mike-E's DRIVE 0-10 */
        snprintf(b, len, "%d%%", (int)lroundf(v)); return;
    case P_pre_color: case P_cmp_mix: case P_out_width:
        snprintf(b, len, "%d%%", (int)lroundf(v)); return;
    case P_cmp_knee:
        if (model_of(x, i) == MODEL_HEARTS) { snprintf(b, len, "%.2f", v); return; }      /* the DS1's 0.0..1.0 */
        snprintf(b, len, "%.1f dB", v); return;
    case P_gate_range:
        snprintf(b, len, "%.1f dB", v); return;
    case P_eq_lmf_gain: case P_eq_hmf_gain: {
        int qi = i == P_eq_lmf_gain ? P_eq_lmf_q : P_eq_hmf_q;
        v *= eq_gain_scale(x, i == P_eq_lmf_gain ? 1 : 2, map_n(x, qi, x->val[qi]), 0);
        break;
    }
    case P_eq_lf_gain: v *= eq_gain_scale(x, 0, 0, OPT(x, P_eq_lf_type)); break;
    case P_eq_hf_gain: v *= eq_gain_scale(x, 3, 0, OPT(x, P_eq_hf_type)); break;
    }
    snprintf(b, len, "%+.1f dB", fabsf(v) < 0.05f ? 0.f : v);
}

const char *xc_param_alt_name(const XConsole *x, int i)
{
    if (!is_lil(model_sel(x, P_sh_model))) return NULL;
    if (i == P_gate_thr) return "De-Ess Threshold";
    if (i == P_gate_hold) return "De-Ess Frequency";
    if (i == P_gate_fast) return "HF Limiter On/Off";
    return NULL;
}

/* ---------------------------------------------------------------- control-rate update */
/* HEXX's proportional Q (0.11.0): wide at small gains, narrower as the gain goes up. choice: Q 0.35 + 1.15 x |gain| / 12 dB
 * (about 0.55 at 2 dB, 0.9 at 6 dB, 1.5 at 12 dB) */
static float hexx_pq(float gdb) { return 0.35f + 1.15f * fminf(fabsf(gdb) / 12.f, 1.f); }

static float onepole_a(float tau_s, float sr) { return 1.f - expf(-1.f / (tau_s * sr)); }

static void eq_coefs(XConsole *x, SvfC *out, int band, int use_sm)
{
    static const int GAIN[4] = {P_eq_lf_gain, P_eq_lmf_gain, P_eq_hmf_gain, P_eq_hf_gain};
    static const int FREQ[4] = {P_eq_lf_freq, P_eq_lmf_freq, P_eq_hmf_freq, P_eq_hf_freq};
    float gn = use_sm ? x->sm[GAIN[band]] : x->val[GAIN[band]], fn = use_sm ? x->sm[FREQ[band]] : x->val[FREQ[band]];
    float gdb = map_n(x, GAIN[band], gn), f = fminf(map_n(x, FREQ[band], fn), 0.47f * x->sr);
    int granite = model_sel(x, P_eq_model) == MODEL_GRANITE, hearts = model_sel(x, P_eq_model) == MODEL_HEARTS, suede = model_sel(x, P_eq_model) == MODEL_SUEDE;
    int sandstone = model_sel(x, P_eq_model) == MODEL_SANDSTONE, hexx = model_sel(x, P_eq_model) == MODEL_HEXX, molten = model_sel(x, P_eq_model) == MODEL_MOLTEN;
    int spades = model_sel(x, P_eq_model) == MODEL_SPADES;   /* SPADES: constant Q (its LO/HI switch), shelves at LF/HF */
    int mocha = model_sel(x, P_eq_model) == MODEL_MOCHA;   /* MOCHA: the 610's shelves, constant Q */
    int lilf = is_lil(model_sel(x, P_eq_model));             /* TITANIUM EQ: constant Q, fixed shelves */
    if (special(x, FREQ[band], fn) == SP_OFF) { svf_set(out, 0.1f, 1.f, 1.f, 0.f, 0.f); return; }   /* SUEDE: a band's OFF position */
    int estyle = granite || hearts || suede || sandstone || hexx || molten || spades || mocha || lilf || (use_sm ? x->act[P_eq_style] : OPT(x, P_eq_style)) == 1;   /* the GRANITE's 242 is E only; the EQ1 constant Q */
    int tk = band == 0 ? P_eq_lf_type : P_eq_hf_type;
    int type = (band == 0 || band == 3) ? (use_sm ? x->act[tk] : OPT(x, tk)) : 0;    /* LF/HF: 0 shelf, 1 bell, 2 cut */
    float q = 0.f;
    if (band == 1 || band == 2) {
        int qi = band == 1 ? P_eq_lmf_q : P_eq_hmf_q;
        q = map_n(x, qi, use_sm ? x->sm[qi] : x->val[qi]);
    }
    gdb *= eq_gain_scale(x, band, q, type);
    float A = powf(10.f, gdb / 40.f), t = tanf(PI_F * f / x->sr);
    if (band == 1 || band == 2) {
        if (!estyle) q *= 0.5f + 0.5f * fminf(fabsf(gdb) / 20.f, 1.f);
        if (hexx) q *= hexx_pq(gdb);                                       /* HEXX: the knob scales its proportional Q */
        if (molten) q *= cb_q(gdb);                                    /* MOLTEN: the knob scales the Curve Bender's width */   /* G (292): wider at small gains, E's width at full gain. choice: 0.5 */
        float k = 1.f / (q * A);
        svf_set(out, t, k, 1.f, k * (A * A - 1.f), 0.f);
        return;
    }
    if (type == 1) {                                                     /* bell: the FLANNEL's Q 2.5 (E only there; extra in G) */
        float bq = (hearts || suede || sandstone) ? 1.0f : 2.5f;   /* SANDSTONE: the EQF-100's LF/HF peak. choice: Q 1.0 */                        /* HEARTS, SUEDE: LF/HF have no Q knob here. choice: Q 1.0 */
        if (granite) {                                                     /* the GRANITE's follows the frequency (Waves). choice: 0.8..1.4 up its range */
            const PInfo *fp = pinfo(x, FREQ[band]);
            bq = 0.8f + 0.6f * clampf(logf(f / fp->lo) / logf(fp->hi / fp->lo), 0.f, 1.f);
        }
        if (hexx) bq = hexx_pq(gdb);                                       /* HEXX: the LF/HF peak is proportional Q too */
        if (molten) bq = cb_q(gdb);                                    /* MOLTEN: Bass / Treble bells narrow with gain too */
        if (lilf) bq = 0.9f;                                             /* TITANIUM EQ: its LF / HF parametric bands. choice: Q 0.9 */
        float k = 1.f / (bq * A);
        svf_set(out, t, k, 1.f, k * (A * A - 1.f), 0.f);
        return;
    }
    if (type == 2) {                                                     /* cut (extra): 12 dB/oct Butterworth at FREQ; GAIN unused */
        float k = lilf ? 1.f / 0.9f : 1.41421356f;                      /* TITANIUM EQ: a slight bump, as its filters (choice: Q 0.9) */
        if (band == 0) svf_set(out, t, k, 1.f, -k, -1.f);
        else svf_set(out, t, k, 0.f, 0.f, 1.f);
        return;
    }
    if (lilf) {                                                          /* TITANIUM EQ: the fixed shelves, gentle as a single pole */
        float kk = 2.f, sA = sqrtf(A);                                   /* (choice: Q 0.5); the FREQ knob is for BELL and CUT */
        t = tanf(PI_F * (band == 0 ? LIL_LF_HZ : LIL_HF_HZ) / x->sr);
        if (band == 0) svf_set(out, t / sA, kk, 1.f, kk * (A - 1.f), A * A - 1.f);
        else svf_set(out, t * sA, kk, A * A, kk * (1.f - A) * A, 1.f - A * A);
        return;
    }
    float k = 1.f / ((suede && band == 0) || !estyle ? 1.0f : 0.70710678f);   /* G shelves, SUEDE's LF: overshoot (the 1073's LF bump). choice: Q 1.0 */
    float sA = sqrtf(A);
    if (band == 0) svf_set(out, t / sA, k, 1.f, k * (A - 1.f), A * A - 1.f);
    else svf_set(out, t * sA, k, A * A, k * (1.f - A) * A, 1.f - A * A);
}

static void update_ctrl(XConsole *x)
{
    float a = x->ctrl_a, sr = x->sr;
    for (int i = 0; i < P_COUNT; i++)
        if (PT[i].kind == 0) x->sm[i] += (x->val[i] - x->sm[i]) * a;

    { float d = V(x, P_in_gain); x->g_in_t = fabsf(d) < 0.001f ? 1.f : DB2LIN(d); }
    /* preamp extra */
    float c = V(x, P_pre_color) / 100.f;
    x->pre_g = 1.f + 3.f * c;                                            /* choice: up to +12 dB into the curve */
    x->pre_bias = 0.25f * c;
    x->pre_norm = 1.f / (x->pre_g * tanh_slope(x->pre_bias));
    x->pre_glo = 1.f + 6.f * c;
    { float g = tanf(PI_F * fminf(22000.f - 8000.f * c, 0.45f * sr) / sr); x->pre_hf_G = g / (1.f + g); }
    { float g = tanf(PI_F * 150.f / (2.f * sr)); x->pre_lo_G = g / (1.f + g); }
    { float A = powf(10.f, 2.f * c / 40.f), k = 1.f / (1.0f * A); svf_set(&x->pre_bump_c, tanf(PI_F * 65.f / sr), k, 1.f, k * (A * A - 1.f), 0.f); }
    /* filters */
    filt_set(&x->lc_c, tanf(PI_F * fminf(V(x, P_lc_freq), 0.45f * sr) / sr), x->act[P_lc_slope] + 1, 1, flt_q(x));
    filt_set(&x->hc_c, tanf(PI_F * fminf(V(x, P_hc_freq), 0.45f * sr) / sr), x->act[P_hc_slope] + 1, 0, flt_q(x));
    /* shape */
    x->punch = V(x, P_sh_punch) / 100.f;
    x->sustain = V(x, P_sh_sustain) / 100.f;
    x->gate_thr = V(x, P_gate_thr);
    x->gate_hyst = 2.f + 6.f * (-10.f - x->gate_thr) / 40.f;            /* grows as the threshold goes down. choice: 2..8 dB */
    x->gate_range = V(x, P_gate_range);
    x->gate_hold_samples = special(x, P_gate_hold, x->val[P_gate_hold]) == SP_OFF ? 0 : (int)(V(x, P_gate_hold) * 0.001f * sr);
    x->gate_rel = 40.f / (V(x, P_gate_rel) * 0.001f * sr);              /* dB a sample: 40 dB per release time. choice */
    if (model_sel(x, P_sh_model) == MODEL_GRANITE)                            /* GRANITE: fast 1 ms; auto program dependent (choice: 40 dB in 3 ms) */
        x->gate_att = 40.f / ((OPT(x, P_gate_fast) ? 0.001f : 0.003f) * sr);
    else if (model_sel(x, P_sh_model) == MODEL_HEARTS)                          /* HEARTS: fast = the DS1's 20 us; normal choice: 40 dB in 0.5 ms */
        x->gate_att = 40.f / ((OPT(x, P_gate_fast) ? 0.00002f : 0.0005f) * sr);
    else if (model_sel(x, P_sh_model) == MODEL_SUEDE || model_sel(x, P_sh_model) == MODEL_SANDSTONE)   /* SUEDE, SANDSTONE (BCA gate): choice: 40 dB in 2 ms, fast 100 us */
        x->gate_att = 40.f / ((OPT(x, P_gate_fast) ? 0.0001f : 0.002f) * sr);
    else
        x->gate_att = 40.f / ((OPT(x, P_gate_fast) ? 0.0001f : 0.0015f) * sr);   /* FLANNEL: 40 dB in 1.5 ms, fast 100 us (linear) */
    x->gate_ratio = V(x, P_gate_ratio);
    x->ds_on = is_lil(model_sel(x, P_sh_model));                         /* TITANIUM EQ's DS section in place of the gate */
    if (x->ds_on) {                                                      /* the band over FREQUENCY: the signal less a 12 dB/oct */
        float f = fminf(V(x, P_gate_hold), 0.45f * sr);                  /* low pass there (choice), so the bands sum back exactly */
        svf_set(&x->ds_c, tanf(PI_F * f / sr), 1.41421356f, 0.f, 0.f, 1.f);
        x->ds_thr = V(x, P_gate_thr);
        x->ds_rel_thr = -12.f + 0.3f * (x->ds_thr + 40.f);               /* de-ess: the band against the whole, -12..0 dB. choice */
        x->ds_lim = OPT(x, P_gate_fast);                                 /* HF LIMITER */
    }
    /* EQ */
    for (int b = 0; b < 4; b++) eq_coefs(x, &x->eqc[b], b, 1);
    /* compressor */
    x->cmp_thr = V(x, P_cmp_thr);
    float r = V(x, P_cmp_ratio);
    x->cmp_slope = special(x, P_cmp_ratio, x->val[P_cmp_ratio]) == SP_LIMIT ? 1.f : 1.f - 1.f / r;
    x->cmp_hearts = model_sel(x, P_cmp_model) == MODEL_HEARTS;
    x->cmp_knee = special(x, P_cmp_knee, x->val[P_cmp_knee]) == SP_AUTO ? (x->act[P_cmp_det] ? 0.f : 10.f) : V(x, P_cmp_knee);   /* choice: RMS knee 10 dB */
    if (x->cmp_hearts) x->cmp_knee = V(x, P_cmp_knee) * 2.f * fabsf(x->cmp_thr);   /* DS1: knee 1.0 runs from 0 dBFS down to twice the threshold */
    x->cmp_rel_a = onepole_a(V(x, P_cmp_rel) * 0.001f / 3.f, sr);       /* choice: the knob is the ~95 % recovery time */
    x->cmp_rel_fast_a = onepole_a(V(x, P_cmp_rel) * 0.001f / 24.f, sr); /* HEARTS release fast. choice: an eighth of release slow */
    x->cmp_auto_att = special(x, P_cmp_att, x->val[P_cmp_att]) == SP_AUTO;
    x->cmp_att_tau = V(x, P_cmp_att) * 0.001f;
    x->cmp_makeup = (pinfo(x, P_cmp_thr)->hi - x->cmp_thr) * x->cmp_slope + V(x, P_cmp_makeup);   /* auto make-up (choice: full) + extra */
    if (x->cmp_hearts) {                                                  /* DS1: manual make-up, no AUTO attack, FAST ATT = 20 us */
        x->cmp_makeup = V(x, P_cmp_makeup);
        x->cmp_auto_att = 0;
        x->cmp_att_tau = OPT(x, P_cmp_fast) ? 0.00002f : V(x, P_cmp_att) * 0.001f;
    }
    x->cmp_nauto = 0;
    if (model_sel(x, P_cmp_model) == MODEL_SUEDE) {                       /* SUEDE: the 2254. Manual GAIN (no auto make-up), attack */
        x->cmp_makeup = V(x, P_cmp_makeup);                              /* 5 ms (the 2254's) to 30 ms (Softube's additions), FAST ATT */
        x->cmp_auto_att = 0;                                             /* 2 ms. choice: the knob is the time constant, as the others */
        x->cmp_att_tau = OPT(x, P_cmp_fast) ? 0.002f : V(x, P_cmp_att) * 0.001f;
        if (special(x, P_cmp_knee, x->val[P_cmp_knee]) == SP_AUTO) x->cmp_knee = x->act[P_cmp_det] ? 0.f : 6.f;   /* choice: the diode bridge's soft 6 dB */
        if (special(x, P_cmp_rel, x->val[P_cmp_rel]) == SP_AUTO) {       /* AUTO recovery: fast after isolated peaks, slow under a */
            x->cmp_nauto = 1;                                            /* sustained level. choices: 40 ms and 2 s, the slow part */
            x->cmp_rel_fast_a = onepole_a(0.040f / 3.f, sr);             /* building up in about 0.5 s */
            x->cmp_rel_a = onepole_a(2.0f / 3.f, sr);
            x->cmp_sa_a = onepole_a(0.500f, sr);
        }
    }
    if (model_sel(x, P_cmp_model) == MODEL_SANDSTONE) {                     /* SANDSTONE: the TLA-100A. Manual GAIN, FAST / MEDIUM / SLOW */
        x->cmp_makeup = V(x, P_cmp_makeup);                              /* attack (FAST ATT = FAST), a smooth soft knee (choice: 12 dB),  */
        x->cmp_auto_att = 0;                                             /* release program dependent: back fast after short peaks, at */
        x->cmp_att_tau = OPT(x, P_cmp_fast) ? 0.0005f : V(x, P_cmp_att) * 0.001f;   /* the switch's time under a sustained level */
        if (special(x, P_cmp_knee, x->val[P_cmp_knee]) == SP_AUTO) x->cmp_knee = x->act[P_cmp_det] ? 0.f : 12.f;
        x->cmp_nauto = 1;                                                /* choices: the fast part an eighth of the switch's time, the */
        x->cmp_rel_fast_a = onepole_a(V(x, P_cmp_rel) * 0.001f / 24.f, sr);   /* slow part building in about 0.5 s */
        x->cmp_rel_a = onepole_a(V(x, P_cmp_rel) * 0.001f / 3.f, sr);
        x->cmp_sa_a = onepole_a(0.500f, sr);
    }
    if (model_sel(x, P_cmp_model) == MODEL_HEXX) {                        /* HEXX: 2500/527 style. Manual output gain, attack 0.03-30 ms */
        x->cmp_makeup = V(x, P_cmp_makeup);                              /* (FAST ATT 0.3 ms), AUTO knee 4 dB (the 2500's MED; choice) */
        x->cmp_auto_att = 0;
        x->cmp_att_tau = OPT(x, P_cmp_fast) ? 0.0003f : V(x, P_cmp_att) * 0.001f;
        if (special(x, P_cmp_knee, x->val[P_cmp_knee]) == SP_AUTO) x->cmp_knee = x->act[P_cmp_det] ? 0.f : 4.f;
    }
    if (model_sel(x, P_cmp_model) == MODEL_MOLTEN) {                   /* MOLTEN: the Zener Limiter. MODE sets the ratio and */
        int zm = zl_mode(V(x, P_cmp_ratio));                             /* the time ranges, OUTPUT is manual (+-10 dB), FAST ATT */
        float rel = zl_ms(zm, 1, V(x, P_cmp_rel)) * 0.001f;              /* 1 ms. choice: AUTO knee 6 dB */
        x->cmp_slope = zl_slope(zm);
        x->cmp_makeup = V(x, P_cmp_makeup);
        x->cmp_auto_att = 0;
        x->cmp_att_tau = OPT(x, P_cmp_fast) ? 0.001f : zl_ms(zm, 0, V(x, P_cmp_att)) * 0.001f;
        x->cmp_rel_a = onepole_a(rel / 3.f, sr);
        x->cmp_rel_fast_a = onepole_a(rel / 24.f, sr);
        if (special(x, P_cmp_knee, x->val[P_cmp_knee]) == SP_AUTO) x->cmp_knee = x->act[P_cmp_det] ? 0.f : 6.f;
    }
    if (model_sel(x, P_cmp_model) == MODEL_SPADES) {                     /* SPADES: the 737's opto compressor. Manual GAIN, attack */
        x->cmp_makeup = V(x, P_cmp_makeup);                              /* 2-200 ms (choice: FAST ATT 1 ms), AUTO knee 10 dB (a soft */
        x->cmp_auto_att = 0;                                             /* opto knee; choice), release program dependent as an opto */
        x->cmp_att_tau = OPT(x, P_cmp_fast) ? 0.001f : V(x, P_cmp_att) * 0.001f;   /* cell: back fast after short peaks, at the */
        if (special(x, P_cmp_knee, x->val[P_cmp_knee]) == SP_AUTO) x->cmp_knee = x->act[P_cmp_det] ? 0.f : 10.f;   /* knob's time */
        x->cmp_nauto = 1;                                                /* under a sustained level (as SANDSTONE's TLA-100A) */
        x->cmp_rel_fast_a = onepole_a(V(x, P_cmp_rel) * 0.001f / 24.f, sr);
        x->cmp_rel_a = onepole_a(V(x, P_cmp_rel) * 0.001f / 3.f, sr);
        x->cmp_sa_a = onepole_a(0.500f, sr);
    }
    if (model_sel(x, P_cmp_model) == MODEL_MOCHA) {                     /* MOCHA: the 1176LN. Manual OUTPUT, attack 20-800 us */
        x->cmp_makeup = V(x, P_cmp_makeup);                              /* (FAST ATT 20 us, the knob's fastest), AUTO knee 2 dB */
        x->cmp_auto_att = 0;                                             /* (choice: a near-hard FET knee) */
        x->cmp_att_tau = OPT(x, P_cmp_fast) ? 0.00002f : V(x, P_cmp_att) * 0.001f;
        if (special(x, P_cmp_knee, x->val[P_cmp_knee]) == SP_AUTO) x->cmp_knee = x->act[P_cmp_det] ? 0.f : 2.f;
    }
    if (is_mke(model_sel(x, P_cmp_model))) {                             /* TITANIUM DRIVE: the CompSat's compressor. Manual GAIN, attack */
        int nuke = special(x, P_cmp_ratio, x->val[P_cmp_ratio]) == SP_LIMIT;   /* 0.9-100 ms (FAST ATT 0.9 ms), release 50 ms-1 s; */
        float rel = V(x, P_cmp_rel) * 0.001f * (nuke ? 0.5f : 1.f);      /* NUKE has "a different attack and release shape" */
        x->cmp_makeup = V(x, P_cmp_makeup);                              /* (choice: twice as fast); AUTO knee by ratio, RMS or */
        x->cmp_auto_att = 0;                                             /* peak alike */
        x->cmp_att_tau = (OPT(x, P_cmp_fast) ? 0.0009f : V(x, P_cmp_att) * 0.001f) * (nuke ? 0.5f : 1.f);
        x->cmp_rel_a = onepole_a(rel / 3.f, sr);
        if (special(x, P_cmp_knee, x->val[P_cmp_knee]) == SP_AUTO) x->cmp_knee = mke_knee(r, nuke);
    }
    x->cmp_fast_tau = model_sel(x, P_cmp_model) == MODEL_GRANITE ? 0.0004f : 0.001f;   /* fast attack: GRANITE 1 ms, FLANNEL 3 ms for 20 dB */
    x->cmp_mix = V(x, P_cmp_mix) / 100.f;
    x->cmp_hp_on = special(x, P_cmp_sc_hpf, x->val[P_cmp_sc_hpf]) != SP_OFF;
    svf_set(&x->cmp_hp_c, tanf(PI_F * V(x, P_cmp_sc_hpf) / sr), 1.41421356f, 1.f, -1.41421356f, -1.f);
    /* drive */
    x->drv_g = DB2LIN(30.f * V(x, P_drv_amt) / 100.f);                  /* choice: 0..+30 dB into the curve */
    x->drv_ge = sqrtf(x->drv_g);                                         /* the 2nd-harmonic side is driven half as hard (in dB) */
    x->drv_char = V(x, P_drv_char) / 100.f;
    x->drv_mke = is_mke(model_sel(x, P_cmp_model));                    /* TITANIUM DRIVE: after the triode-like curve a germanium stage */
    x->drv_th = 1.4f - 0.9f * V(x, P_drv_amt) / 100.f;                   /* rounds the peaks harder as DRIVE goes up ("12% THD and */
                                                                         /* tape like compression"). choice: its ceiling 1.4 -> 0.5 */
    x->drv_hearts = model_sel(x, P_cmp_model) == MODEL_HEARTS;           /* HEARTS: the safety limiter */
    if (x->drv_hearts) {
        float t = V(x, P_drv_char);
        x->lim_pre = DB2LIN(V(x, P_drv_amt));
        x->lim_type = t < 33.4f ? 0 : t < 66.7f ? 1 : 2;
    }
    /* output */
    float p = V(x, P_out_pan) / 100.f, th = (p + 1.f) * PI_F / 4.f;
    x->pan_l_t = cosf(th) * 1.41421356f;
    x->pan_r_t = sinf(th) * 1.41421356f;
    if (x->pan_l_t > 1.f) x->pan_l_t = 1.f;                              /* centre is unity; one side only drops */
    if (x->pan_r_t > 1.f) x->pan_r_t = 1.f;
    x->width_t = V(x, P_out_width) / 100.f;
    { float d = V(x, P_out_vol); x->g_out_t = special(x, P_out_vol, x->val[P_out_vol]) == SP_OFF ? 0.f : fabsf(d) < 0.001f ? 1.f : DB2LIN(d); }
}

/* ---------------------------------------------------------------- per-sample sections */
static inline void fade_to(float *w, int on, float step)
{
    if (on) { if (*w < 1.f) *w = fminf(1.f, *w + step); }
    else if (*w > 0.f) *w = fmaxf(0.f, *w - step);
}

static void filters(XConsole *x, FiltPair *fp, float *l, float *r, float wlc, float whc)
{
    float *ch[2] = {l, r};
    for (int c = 0; c < 2; c++) {
        float v = *ch[c];
        if (wlc > 0.f) { float y = filt_tick(&fp[c].lc, &x->lc_c, v, 1); v += wlc * (y - v); }
        if (whc > 0.f) { float y = filt_tick(&fp[c].hc, &x->hc_c, v, 0); v += whc * (y - v); }
        *ch[c] = v;
    }
}

static inline float env(float e, float in, float a, float r) { return e + (in - e) * (in > e ? a : r); }

/* TITANIUM EQ's DS section: the band over FREQUENCY (the signal less a low pass, so it sums back exactly) turned down by the
 * reduction. De-ess (HF LIMITER off): "level insensitive", the band's level against the whole signal's (-80 dBFS and under
 * left alone), choice 4:1 over the threshold. HF LIM: "level sensitive", a soft-knee limiter on the band. Attack "less than
 * 1mS" (choice 0.3 ms), release ".04 sec, fixed" (EL-Q manual). */
static void deess(XConsole *x, float *l, float *r)
{
    float hl = *l - svf_tick(&x->ds_lp[0], &x->ds_c, *l), hr = *r - svf_tick(&x->ds_lp[1], &x->ds_c, *r);
    x->ds_hf = env(x->ds_hf, fmaxf(fabsf(hl), fabsf(hr)), x->ds_a, x->ds_r);
    x->ds_full = env(x->ds_full, fmaxf(fabsf(*l), fabsf(*r)), x->ds_a, x->ds_r);
    float hdb = LIN2DB(x->ds_hf + 1e-9f), gt = 0.f;
    if (x->ds_lim) gt = ds_lim_db(hdb - x->ds_thr);
    else if (x->ds_full > 1e-4f) {
        float o = hdb - LIN2DB(x->ds_full + 1e-9f) - x->ds_rel_thr;
        gt = o > 0.f ? fminf(0.75f * o, 24.f) : 0.f;
    }
    x->gate_gr = gt;
    x->sh_db = 0.f;
    float g = DB2LIN(-gt) - 1.f;
    *l += g * hl; *r += g * hr;
}

static void shape(XConsole *x, float *l, float *r, float scl, float scr)
{
    if (x->ds_on) { deess(x, l, r); return; }
    float in_l = *l, in_r = *r;
    float det = fmaxf(fabsf(scl), fabsf(scr));
    float gain = 1.f;
    /* transients (extra) */
    if (x->punch != 0.f || x->sustain != 0.f) {
        x->e_fa = env(x->e_fa, det, x->a_fast, x->r_mid);
        x->e_sa = env(x->e_sa, det, x->a_slow, x->r_mid);
        x->e_fr = env(x->e_fr, det, x->a_fast, x->r_fast);
        x->e_sr = env(x->e_sr, det, x->a_fast, x->r_long);
        float pdb = LIN2DB((x->e_fa + 1e-5f) / (x->e_sa + 1e-5f));
        float sdb = LIN2DB((x->e_sr + 1e-5f) / (x->e_fr + 1e-5f));
        float t = clampf(x->punch * pdb + 0.7f * x->sustain * sdb, -30.f, 18.f);
        x->sh_db += (t - x->sh_db) * (t < x->sh_db ? x->a_sm_dn : x->a_sm);
    } else {
        x->sh_db *= 1.f - x->a_sm;
        x->e_fa = x->e_sa = x->e_fr = x->e_sr = det;
    }
    gain = DB2LIN(x->sh_db);
    /* gate / expander (FLANNEL) */
    if (x->gate_range > 0.f || x->gate_gr > 0.f) {
        if (det >= x->gate_pk) { x->gate_pk = det; x->gate_hold_n = 0.012f * x->sr; }   /* peak, held 12 ms, then 15 ms fall. choice */
        else if (x->gate_hold_n > 0.f) x->gate_hold_n -= 1.f;
        else x->gate_pk *= 1.f - x->gate_pk_rel;
        float lv = LIN2DB(x->gate_pk + 1e-9f), tgt;
        if (x->act[P_gate_mode] == 0) {
            if (lv > x->gate_thr) { x->gate_open = 1; x->gate_hold_left = x->gate_hold_samples; }
            else if (lv < x->gate_thr - x->gate_hyst) { if (x->gate_hold_left > 0) x->gate_hold_left--; else x->gate_open = 0; }
            tgt = x->gate_open ? 0.f : x->gate_range;
        } else {
            if (lv > x->gate_thr) x->gate_hold_left = x->gate_hold_samples;
            else if (x->gate_hold_left > 0) x->gate_hold_left--;
            float under = x->gate_thr - lv;
            tgt = under > 0.f ? fminf(x->gate_range, under * (x->gate_ratio - 1.f)) : 0.f;
        }
        if (tgt < x->gate_gr) x->gate_gr = fmaxf(tgt, x->gate_gr - x->gate_att);
        else if (x->gate_hold_left <= 0) x->gate_gr = fminf(tgt, x->gate_gr + x->gate_rel);
        gain *= DB2LIN(-x->gate_gr);
    }
    *l = in_l * gain;
    *r = in_r * gain;
}

static void eq(XConsole *x, float *l, float *r)
{
    for (int b = 0; b < 4; b++) {
        *l = svf_tick(&x->eq[b][0], &x->eqc[b], *l);
        *r = svf_tick(&x->eq[b][1], &x->eqc[b], *r);
    }
}

static void comp(XConsole *x, float *l, float *r, float scl, float scr)
{
    if (x->cmp_hp_on) { scl = svf_tick(&x->cmp_hp[0], &x->cmp_hp_c, scl); scr = svf_tick(&x->cmp_hp[1], &x->cmp_hp_c, scr); }
    float lv, pk = fmaxf(fabsf(scl), fabsf(scr)), sq = fmaxf(scl * scl, scr * scr);
    x->cmp_ms += (sq - x->cmp_ms) * x->cmp_ms_a;                          /* the RMS runs always: HEARTS's release reads it */
    if (x->act[P_cmp_det] == 0) lv = 4.34294482f * logf(x->cmp_ms + 1e-12f);   /* RMS, linked */
    else lv = LIN2DB(pk + 1e-9f);                                         /* PK: peak, hard knee (HEARTS: its own knee) */
    float o = lv - x->cmp_thr, W = x->cmp_knee, gt;
    if (2.f * o <= -W) gt = 0.f;
    else if (2.f * fabsf(o) < W) gt = x->cmp_slope * (o + W * 0.5f) * (o + W * 0.5f) / (2.f * W);
    else gt = x->cmp_slope * o;
    if (gt < -24.f) gt = -24.f;                                           /* HEARTS upward expansion (ratio under 1:1). choice: at most +24 dB */
    if (x->cmp_nauto) {                                                   /* SUEDE AUTO recovery */
        if (gt > x->cmp_gr_f) x->cmp_gr_f += (gt - x->cmp_gr_f) / (1.f + x->cmp_att_tau * x->sr);
        else x->cmp_gr_f += (gt - x->cmp_gr_f) * x->cmp_rel_fast_a;
        x->cmp_gr_s += (gt - x->cmp_gr_s) * (gt > x->cmp_gr_s ? x->cmp_sa_a : x->cmp_rel_a);
        x->cmp_gr = fmaxf(x->cmp_gr_f, x->cmp_gr_s);
    } else if (fabsf(gt) > fabsf(x->cmp_gr)) {                                   /* more gain change: attack (the same as gt > gr for compression) */
        float tau;
        if (!x->cmp_auto_att) tau = x->cmp_att_tau;
        else if (OPT(x, P_cmp_fast)) tau = x->cmp_fast_tau;
        else tau = 0.010f * powf(0.1f, fminf(gt, 20.f) / 20.f);         /* program dependent, 3..30 ms */
        x->cmp_gr += (gt - x->cmp_gr) / (1.f + tau * x->sr);
    } else if (x->cmp_hearts && LIN2DB(pk + 1e-9f) - 4.34294482f * logf(x->cmp_ms + 1e-12f) > 9.f)
        x->cmp_gr += (gt - x->cmp_gr) * x->cmp_rel_fast_a;               /* DS1: a short peak (peak well over the RMS) releases fast. choice: 9 dB */
    else x->cmp_gr += (gt - x->cmp_gr) * x->cmp_rel_a;
    if (!x->cmp_nauto) x->cmp_gr_f = x->cmp_gr_s = x->cmp_gr;
    float g = DB2LIN(x->cmp_makeup - x->cmp_gr);
    float m = x->cmp_mix;
    *l += m * (*l * g - *l);
    *r += m * (*r * g - *r);
}

static void preamp(XConsole *x, float *l, float *r)
{
    float *ch[2] = {l, r};
    int type = x->act[P_pre_type];
    for (int c = 0; c < 2; c++) {
        float u0, u1, y[2];
        hb_up(&x->pre_up[c], x->hbc, *ch[c], &u0, &u1);
        float u[2] = {u0, u1};
        for (int k = 0; k < 2; k++) {
            float v = u[k];
            if (type == 0) y[k] = tanh_f(x->pre_g * v) / x->pre_g;                                      /* TAPE */
            else if (type == 1) y[k] = (tanh_f(x->pre_g * v + x->pre_bias) - tanh_f(x->pre_bias)) * x->pre_norm;   /* TUBE */
            else {                                                                                       /* IRON: the lows saturate first */
                float lo = op_lp(&x->pre_lo[c], v, x->pre_lo_G);
                v = (v - lo) + tanh_f(x->pre_glo * lo) / x->pre_glo;
                y[k] = tanh_f(1.3f * v) / 1.3f;
            }
        }
        float o = hb_down(&x->pre_dn[c], x->hbc, y[0], y[1]);
        if (type == 0) { o = svf_tick(&x->pre_bump[c], &x->pre_bump_c, o); o = op_lp(&x->pre_hf[c], o, x->pre_hf_G); }
        if (type == 1) o -= op_lp(&x->pre_dc[c], o, x->pre_dc_G);
        *ch[c] = o;
    }
}

/* The drive curve and its anti-derivative, in double: y = (1-c) nE E(x) + c nO O(x), with
 *   E(x) = T(ge x + b) - T(b)              a biased (asymmetric) curve: 2nd harmonic, valve side
 *   O(x) = 1.5 T(0.6667 g x)               symmetric: 3rd harmonic, transistor side
 * T is the rational tanh (tanh_f) and A its anti-derivative. ADAA1: y = (F(x1) - F(x0)) / (x1 - x0).
 * nE and nO are the auto-gain: a -12 dBFS sine comes out at its own RMS level on either side, whatever the drive. */
#define DRV_BIAS 0.6
static double rt(double v) { if (v > 3) return 1; if (v < -3) return -1; double v2 = v * v; return v * (27 + v2) / (27 + 9 * v2); }
static double rA(double v)
{
    double a = fabs(v);
    if (a > 3) return a - 3 + 2.348392481;                         /* the inner piece at 3: 0.5 + 4/3 ln 4, so F is continuous */
    return v * v / 18 + 4.0 / 3.0 * log(9 * v * v + 27) - 4.0 / 3.0 * log(27.0);
}
static double drv_f(double u, const DrvK *k)
{
    double tb = rt(DRV_BIAS);
    return (1 - k->c) * k->nE * (rt(k->ge * u + DRV_BIAS) - tb) + k->c * k->nO * 1.5 * rt(0.6667 * k->g * u);
}
static double drv_F(double u, const DrvK *k)
{
    double e = 0, o = 0;
    if (k->c < 1) e = k->nE * (rA(k->ge * u + DRV_BIAS) / k->ge - rt(DRV_BIAS) * u);
    if (k->c > 0) o = k->nO * 1.5 * rA(0.6667 * k->g * u) / (0.6667 * k->g);
    return (1 - k->c) * e + k->c * o;
}
static void drv_gain(DrvK *k)                                        /* the auto-gain, from a 32-point -12 dBFS sine */
{
    double se = 0, so = 0, me = 0, tb = rt(DRV_BIAS), ev[32];
    for (int i = 0; i < 32; i++) { double a = 0.25 * sin(2 * M_PI * i / 32); ev[i] = rt(k->ge * a + DRV_BIAS) - tb; me += ev[i] / 32; so += pow(1.5 * rt(0.6667 * k->g * a), 2); }
    for (int i = 0; i < 32; i++) se += (ev[i] - me) * (ev[i] - me);
    double ref = 0.25 / sqrt(2.0);
    k->nE = ref / sqrt(se / 32); k->nO = ref / sqrt(so / 32);
}

/* HEARTS: the DS1-MK3's safety limiter. Ceiling -0.1 dBFS (choice); the gain comes from the sample going out and the one
 * after it (one sample of look-ahead, so no sample passes the ceiling). ORIGINAL releases in 50 ms; TYPE 1 releases
 * fast (10 ms) after short peaks and slowly (250 ms) under sustained limiting (choices; the MK3's auto release);
 * TYPE 2 adds inter-sample (true) peaks, estimated half way between samples. */
static void limiter(XConsole *x, float *l, float *r)
{
    float a = *l * x->lim_pre, b = *r * x->lim_pre;
    float p = fmaxf(fmaxf(fabsf(a), fabsf(b)), fmaxf(fabsf(x->lim_d[0]), fabsf(x->lim_d[1])));
    if (x->lim_type == 2) {
        float in[2] = {a, b};
        for (int c = 0; c < 2; c++) {                                   /* quadratic through the last three samples, at t = 1.5 */
            float m = (-x->lim_d2[c] + 6.f * x->lim_d[c] + 3.f * in[c]) * 0.125f;
            p = fmaxf(p, fabsf(m));
        }
    }
    float tgt = p > x->lim_ceil ? x->lim_ceil / p : 1.f;
    if (tgt < x->lim_g) x->lim_g = tgt;
    else {
        int k = x->lim_type == 0 ? 0 : x->lim_avg > 1.f ? 2 : 1;
        x->lim_g += (tgt - x->lim_g) * x->lim_rel_a[k];
    }
    x->lim_avg += (-LIN2DB(x->lim_g) - x->lim_avg) * x->lim_avg_a;
    *l = x->lim_d[0] * x->lim_g; *r = x->lim_d[1] * x->lim_g;
    x->lim_d2[0] = x->lim_d[0]; x->lim_d2[1] = x->lim_d[1];
    x->lim_d[0] = a; x->lim_d[1] = b;
}

static void drive(XConsole *x, float *l, float *r)
{
    if (x->drv_hearts) { limiter(x, l, r); return; }
    float *ch[2] = {l, r};
    double g = x->drv_g, ge = x->drv_ge, cc = x->drv_char;
    DrvK *K = &x->drv_k;
    if (K->g != g || K->ge != ge) { K->g = g; K->ge = ge; drv_gain(K); }
    K->c = cc;
    for (int c = 0; c < 2; c++) {
        float a0, a1, q[4], y[4];
        hb_up(&x->drv_up[c], x->hbc, *ch[c], &a0, &a1);
        hb_up(&x->drv_up2[c], x->hbc, a0, &q[0], &q[1]);              /* one filter on the 2x stream: a0 then a1 */
        hb_up(&x->drv_up2[c], x->hbc, a1, &q[2], &q[3]);
        if (x->drv_key[c][0] != g || x->drv_key[c][1] != ge || x->drv_key[c][2] != cc) {   /* settings moved: F of the last input again */
            x->drv_F1[c] = drv_F(x->drv_x1[c], K);
            x->drv_key[c][0] = g; x->drv_key[c][1] = ge; x->drv_key[c][2] = cc;
        }
        for (int k = 0; k < 4; k++) {
            double x1 = q[k], x0 = x->drv_x1[c], d = x1 - x0, F1 = drv_F(x1, K);
            y[k] = (float)(fabs(d) > 1e-4 ? (F1 - x->drv_F1[c]) / d : drv_f(0.5 * (x0 + x1), K));
            if (x->drv_mke) y[k] = x->drv_th * tanh_f(y[k] / x->drv_th);   /* TITANIUM DRIVE: the germanium stage */
            x->drv_x1[c] = x1; x->drv_F1[c] = F1;
        }
        float b0 = hb_down(&x->drv_dn2[c], x->hbc, y[0], y[1]);
        float b1 = hb_down(&x->drv_dn2[c], x->hbc, y[2], y[3]);
        float o = hb_down(&x->drv_dn[c], x->hbc, b0, b1);
        o -= op_lp(&x->drv_dc[c], o, x->drv_dc_G);                      /* the 2nd harmonic's DC */
        *ch[c] = o;
    }
}

/* ---------------------------------------------------------------- the dip that applies structural switches */
static void apply_struct(XConsole *x)
{
    int was_lc = x->act[P_lc_slope], was_hc = x->act[P_hc_slope], was_sc = x->act[P_flt_sc];
    for (int k = 0; k < N_STRUCT; k++) x->act[STRUCT_KEYS[k]] = OPT(x, STRUCT_KEYS[k]);
    x->pol = x->act[P_phase] ? -1.f : 1.f;
    if (was_lc != x->act[P_lc_slope] || was_hc != x->act[P_hc_slope] || was_sc != x->act[P_flt_sc]) {
        memset(x->f_audio, 0, sizeof x->f_audio); memset(x->f_sc_sh, 0, sizeof x->f_sc_sh); memset(x->f_sc_cmp, 0, sizeof x->f_sc_cmp);
    }
    memset(x->pre_up, 0, sizeof x->pre_up); memset(x->pre_dn, 0, sizeof x->pre_dn);
    for (int b = 0; b < 4; b++) eq_coefs(x, &x->eqc[b], b, 1);
    filt_set(&x->lc_c, tanf(PI_F * fminf(V(x, P_lc_freq), 0.45f * x->sr) / x->sr), x->act[P_lc_slope] + 1, 1, flt_q(x));
    filt_set(&x->hc_c, tanf(PI_F * fminf(V(x, P_hc_freq), 0.45f * x->sr) / x->sr), x->act[P_hc_slope] + 1, 0, flt_q(x));
}

/* ---------------------------------------------------------------- process */
static const int ORDERS[6][3] = {{0, 1, 2}, {0, 2, 1}, {1, 0, 2}, {1, 2, 0}, {2, 0, 1}, {2, 1, 0}};   /* 0 shape, 1 EQ, 2 comp */

#define XC_BLK 256   /* run_block's most frames: the noise generator fills a block of noise first */
static void run_block(XConsole *x, const float *in_l, const float *in_r, float *out_l, float *out_r, int n)
{
    float nzl[XC_BLK], nzr[XC_BLK];   /* the noise generator's output (0.19.0: added after INPUT, before the preamp) */
    memset(nzl, 0, sizeof nzl); memset(nzr, 0, sizeof nzr);
    if (x->nz) noise_process(x->nz, nzl, nzr, n);   /* adds noise to silence: noise alone */
    const float fs = x->fade_step;
    float pk[4] = {0, 0, 0, 0};
    for (int i = 0; i < n; i++) {
        if (x->ctrl_left <= 0) {
            update_ctrl(x);
            x->ctrl_left = CTRL;
        }
        x->ctrl_left--;
        /* structural switches: down 5 ms, swap, hold 10 ms, up 5 ms */
        if (x->pending && x->dip_state == 0) x->dip_state = 1;
        if (x->dip_state == 1) { x->dip -= 2.f * fs; if (x->dip <= 0.f) { x->dip = 0.f; apply_struct(x); x->pending = 0; x->dip_state = 2; x->dip_hold = (int)(0.010f * x->sr); } }
        else if (x->dip_state == 2) { if (--x->dip_hold <= 0) x->dip_state = 3; }
        else if (x->dip_state == 3) { x->dip += 2.f * fs; if (x->dip >= 1.f) { x->dip = 1.f; x->dip_state = x->pending ? 1 : 0; } }

        /* glides: one-pole per sample towards the control-rate targets (about 2 ms) */
        const float gs = 0.01f;
        x->g_in += (x->g_in_t - x->g_in) * gs; x->g_out += (x->g_out_t - x->g_out) * gs;
        x->pan_l += (x->pan_l_t - x->pan_l) * gs; x->pan_r += (x->pan_r_t - x->pan_r) * gs;
        x->width += (x->width_t - x->width) * gs;
        fade_to(&x->w_pre, OPT(x, P_pre_on), fs);
        int flt = OPT(x, P_flt_on);
        fade_to(&x->w_lc, flt && special(x, P_lc_freq, x->val[P_lc_freq]) != SP_OFF, fs);
        fade_to(&x->w_hc, flt && special(x, P_hc_freq, x->val[P_hc_freq]) != SP_OFF, fs);
        fade_to(&x->w_sh, OPT(x, P_sh_on), fs);
        fade_to(&x->w_eq, OPT(x, P_eq_on), fs);
        fade_to(&x->w_cmp, OPT(x, P_cmp_on), fs);
        fade_to(&x->w_drv, OPT(x, P_drv_on), fs);
        fade_to(&x->w_byp, !OPT(x, P_bypass), fs);

        float dl = in_l[i], dr = in_r[i];
        float l = dl * x->g_in * x->pol + nzl[i], r = dr * x->g_in * x->pol + nzr[i];
        pk[0] = fmaxf(pk[0], fabsf(l)); pk[1] = fmaxf(pk[1], fabsf(r));

        if (x->w_pre > 0.f) { float pl = l, pr = r; preamp(x, &pl, &pr); l += x->w_pre * (pl - l); r += x->w_pre * (pr - r); }
        float sc_ok = x->act[P_flt_sc];
        if (!sc_ok) filters(x, x->f_audio, &l, &r, x->w_lc, x->w_hc);
        if (x->w_drv > 0.f && x->act[P_drv_pos] == 1) { float a = l, b = r; drive(x, &a, &b); l += x->w_drv * (a - l); r += x->w_drv * (b - r); }

        const int *ord = ORDERS[x->act[P_order]];
        for (int s = 0; s < 3; s++) {
            if (ord[s] == 0 && x->w_sh > 0.f) {
                float a = l, b = r, sa = l, sb = r;
                if (sc_ok) filters(x, x->f_sc_sh, &sa, &sb, x->w_lc, x->w_hc);
                shape(x, &a, &b, sa, sb);
                l += x->w_sh * (a - l); r += x->w_sh * (b - r);
            } else if (ord[s] == 1 && x->w_eq > 0.f) {
                float a = l, b = r;
                eq(x, &a, &b);
                l += x->w_eq * (a - l); r += x->w_eq * (b - r);
            } else if (ord[s] == 2 && x->w_cmp > 0.f) {
                float a = l, b = r, sa = l, sb = r;
                if (sc_ok) filters(x, x->f_sc_cmp, &sa, &sb, x->w_lc, x->w_hc);
                comp(x, &a, &b, sa, sb);
                l += x->w_cmp * (a - l); r += x->w_cmp * (b - r);
            }
        }
        if (x->w_drv > 0.f && x->act[P_drv_pos] == 0) { float a = l, b = r; drive(x, &a, &b); l += x->w_drv * (a - l); r += x->w_drv * (b - r); }

        /* width (M/S), pan (balance), volume */
        float m = 0.5f * (l + r), sd = 0.5f * (l - r) * x->width;
        l = (m + sd) * x->pan_l * x->g_out;
        r = (m - sd) * x->pan_r * x->g_out;
        l *= x->dip; r *= x->dip;
        l = dl + x->w_byp * (l - dl);
        r = dr + x->w_byp * (r - dr);
        pk[2] = fmaxf(pk[2], fabsf(l)); pk[3] = fmaxf(pk[3], fabsf(r));
        out_l[i] = l; out_r[i] = r;
    }
    /* meters: peak with a 20 dB/s fall */
    float fall = 20.f * n / x->sr;
    for (int k = 0; k < 4; k++) {
        float d = LIN2DB(pk[k] + 1e-9f);
        x->lev[k] = d > x->lev[k] - fall ? d : x->lev[k] - fall;
        if (x->lev[k] < -120.f) x->lev[k] = -120.f;
    }
    x->gr_show = x->w_cmp > 0.f ? x->cmp_gr : 0.f;
    x->gate_show = x->w_sh > 0.f ? x->gate_gr : 0.f;
    /* meter parameters, 0..1: levels -60..+6 dBFS, reductions 0..20 dB (comp) and 0..40 dB (gate) */
    x->val[P_m_in_l] = clampf((x->lev[0] + 60.f) / 66.f, 0, 1); x->val[P_m_in_r] = clampf((x->lev[1] + 60.f) / 66.f, 0, 1);
    x->val[P_m_out_l] = clampf((x->lev[2] + 60.f) / 66.f, 0, 1); x->val[P_m_out_r] = clampf((x->lev[3] + 60.f) / 66.f, 0, 1);
    x->val[P_m_gr] = clampf(x->gr_show / 20.f, 0, 1);
    x->val[P_m_gate] = clampf(x->gate_show / 40.f, 0, 1);
    /* the SHAPE section's gain change: transients (+-) less the gate's reduction, -20..+20 dB (0.8.0) */
    x->val[P_m_shape] = clampf(((x->w_sh > 0.f ? x->sh_db - x->gate_gr : 0.f) + 20.f) / 40.f, 0, 1);
}

void xc_process(XConsole *x, const float *in_l, const float *in_r, float *out_l, float *out_r, int n)
{
    for (int o = 0; o < n; o += XC_BLK) {
        int c = n - o < XC_BLK ? n - o : XC_BLK;
        run_block(x, in_l + o, in_r + o, out_l + o, out_r + o, c);
    }
}

float xc_level_db(const XConsole *x, int w) { return (w >= 0 && w < 4) ? x->lev[w] : -120.f; }
float xc_comp_gr_db(const XConsole *x) { return x->gr_show; }
float xc_gate_gr_db(const XConsole *x) { return x->gate_show; }

/* the gate/expander's static curve from the knob targets: GATE drops by RANGE under the threshold, EXP by (ratio - 1) dB
 * a dB under it, at most RANGE (no hysteresis, hold or timing) */
float xc_gate_curve_db(const XConsole *x, float in_db)
{
    if (is_lil(model_sel(x, P_sh_model)))                                /* TITANIUM EQ: HF LIM's curve for a tone in the band; */
        return OPT(x, P_gate_fast) ? in_db - ds_lim_db(in_db - map_n(x, P_gate_thr, x->val[P_gate_thr])) : in_db;   /* de-ess: 1:1 */
    float thr = map_n(x, P_gate_thr, x->val[P_gate_thr]), range = map_n(x, P_gate_range, x->val[P_gate_range]);
    if (in_db >= thr || range <= 0.f) return in_db;
    if (OPT(x, P_gate_mode) == 0) return in_db - range;
    return in_db - fminf(range, (thr - in_db) * (map_n(x, P_gate_ratio, x->val[P_gate_ratio]) - 1.f));
}

/* the compressor's static curve from the knob targets: threshold, ratio, knee and make-up as update_ctrl() works them
 * out (the GRANITE / FLANNEL auto make-up, HEARTS's manual one and its knee), full wet */
float xc_comp_curve_db(const XConsole *x, float in_db)
{
    float thr = map_n(x, P_cmp_thr, x->val[P_cmp_thr]), r = map_n(x, P_cmp_ratio, x->val[P_cmp_ratio]);
    float slope = special(x, P_cmp_ratio, x->val[P_cmp_ratio]) == SP_LIMIT ? 1.f : 1.f - 1.f / r;
    int hearts = model_sel(x, P_cmp_model) == MODEL_HEARTS, suede = model_sel(x, P_cmp_model) == MODEL_SUEDE;
    int sandstone = model_sel(x, P_cmp_model) == MODEL_SANDSTONE, hexx = model_sel(x, P_cmp_model) == MODEL_HEXX, molten = model_sel(x, P_cmp_model) == MODEL_MOLTEN;
    if (molten) slope = zl_slope(zl_mode(r));
    float knee = special(x, P_cmp_knee, x->val[P_cmp_knee]) == SP_AUTO ? (OPT(x, P_cmp_det) ? 0.f : (suede || molten) ? 6.f : sandstone ? 12.f : hexx ? 4.f : model_sel(x, P_cmp_model) == MODEL_MOCHA ? 2.f : 10.f) : map_n(x, P_cmp_knee, x->val[P_cmp_knee]);
    if (hearts) knee = map_n(x, P_cmp_knee, x->val[P_cmp_knee]) * 2.f * fabsf(thr);
    int mke = is_mke(model_sel(x, P_cmp_model));
    if (mke && special(x, P_cmp_knee, x->val[P_cmp_knee]) == SP_AUTO) knee = mke_knee(r, special(x, P_cmp_ratio, x->val[P_cmp_ratio]) == SP_LIMIT);
    float makeup = map_n(x, P_cmp_makeup, x->val[P_cmp_makeup]);
    int spades = model_sel(x, P_cmp_model) == MODEL_SPADES;
    int mocha = model_sel(x, P_cmp_model) == MODEL_MOCHA;
    if (!hearts && !suede && !sandstone && !hexx && !molten && !spades && !mocha && !mke) makeup += (pinfo(x, P_cmp_thr)->hi - thr) * slope;
    float o = in_db - thr, gt;
    if (2.f * o <= -knee) gt = 0.f;
    else if (2.f * fabsf(o) < knee) gt = slope * (o + knee * 0.5f) * (o + knee * 0.5f) / (2.f * knee);
    else gt = slope * o;
    if (gt < -24.f) gt = -24.f;
    return in_db - gt + makeup;
}

float xc_eq_curve_db(const XConsole *x, float hz)
{
    XConsole *t = (XConsole *)x;          /* coefficients from targets, without touching the running ones */
    float db = 0.f;
    for (int b = 0; b < 4; b++) {
        SvfC c;
        eq_coefs(t, &c, b, 0);
        db += svf_db(&c, hz, x->sr);
    }
    return db;
}

float xc_filter_curve_db(const XConsole *x, float hz)
{
    if (!OPT(x, P_flt_on) || OPT(x, P_flt_sc)) return 0.f;     /* from the targets, like the EQ curve */
    float db = 0.f;
    FiltC f;
    if (special(x, P_lc_freq, x->val[P_lc_freq]) != SP_OFF) {
        filt_set(&f, tanf(PI_F * fminf(map_n(x, P_lc_freq, x->val[P_lc_freq]), 0.45f * x->sr) / x->sr), OPT(x, P_lc_slope) + 1, 1, flt_q(x));
        db += filt_db(&f, hz, x->sr, 1);
    }
    if (special(x, P_hc_freq, x->val[P_hc_freq]) != SP_OFF) {
        filt_set(&f, tanf(PI_F * fminf(map_n(x, P_hc_freq, x->val[P_hc_freq]), 0.45f * x->sr) / x->sr), OPT(x, P_hc_slope) + 1, 0, flt_q(x));
        db += filt_db(&f, hz, x->sr, 0);
    }
    return db;
}

/* ---------------------------------------------------------------- life cycle */
void xc_reset(XConsole *x)
{
    memset(x->pre_up, 0, sizeof x->pre_up); memset(x->pre_dn, 0, sizeof x->pre_dn);
    memset(x->pre_lo, 0, sizeof x->pre_lo); memset(x->pre_hf, 0, sizeof x->pre_hf); memset(x->pre_dc, 0, sizeof x->pre_dc);
    memset(x->pre_bump, 0, sizeof x->pre_bump);
    memset(x->f_audio, 0, sizeof x->f_audio); memset(x->f_sc_sh, 0, sizeof x->f_sc_sh); memset(x->f_sc_cmp, 0, sizeof x->f_sc_cmp);
    memset(x->eq, 0, sizeof x->eq); memset(x->cmp_hp, 0, sizeof x->cmp_hp);
    memset(x->ds_lp, 0, sizeof x->ds_lp); x->ds_hf = x->ds_full = 0.f;
    memset(x->drv_up, 0, sizeof x->drv_up); memset(x->drv_dn, 0, sizeof x->drv_dn); memset(x->drv_dc, 0, sizeof x->drv_dc);
    memset(x->drv_up2, 0, sizeof x->drv_up2); memset(x->drv_dn2, 0, sizeof x->drv_dn2); memset(x->drv_x1, 0, sizeof x->drv_x1);
    memset(x->drv_F1, 0, sizeof x->drv_F1); memset(x->drv_key, 0, sizeof x->drv_key); memset(&x->drv_k, 0, sizeof x->drv_k);
    x->e_fa = x->e_sa = x->e_fr = x->e_sr = x->sh_db = 0.f;
    x->gate_pk = x->gate_hold_n = x->gate_gr = 0.f; x->gate_open = 0; x->gate_hold_left = 0;
    x->cmp_ms = x->cmp_gr = x->cmp_gr_f = x->cmp_gr_s = 0.f;
    memset(x->lim_d, 0, sizeof x->lim_d); memset(x->lim_d2, 0, sizeof x->lim_d2); x->lim_g = 1.f; x->lim_avg = 0.f;
    for (int k = 0; k < 4; k++) x->lev[k] = -120.f;
}

XConsole *xc_create(float sr)
{
    XConsole *x = calloc(1, sizeof *x);
    if (!x) return NULL;
    x->sr = sr;
    x->ctrl_a = 1.f - expf(-(float)CTRL / (0.020f * sr));
    x->fade_step = 1.f / (0.010f * sr);
    hb_design(x->hbc, HB_NC, HB_TBW);
    ptm_init();
    for (int i = 0; i < P_COUNT; i++) { x->val[i] = x->sm[i] = PT[i].def; x->act[i] = (int)(PT[i].def + 0.5f); }
    x->nz = noise_create(sr);                                            /* the NOISE page (0.18.0); NULL: no noise, the strip still runs */
    for (int k = 0; k < NOF(NZ); k++) nz_push(x, NZ[k].p);
    x->a_fast = onepole_a(0.0003f, sr); x->a_slow = onepole_a(0.012f, sr);
    x->r_fast = onepole_a(0.025f, sr); x->r_mid = onepole_a(0.060f, sr); x->r_long = onepole_a(0.400f, sr);
    x->a_sm = onepole_a(0.001f, sr);
    x->a_sm_dn = onepole_a(0.0001f, sr);
    x->gate_pk_rel = onepole_a(0.015f, sr);
    x->ds_a = onepole_a(0.0003f, sr); x->ds_r = onepole_a(0.040f / 3.f, sr);   /* TITANIUM EQ's DS: attack < 1 ms, release 0.04 s */
    x->cmp_ms_a = onepole_a(0.010f, sr);                                 /* choice: RMS window about 10 ms */
    x->lim_ceil = DB2LIN(-0.1f);                                         /* HEARTS limiter: choices in limiter() */
    x->lim_rel_a[0] = onepole_a(0.050f / 3.f, sr); x->lim_rel_a[1] = onepole_a(0.010f / 3.f, sr); x->lim_rel_a[2] = onepole_a(0.250f / 3.f, sr);
    x->lim_avg_a = onepole_a(0.100f, sr);
    x->lim_pre = 1.f;
    { float g = tanf(PI_F * 10.f / sr); x->drv_dc_G = g / (1.f + g); }
    x->pre_dc_G = x->drv_dc_G;
    x->dip = 1.f;
    x->pol = 1.f;
    update_ctrl(x);
#ifdef XC_ONLY_MODEL
    /* a single-preset plugin (user, 2026-11-08: "split the presets up into individual plugins"; -DXC_ONLY_MODEL=<model
     * number> in its vst.json cflags): every section starts on that strip with its defaults, as a CHANNEL STRIP pick */
    for (int s = SEC_INPUT; s < SEC_COUNT; s++) xc_apply_preset(x, s, XC_ONLY_MODEL);
    x->val[P_strip_sel] = (float)xc_strip_opt(XC_ONLY_MODEL);
#endif
    for (int i = 0; i < P_COUNT; i++) x->sm[i] = x->val[i];
    update_ctrl(x);
    x->g_in = x->g_in_t; x->g_out = x->g_out_t; x->pan_l = x->pan_l_t; x->pan_r = x->pan_r_t; x->width = x->width_t;
    x->w_pre = OPT(x, P_pre_on); x->w_sh = OPT(x, P_sh_on); x->w_eq = OPT(x, P_eq_on); x->w_cmp = OPT(x, P_cmp_on);
    x->w_drv = OPT(x, P_drv_on); x->w_byp = !OPT(x, P_bypass);
    xc_reset(x);
    return x;
}

void xc_destroy(XConsole *x)
{
    if (x) noise_destroy(x->nz);
    free(x);
}
