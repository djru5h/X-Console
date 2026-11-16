/* X-Console through the real VST2 wrapper, the way MPC drives it: parameters by index, float blocks of 128, chunks,
 * the 100 ms display poll and its reports (audioMasterAutomate). Checks what only the whole plugin can show: audio
 * passes, meters and the EQ curve reach the host (and stay quiet when nothing moves), Q-Link read-back is exact, the
 * knob texts arrive whole, a saved project comes back. See harness/wraptest.sh. */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "params.h"

typedef struct AEffect AEffect;
typedef intptr_t (*cb)(AEffect *, int32_t, int32_t, intptr_t, void *, float);
struct AEffect { int32_t magic; intptr_t (*d)(AEffect *, int32_t, int32_t, intptr_t, void *, float);
    void *p; void (*setP)(AEffect *, int32_t, float); float (*getP)(AEffect *, int32_t);
    int32_t np, npar, ni, no, flags; intptr_t r1, r2; int32_t a, b, c; float io; void *obj, *user; int32_t uid, ver;
    void (*pr)(AEffect *, float **, float **, int32_t); void *pdr; char f[56]; };
extern AEffect *VSTPluginMain(cb);

static int automated[NPARAMS], updates, fails, checks;

/* a spectrum column's value -> dBFS: frame = level x (2J+1) + join + J (J = 3 in the Gen2 build, 0 in Gen1), levels 2 dB from -72 */
#ifdef XC_GEN2
#define WJ 3
#else
#define WJ 0
#endif
#ifdef XC_GEN2
#define WJE 8
#else
#define WJE 0
#endif
static float eq_db(float v) { int f = (int)lroundf(v * (37 * (2 * WJE + 1) - 1)); return (f / (2 * WJE + 1)) - 18.f; }   /* a curve column -> dB */
static float sp_db(float v) { int f = (int)lroundf(v * (37 * (2 * WJ + 1) - 1)); return (f / (2 * WJ + 1)) * 2.f - 72.f; }
static float reported[NPARAMS];

static intptr_t host(AEffect *e, int32_t op, int32_t i, intptr_t v, void *p, float o)
{
    (void)e; (void)v; (void)p;
    if (op == 0 && i >= 0 && i < NPARAMS) { automated[i]++; reported[i] = o; }
    if (op == 42) updates++;
    return 0;
}

#define CHECK(c, ...) do { checks++; printf("%-4s ", (c) ? "ok" : "FAIL"); printf(__VA_ARGS__); printf("\n"); if (!(c)) fails++; } while (0)

static int idx(const char *key)
{
    for (int i = 0; i < NPARAMS; i++) if (!strcmp(PARAMS[i].key, key)) return i;
    printf("no parameter %s\n", key);
    exit(2);
}
static void clear(void) { memset(automated, 0, sizeof automated); updates = 0; }
static int reports(const char *prefix)
{
    int n = 0;
    for (int i = 0; i < NPARAMS; i++) if (!strncmp(PARAMS[i].key, prefix, strlen(prefix))) n += automated[i];
    return n;
}

static double phase;
static float peak_out, worst_diff;
/* seconds of a sine (amp 0 = silence) through the plugin, 128 frames at a time */
static void run(AEffect *a, double seconds, float amp, float hz)
{
    float il[128], ir[128], ol[128], orr[128], *in[2] = {il, ir}, *out[2] = {ol, orr};
    peak_out = 0; worst_diff = 0;
    for (long left = (long)(seconds * 44100.0); left > 0; left -= 128) {
        for (int i = 0; i < 128; i++) { il[i] = ir[i] = amp * (float)sin(phase); phase += 2 * M_PI * hz / 44100.0; }
        a->pr(a, in, out, 128);
        for (int i = 0; i < 128; i++) {
            peak_out = fmaxf(peak_out, fabsf(ol[i]));
            worst_diff = fmaxf(worst_diff, fmaxf(fabsf(ol[i] - il[i]), fabsf(orr[i] - ir[i])));
        }
    }
}
static void text(AEffect *a, const char *key, char *buf) { buf[0] = 0; a->d(a, 7, idx(key), 0, buf, 0); }   /* effGetParamDisplay */

