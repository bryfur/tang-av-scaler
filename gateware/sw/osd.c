/* osd.c: the on-screen text (rtl/osd.v: 8 lines of 48 characters): what comes in and goes out,
 * what is done to the picture and how long it takes; a character is written when it changes. */
#include "hw.h"

#define COLS 48
#define ROWS 8

static const char *const noise[4] = {"off", "low", "medium", "high"};
static char want[ROWS][COLS];           /* the text as it should be */
static char shown[ROWS][COLS];          /* ... as the RAM has it */
static int row, col;

static void put(char c)
{
    if (col < COLS)
        want[row][col++] = c;
}

static void str(const char *s)
{
    while (*s)
        put(*s++);
}

/* a number, at least w digits wide (blanks before it) */
static void num(uint32_t v, int w)
{
    char b[10];
    int n = 0;
    do {
        b[n++] = '0' + v % 10;
        v /= 10;
    } while (v);
    while (w-- > n)
        put(' ');
    while (n)
        put(b[--n]);
}

/* v / 10^d with d decimals */
static void fix(uint32_t v, int d)
{
    uint32_t p = 1;
    for (int k = 0; k < d; k++)
        p *= 10;
    num(v / p, 1);
    put('.');
    for (p /= 10; p; p /= 10)
        put('0' + v / p % 10);
}

static void line(int r)
{
    row = r;
    col = 0;
    for (int k = 0; k < COLS; k++)
        want[r][k] = ' ';
}

void osd_init(void)
{
    for (int r = 0; r < ROWS; r++)
        for (int c = 0; c < COLS; c++) {
            shown[r][c] = ' ';
            REG(R_OSDW) = (uint32_t)(r * 64 + c) << 8 | ' ';
        }
}

void osd_update(void)
{
    const struct link_settings *s = &set;
    uint32_t tx_hz = (uint32_t)((uint64_t)REG(R_FREQ + 2) * 800000000u >> 25);
    bool in = st.fields_s >= 45 && st.pix != 0;

    line(0);
    str("IN   ");
    if (st.in_std != LINK_IN_NONE && !st.in_ok) {
        static const char *const names[] = LINK_IN_NAMES;
        str(names[st.in_std]);
        put(' ');
        fix(st.in_hz100, 2);
        str(" Hz  ");
        num(st.in_lines, 1);
        str(" lines  NOT HANDLED");
    } else if (in) {
        str(st.in_std == LINK_IN_240P ? "240p " : "480i ");
        fix(st.llc_hz * 100 / 225225, 2);       /* (a field is 858 x 262.5 samples of the decoder's clock) */
        str(" Hz  YPbPr  ");
        num(st.pix, 1);
        put('x');
        num(2 * st.lines, 1);
        str("  phase ");
        num(s->phase, 1);
    } else
        str("no signal");

    line(1);
    str("OUT  1080p ");
    fix(tx_hz / 24750, 2);              /* (2200 x 1125 pixels a frame: Hz x 100) */
    str(" Hz  ");
    str(s->wide ? "16:9" : "4:3 ");
    str(s->audio ? "  HDMI + sound" : "  DVI");
    if (!st.hpd)
        str("  no display");

    line(2);
    str("SHOWN ");
    num(st.show_w, 1);
    put('x');
    num(st.show_h, 1);
    str(" from ");
    num(st.show_x, 1);
    put(',');
    num(st.show_y, 1);
    str(s->crop == 1 ? "  (found)" : s->crop == 2 ? "  (set)" : "  (all)");

    line(3);
    str("DEINT ");
    str(s->mode == 1 ? "bob" : s->mode == 2 ? "weave" : st.hist ? "motion adaptive" : "bob (no history)");
    str("   NOISE ");
    str(noise[s->nr & 3]);

    line(4);
    str("SMAA ");
    if (s->aa) {
        str("on  edge ");
        num(s->aa_thr, 1);
        if (s->aa_diag)
            str("  diagonals");
        if (s->aa_corner)
            str("  corners");
    } else
        str("off");

    line(5);
    str("FSR 1  EASU + RCAS ");
    num(s->sharp, 1);
    str("/16");
    if (s->dn)
        str("  noise aware");
    if (REG(R_VID) >> 1 & 1)
        str("  FROZEN");

    line(6);
    str("DELAY ");
    if (in) {
        fix(st.delay_us10 / 10, 1);
        str(" ms ");
        fix(st.delay_us10 * 100u / 1668, 2);    /* (in frames of 16.68 ms) */
        str(" fr ");
        num(st.frames_s, 1);
        str(" fps");
        if (st.ll)
            str(" LL");
        if (st.lock >= 2) {
            int p = st.lock_ppm10;
            str(st.lock == 3 ? " LOCKED " : " locking ");
            put(p < 0 ? '-' : '+');
            fix(p < 0 ? -p : p, 1);
            str("ppm");
        }
    } else
        str("-");

    line(7);
    str("FPGA ");
    if (st.temp4 != -32768) {
        int t4 = st.temp4;
        if (t4 < 0) {
            put('-');
            t4 = -t4;
        }
        num(t4 / 4, 1);
        put('.');
        put("0257"[t4 & 3]);
        str("\x7f" "C");
    } else
        str("--");
    str("   CPU A25 400 MHz  up ");
    num(st.up_s / 3600, 1);
    put(':');
    put('0' + st.up_s / 600 % 6);
    put('0' + st.up_s / 60 % 10);
    put(':');
    put('0' + st.up_s / 10 % 6);
    put('0' + st.up_s % 10);

    for (int r = 0; r < ROWS; r++)
        for (int c = 0; c < COLS; c++)
            if (want[r][c] != shown[r][c]) {
                shown[r][c] = want[r][c];
                REG(R_OSDW) = (uint32_t)(r * 64 + c) << 8 | (uint8_t)want[r][c];
            }
}
