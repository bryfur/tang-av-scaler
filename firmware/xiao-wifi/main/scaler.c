/* The scaler kept running by the link, with no host: what gateware/tools/hdmi.py, clkgen.py, adv.py
 * and video.py do from a PC, done here through the FPGA's monitor (gateware/rtl/top.v: its
 * registers over the UART, 'W' addr data and 'R' addr):
 *
 *  - when the FPGA answers and is not brought up (after its configuration, a reload): the MS5351M to
 *    the transceivers' reference (148.5 MHz, or 148.5/1.001 for a 59.94 Hz picture), the SN65DP159
 *    a redriver, the sink's SCDC, the lanes out of reset; the ADV7181D to 480i component through
 *    its CP core; the picture's settings (deinterlacing, anti-aliasing, sharpening);
 *  - each second: is it still up (after a reload: again), and what the capture and
 *    the deinterlacer say, for the web page;
 *  - the part of the picture shown (the scaler fills the output with it): all, as set, or where
 *    the FPGA finds picture in the fields (border.v: it only grows, so a dark scene takes nothing
 *    away; found again after a bring-up or when asked);
 *  - the decoder's sampling phase (its DLL, 32 steps): a console's pixels come at the samples' rate
 *    (13.5 MHz for a picture 640 wide), so where in a pixel the sample is taken shows: as set, or
 *    each tried on a still picture and the sharpest kept (the FPGA's focus.v measures);
 *  - the settings (kept in NVS), changed from the web page: POST /api/video.
 *
 * While a host is on the console's TCP port the scaler is left to it (its tools write the same
 * registers).  I2C is bit by bit through the monitor's I2C register, nothing read back before a
 * transaction's stop (gateware/tools/avb.py: the link's radio beside the MS5351M's bus); what is
 * written is read back, and written again if it is not there. */

#include <stdio.h>
#include <string.h>

#include "app.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "nvs.h"

static const char *TAG = "scaler";

enum { R_ID = 0x00, R_BUILD = 0x01, R_CTRL = 0x02, R_STAT = 0x03, R_I2C = 0x04, R_I2C_SH = 0x05, R_FREQ = 0x10,
       R_GT_CTRL = 0x20, R_GT_STAT = 0x21, R_MODE = 0x25, R_HDMI = 0x26, R_VID = 0x30, R_CAP = 0x31,
       R_FIELDS = 0x32, R_DEINT = 0x35, R_DSTAT = 0x36,
       R_FOCUS = 0x37, R_GEOM = 0x3A, R_BORDER = 0x3E, R_BORDERL = 0x3F };
#define ADV 0x21
#define ADV_DLL 0x6A                    /* the sampling phase: bits 4:0 */
#define MAGIC 0x31425641u
#define DP_OE (1u << 2)
#define IN_RESET_N (1u << 3)
enum { BUS_PLL, BUS_DP, BUS_DDC, BUS_IN };

static struct scaler_state state;
static struct scaler_settings set = {.on = true, .ntsc = true, .mode = 0, .thr = 6, .aa = true, .aa_thr = 20, .sharp = 8,
                                      .audio = true, .aa_diag = true, .aa_corner = true, .crop = 1, .crop_w = 720, .crop_h = 480, .nr = 2, .dn = true};
static SemaphoreHandle_t lock;          /* set, state, dirty */
static bool dirty, again, measure, tune;

/* ---- the monitor ---- */
static uint8_t out[2048];
static size_t on;
static uint8_t drv;                     /* the I2C lines pulled low */

static bool rd(uint8_t addr, uint32_t *v)
{
    uint8_t rx[4];
    out[on++] = 'R';
    out[on++] = addr;
    bool ok = console_xfer(out, on, rx, 4, 400);
    on = 0;
    *v = ok ? rx[0] | rx[1] << 8 | rx[2] << 16 | (uint32_t)rx[3] << 24 : 0;
    return ok;
}

static void wr(uint8_t addr, uint32_t v)
{
    uint32_t x;
    if (on + 6 > sizeof out - 8)        /* (the FPGA has taken all of it when it answers) */
        rd(R_ID, &x);
    out[on++] = 'W';
    out[on++] = addr;
    for (int k = 0; k < 4; k++)
        out[on++] = v >> 8 * k;
}

