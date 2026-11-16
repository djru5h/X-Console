/* X-Console's MPC adapter: the wrapper's (vst2_wrap.c, engine.h) calls onto xconsole.c.
 * - Values travel as text: an option's index, or a continuous control's 0..1 position at full precision (MPC steps a
 *   Q-Link from the value it reads back, so rounding here would swallow clicks; see YES-SL 9000's NOTES).
 * - "<key>_display": the value as the knob's text. "state": every control as key=value; (project save and reload);
 *   a reload sets the presets without resetting their sections, then the saved values.
 * - "display_rev": polled every 100 ms. It moves when the meters or the EQ curve changed by a frame, or a preset pick moved
 *   knobs, and the wrapper then reports what moved (12 a block). Meters and curve columns are quantised to their
 *   filmstrip frames, so nothing is reported that wouldn't change the picture.
 * - Audio: float in and out (no clipping at 0 dBFS), denormals flushed while rendering. */
#define _GNU_SOURCE
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "engine.h"
#include "spectrum.h"
#include "xconsole.h"

#define SR 44100.f
#define BLK 128

#if defined(__aarch64__)
#define FP_ENTER() uint64_t fpcr_; __asm__ volatile("mrs %0, fpcr" : "=r"(fpcr_)); __asm__ volatile("msr fpcr, %0" : : "r"(fpcr_ | (1ULL << 24)))
#define FP_LEAVE() __asm__ volatile("msr fpcr, %0" : : "r"(fpcr_))
#elif defined(__arm__)
#define FP_ENTER() uint32_t fpscr_; __asm__ volatile("vmrs %0, fpscr" : "=r"(fpscr_)); __asm__ volatile("vmsr fpscr, %0" : : "r"(fpscr_ | (1u << 24)))
#define FP_LEAVE() __asm__ volatile("vmsr fpscr, %0" : : "r"(fpscr_))
#else
#define FP_ENTER() do { } while (0)
#define FP_LEAVE() do { } while (0)
#endif

/* The spectrum (EQ page): a reading is ready just before each display poll (the snapshot is taken SP_LEAD frames
 * ahead, the FFT then runs over the next blocks), so a hit shows at the first poll after it. A column is reported
 * only when it moves SP_MIN_STEP frames (MPC repaints about 300-350 reported values a second; see YES-SL 9000's
 * NOTES), and it falls back at SP_FALL dB a second. Only one instance analyses: the one whose controls were set last
 * (a touch, a Q-Link, a project load), else the newest; the others rest at the floor. */
#define SP_LEAD 768
#define SP_MIN_STEP 2
#define SP_FALL 30.f
#define SP_FLOOR -72.f
/* As YES-SL 9000's spectrum on the XL: each column is the 1-2-3-2-1 power mean of its neighbourhood (about 1/3 octave,
 * a lone tone reads ~4.8 dB low), and on Gen2 (the XL's skin, layout-gen2.conf) each column's frame also carries the
 * join to its right neighbour: frame = level x (2 SP_J + 1) + join + SP_J, so the steps read as one outline. */
#if defined(__aarch64__) || defined(XC_GEN2)
#define SP_J SPC_JOIN
#else
#define SP_J 0
#endif
#define SP_NF (SPC_FRAMES * (2 * SP_J + 1))
/* PEAK HOLD (pk_hold: Off, 1 s, 3 s, 6 s, Infinite): each IN/OUT LED bar and spectrum column keeps its highest frame as a
 * separate mark (m_pk_*, spk_*); after the hold time with nothing as high the mark drops to the live level and holds from
 * there. Infinite holds until the setting changes. Off: no marks (frame 0). */
static const float PK_HOLD_S[5] = {0.f, 1.f, 3.f, 6.f, -1.f};
/* the EQ curve likewise on Gen2: frame = level x (2 EQ_J + 1) + join + EQ_J, drawn sloped to the right neighbour */
#if defined(__aarch64__) || defined(XC_GEN2)
#define EQ_J EQC_JOIN
#else
#define EQ_J 0
#endif
#define EQ_NF (EQC_FRAMES * (2 * EQ_J + 1))
/* the transfer curves (0.8.2): on Gen2 a column's frame also carries the join to its right neighbour, the nearest of
 * TC_STEPS (dB): frame = level x TC_NJ + join; Gen1 shows the level alone */
