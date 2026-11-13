/* board.c: the board brought up and looked after, as the link did it through the monitor
 * (firmware/xiao-wifi/main/scaler.c, and gateware/tools/hdmi.py, clkgen.py, adv.py, video.py before
 * it):
 *
 *  - the bring-up: the MS5351M to the transceivers' reference (148.5 MHz, or 148.5/1.001 for a
 *    59.94 Hz picture), the SN65DP159 a redriver, the display's SCDC, the lanes out of reset, the
 *    ADV7181D to 480i component through its CP core;
 *  - the settings into the scaler's registers;
 *  - the frame lock: the output's frames kept in step with the input's fields: the clock chip's
 *    frequency trimmed, ten times a second, so that a frame is begun LOCK_AT after a field's end
 *    (the scaler's LAT register says how long after it was): no field shown twice or left out, and
 *    the picture's delay the same all the time;
 *  - each second: what comes in and goes out; the part of the picture shown (all, as set, or where
 *    the fields have picture: border.v); the decoder's sampling phase (as set, or tuned: every
 *    phase tried on a still picture against focus.v, the sharpest kept).
 */
#include "hw.h"

#define ADV      0x21
#define ADV_DLL  0x6A                   /* the sampling phase: bits 4:0 */

struct link_settings set = LINK_SETTINGS_DEFAULT;
struct link_status st;

static bool want_again, want_measure, want_tune;
static uint32_t grab_ms;                /* a screen capture holds the fields still: when it last asked */
static bool grabbing;

/* ---- the MS5351M (Si5351A's registers): CLK0, CLK1 (inverted), CLK2 at 891 MHz / 6 = 148.5 MHz,
 * or 148.5 / 1.001.  The VCO / 25 MHz = 35 + b / PLL_C: b's steps are 0.028 ppm, for the frame lock ---- */
#define PLL_C   1000000u
static uint32_t pll_b0;                 /* b for the rate itself: 640000 (35.64), or 604396 (35.64 / 1.001) */
static uint8_t pll_now[8];              /* the PLL's eight registers as they are */
static void reg8(uint8_t *r, uint32_t p1, uint32_t p2, uint32_t p3)
{
    r[0] = p3 >> 8;
    r[1] = p3;
    r[2] = p1 >> 16 & 3;
    r[3] = p1 >> 8;
    r[4] = p1;
    r[5] = (p3 >> 16 & 15) << 4 | (p2 >> 16 & 15);
    r[6] = p2 >> 8;
    r[7] = p2;
}

/* the PLL's registers for b = pll_b0 + trim */
static void pll_regs(uint8_t *r, int32_t trim)
{
    const uint32_t b = pll_b0 + trim, f = (uint32_t)((uint64_t)128 * b / PLL_C);
    reg8(r, 128 * 35 + f - 512, 128 * b - PLL_C * f, PLL_C);
}

/* the clock moved by trim steps of b: the registers that change written (and seen to be) */
static bool pll_trim(int32_t trim)
{
    uint8_t r[8];
    bool ok = true;
    pll_regs(r, trim);
    for (int k = 0; k < 8; k++)
        if (r[k] != pll_now[k]) {
            ok &= i2c_sure(BUS_PLL, 0x60, 26 + k, r[k]);
            pll_now[k] = r[k];
        }
    return ok;
}

static bool clkgen(bool ntsc)
{
    uint8_t pll[8], msd[8];
    bool ok = true;
    pll_b0 = ntsc ? 604396 : 640000;
    pll_regs(pll, 0);
    for (int k = 0; k < 8; k++)
        pll_now[k] = pll[k];
    reg8(msd, 128 * 6 - 512, 0, 1);
    ok &= i2c_sure(BUS_PLL, 0x60, 3, 0xFF);                 /* outputs off */
    for (int k = 0; k < 8; k++)
        ok &= i2c_sure(BUS_PLL, 0x60, 16 + k, 0x80);        /* all powered down */
    ok &= i2c_sure(BUS_PLL, 0x60, 183, 0xD2);               /* crystal load 10 pF */
    ok &= i2c_sure(BUS_PLL, 0x60, 15, 0x00);
    for (int k = 0; k < 8; k++)
        ok &= i2c_sure(BUS_PLL, 0x60, 26 + k, pll[k]);
    for (int m = 0; m < 3; m++)
        for (int k = 0; k < 8; k++)
            ok &= i2c_sure(BUS_PLL, 0x60, 42 + 8 * m + k, msd[k]);
    for (int k = 0; k < 3; k++)
        ok &= i2c_sure(BUS_PLL, 0x60, 165 + k, 0);
    ok &= i2c_sure(BUS_PLL, 0x60, 16, 0x4F);                /* whole-number mode, PLL A, 8 mA */
    ok &= i2c_sure(BUS_PLL, 0x60, 17, 0x5F);                /* CLK1 inverted */
    ok &= i2c_sure(BUS_PLL, 0x60, 18, 0x4F);
    i2c_set(BUS_PLL, 0x60, 177, 0xA0);                      /* reset both PLLs */
    ok &= i2c_sure(BUS_PLL, 0x60, 3, 0xF8);                 /* CLK0-2 on */
    return ok;
}