static void flush(void)
{
    uint32_t x;
    if (on)
        rd(R_ID, &x);
}

static void pause_ms(int ms)
{
    flush();
    vTaskDelay(pdMS_TO_TICKS(ms));
}

/* ---- I2C through the monitor ---- */
static void lines(int bus, int scl, int sda)
{
    if (scl >= 0)
        drv = (drv & ~(1 << 2 * bus)) | (scl ? 0 : 1) << 2 * bus;
    if (sda >= 0)
        drv = (drv & ~(2 << 2 * bus)) | (sda ? 0 : 2) << 2 * bus;
    wr(R_I2C, drv);
}

static void i2c_start(int bus)
{
    lines(bus, -1, 1);
    lines(bus, 1, -1);
    lines(bus, -1, 0);
    lines(bus, 0, -1);
}

static void i2c_stop(int bus)
{
    lines(bus, -1, 0);
    lines(bus, 1, -1);
    lines(bus, -1, 1);
}

static void i2c_clock(int bus, int sda)
{
    lines(bus, -1, sda);
    lines(bus, 1, -1);
    lines(bus, 0, -1);
}

static void i2c_put(int bus, uint8_t b)
{
    for (int k = 7; k >= 0; k--)
        i2c_clock(bus, b >> k & 1);
    i2c_clock(bus, 1);
}

/* true if the last three bytes (all of them, up to two after the address) were acknowledged */
static bool i2c_write(int bus, uint8_t dev, const uint8_t *d, int n)
{
    uint32_t sh;
    i2c_start(bus);
    i2c_put(bus, dev << 1);
    for (int k = 0; k < n; k++)
        i2c_put(bus, d[k]);
    i2c_stop(bus);
    if (!rd(R_I2C_SH + bus, &sh))
        return false;
    for (int j = 0; j < (n + 1 < 3 ? n + 1 : 3); j++)
        if (sh >> (1 + 9 * j) & 1)
            return false;
    return true;
}

static bool i2c_set(int bus, uint8_t dev, uint8_t reg, uint8_t val)
{
    const uint8_t d[2] = {reg, val};
    return i2c_write(bus, dev, d, 2);
}

static bool i2c_get(int bus, uint8_t dev, uint8_t reg, uint8_t *val)
{
    uint32_t sh;
    i2c_start(bus);
    i2c_put(bus, dev << 1);
    i2c_put(bus, reg);
    lines(bus, -1, 1);
    i2c_start(bus);
    i2c_put(bus, dev << 1 | 1);
    for (int k = 0; k < 8; k++)
        i2c_clock(bus, 1);
    i2c_clock(bus, 1);
    i2c_stop(bus);
    if (!rd(R_I2C_SH + bus, &sh) || (sh >> 10 & 1))
        return false;
    *val = sh >> 2 & 0xFF;
    return true;
}

/* a register set and seen to be: up to six times */
static bool i2c_sure(int bus, uint8_t dev, uint8_t reg, uint8_t val)
{
    for (int k = 0; k < 6; k++) {
        uint8_t got;
        if (i2c_set(bus, dev, reg, val) && i2c_get(bus, dev, reg, &got) && got == val)
            return true;
    }
    ESP_LOGW(TAG, "I2C bus %d device %02x register %02x: not set", bus, dev, reg);
    return false;
}

/* ---- the MS5351M (Si5351A's registers): CLK0, CLK1 (inverted), CLK2 at 891 MHz / 6 = 148.5 MHz,
 * or 148.5 / 1.001 (gateware/tools/clkgen.py) ---- */
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