static const int TC_STEP[TC_NJ] = {TC_STEPS_LIST};
static float tc_frame(int lv, int next, int levels)   /* levels: 61 (-60..0) or 61 + TC_TOP_G (HEARTS's compressor, 0.8.3) */
{
#if defined(__aarch64__) || defined(XC_GEN2)
    int d = next - lv, best = 0;
    for (int j = 1; j < TC_NJ; j++) if (abs(TC_STEP[j] - d) < abs(TC_STEP[best] - d)) best = j;
    return (float)(lv * TC_NJ + best) / (levels * TC_NJ - 1);
#else
    (void)next;
    return (float)lv / (levels - 1);
#endif
}

typedef struct {
    XConsole *x;
    Spectrum *sp;
    float shown[P_COUNT];        /* meters and curve columns as last handed to the wrapper (frame-quantised) */
    float sp_lvl[EQC_COLS];      /* the spectrum's held level per column, dBFS */
    int sp_lv[EQC_COLS];         /* the level each column shows (0..SPC_FRAMES-1) */
    float pk_led[4], pk_led_t[4];        /* PEAK HOLD: the held LED value (0..1, frame-quantised) and how long it has held, s */
    int pk_sp[EQC_COLS];                 /* the held spectrum level per column (0..SPC_FRAMES-1) */
    float pk_sp_t[EQC_COLS];
    int pk_mode;
    unsigned rev, seen_core_rev;
    int curve_dirty;
    int first_eqc, first_spc, first_spk, first_gtc, first_ctc;
    int since_poll, poll_period, snapped;
} inst_t;

static inst_t *volatile g_owner;

static int is_curve_key(const char *k)
{
    return !strncmp(k, "eq_", 3) || !strncmp(k, "lc_", 3) || !strncmp(k, "hc_", 3) || !strncmp(k, "flt_", 4);
}

static void *create(const char *data_dir)
{
    (void)data_dir;
    inst_t *e = calloc(1, sizeof *e);
    if (!e || !(e->x = xc_create(SR)) || !(e->sp = sp_create(SR, EQC_COLS, 20.f, 20000.f))) {
        if (e) { if (e->x) xc_destroy(e->x); free(e); }
        return NULL;
    }
    e->first_eqc = xc_param_index("eqc_00");
    e->first_spc = xc_param_index("spc_00");
    e->first_spk = xc_param_index("spk_00");
    e->first_gtc = xc_param_index("gtc_00");
    e->first_ctc = xc_param_index("ctc_00");
    for (int i = 0; i < EQC_COLS; i++) { e->shown[e->first_eqc + i] = 0.5f; e->sp_lvl[i] = SP_FLOOR; }
    e->curve_dirty = 1;
    g_owner = e;                                          /* the newest instance analyses until another is touched */
    return e;
}
static void destroy(void *inst)
{
    inst_t *e = inst;
    if (g_owner == e) g_owner = NULL;
    sp_destroy(e->sp);
    xc_destroy(e->x);
    free(e);
}
static void midi(void *inst, const uint8_t *msg, int len) { (void)inst; (void)msg; (void)len; }

/* ---------------------------------------------------------------- state */
static int save_state(inst_t *e, char *buf, int len)
{
    /* 3 (0.7.1): presets saved as model numbers, which don't move when a preset is added or renamed; 2 (0.5.11-0.7.0)
     * saved the drop-down place in the list of then; 1 model numbers */
    int n = snprintf(buf, len, "xconsole=3;");
    for (int i = 0; i < P_COUNT && n < len; i++) {
        if (xc_param_is_meter(i)) continue;
        if (i == P_strip_sel) { n += snprintf(buf + n, len - n, "strip_sel=%d;", xc_strip_model_at((int)xc_get(e->x, i))); continue; }   /* a model number */
        if (strstr(xc_param_key(i), "_unit")) continue;    /* the section lists follow the models (xc_sync_selectors) */
        if (xc_param_is_option(i) && strstr(xc_param_key(i), "_model"))
            n += snprintf(buf + n, len - n, "%s=%d;", xc_param_key(i), xc_opt_model(xc_model_section(i), (int)xc_get(e->x, i)));
        else if (xc_param_is_option(i)) n += snprintf(buf + n, len - n, "%s=%d;", xc_param_key(i), (int)xc_get(e->x, i));
        else n += snprintf(buf + n, len - n, "%s=%.6f;", xc_param_key(i), xc_get(e->x, i));
    }
    return n < len ? n : 0;
}