/* ---- the ADV7181D: 480i component through its CP core (gateware/tools/adv.py CP480I) ---- */
static bool decoder(uint32_t ctrl)
{
    static const uint8_t regs[][2] = {
        {0x05, 0x00}, {0x06, 0x0A}, {0x1D, 0x47}, {0x3A, 0x11}, {0x3B, 0x81}, {0x3C, 0x52}, {0x6B, 0xC1},
        {0xC3, 0x46}, {0xC4, 0xB5}, {0x85, 0x19}, {0x86, 0x0B}, {0x8F, 0x07}, {0x90, 0x1C}, {0x73, 0xCF},
        {0x74, 0xA3}, {0x75, 0xE8}, {0x76, 0xFA}, {0xC5, 0x01}, {0x0E, 0x80}, {0x52, 0x46}, {0x54, 0x00},
        {0xF6, 0x3B}, {0x0E, 0x00},
    };
    bool ok = true;
    REG(R_CTRL) = ctrl & ~IN_RESET_N;
    wait_ms(20);
    REG(R_CTRL) = ctrl | IN_RESET_N;
    wait_ms(50);
    for (size_t k = 0; k < sizeof regs / sizeof regs[0]; k++) {
        bool done = false;
        for (int t = 0; t < 4 && !done; t++)
            done = i2c_set(BUS_IN, ADV, regs[k][0], regs[k][1]);
        ok &= done;
    }
    return ok;
}

/* the decoder's sampling phase set (the register's other bits as they are) */
static bool phase_set(uint8_t p)
{
    uint8_t was;
    for (int k = 0; k < 4; k++)
        if (i2c_get(BUS_IN, ADV, ADV_DLL, &was))
            return i2c_sure(BUS_IN, ADV, ADV_DLL, (was & 0xE0) | (p & 31));
    return false;
}

/* ---- the settings into the registers ---- */
static void picture(void)
{
    const struct link_settings *s = &set;
    REG(R_DEINT) = (uint32_t)s->aa_thr << 24 | (s->aa_corner ? 1u : 0) << 19 | (s->aa_diag ? 1u : 0) << 18 |
                   (s->aa_dbg ? 1u : 0) << 17 | (s->aa ? 1u : 0) << 16 | (uint32_t)s->thr << 8 |
                   (s->lowlat ? 1u : 0) << 6 | (uint32_t)(s->nr & 3) << 4 | (s->top1 ? 4 : 0) | (s->mode & 3);
    REG(R_OSD) = s->osd ? 1 : 0;
    REG(R_HDMI) = s->audio ? 6 : 0;     /* the video guard band and the data islands, or DVI's blanking */
    REG(R_VID) = (uint32_t)(s->sharp > 16 ? 16 : s->sharp) << 16 | (s->dn ? 16 : 0) | (s->swap ? 8 : 0) | 4 |
                 (s->pattern ? 0 : 1) | (s->freeze || grabbing ? 2 : 0);
}

/* the scaler's part of the source (gateware/sim/fsr.py geom()) */
static void geom(const uint16_t *p, bool wide)
{
    int32_t ow = wide ? 1920 : 1440, ox0 = wide ? 0 : 240;
    int32_t dx = (int32_t)((p[1] * 65536u + ow / 2) / ow), dy = (int32_t)((p[3] * 65536u + 540) / 1080);
    REG(R_GEOM) = ((uint32_t)((int32_t)(p[0] * 65536u) + dx / 2 - 32768 + 4096 - (ox0 + 120) * dx)) & 0xFFFFFFFu;
    REG(R_GEOM + 1) = (uint32_t)dx | (wide ? 1u << 31 : 0);
    REG(R_GEOM + 2) = (uint32_t)((int32_t)(p[2] * 65536u) + dy / 2 - 32768);
    REG(R_GEOM + 3) = (uint32_t)dy;
    st.show_x = p[0], st.show_w = p[1], st.show_y = p[2], st.show_h = p[3];
}