static bool clkgen(bool ntsc)
{
    /* the VCO / 25 MHz = 35 + b/c: 35.64 (16/25), or 35.64 / 1.001 (55/91) */
    const uint32_t a = 35, b = ntsc ? 55 : 16, c = ntsc ? 91 : 25, f = 128 * b / c;
    uint8_t pll[8], ms[8];
    bool ok = true;
    reg8(pll, 128 * a + f - 512, 128 * b - c * f, c);
    reg8(ms, 128 * 6 - 512, 0, 1);
    ok &= i2c_sure(BUS_PLL, 0x60, 3, 0xFF);                 /* outputs off */
    for (int k = 0; k < 8; k++)
        ok &= i2c_sure(BUS_PLL, 0x60, 16 + k, 0x80);        /* all powered down */
    ok &= i2c_sure(BUS_PLL, 0x60, 183, 0xD2);               /* crystal load 10 pF */
    ok &= i2c_sure(BUS_PLL, 0x60, 15, 0x00);
    for (int k = 0; k < 8; k++)
        ok &= i2c_sure(BUS_PLL, 0x60, 26 + k, pll[k]);
    for (int m = 0; m < 3; m++)
        for (int k = 0; k < 8; k++)
            ok &= i2c_sure(BUS_PLL, 0x60, 42 + 8 * m + k, ms[k]);
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
    wr(R_CTRL, ctrl & ~IN_RESET_N);
    pause_ms(20);
    wr(R_CTRL, ctrl | IN_RESET_N);
    pause_ms(50);
    for (size_t k = 0; k < sizeof regs / sizeof regs[0]; k++) {
        bool done = false;
        for (int t = 0; t < 4 && !done; t++)
            done = i2c_set(BUS_IN, 0x21, regs[k][0], regs[k][1]);
        ok &= done;
    }
    return ok;
}