int main(void)
{
    AEffect *a = VSTPluginMain(host);
    CHECK(a && a->magic == 0x56737450, "plugin loads (%d parameters, %d in / %d out)", a ? a->npar : 0, a ? a->ni : 0, a ? a->no : 0);
    a->d(a, 12, 0, 1, 0, 0);   /* effMainsChanged on */

    clear();
    run(a, 0.5, 0.25f, 997);
    CHECK(worst_diff < 1e-6f, "defaults: audio passes untouched through the wrapper (worst difference %.2g)", worst_diff);

    /* meters: a -12 dBFS tone shows about -12 on IN and OUT, reported to the host (counted from the first block) */
    run(a, 0.6, 0.25f, 997);
    float want = roundf((-12.04f + 60.f) / 66.f * 30.f) / 30.f;
    CHECK(automated[idx("m_in_l")] > 0 && fabsf(reported[idx("m_in_l")] - want) < 0.04f && fabsf(reported[idx("m_out_r")] - want) < 0.04f,
          "IN/OUT meters reported at %.3f / %.3f (-12 dBFS is %.3f)", reported[idx("m_in_l")], reported[idx("m_out_r")], want);
    int steady = reports("m_");
    clear();
    run(a, 1.0, 0.25f, 997);
    CHECK(reports("m_") == 0 && reports("eqc_") == 0, "a steady tone: no meter or curve reports once settled (%d then %d)", steady, reports("m_"));
    CHECK(updates == 0, "and no screen rebuilds (UpdateDisplay %d)", updates);

    /* spectrum: the 1 kHz tone at -12 dBFS lights its column at about -12, and a low column stays near the floor */
    {
        int c1k = (int)floorf(44.f * logf(1000.f / 20.f) / logf(1000.f)), c100 = (int)floorf(44.f * logf(100.f / 20.f) / logf(1000.f));
        char k1[16], k2[16];
        snprintf(k1, sizeof k1, "spc_%02d", c1k); snprintf(k2, sizeof k2, "spc_%02d", c100);
        float v1 = sp_db(a->getP(a, idx(k1))), v2 = sp_db(a->getP(a, idx(k2)));
        CHECK(fabsf(v1 + 16.8f) <= 4.5f && v2 < -50.f, "spectrum (%s): %s (1 kHz) reads %.0f dBFS for a -12 dBFS tone (smoothing: ~-16.8), %s (100 Hz) %.0f",
              WJ ? "joined" : "plain", k1, v1, k2, v2);
    }
    /* a drum-like signal: noise hits 4 a second over a bass tone. MPC repaints about 300-350 reported values a second */
    {
        clear();
        float il[128], ir[128], ol[128], orr[128], *in[2] = {il, ir}, *out[2] = {ol, orr};
        unsigned rs = 7;
        long frames = 0;
        for (int b = 0; b < (int)(5.0 * 44100 / 128); b++) {
            for (int i = 0; i < 128; i++, frames++) {
                double t = (frames % 11025) / 44100.0;
                rs = rs * 1664525u + 1013904223u;
                float hit = (float)(0.6 * exp(-t * 25) * ((int)rs * (1.0 / 2147483648.0)));
                il[i] = ir[i] = hit + 0.2f * (float)sin(2 * M_PI * 55 * frames / 44100.0);
            }
            a->pr(a, in, out, 128);
        }
        double per_s = (reports("spc_") + reports("m_")) / 5.0;
        CHECK(per_s < (WJ ? 350 : 250), "drum-like signal: %.0f spectrum + meter reports a second (MPC budget ~300-350; joined columns also move with their neighbour)", per_s);
    }
    /* PEAK HOLD (Off, 1 s, 3 s, 6 s, Infinite): held marks on IN/OUT and the spectrum, separate from the live meters */
    {
        int c1k = (int)floorf(44.f * logf(1000.f / 20.f) / logf(1000.f));
        char sk[16], pk[16];
        snprintf(sk, sizeof sk, "spc_%02d", c1k); snprintf(pk, sizeof pk, "spk_%02d", c1k);
        int marks = 0;
        for (int i = 0; i < NPARAMS; i++)
            if ((!strncmp(PARAMS[i].key, "m_pk_", 5) || !strncmp(PARAMS[i].key, "spk_", 4)) && a->getP(a, i) > 0.f) marks++;
        CHECK(marks == 0, "peak hold Off (the default): no marks after all that signal (%d)", marks);

        run(a, 2.0, 0.f, 0);                                    /* the meters back at rest first */
        a->setP(a, idx("pk_hold"), 1.f / 4.f);                  /* 1 s */
        run(a, 0.5, 0.25f, 997);
        float live_in = a->getP(a, idx("m_in_l")), held_in = a->getP(a, idx("m_pk_in_l")), held_sp = a->getP(a, idx(pk));
        CHECK(held_in == live_in && held_in > 0.5f && held_sp > 0.4f, "peak hold 1 s: a -12 dBFS tone marks IN at %.3f (live %.3f), the 1 kHz column at %.2f",
              held_in, live_in, held_sp);
        run(a, 0.6, 0.f, 0);
        CHECK(a->getP(a, idx("m_pk_in_l")) == held_in && a->getP(a, idx("m_in_l")) < held_in && a->getP(a, idx(pk)) == held_sp
              && sp_db(a->getP(a, idx(sk))) < held_sp * 72.f - 72.f,
              "  0.6 s of silence: the marks hold (IN %.3f, live %.3f; column %.2f, live %.0f dBFS)", a->getP(a, idx("m_pk_in_l")), a->getP(a, idx("m_in_l")),
              a->getP(a, idx(pk)), sp_db(a->getP(a, idx(sk))));
        run(a, 1.0, 0.f, 0);
        CHECK(a->getP(a, idx("m_pk_in_l")) < held_in && a->getP(a, idx(pk)) < held_sp,
              "  1.6 s of silence: they have dropped (IN %.3f, column %.2f)", a->getP(a, idx("m_pk_in_l")), a->getP(a, idx(pk)));

        a->setP(a, idx("pk_hold"), 1.f);                        /* Infinite */
        run(a, 0.5, 0.25f, 997);
        held_in = a->getP(a, idx("m_pk_in_l")); held_sp = a->getP(a, idx(pk));
        run(a, 8.0, 0.f, 0);
        CHECK(held_in > 0.5f && a->getP(a, idx("m_pk_in_l")) == held_in && a->getP(a, idx(pk)) == held_sp && a->getP(a, idx("m_in_l")) < held_in,
              "peak hold Infinite: the marks are still there after 8 s of silence (IN %.3f, column %.2f)", a->getP(a, idx("m_pk_in_l")), a->getP(a, idx(pk)));

        a->setP(a, idx("pk_hold"), 3.f / 4.f);                  /* 6 s: a new setting starts afresh */
        run(a, 0.2, 0.f, 0);
        CHECK(a->getP(a, idx("m_pk_in_l")) == a->getP(a, idx("m_in_l")) && a->getP(a, idx(pk)) == 0.f,
              "  picking 6 s clears them (IN %.3f, column %.2f)", a->getP(a, idx("m_pk_in_l")), a->getP(a, idx(pk)));

        /* the report budget with marks on: the drum-like signal again */
        clear();
        float il[128], ir[128], ol[128], orr[128], *in[2] = {il, ir}, *out[2] = {ol, orr};
        unsigned rs = 7;
        long frames = 0;
        for (int b = 0; b < (int)(5.0 * 44100 / 128); b++) {
            for (int i = 0; i < 128; i++, frames++) {
                double t = (frames % 11025) / 44100.0;
                rs = rs * 1664525u + 1013904223u;
                float hit = (float)(0.6 * exp(-t * 25) * ((int)rs * (1.0 / 2147483648.0)));
                il[i] = ir[i] = hit + 0.2f * (float)sin(2 * M_PI * 55 * frames / 44100.0);
            }
            a->pr(a, in, out, 128);
        }
        double per_s = (reports("spc_") + reports("spk_") + reports("m_")) / 5.0;
        CHECK(per_s < (WJ ? 350 : 250), "  drum-like signal with peak hold 6 s: %.0f reports a second (marks %.0f)", per_s, (reports("spk_") + reports("m_pk_")) / 5.0);

        a->setP(a, idx("pk_hold"), 0.f);                        /* Off again */
        run(a, 0.2, 0.f, 0);
        marks = 0;
        for (int i = 0; i < NPARAMS; i++)
            if ((!strncmp(PARAMS[i].key, "m_pk_", 5) || !strncmp(PARAMS[i].key, "spk_", 4)) && a->getP(a, i) > 0.f) marks++;
        CHECK(marks == 0, "  Off again: every mark gone (%d)", marks);
    }
    /* EQ curve: LMF +12 dB at 1 kHz shows in the column at 1 kHz */
    clear();
    a->setP(a, idx("eq_on"), 1.f);
    a->setP(a, idx("eq_lmf_gain"), (12.f + 20.f) / 40.f);
    a->setP(a, idx("eq_lmf_freq"), logf(1000.f / 200.f) / logf(2500.f / 200.f));
    run(a, 0.5, 0.f, 0);
    int col = (int)floorf(44.f * logf(1000.f / 20.f) / logf(1000.f));
    char ck[16]; snprintf(ck, sizeof ck, "eqc_%02d", col);
    float v = a->getP(a, idx(ck));
    CHECK(automated[idx(ck)] > 0 && fabsf(eq_db(v) - 12.f) <= 1.0f, "EQ curve column %s (near 1 kHz) reads %+.0f dB after LMF +12 dB at 1 kHz; %d columns reported",
          ck, eq_db(v), reports("eqc_"));
    CHECK(reports("eqc_") <= 44, "  each column reported at most once (%d)", reports("eqc_"));
    clear();
    run(a, 1.0, 0.f, 0);
    CHECK(reports("eqc_") == 0, "  and the curve is quiet once the knob stops (%d)", reports("eqc_"));
    /* the low cut shows in the curve too */
    a->setP(a, idx("lc_freq"), logf(200.f / 20.f) / logf(500.f / 20.f));
    run(a, 0.3, 0.f, 0);
    float c0 = eq_db(a->getP(a, idx("eqc_00")));
    CHECK(c0 <= -17.f, "low cut 200 Hz pulls the first column (23 Hz) to the floor (%+.0f dB)", c0);

    /* Q-Link read-back: exactly what was set (MPC steps from the read-back) */
    float worst = 0;
    for (int k = 1; k < 128; k++) {
        float n = k / 128.f;
        a->setP(a, idx("cmp_thr"), n);
        worst = fmaxf(worst, fabsf(a->getP(a, idx("cmp_thr")) - n));
    }
    CHECK(worst < 1e-5f, "Q-Link read-back is exact over 127 clicks (worst %.2g)", worst);

    /* knob texts arrive whole */
    char t1[64], t2[64], t3[64], t4[64], t5[64];
    a->setP(a, idx("cmp_att"), 0.f); text(a, "cmp_att", t1);
    text(a, "lc_freq", t2);
    a->setP(a, idx("cmp_ratio"), 1.f); text(a, "cmp_ratio", t3);
    a->setP(a, idx("drv_char"), 0.25f); text(a, "drv_char", t4);
    text(a, "eq_lmf_gain", t5);
    CHECK(!strcmp(t1, "AUTO") && !strcmp(t2, "200 Hz") && !strcmp(t3, "Limit") && !strcmp(t4, "2nd 75 / 3rd 25") && !strcmp(t5, "+12.0 dB"),
          "texts: attack \"%s\", low cut \"%s\", ratio \"%s\", character \"%s\", LMF \"%s\"", t1, t2, t3, t4, t5);

    /* gain reduction reaches the VU */
    a->setP(a, idx("cmp_on"), 1.f);
    a->setP(a, idx("cmp_ratio"), 0.7f);
    a->setP(a, idx("cmp_thr"), 0.f);
    clear();
    run(a, 1.0, 0.5f, 997);
    CHECK(automated[idx("m_gr")] > 0 && reported[idx("m_gr")] > 0.3f, "compressor working: the VU's needle reported at %.2f (of 20 dB)", reported[idx("m_gr")]);

    /* project save and reload: a second instance gets every control back */
    void *chunk = NULL;
    intptr_t len = a->d(a, 23, 0, 0, &chunk, 0);
    char saved[8192];
    memcpy(saved, chunk, len);
    AEffect *b = VSTPluginMain(host);
    b->d(b, 12, 0, 1, 0, 0);
    b->d(b, 24, 0, len, saved, 0);
    int differ = 0;
    for (int i = 0; i < NPARAMS && i < AUTOMATABLE_PARAMS; i++)
        if (fabsf(a->getP(a, i) - b->getP(b, i)) > 1e-5f) { differ++; printf("     differs: %s %.5f vs %.5f\n", PARAMS[i].key, a->getP(a, i), b->getP(b, i)); }
    CHECK(len > 100 && differ == 0, "chunk of %ld bytes restores all %d controls on a new instance", (long)len, AUTOMATABLE_PARAMS);

    /* one spectrum at a time: b was set last (its project load), so a's columns go to rest */
    run(a, 0.3, 0.25f, 997);
    int lit = 0;
    for (int i = 0; i < 44; i++) { char k[16]; snprintf(k, sizeof k, "spc_%02d", i); if (a->getP(a, idx(k)) > 0.f) lit++; }
    CHECK(lit == 0, "with a second instance worked on last, the first one's spectrum rests (%d columns lit)", lit);

    /* a pick from the preset drop-down when it's already the preset: nothing moves */
    float before = a->getP(a, idx("eq_lmf_gain"));
    a->setP(a, idx("eq_model"), 8.f / 10.f);   /* the FLANNEL: ninth of eleven (MOCHA, HEXX, SPADES, MOLTEN, HEARTS, TITANIUM EQ, SUEDE, GRANITE, FLANNEL, SANDSTONE, TITANIUM) */
    run(a, 0.3, 0.f, 0);
    CHECK(a->getP(a, idx("eq_lmf_gain")) == before, "re-picking the current EQ preset leaves the knobs as they are");

    /* a project saved before 0.5.11 (format 1: model numbers, 0 = FLANNEL, 1 = GRANITE) opens with the same presets */
    char old1[] = "xconsole=1;in_model=0;eq_model=1;cmp_model=1;";
    b->d(b, 24, 0, (intptr_t)sizeof old1, old1, 0);   /* with its NUL, as the plugin saves it */
    CHECK(fabsf(b->getP(b, idx("in_model")) - 7.f / 9.f) < 1e-4f && fabsf(b->getP(b, idx("eq_model")) - 7.f / 10.f) < 1e-4f && fabsf(b->getP(b, idx("cmp_model")) - 7.f / 10.f) < 1e-4f,
          "an old project's presets survive the alphabetical order (FLANNEL -> %.2f, GRANITE -> %.2f / %.2f of the host's 0..1)", b->getP(b, idx("in_model")), b->getP(b, idx("eq_model")), b->getP(b, idx("cmp_model")));
    /* a project saved by 0.5.11-0.7.0 (format 2: places in that list, GRANITE, FLANNEL, HEARTS) */
    char old2[] = "xconsole=2;in_model=1;sh_model=0;eq_model=2;cmp_model=1;";
    b->d(b, 24, 0, (intptr_t)sizeof old2, old2, 0);
    CHECK(fabsf(b->getP(b, idx("in_model")) - 7.f / 9.f) < 1e-4f && fabsf(b->getP(b, idx("sh_model")) - 7.f / 10.f) < 1e-4f && fabsf(b->getP(b, idx("eq_model")) - 4.f / 10.f) < 1e-4f && fabsf(b->getP(b, idx("cmp_model")) - 8.f / 10.f) < 1e-4f,
          "a 0.5.11-0.7.0 project opens on the same presets: FLANNEL %.2f, GRANITE %.2f, (HEARTS) HEARTS %.2f, FLANNEL %.2f of the host's 0..1",
          b->getP(b, idx("in_model")), b->getP(b, idx("sh_model")), b->getP(b, idx("eq_model")), b->getP(b, idx("cmp_model")));
    /* and this version's save (format 3, model numbers) comes back the same */
    {
        void *chunk = 0;
        long n3 = (long)b->d(b, 23, 0, 0, &chunk, 0);   /* effGetChunk */
        int f3 = chunk && n3 > 11 && !strncmp((char *)chunk, "xconsole=3;", 11);
        char *copy = malloc(n3 + 1);
        memcpy(copy, chunk, n3); copy[n3] = 0;
        a->d(a, 24, 0, (intptr_t)n3, copy, 0);
        CHECK(f3 && fabsf(a->getP(a, idx("eq_model")) - 4.f / 10.f) < 1e-4f && fabsf(a->getP(a, idx("in_model")) - 7.f / 9.f) < 1e-4f && fabsf(a->getP(a, idx("sh_model")) - 7.f / 10.f) < 1e-4f,
              "format 3 saves model numbers and reopens on the same presets (%.11s)", f3 ? (char *)chunk : "?");
        free(copy);
    }
    /* 0.17.0: a 0.16 save (no strip_sel) opens with PREAMP's strip as the CHANNEL STRIP and the units in their lists;
     * a new save keeps strip_sel as a model number */
    {
        char old3[] = "xconsole=3;in_model=5;sh_model=5;eq_model=10;cmp_model=11;";   /* HEXX, HEXX, TITANIUM EQ, TITANIUM DRIVE */
        b->d(b, 24, 0, (intptr_t)sizeof old3, old3, 0);
        int ok = fabsf(b->getP(b, idx("strip_sel")) - 1.f / 9.f) < 1e-4f && b->getP(b, idx("sh_unit")) == 0.f
              && b->getP(b, idx("eq_unit")) == 1.f && b->getP(b, idx("cmp_unit")) == 1.f && b->getP(b, idx("in_unit")) == 0.f;
        void *chunk = 0;
        long n4 = (long)b->d(b, 23, 0, 0, &chunk, 0);
        ok &= chunk && n4 > 0 && strstr((char *)chunk, "strip_sel=5;") && !strstr((char *)chunk, "_unit=");
        CHECK(ok, "an older project gets its CHANNEL STRIP from PREAMP (HEXX %.3f) and EQ / COMP units (%.0f / %.0f); saves strip_sel as a model",
              b->getP(b, idx("strip_sel")), b->getP(b, idx("eq_unit")), b->getP(b, idx("cmp_unit")));
    }
    b->d(b, 1, 0, 0, 0, 0);   /* effClose */
    a->d(a, 1, 0, 0, 0, 0);
    printf("%d checks, %d failed\n", checks, fails);
    return fails;
}
