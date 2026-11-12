/* The scaler's CPU (the SOM's hard core, an Andes A25: rtl/cpu.v): what need not be logic.  For
 * now: the on-screen text (rtl/osd.v): what comes in and goes out, what is done to the picture and
 * how long it takes, from the scaler's own registers (rtl/top.v: at 0xE8000000 + 4 x the register),
 * four times a second.  Register 64 counts up while this runs, 65 says what it is.
 */

#include <stdint.h>

#define REG(n)      (*(volatile uint32_t *)(0xe8000000u + 4u * (n)))
#define CORE_HZ     400000000u          /* rtl/sys_pll.v */

enum { R_BUILD = 0x01, R_STAT = 0x03, R_FREQ = 0x10, R_GT_STAT = 0x21, R_HDMI = 0x26, R_LAT = 0x27, R_OSD = 0x28,
       R_OSDW = 0x29, R_TEMP = 0x2a, R_VID = 0x30, R_CAP = 0x31, R_FIELDS = 0x32, R_DEINT = 0x35, R_DSTAT = 0x36,
       R_GEOM = 0x3a, R_CPUM = 0x64 };

#define COLS 48
#define ROWS 8

static const char *const noise[4] = {"off", "low", "medium", "high"};
static char want[ROWS][COLS];           /* the text as it should be */
static char shown[ROWS][COLS];          /* ... as the RAM has it */
static int row, col;

static uint32_t cycles(void)
{
    uint32_t c;
    __asm__ volatile ("csrr %0, mcycle" : "=r"(c));
    return c;
}

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

static void text(uint32_t up_s, uint32_t fields_s, uint32_t frames_s)
{
    uint32_t vid = REG(R_VID), de = REG(R_DEINT), cap = REG(R_CAP), hd = REG(R_HDMI), lat = REG(R_LAT),
             temp = REG(R_TEMP), llc = REG(R_FREQ + 1), txc = REG(R_FREQ + 2), dst = REG(R_DSTAT);
    int32_t xr = (int32_t)REG(R_GEOM), ys = (int32_t)REG(R_GEOM + 2);
    uint32_t dxr = REG(R_GEOM + 1), dy = REG(R_GEOM + 3) & 0x1ffff, dx = dxr & 0x1ffff;
    int wide = dxr >> 31, ow = wide ? 1920 : 1440, ox0 = wide ? 0 : 240;
    /* (fmeter.v's count is the clock / 23.84 Hz: 16 x 50 MHz / 2^25) */
    uint32_t llc_hz = (uint32_t)((uint64_t)llc * 800000000u >> 25), tx_hz = (uint32_t)((uint64_t)txc * 800000000u >> 25);
    uint32_t pix = cap & 0x7ff, lines = cap >> 11 & 0x3ff;
    int in = fields_s >= 45 && pix != 0;

    line(0);
    str("IN   ");
    if (in) {
        num(2 * lines, 1);
        str("i ");
        /* (a field is 858 x 262.5 samples of the decoder's clock) */
        fix(llc_hz * 100 / 225225, 2);
        str(" Hz  YPbPr  ");
        num(pix, 1);
        put('x');
        num(2 * lines, 1);
    } else
        str("no signal");

    line(1);
    str("OUT  1080p ");
    fix(tx_hz / 24750, 2);              /* (2200 x 1125 pixels a frame: Hz x 100) */
    str(" Hz  ");
    str(wide ? "16:9" : "4:3 ");
    str(hd & 4 ? "  HDMI + sound" : "  DVI");

    line(2);
    str("SHOWN ");
    num((dx * ow + 32768) >> 16, 1);
    put('x');
    num((dy * 1080 + 32768) >> 16, 1);
    str(" from ");
    num((uint32_t)((xr + (int32_t)((ox0 + 120) * dx) - (int32_t)(dx / 2) + 32768 - 4096 + 32768) >> 16), 1);
    put(',');
    num((uint32_t)((ys - (int32_t)(dy / 2) + 32768 + 32768) >> 16), 1);
    str(" of 720x480");

    line(3);
    str("DEINT ");
    str((de & 3) == 1 ? "bob" : (de & 3) == 2 ? "weave" : dst >> 14 & 1 ? "motion adaptive" : "bob (no history)");
    str("   NOISE ");
    str(noise[de >> 4 & 3]);

    line(4);
    str("SMAA ");
    if (de >> 16 & 1) {
        str("on  edge ");
        num(de >> 24, 1);
        if (de >> 18 & 1)
            str("  diagonals");
        if (de >> 19 & 1)
            str("  corners");
    } else
        str("off");

    line(5);
    str("FSR 1  EASU + RCAS ");
    num(vid >> 16 & 31, 1);
    str("/16");
    if (vid >> 4 & 1)
        str("  noise aware");
    if (vid >> 1 & 1)
        str("  FROZEN");

    line(6);
    str("DELAY ");
    if (in) {
        /* (the field's end to the frame's start, then a field's time to the picture's lines: 16.3 ms) */
        uint32_t us10 = (lat & 0xfff) + 1630;
        fix(us10 / 10, 1);
        str(" ms  ");
        fix(us10 * 100 / 1668, 2);      /* (in frames of 16.68 ms) */
        str(" frames  ");
        num(frames_s, 1);
        str(" fps");
    } else
        str("-");

    line(7);
    str("FPGA ");
    if (temp >> 31) {
        int32_t t4 = (int32_t)(temp << 18) >> 18;
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
    num(up_s / 3600, 1);
    put(':');
    put('0' + up_s / 600 % 6);
    put('0' + up_s / 60 % 10);
    put(':');
    put('0' + up_s / 10 % 6);
    put('0' + up_s % 10);
}

int main(void)
{
    uint32_t t0 = cycles(), n = 0, up = 0, q = 0, fields_was = REG(R_FIELDS), frames_was = REG(R_DSTAT) >> 16,
             fields_s = 0, frames_s = 0;

    REG(R_CPUM + 1) = 0x31435641;       /* "AVC1" */
    for (int r = 0; r < ROWS; r++)
        for (int c = 0; c < COLS; c++) {
            shown[r][c] = ' ';
            REG(R_OSDW) = (uint32_t)(r * 64 + c) << 8 | ' ';
        }
    for (;;) {
        /* a quarter of a second */
        while (cycles() - t0 < CORE_HZ / 4)
            ;
        t0 += CORE_HZ / 4;
        REG(R_CPUM) = ++n;
        if (++q == 4) {
            uint32_t f = REG(R_FIELDS), d = REG(R_DSTAT) >> 16;
            q = 0;
            up++;
            fields_s = (f - fields_was) & 0xffff;
            frames_s = (d - frames_was) & 0xffff;
            fields_was = f;
            frames_was = d;
        }
        text(up, fields_s, frames_s);
        for (int r = 0; r < ROWS; r++)
            for (int c = 0; c < COLS; c++)
                if (want[r][c] != shown[r][c]) {
                    shown[r][c] = want[r][c];
                    REG(R_OSDW) = (uint32_t)(r * 64 + c) << 8 | (uint8_t)want[r][c];
                }
    }
}