static void picture(void)
{
    struct scaler_settings s;
    xSemaphoreTake(lock, portMAX_DELAY);
    s = set;
    dirty = false;
    xSemaphoreGive(lock);
    wr(R_DEINT, (uint32_t)s.aa_thr << 24 | (s.aa_corner ? 1u : 0) << 19 | (s.aa_diag ? 1u : 0) << 18 | (s.aa_dbg ? 1u : 0) << 17 | (s.aa ? 1u : 0) << 16 | (uint32_t)s.thr << 8 | (uint32_t)(s.nr & 3) << 4 | (s.top1 ? 4 : 0) | (s.mode & 3));
    wr(R_HDMI, s.audio ? 6 : 0);        /* the video guard band and the data islands, or DVI's blanking */
    wr(R_VID, (uint32_t)(s.sharp > 16 ? 16 : s.sharp) << 16 | (s.dn ? 16 : 0) | (s.swap ? 8 : 0) | 4 | (s.pattern ? 0 : 1) | (s.freeze ? 2 : 0));
    flush();
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

/* focus.v's sharpness: the mean of three fields, after two left out (the phase has just changed);
 * 0: no fields come */
static uint32_t focus(void)
{
    uint32_t v, w, n, sum = 0;
    int got = -2;
    if (!rd(R_FOCUS, &v))
        return 0;
    n = v >> 28;
    for (int t = 0; t < 300 && got < 3; t++) {
        if (!rd(R_FOCUS, &v) || !rd(R_FOCUS, &w))
            return 0;
        if (v != w || v >> 28 == n) {
            vTaskDelay(pdMS_TO_TICKS(2));
            continue;
        }
        n = v >> 28;
        if (++got > 0)
            sum += (v & 0xFFFFFFF) >> 2;
    }
    return got == 3 ? sum / 3 + 1 : 0;
}

/* every phase tried on the picture as it is; the sharpest's number, or -1 (the picture moved: the
 * first phase is not as sharp again as it was), -2 (no fields).  The phase is left at 0. */
static int phase_tune(uint16_t *gain)
{
    uint32_t f[32], again, lo = ~0u;
    int best = 0;
    for (int p = 0; p < 32; p++) {
        if (!phase_set(p) || !(f[p] = focus()))
            return -2;
        if (f[p] > f[best])
            best = p;
        if (f[p] < lo)
            lo = f[p];
    }
    if (!phase_set(0) || !(again = focus()))
        return -2;
    uint32_t d = again > f[0] ? again - f[0] : f[0] - again;
    ESP_LOGI(TAG, "sampling phase: sharpest %d (%u), least %u, phase 0 %u and again %u", best, (unsigned)f[best],
             (unsigned)lo, (unsigned)f[0], (unsigned)again);
    if (d > f[best] / 32)
        return -1;
    *gain = (uint16_t)((uint64_t)f[best] * 100 / lo);
    return best;
}

/* the scaler's part of the source (gateware/sim/fsr.py geom()) */
static void geom(unsigned x0, unsigned cw, unsigned y0, unsigned ch, bool wide)
{
    int32_t ow = wide ? 1920 : 1440, ox0 = wide ? 0 : 240;
    int32_t dx = (int32_t)((cw * 65536u + ow / 2) / ow), dy = (int32_t)((ch * 65536u + 540) / 1080);
    wr(R_GEOM, ((uint32_t)((int32_t)(x0 * 65536u) + dx / 2 - 32768 + 4096 - (ox0 + 120) * dx)) & 0xFFFFFFFu);
    wr(R_GEOM + 1, (uint32_t)dx | (wide ? 1u << 31 : 0));
    wr(R_GEOM + 2, (uint32_t)((int32_t)(y0 * 65536u) + dy / 2 - 32768));
    wr(R_GEOM + 3, (uint32_t)dy);
    flush();
}

/* where the fields have had picture since the count began, as a part of the frame; false: nowhere
 * yet, or too little to be a game's whole picture (a dark scene with a few lights) */
static bool border(uint16_t *b)
{
    uint32_t x, l, x2, l2;
    for (int t = 0; t < 4; t++) {
        if (!rd(R_BORDER, &x) || !rd(R_BORDERL, &l) || !rd(R_BORDER, &x2) || !rd(R_BORDERL, &l2))
            return false;
        if (x == x2 && l == l2)
            break;
    }
    if (x != x2 || l != l2 || !(x >> 31))
        return false;
    unsigned x0 = x & 0x1FF, x1 = x >> 16 & 0x1FF, l0 = l & 0x3FF, l1 = l >> 16 & 0x3FF;
    if (x1 < x0 || l1 < l0 || x1 > 359 || l1 > 239)
        return false;
    if (2 * (x1 - x0 + 1) < 560 || 2 * (l1 - l0 + 1) < 380)
        return false;
    b[0] = 2 * x0;
    b[1] = 2 * (x1 - x0 + 1);
    b[2] = 2 * l0;
    b[3] = 2 * (l1 - l0 + 1);
    return true;
}

static bool bringup(void)
{
    uint32_t mode, stat, x;
    bool ntsc, ok;
    xSemaphoreTake(lock, portMAX_DELAY);
    ntsc = set.ntsc;
    xSemaphoreGive(lock);
    if (!rd(R_MODE, &mode))
        return false;
    drv = 0;
    wr(R_I2C, 0);
    wr(R_CTRL, IN_RESET_N);             /* the redriver's outputs off (OE low clears its registers) */
    wr(R_GT_CTRL, 0);                   /* the lanes in reset */
    ok = clkgen(ntsc);
    wr(R_CTRL, IN_RESET_N | DP_OE);
    pause_ms(50);
    i2c_set(BUS_DP, 0x5E, 0x0A, 0x38);  /* a redriver (as a retimer it corrupts 2.97 Gb/s); PD_EN toggled, it takes */
    i2c_set(BUS_DP, 0x5E, 0x09, 0x0A);
    pause_ms(100);
    /* (bit 2: its outputs stay on with hot plug low: a capture dongle raises hot plug only once it
     * sees a signal, and the redriver waits for hot plug before it sends one) */
    i2c_set(BUS_DP, 0x5E, 0x09, 0x06);
    i2c_set(BUS_DP, 0x5E, 0x0B, mode == 1 ? 0x00 : mode == 2 ? 0x08 : 0x18);
    pause_ms(300);
    wr(R_HDMI, 0);                      /* DVI's blanking, nothing scrambled; picture() sets the sound's */
    if (i2c_set(BUS_DDC, 0x54, 0x02, 0x01))     /* an HDMI 2.0 sink: source version 1, clock 1/10, plain */
        i2c_set(BUS_DDC, 0x54, 0x20, 0x00);
    wr(R_GT_CTRL, 0x00F);               /* the lanes released: the quad's PLL locks */
    pause_ms(20);
    wr(R_GT_CTRL, 0x0FF);               /* the transmit PCS resets, a pulse */
    wr(R_GT_CTRL, 0x00F);
    wr(R_GT_CTRL, 0xF0F);               /* data valid */
    flush();
    rd(R_GT_STAT, &stat);
    ok &= (stat >> 13 & 1) != 0;
    if (mode == 1) {
        uint8_t ph;
        ok &= decoder(IN_RESET_N | DP_OE);
        xSemaphoreTake(lock, portMAX_DELAY);
        ph = set.phase;
        xSemaphoreGive(lock);
        ok &= phase_set(ph);
    }
    picture();
    rd(R_ID, &x);
    ESP_LOGI(TAG, "brought up: %s, clock chip and decoder %s, transceiver PLL %s", ntsc ? "59.94 Hz" : "60 Hz",
             ok ? "set" : "NOT all set", stat >> 13 & 1 ? "locked" : "not locked");
    return ok;
}

static void task(void *arg)
{
    bool up_ok = false, seen = false;
    uint16_t shown[4] = {0, 720, 0, 480}, want[4];
    int counted = 0;                    /* seconds the border has been looked for */
    uint8_t crop_was = 255, phase_was = 255, tune_st = 0;
    uint16_t tune_gain = 0;
    bool wide_was = false;
    uint32_t fields_was = 0, frames_was = 0;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        struct scaler_state s = {0};
        bool on_now, redo;
        xSemaphoreTake(lock, portMAX_DELAY);
        on_now = set.on;
        redo = again;
        again = false;
        s.ups = state.ups;
        xSemaphoreGive(lock);
        s.host = console_busy();
        uint32_t v, ctrl, gt, stat, cap, fields, dstat, llc;
        on = 0;
        if (!s.host && on_now && rd(R_ID, &v) && v == MAGIC) {
            /* (the FPGA's banner may have been in the way of the first answer: twice) */
            s.fpga = rd(R_ID, &v) && v == MAGIC && rd(R_BUILD, &s.build) && rd(R_CTRL, &ctrl) && rd(R_GT_CTRL, &gt) &&
                     rd(R_STAT, &stat);
            if (s.fpga) {
                bool hpd = stat >> 2 & 1;
                /* (not again on hot plug: at these rates a display needs nothing told, the output
                 * runs with or without one, and a capture dongle drops and raises hot plug each
                 * time the signal restarts: it would never end) */
                if (redo || gt != 0xF0F || (ctrl & (IN_RESET_N | DP_OE)) != (IN_RESET_N | DP_OE)) {
                    up_ok = bringup();
                    s.ups++;
                    crop_was = 255;
                    seen = true;
                    phase_was = 255;
                } else {
                    /* (found up after this firmware's own restart: the bring-up before it stands) */
                    if (!seen)
                        up_ok = true;
                    seen = true;
                    if (dirty)
                        picture();
                }
                s.ok = up_ok;
                /* the part shown */
                struct scaler_settings c;
                bool again_m, tune_now;
                xSemaphoreTake(lock, portMAX_DELAY);
                c = set;
                again_m = measure;
                measure = false;
                tune_now = tune;
                tune = false;
                if (tune_now)
                    state.tune = 1;
                xSemaphoreGive(lock);
                /* the sampling phase: as set; or tuned (some eight seconds), and that kept */
                if (phase_was == 255)
                    phase_was = c.phase;        /* (the bring-up set it) */
                if (tune_now) {
                    int best = phase_tune(&tune_gain);
                    tune_st = best >= 0 ? 2 : best == -1 ? 3 : 4;
                    if (best >= 0) {
                        nvs_handle_t h;
                        xSemaphoreTake(lock, portMAX_DELAY);
                        set.phase = c.phase = best;
                        c = set;
                        xSemaphoreGive(lock);
                        if (nvs_open("av", NVS_READWRITE, &h) == ESP_OK) {
                            nvs_set_blob(h, "video", &c, sizeof c);
                            nvs_commit(h);
                            nvs_close(h);
                        }
                    }
                    phase_set(c.phase);
                    phase_was = c.phase;
                } else if (c.phase != phase_was) {
                    phase_set(c.phase);
                    phase_was = c.phase;
                }
                s.tune = tune_st;
                s.tune_gain = tune_gain;
                if (c.crop != crop_was || again_m) {
                    wr(R_BORDER, 40);           /* (the luma picture is above) */
                    flush();
                    counted = 0;
                    if (c.crop != crop_was)
                        shown[1] = 0;           /* (set, whatever it was) */
                    crop_was = c.crop;
                }
                want[0] = 0, want[1] = 720, want[2] = 0, want[3] = 480;
                if (c.crop == 2 && c.crop_w >= 64 && c.crop_h >= 64 && c.crop_x + c.crop_w <= 720 &&
                    c.crop_y + c.crop_h <= 480)
                    want[0] = c.crop_x, want[1] = c.crop_w, want[2] = c.crop_y, want[3] = c.crop_h;
                if (c.crop == 1) {
                    /* (three seconds of fields first; until then, and with nothing found, as it is) */
                    if (++counted < 3 || !border(want)) {
                        if (shown[1] != 0)
                            memcpy(want, shown, sizeof want);
                    }
                }
                if (memcmp(want, shown, sizeof want) || c.wide != wide_was) {
                    geom(want[0], want[1], want[2], want[3], c.wide);
                    wide_was = c.wide;
                    memcpy(shown, want, sizeof shown);
                    ESP_LOGI(TAG, "shown: %u x %u from %u, %u", want[1], want[3], want[0], want[2]);
                }
                s.show_x = shown[0], s.show_w = shown[1], s.show_y = shown[2], s.show_h = shown[3];
                rd(R_GT_STAT, &gt);
                rd(R_CAP, &cap);
                rd(R_FIELDS, &fields);
                rd(R_DSTAT, &dstat);
                rd(R_FREQ + 1, &llc);
                s.hpd = hpd;
                s.pll = gt >> 13 & 1;
                s.pix = cap & 0x7FF;
                s.lines = cap >> 11 & 0x3FF;
                s.fields_s = (fields - fields_was) & 0xFFFF;
                s.frames_s = ((dstat >> 16) - frames_was) & 0xFFFF;
                s.hist = dstat >> 14 & 1;
                s.llc_khz = (uint32_t)((uint64_t)llc * 800000 / 33554432);     /* 16 x 50 MHz / 2^25 Hz a count */
                fields_was = fields;
                frames_was = dstat >> 16;
            }
        }
        xSemaphoreTake(lock, portMAX_DELAY);
        state = s;
        xSemaphoreGive(lock);
    }
}