static void load_state(inst_t *e, const char *s)
{
    if (strncmp(s, "xconsole=", 9)) return;               /* not ours: keep what we have */
    int format = atoi(s + 9);
    float v[P_COUNT];
    int have[P_COUNT];
    memset(have, 0, sizeof have);
    const char *p = s;
    while (*p) {
        const char *eq = strchr(p, '='), *end = strchr(p, ';');
        if (!eq || !end || eq > end) break;
        char key[64];
        int kl = (int)(eq - p);
        if (kl > 0 && kl < (int)sizeof key) {
            memcpy(key, p, kl); key[kl] = 0;
            int i = xc_param_index(key);
            if (i >= 0 && !xc_param_is_meter(i) && !strstr(key, "_unit")) {
                v[i] = strtof(eq + 1, NULL); have[i] = 1;
                if (i == P_strip_sel) v[i] = (float)xc_strip_opt((int)(v[i] + 0.5f));   /* saved as a model number (0.17.0) */
                if (strstr(key, "_model")) {
                    int m = (int)(v[i] + 0.5f);
                    if (format == 2) {                               /* a place in 0.5.11-0.7.0's list: GRANITE, FLANNEL, HEARTS */
                        static const int OLD2[3] = {MODEL_GRANITE, MODEL_FLANNEL, MODEL_HEARTS};
                        m = OLD2[m < 0 ? 0 : m > 2 ? 2 : m];
                    }
                    v[i] = (float)xc_model_opt(xc_model_section(i), m);   /* formats 1 and 3: a model number (not in that list: the FLANNEL) */
                }
            }
        }
        p = end + 1;
    }
    xc_set_restoring(e->x, 1);
    for (int pass = 0; pass < 2; pass++)                    /* the presets first, then the knobs they'd otherwise reset */
        for (int i = 0; i < P_COUNT; i++) {
            if (!have[i]) continue;
            int is_model = strstr(xc_param_key(i), "_model") != NULL;
            if (is_model == (pass == 0)) xc_set(e->x, i, v[i]);
        }
    xc_set_restoring(e->x, 0);
    xc_sync_selectors(e->x, have[P_strip_sel]);
    e->curve_dirty = 1;
    e->rev++;
}

/* ---------------------------------------------------------------- display_rev: meters and the curve */
static float quant(float v, int frames) { return roundf(fminf(fmaxf(v, 0.f), 1.f) * (frames - 1)) / (frames - 1); }