/* where the fields have had picture since the count began, as a part of the frame; false: nowhere
 * yet, or too little to be a game's whole picture (a dark scene with a few lights) */
static bool border(uint16_t *b)
{
    uint32_t x = REG(R_BORDER), l = REG(R_BORDERL);
    if (x != REG(R_BORDER) || l != REG(R_BORDERL) || !(x >> 31))
        return false;
    unsigned x0 = x & 0x1FF, x1 = x >> 16 & 0x1FF, l0 = l & 0x3FF, l1 = l >> 16 & 0x3FF;
    if (x1 < x0 || l1 < l0 || x1 > 359 || l1 > 239 || 2 * (x1 - x0 + 1) < 560 || 2 * (l1 - l0 + 1) < 380)
        return false;
    b[0] = 2 * x0;
    b[1] = 2 * (x1 - x0 + 1);
    b[2] = 2 * l0;
    b[3] = 2 * (l1 - l0 + 1);
    return true;
}

/* focus.v's sharpness: the mean of three fields, after two left out (the phase has just changed);
 * 0: no fields come */
static uint32_t focus(void)
{
    uint32_t v, n = REG(R_FOCUS) >> 28, sum = 0, t = ms();
    int got = -2;
    while (got < 3) {
        if (ms() - t > 400)
            return 0;
        v = REG(R_FOCUS);
        if (v != REG(R_FOCUS) || v >> 28 == n) {
            service();
            continue;
        }
        n = v >> 28;
        if (++got > 0)
            sum += (v & 0xFFFFFFF) >> 2;
    }
    return sum / 3 + 1;
}

/* every phase tried on the picture as it is: the sharpest kept and told; or the picture moved (the
 * first phase is not as sharp again as it was), or no fields came: the phase as it was */
static void tune(void)
{
    uint32_t f[32], again = 0, lo = ~0u;
    int best = 0;
    bool ok = true;
    st.tune = 1;
    for (int p = 0; p < 32 && ok; p++) {
        ok = phase_set(p) && (f[p] = focus()) != 0;
        if (ok && f[p] > f[best])
            best = p;
        if (ok && f[p] < lo)
            lo = f[p];
    }
    ok = ok && phase_set(0) && (again = focus()) != 0;
    if (!ok)
        st.tune = 4;
    else if ((again > f[0] ? again - f[0] : f[0] - again) > f[best] / 32)
        st.tune = 3;
    else {
        st.tune = 2;
        st.tune_gain = (uint16_t)((uint64_t)f[best] * 100 / lo);
        set.phase = best;
        st.gen++;
    }
    phase_set(set.phase);
}

/* ---- the bring-up ---- */
static uint8_t crop_was = 255, wide_was, phase_was;
static int counted;                     /* seconds the border has been looked for */
static int settle;                      /* seconds until the decoder's picture is to be trusted (after a bring-up) */

/* ---- the frame lock ---- */
#define LOCK_AT    50                   /* a frame begun this long after a field's end: 0.5 ms (in 10 us) */
/* ... or, made from the field coming in (lowlat), when some lines of that are in: its picture begins
 * 1.43 ms after the last one's end (22.5 lines of blanking), a line is 63.56 us.  The lines that must
 * be in (the scaler's LLMIN): what the picture's first rows need of the field (half the part shown's
 * first line and 24 more: the anti-aliasing looks 18 ahead) less the 8 that come in before the first
 * row is sent, and 5 to spare; the frame is begun 4 lines after that. */
#define LL_BLANK   143
static int ll_min(void)
{
    return st.show_y / 2 + 10;
}
#define LOCK_MAX   300                  /* ppm either way at most */
static int32_t lock_i;                  /* the errors' sum */
static int32_t lock_u;                  /* the trim now, ppm x 256 */
static int lock_good;                   /* steps in a row near enough */