void scaler_start(void)
{
    lock = xSemaphoreCreateMutex();
    nvs_handle_t h;
    if (nvs_open("av", NVS_READONLY, &h) == ESP_OK) {
        /* (an older firmware's settings are shorter: they are taken as far as they go) */
        struct scaler_settings s = set;
        size_t n = sizeof s;
        if (nvs_get_blob(h, "video", &s, &n) == ESP_OK && n <= sizeof s)
            set = s;
        nvs_close(h);
    }
    xTaskCreate(task, "scaler", 6144, NULL, 4, NULL);
}

void scaler_get(struct scaler_state *s, struct scaler_settings *v)
{
    xSemaphoreTake(lock, portMAX_DELAY);
    *s = state;
    *v = set;
    xSemaphoreGive(lock);
}

void scaler_set(const struct scaler_settings *v)
{
    nvs_handle_t h;
    xSemaphoreTake(lock, portMAX_DELAY);
    if (v->ntsc != set.ntsc || (v->on && !set.on))
        again = true;                   /* the clocks change: everything again */
    set = *v;
    dirty = true;
    xSemaphoreGive(lock);
    if (nvs_open("av", NVS_READWRITE, &h) == ESP_OK) {
        nvs_set_blob(h, "video", v, sizeof *v);
        nvs_commit(h);
        nvs_close(h);
    }
}

void scaler_tune(void)
{
    xSemaphoreTake(lock, portMAX_DELAY);
    tune = true;
    xSemaphoreGive(lock);
}

void scaler_measure(void)
{
    xSemaphoreTake(lock, portMAX_DELAY);
    measure = true;
    xSemaphoreGive(lock);
}

void scaler_again(void)
{
    xSemaphoreTake(lock, portMAX_DELAY);
    again = true;
    xSemaphoreGive(lock);
}
