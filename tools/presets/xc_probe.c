/* X-Console preset helper: loads the engine on the desktop (built with -DXC_ONLY_MODEL=<model>, like a single plugin)
 * and answers what a preset author needs, since the engine keeps every control as a 0..1 position.
 *   xc_probe state                  the plugin's starting state (key=value; as a project saves it)
 *   xc_probe table <key> [n]        n+1 positions (default 40) and the text the knob shows at each
 *   xc_probe show <key>=<v> ...     set each in order, then print each one's text (checks a preset's values)
 * Build: gcc -O1 -DXC_ONLY_MODEL=5 -I<x>/src -I<mv>/wrapper xc_probe.c <x>/src/{engine,xconsole,spectrum,noise}.c -lm -lpthread */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "engine.h"

static void text(const mpc_engine_t *hexx, void *e, const char *key, char *out, int len)
{
    char k2[96];
    snprintf(k2, sizeof k2, "%s_display", key);
    if (hexx->get_param(e, k2, out, len) > 0) return;
    if (hexx->get_param(e, key, out, len) <= 0) snprintf(out, len, "?");   /* an option: its index */
}

int main(int argc, char **argv)
{
    const mpc_engine_t *hexx = mpc_engine();
    void *e = hexx->create(NULL);
    static char buf[1 << 16];
    if (!e) return 1;
    if (argc >= 2 && !strcmp(argv[1], "state")) {
        hexx->get_param(e, "state", buf, sizeof buf);
        puts(buf);
    } else if (argc >= 3 && !strcmp(argv[1], "table")) {
        int n = argc >= 4 ? atoi(argv[3]) : 40;
        char v[32], t[64];
        for (int i = 0; i <= n; i++) {
            snprintf(v, sizeof v, "%.6f", (double)i / n);
            hexx->set_param(e, argv[2], v);
            text(hexx, e, argv[2], t, sizeof t);
            printf("%s %s\n", v, t);
        }
    } else if (argc >= 3 && !strcmp(argv[1], "show")) {
        for (int i = 2; i < argc; i++) {
            char *eq = strchr(argv[i], '=');
            if (!eq) continue;
            *eq = 0;
            hexx->set_param(e, argv[i], eq + 1);
            *eq = '=';
        }
        for (int i = 2; i < argc; i++) {
            char key[64], t[64];
            char *eq = strchr(argv[i], '=');
            if (!eq || eq - argv[i] >= (int)sizeof key) continue;
            memcpy(key, argv[i], eq - argv[i]); key[eq - argv[i]] = 0;
            text(hexx, e, key, t, sizeof t);
            printf("%s %s\n", argv[i], t);
        }
    } else {
        fprintf(stderr, "usage: xc_probe state | table <key> [n] | show <key>=<v> ...\n");
        return 2;
    }
    hexx->destroy(e);
    return 0;
}