static void refresh(inst_t *e)
{
    int moved = 0;
    static const int LED[4] = {P_m_in_l, P_m_in_r, P_m_out_l, P_m_out_r};
    for (int k = 0; k < 4; k++) {
        float q = quant(xc_get(e->x, LED[k]), LED_FRAMES);
        if (q != e->shown[LED[k]]) { e->shown[LED[k]] = q; moved = 1; }
    }
    /* PEAK HOLD */
    float pdt = (e->poll_period > 0 ? e->poll_period : 4410) / SR;
    int pm = (int)xc_get(e->x, P_pk_hold);
    if (pm < 0 || pm > 4) pm = 0;
    if (pm != e->pk_mode) {                               /* a new setting starts afresh */
        e->pk_mode = pm;
        for (int k = 0; k < 4; k++) e->pk_led[k] = 0.f, e->pk_led_t[k] = 0.f;
        for (int i = 0; i < EQC_COLS; i++) e->pk_sp[i] = 0, e->pk_sp_t[i] = 0.f;
    }
    float hold = PK_HOLD_S[pm];
    float qs = quant(xc_get(e->x, P_m_shape), SHP_FRAMES);            /* the SHAPE gain meter (0.8.0) */
    if (qs != e->shown[P_m_shape]) { e->shown[P_m_shape] = qs; moved = 1; }
    {                                                                    /* the transfer curves: output -60..0 over input -60..0 */
        int gl[TC_COLS + 1], cl[TC_COLS + 1];                             /* levels (TC_FRAMES over 60 dB), one past the last column */
        float lpd = (TC_FRAMES - 1) / 60.f;                               /* levels per dB (0.25 dB frames, 2026-11-08) */
        int clev = xc_opt_model(SEC_COMP, (int)(xc_get(e->x, P_cmp_model) + 0.5f)) == MODEL_HEARTS ? TC_FRAMES + (int)lroundf(TC_TOP_G * lpd) : TC_FRAMES;
        for (int i = 0; i <= TC_COLS; i++) {
            float in = -60.f + 60.f * (i + (i < TC_COLS ? 0.5f : 0.f)) / TC_COLS;
            if (i == TC_COLS) in = 0.f;
            int a = (int)lroundf((xc_gate_curve_db(e->x, in) + 60.f) * lpd), b = (int)lroundf((xc_comp_curve_db(e->x, in) + 60.f) * lpd);
            gl[i] = a < 0 ? 0 : a > TC_FRAMES - 1 ? TC_FRAMES - 1 : a;
            cl[i] = b < 0 ? 0 : b > clev - 1 ? clev - 1 : b;
        }
        for (int i = 0; i < TC_COLS; i++) {
            float g = tc_frame(gl[i], gl[i + 1], TC_FRAMES), c = tc_frame(cl[i], cl[i + 1], clev);
            if (g != e->shown[e->first_gtc + i]) { e->shown[e->first_gtc + i] = g; moved = 1; }
            if (c != e->shown[e->first_ctc + i]) { e->shown[e->first_ctc + i] = c; moved = 1; }
        }
    }
    static const int PK[4] = {P_m_pk_in_l, P_m_pk_in_r, P_m_pk_out_l, P_m_pk_out_r};
    for (int k = 0; k < 4; k++) {
        float live = e->shown[LED[k]];
        if (pm == 0) e->pk_led[k] = 0.f;
        else if (live >= e->pk_led[k]) e->pk_led[k] = live, e->pk_led_t[k] = 0.f;
        else if ((e->pk_led_t[k] += pdt) >= hold && hold > 0.f) e->pk_led[k] = live, e->pk_led_t[k] = 0.f;
        if (e->pk_led[k] != e->shown[PK[k]]) { e->shown[PK[k]] = e->pk_led[k]; moved = 1; }
    }
    float q = quant(xc_get(e->x, P_m_gr), VU_FRAMES);
    if (q != e->shown[P_m_gr]) { e->shown[P_m_gr] = q; moved = 1; }
    q = quant(xc_get(e->x, P_m_gate), GR_FRAMES);
    if (q != e->shown[P_m_gate]) { e->shown[P_m_gate] = q; moved = 1; }

    unsigned cr = xc_display_rev(e->x);
    if (cr != e->seen_core_rev) { e->seen_core_rev = cr; e->curve_dirty = 1; moved = 1; }   /* a preset pick moved knobs */
    if (e->curve_dirty) {
        e->curve_dirty = 0;
        int eq_on = (int)xc_get(e->x, P_eq_on), lv[EQC_COLS];
        for (int i = 0; i < EQC_COLS; i++) {
            float hz = 20.f * powf(1000.f, (i + 0.5f) / EQC_COLS);
            float db = (eq_on ? xc_eq_curve_db(e->x, hz) : 0.f) + xc_filter_curve_db(e->x, hz);
            int half = (EQC_FRAMES - 1) / 2;
            lv[i] = (int)lroundf(fminf(fmaxf(db, -half), half)) + half;
        }
        for (int i = 0; i < EQC_COLS; i++) {
            int j = 0;
            if (EQ_J > 0 && i + 1 < EQC_COLS) {
                j = lv[i + 1] - lv[i];
                if (j > EQ_J) j = EQ_J;
                if (j < -EQ_J) j = -EQ_J;
            }
            float c = (float)(lv[i] * (2 * EQ_J + 1) + j + EQ_J) / (EQ_NF - 1);
            if (c != e->shown[e->first_eqc + i]) { e->shown[e->first_eqc + i] = c; moved = 1; }
        }
    }
    /* the spectrum */
    int sp_new = 0;
    if (g_owner == e && sp_ready(e->sp)) {
        float meas[EQC_COLS], pw[EQC_COLS], dt = (e->poll_period > 0 ? e->poll_period : 4410) / SR;
        sp_read(e->sp, meas);
        for (int i = 0; i < EQC_COLS; i++) pw[i] = powf(10.f, 0.1f * meas[i]);
        for (int i = 0; i < EQC_COLS; i++) {
            static const float W[5] = {1, 2, 3, 2, 1};
            float s = 0.f, ws = 0.f;
            for (int j = -2; j <= 2; j++)
                if (i + j >= 0 && i + j < EQC_COLS) { s += W[j + 2] * pw[i + j]; ws += W[j + 2]; }
            float db = 10.f * log10f(s / ws + 1e-12f);
            float fallen = e->sp_lvl[i] - SP_FALL * dt;
            e->sp_lvl[i] = fmaxf(db, fmaxf(fallen, SP_FLOOR));
            int k = (int)lroundf((e->sp_lvl[i] - SP_FLOOR) / (-SP_FLOOR) * (SPC_FRAMES - 1));
            if (k < 0) k = 0;
            if (k > SPC_FRAMES - 1) k = SPC_FRAMES - 1;
            if (abs(k - e->sp_lv[i]) >= SP_MIN_STEP || (k == 0 && e->sp_lv[i] != 0)) e->sp_lv[i] = k;
        }
        sp_new = 1;
    } else if (g_owner != e) {
        for (int i = 0; i < EQC_COLS; i++) { e->sp_lv[i] = 0; e->sp_lvl[i] = SP_FLOOR; }
        sp_new = 1;
    }
    if (sp_new)                                           /* the frames, joins included: a column also moves when its neighbour does */
        for (int i = 0; i < EQC_COLS; i++) {
            int j = 0;
            if (SP_J > 0 && i + 1 < EQC_COLS) {
                j = e->sp_lv[i + 1] - e->sp_lv[i];
                if (j > SP_J) j = SP_J;
                if (j < -SP_J) j = -SP_J;
            }
            float v = (float)(e->sp_lv[i] * (2 * SP_J + 1) + j + SP_J) / (SP_NF - 1);
            if (e->sp_lv[i] == 0 && j <= 0) v = 0.f;                /* the floor: frame 0 (the same picture), as at start */
            if (v != e->shown[e->first_spc + i]) { e->shown[e->first_spc + i] = v; moved = 1; }
        }
    for (int i = 0; i < EQC_COLS; i++) {                  /* PEAK HOLD on the spectrum, from the levels as shown */
        int live = e->sp_lv[i];
        if (pm == 0 || g_owner != e) e->pk_sp[i] = 0, e->pk_sp_t[i] = 0.f;
        else if (live >= e->pk_sp[i]) e->pk_sp[i] = live, e->pk_sp_t[i] = 0.f;
        else if ((e->pk_sp_t[i] += pdt) >= hold && hold > 0.f) e->pk_sp[i] = live, e->pk_sp_t[i] = 0.f;
        float v = (float)e->pk_sp[i] / (SPC_FRAMES - 1);
        if (v != e->shown[e->first_spk + i]) { e->shown[e->first_spk + i] = v; moved = 1; }
    }
    if (moved) e->rev++;
}

