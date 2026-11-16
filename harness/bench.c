/* CPU bench for the strip alone: % of one 128-frame block at 44.1 kHz on one core, per scenario.
 *   bench [seconds]    on the MPC, pin it to an audio core with taskset (XL: an A76, cores 4-7) */
#include "../src/xconsole.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <math.h>

#define SR 44100
#define BLOCK 128

static double now_us(void)
{
    struct timespec t;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t);
    return t.tv_sec * 1e6 + t.tv_nsec * 1e-3;
}
static int cmp(const void *a, const void *b) { double d = *(const double *)a - *(const double *)b; return d < 0 ? -1 : d > 0; }
static void on(XConsole *x, const char *k, float v) { xc_set(x, xc_param_index(k), v); }

static void run(const char *name, int level, int secs)
{
    XConsole *x = xc_create(SR);
    if (level >= 1 && level < 10) { on(x, "sh_on", 1); on(x, "eq_on", 1); on(x, "cmp_on", 1); on(x, "lc_freq", 0.3f); on(x, "hc_freq", 0.7f); on(x, "lc_slope", 3); on(x, "hc_slope", 3);
                      on(x, "gate_range", 0.5f); on(x, "eq_lf_gain", 0.7f); on(x, "cmp_ratio", 0.5f); on(x, "cmp_thr", 0.3f); }
    if (level >= 2 && level < 10) { on(x, "pre_on", 1); on(x, "drv_on", 1); on(x, "drv_amt", 0.5f); on(x, "sh_punch", 0.8f); on(x, "sh_sustain", 0.7f); }
    if (level >= 3 && level < 10) on(x, "flt_sc", 1);
    if (level == 10) { on(x, "drv_on", 1); on(x, "drv_amt", 0.5f); }
    if (level == 11) on(x, "pre_on", 1);
    if (level == 12) { on(x, "sh_on", 1); on(x, "sh_punch", 0.8f); on(x, "sh_sustain", 0.7f); }
    int blocks = secs * SR / BLOCK;
    double *t = malloc(sizeof(double) * blocks), sum = 0;
    float il[BLOCK], ir[BLOCK], ol[BLOCK], orr[BLOCK];
    unsigned r = 1;
    for (int b = 0; b < blocks; b++) {
        for (int i = 0; i < BLOCK; i++) { r = r * 1664525u + 1013904223u; il[i] = ir[i] = 0.3f * ((int)r * (1.f / 2147483648.f)); }
        double a = now_us();
        xc_process(x, il, ir, ol, orr, BLOCK);
        t[b] = now_us() - a;
        sum += t[b];
    }
    qsort(t, blocks, sizeof(double), cmp);
    double budget = 1e6 * BLOCK / SR;
    printf("%-44s mean %5.2f%%  p99 %5.2f%%  worst %5.2f%%\n", name, 100 * sum / blocks / budget, 100 * t[blocks * 99 / 100] / budget, 100 * t[blocks - 1] / budget);
    free(t);
    xc_destroy(x);
}

int main(int argc, char **argv)
{
    int secs = argc > 1 ? atoi(argv[1]) : 5;
    run("defaults (sections off)", 0, secs);
    run("filters 24 dB, gate, EQ, comp", 1, secs);
    run("+ preamp (2x), drive (4x), transients", 2, secs);
    run("+ filters in the side chains (TO S/C)", 3, secs);
    run("drive alone (4x, ADAA)", 10, secs);
    run("preamp alone (2x)", 11, secs);
    run("transients alone", 12, secs);
    return 0;
}