void board_lock(void)
{
    uint32_t lat = REG(R_LAT);
    int32_t e, u;
    if (st.host)
        return;                         /* (a host tool has the scaler: the clock as it is) */
    if (!set.flock || !set.on) {
        if (lock_u) {
            lock_u = lock_i = 0;
            pll_trim(0);
        }
        st.lock = 0, st.lock_err = 0, st.lock_ppm10 = 0;
        return;
    }
    if (REG(R_VID) >> 1 & 1)
        return;                         /* (the picture frozen: no fields to steer by; the clock as it is) */
    if (st.fields_s < 45 || !st.up_ok || lat != REG(R_LAT)) {
        if (st.fields_s < 45)
            st.lock = 1;                /* (the clock as it was: the input may come back) */
        return;
    }
    /* how far the frame's start is from where it should be: the nearer way round a field's time */
    e = (int32_t)(lat & 0xFFF) - (set.lowlat && st.hist ? LL_BLANK + (ll_min() + 4) * 636 / 100 : LOCK_AT);
    while (e > 834)
        e -= 1668;
    while (e < -834)
        e += 1668;
    /* late (the output slow): the clock up.  4 ppm for each 10 us, and the sum's part (not while
     * the trim is at its end); 25 ppm a step at most */
    u = 1024 * e + 10 * lock_i;
    if (u > LOCK_MAX * 256)
        u = LOCK_MAX * 256;
    else if (u < -LOCK_MAX * 256)
        u = -LOCK_MAX * 256;
    else
        lock_i += e;
    if (u > lock_u + 25 * 256)
        u = lock_u + 25 * 256;
    if (u < lock_u - 25 * 256)
        u = lock_u - 25 * 256;
    lock_u = u;
    /* (a ppm is 35.6 steps of b) */
    pll_trim((int32_t)(((int64_t)u * 9115) >> 16));
    lock_good = e >= -5 && e <= 5 ? lock_good + 1 : 0;
    st.lock = lock_good >= 20 ? 3 : 2;
    st.lock_err = e;
    st.lock_ppm10 = u * 10 / 256;
}

static void bringup(void)
{
    uint32_t mode = REG(R_MODE);
    bool ok;
    REG(R_I2C) = 0;
    REG(R_CTRL) = IN_RESET_N;           /* the redriver's outputs off (OE low clears its registers) */
    REG(R_GT_CTRL) = 0;                 /* the lanes in reset */
    ok = clkgen(set.ntsc);
    REG(R_CTRL) = IN_RESET_N | DP_OE;
    wait_ms(50);
    i2c_set(BUS_DP, 0x5E, 0x0A, 0x38);  /* a redriver (as a retimer it corrupts 2.97 Gb/s); PD_EN toggled, it takes */
    i2c_set(BUS_DP, 0x5E, 0x09, 0x0A);
    wait_ms(100);
    /* (bit 2: its outputs stay on with hot plug low: a capture dongle raises hot plug only once it
     * sees a signal, and the redriver waits for hot plug before it sends one) */
    i2c_set(BUS_DP, 0x5E, 0x09, 0x06);
    i2c_set(BUS_DP, 0x5E, 0x0B, mode == 1 ? 0x00 : mode == 2 ? 0x08 : 0x18);
    wait_ms(300);
    REG(R_HDMI) = 0;                    /* DVI's blanking, nothing scrambled; picture() sets the sound's */
    if (i2c_set(BUS_DDC, 0x54, 0x02, 0x01))     /* an HDMI 2.0 sink: source version 1, clock 1/10, plain */
        i2c_set(BUS_DDC, 0x54, 0x20, 0x00);
    REG(R_GT_CTRL) = 0x00F;             /* the lanes released: the quad's PLL locks */
    wait_ms(20);
    REG(R_GT_CTRL) = 0x0FF;             /* the transmit PCS resets, a pulse */
    REG(R_GT_CTRL) = 0x00F;
    REG(R_GT_CTRL) = 0xF0F;             /* data valid */
    wait_ms(2);
    ok &= (REG(R_GT_STAT) >> 13 & 1) != 0;
    if (mode == 1) {
        ok &= decoder(IN_RESET_N | DP_OE);
        ok &= phase_set(set.phase);
        phase_was = set.phase;
    }
    picture();
    lock_u = lock_i = lock_good = 0;
    st.up_ok = ok;
    st.ups++;
    want_measure = true;                /* (the part shown stays until it is found again) */
    settle = 2;
}

void board_init(void)
{
    st.magic = LINK_MAGIC;
    st.fpga_build = REG(R_BUILD);
    st.temp4 = -32768;
    if (set.on)
        bringup();
}

void board_apply(const struct link_settings *was)
{
    st.gen++;
    if (!set.on || st.host)
        return;
    if (set.ntsc != was->ntsc || !was->on)
        want_again = true;              /* the clocks change: everything again */
    else
        picture();
}