/* ---------------------------------------------------------------- the wrapper's calls */
static void set_param(void *inst, const char *key, const char *val)
{
    inst_t *e = inst;
    g_owner = e;                                          /* the one being worked on: its spectrum runs */
    if (!strcmp(key, "state")) { load_state(e, val); return; }
    int i = xc_param_index(key);
    if (i < 0 || xc_param_is_meter(i)) return;
    xc_set(e->x, i, xc_param_is_option(i) ? (float)atoi(val) : strtof(val, NULL));
    if (is_curve_key(key)) e->curve_dirty = 1;
}

static int get_param(void *inst, const char *key, char *buf, int len)
{
    inst_t *e = inst;
    if (len <= 0) return 0;
    if (!strcmp(key, "state")) return save_state(e, buf, len);
    if (!strcmp(key, "display_rev")) {
        if (e->since_poll > 1000 && e->since_poll < 20000) e->poll_period = e->since_poll;   /* learn the wrapper's poll rate */
        e->since_poll = 0;
        e->snapped = 0;
        refresh(e);
        return snprintf(buf, len, "%u", e->rev);
    }
    size_t kl = strlen(key);
    if (kl > 8 && !strcmp(key + kl - 8, "_display")) {
        char base[64];
        if (kl - 8 >= sizeof base) return 0;
        memcpy(base, key, kl - 8); base[kl - 8] = 0;
        int i = xc_param_index(base);
        if (i < 0 || xc_param_is_option(i) || xc_param_is_meter(i)) return 0;
        xc_display(e->x, i, buf, len);
        return (int)strlen(buf);
    }
    if (kl > 5 && !strcmp(key + kl - 5, "_name")) {                     /* dynamic names: SHAPE's knobs under TITANIUM EQ's DS */
        char base[64];
        if (kl - 5 >= sizeof base) return 0;
        memcpy(base, key, kl - 5); base[kl - 5] = 0;
        const char *nm = xc_param_alt_name(e->x, xc_param_index(base));
        return nm ? snprintf(buf, len, "%s", nm) : 0;
    }
    int i = xc_param_index(key);
    if (i < 0) return 0;
    if (xc_param_is_meter(i)) return snprintf(buf, len, "%.6f", e->shown[i]);
    if (xc_param_is_option(i)) return snprintf(buf, len, "%d", (int)xc_get(e->x, i));
    return snprintf(buf, len, "%.6f", xc_get(e->x, i));
}

void mpc_engine_process_f(void *inst, const float *in_lr, float *out_lr, int frames)
{
    inst_t *e = inst;
    float il[BLK], ir[BLK], ol[BLK], orr[BLK];
    FP_ENTER();
    for (int done = 0; done < frames; done += BLK) {
        int n = frames - done < BLK ? frames - done : BLK;
        const float *in = in_lr + 2 * done;
        for (int i = 0; i < n; i++) { il[i] = in[2 * i]; ir[i] = in[2 * i + 1]; }
        xc_process(e->x, il, ir, ol, orr, n);
        if (g_owner == e) {
            sp_feed(e->sp, ol, orr, n);
            e->since_poll += n;
            int period = e->poll_period > 0 ? e->poll_period : 4410;   /* no polls yet (a test host): every 0.1 s */
            if (!e->snapped && e->since_poll >= period - SP_LEAD) {
                if (sp_start(e->sp)) e->snapped = 1;
                if (e->poll_period <= 0 && e->since_poll >= period) e->since_poll = 0, e->snapped = 0;
            }
        }
        float *out = out_lr + 2 * done;
        for (int i = 0; i < n; i++) { out[2 * i] = ol[i]; out[2 * i + 1] = orr[i]; }
    }
    FP_LEAVE();
}

/* int16 path, only for a wrapper without the float one */
static void process(void *inst, const int16_t *in_lr, int16_t *out_lr, int frames)
{
    float fi[2 * BLK], fo[2 * BLK];
    for (int done = 0; done < frames; done += BLK) {
        int n = frames - done < BLK ? frames - done : BLK;
        for (int i = 0; i < 2 * n; i++) fi[i] = in_lr[2 * done + i] * (1.f / 32768.f);
        mpc_engine_process_f(inst, fi, fo, n);
        for (int i = 0; i < 2 * n; i++) {
            float v = fo[i] * 32768.f;
            out_lr[2 * done + i] = v >= 32767.f ? 32767 : v <= -32768.f ? -32768 : (int16_t)lrintf(v);
        }
    }
}

static const mpc_engine_t hexx = { create, destroy, midi, set_param, get_param, NULL, process, NULL };
const mpc_engine_t *mpc_engine(void) { return &hexx; }