void board_cmd(int cmd)
{
    switch (cmd) {
    case LINK_CMD_AGAIN: want_again = true; break;
    case LINK_CMD_MEASURE: want_measure = true; break;
    case LINK_CMD_TUNE: want_tune = true; st.tune = 1; break;
    case LINK_CMD_HOST_ON: st.host = 1; break;
    /* (a host tool gone: the settings again over whatever it left; the bring-up only if it undid it) */
    case LINK_CMD_HOST_OFF: st.host = 0; picture(); wide_was = !set.wide; break;
    case LINK_CMD_GRAB_BEGIN: grabbing = true; grab_ms = ms(); picture(); wait_ms(150); break;
    case LINK_CMD_GRAB_END: grabbing = false; picture(); break;
    }
}

/* a screen capture's fields held still: let go if it stopped asking */
void board_grab_seen(void)
{
    grab_ms = ms();
}

/* the picture is held for a grab (the on-screen text is left as it was: it is in what is grabbed) */
bool board_grabbing(void)
{
    return grabbing;
}

void board_second(void)
{
    static uint32_t fields_was, frames_was;
    uint32_t cap = REG(R_CAP), fields = REG(R_FIELDS), dstat = REG(R_DSTAT), temp = REG(R_TEMP);
    uint16_t want[4] = {0, 720, 0, 480};

    st.pix = cap & 0x7FF;
    st.lines = cap >> 11 & 0x3FF;
    st.fields_s = (fields - fields_was) & 0xFFFF;
    st.frames_s = ((dstat >> 16) - frames_was) & 0xFFFF;
    fields_was = fields;
    frames_was = dstat >> 16;
    st.hist = dstat >> 14 & 1;
    st.hpd = REG(R_STAT) >> 2 & 1;
    st.pll = REG(R_GT_STAT) >> 13 & 1;
    /* (fmeter.v's count is the clock / 23.84 Hz: 16 x 50 MHz / 2^25) */
    st.llc_hz = (uint32_t)((uint64_t)REG(R_FREQ + 1) * 800000000u >> 25);
    st.temp4 = temp >> 31 ? (int16_t)((int32_t)(temp << 18) >> 18) : -32768;
    /* (the field's end to the frame's start, and a field's time to its lines: 16.3 ms; or, made from
     * the field coming in: from its first line in to the first row out, 0.67 ms after the frame's start) */
    if (!(REG(R_VID) >> 1 & 1)) {       /* (not of a frozen picture: that only grows older) */
        uint32_t lat = REG(R_LAT);
        st.ll = dstat >> 12 & 1;
        st.ll_lines = lat >> 16 & 0x3FF;
        st.delay_us10 = st.ll ? (lat & 0xFFF) + 67 - LL_BLANK : (lat & 0xFFF) + 1630;
        REG(R_LLMIN) = ll_min();
    }

    if (grabbing && ms() - grab_ms > 3000) {
        grabbing = false;
        picture();
    }
    if (!set.on || st.host)
        return;
    if (want_again || REG(R_GT_CTRL) != 0xF0F || (REG(R_CTRL) & (IN_RESET_N | DP_OE)) != (IN_RESET_N | DP_OE)) {
        want_again = false;
        bringup();
    }

    /* the sampling phase: as set; or tuned, and that kept */
    if (want_tune) {
        want_tune = false;
        tune();
        phase_was = set.phase;
    } else if (set.phase != phase_was) {
        phase_set(set.phase);
        phase_was = set.phase;
    }

    /* the part shown (not looked for while the decoder is still finding the picture) */
    if (settle) {
        settle--;
        return;
    }
    if (set.crop != crop_was || want_measure) {
        REG(R_BORDER) = 40;             /* (the luma picture is above) */
        counted = 0;
        if (set.crop != crop_was)
            st.show_w = 0;              /* (set, whatever it was) */
        crop_was = set.crop;
        want_measure = false;
    }
    if (set.crop == 2 && set.crop_w >= 64 && set.crop_h >= 64 && set.crop_x + set.crop_w <= 720 &&
        set.crop_y + set.crop_h <= 480)
        want[0] = set.crop_x, want[1] = set.crop_w, want[2] = set.crop_y, want[3] = set.crop_h;
    /* (three seconds of fields first; until then, and with nothing found, as it is) */
    if (set.crop == 1 && (++counted < 3 || !border(want)) && st.show_w != 0)
        want[0] = st.show_x, want[1] = st.show_w, want[2] = st.show_y, want[3] = st.show_h;
    if (want[0] != st.show_x || want[1] != st.show_w || want[2] != st.show_y || want[3] != st.show_h ||
        set.wide != wide_was) {
        geom(want, set.wide);
        wide_was = set.wide;
    }
}
