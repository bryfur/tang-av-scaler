/* The scaler and the link.
 *
 * The FPGA's own CPU (gateware/rtl/cpu.v, its program gateware/sw) brings the board up, looks after
 * it and holds the settings; the link relays over the SPI port (link.c, gateware/sw/link.h): the
 * settings kept in NVS given to a CPU that has just begun, the web page's changes and commands
 * passed on, what the CPU says shown; and the CPU's program itself, if the copy built into this
 * firmware is newer than the one that runs (cpu_second()).  The board standing by (its image
 * halted: standby_load()) and its waking are the link's.
 *
 * (Before the CPU, the link brought the board up itself through the FPGA's UART monitor: the clock
 * chip, the decoder, the picture's settings, the crop and the sampling phase.  That went in
 * 2026-11-16: an image without the CPU is not run by the link; the host tools in gateware/tools
 * still reach the monitor over the console's TCP port.) */

#include <stdio.h>
#include <string.h>

#include "app.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "board.h"
#include "driver/gpio.h"
#include "gowin.h"
#include "miniz.h"
#include "jtag.h"
#include "link.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "nvs.h"

static const char *TAG = "scaler";

/* (the FPGA's registers the link reads itself, over the SPI port: gateware/rtl/top.v) */
enum { R_ID = 0x00, R_FREQ = 0x10, R_MODE = 0x25 };
#define MAGIC 0x31425641u

static struct scaler_state state;
static struct scaler_settings set;      /* (scaler_start: the defaults, then what was kept) */
static SemaphoreHandle_t lock;          /* set, state */
static bool again, measure, tune;
static bool cpu_mode;                   /* the FPGA's CPU runs the scaler */

/* ---- the FPGA's CPU runs the scaler: the link relays ---- */
extern const uint8_t cpu_bin_start[] asm("_binary_cpu_bin_start");
extern const uint8_t cpu_bin_end[] asm("_binary_cpu_bin_end");

static struct link_settings to_link(const struct scaler_settings *v)
{
    struct link_settings l = {.on = v->on, .ntsc = v->ntsc, .mode = v->mode, .thr = v->thr, .aa = v->aa,
                              .aa_thr = v->aa_thr, .sharp = v->sharp, .swap = v->swap, .top1 = v->top1,
                              .pattern = v->pattern, .freeze = v->freeze, .audio = v->audio, .aa_dbg = v->aa_dbg,
                              .aa_diag = v->aa_diag, .aa_corner = v->aa_corner, .crop = v->crop, .wide = v->wide,
                              .nr = v->nr, .dn = v->dn, .phase = v->phase, .osd = v->osd, .flock = !v->nolock, .lowlat = v->lowlat, .surround = v->surround, .table = v->table, .mv_dbg = v->mv_dbg, .net = v->net, .aa_keep = v->aa_keep,
                              .crop_x = v->crop_x, .crop_w = v->crop_w, .crop_y = v->crop_y, .crop_h = v->crop_h};
    return l;
}

static struct scaler_settings from_link(const struct link_settings *l)
{
    struct scaler_settings v = {.on = l->on, .ntsc = l->ntsc, .mode = l->mode, .thr = l->thr, .aa = l->aa,
                                .aa_thr = l->aa_thr, .sharp = l->sharp, .swap = l->swap, .top1 = l->top1,
                                .pattern = l->pattern, .freeze = l->freeze, .audio = l->audio, .aa_dbg = l->aa_dbg,
                                .aa_diag = l->aa_diag, .aa_corner = l->aa_corner, .crop = l->crop, .wide = l->wide,
                                .nr = l->nr, .dn = l->dn, .phase = l->phase, .osd = l->osd, .nolock = !l->flock, .lowlat = l->lowlat, .surround = l->surround, .table = l->table, .mv_dbg = l->mv_dbg, .net = l->net, .aa_keep = l->aa_keep,
                                .crop_x = l->crop_x, .crop_w = l->crop_w, .crop_y = l->crop_y, .crop_h = l->crop_h};
    return v;
}

void scaler_defaults(struct scaler_settings *v)
{
    /* (the FPGA's CPU's own: one table of them for both sides) */
    static const struct link_settings d = LINK_SETTINGS_DEFAULT;
    *v = from_link(&d);
}

static void save(const struct scaler_settings *v)
{
    /* (only what has changed: the flash's work holds every interrupt off for a while; compared as
     * the CPU has them: that form has no gaps) */
    static struct link_settings kept;
    static bool have;
    struct link_settings now = to_link(v);
    nvs_handle_t h;
    if (have && !memcmp(&kept, &now, sizeof kept))
        return;
    kept = now;
    have = true;
    if (nvs_open("av", NVS_READWRITE, &h) == ESP_OK) {
        nvs_set_blob(h, "video", v, sizeof *v);
        nvs_commit(h);
        nvs_close(h);
    }
}

static bool cmd(uint8_t c)
{
    const uint8_t rq[2] = {LINK_CMD, c};
    uint8_t a[4];
    return link_msg(rq, 2, a, sizeof a, 500) >= 1 && a[0] == (LINK_CMD | 0x80);
}

static bool set_all(const struct scaler_settings *v)
{
    uint8_t rq[1 + sizeof(struct link_settings)], a[4];
    struct link_settings l = to_link(v);
    rq[0] = LINK_SET_ALL;
    memcpy(rq + 1, &l, sizeof l);
    return link_msg(rq, sizeof rq, a, sizeof a, 500) >= 1 && a[0] == (LINK_SET_ALL | 0x80);
}

/* a second of it; false: this FPGA image has no SPI port (no CPU): the old way */
/* After a power-on the transmit clock (lane 0's word clock: the whole picture runs on it) can come
 * up at some 61 MHz for 148.5: the FPGA configured itself before the clock generator ran (it has no
 * clock until the CPU sets it), and the lanes' resets do not clear it; an FPGA that configures with
 * the reference running is right (seen 2026-11-12: a receiver found no signal, 25 frames a second).
 * So: the output up, the reference there and the transmit clock not at it for four seconds running:
 * the FPGA loads its flash's image again, by JTAG.  Three times at most. */
static void transmit_check(const struct link_status *ls, bool host)
{
    static int bad, reloads;
    uint32_t mode, tx, ref;
    if (host || !ls->up_ok || !link_reg_read(R_MODE, &mode) || mode != 1 || !link_reg_read(R_FREQ + 2, &tx) ||
        !link_reg_read(R_FREQ + 3, &ref)) {
        bad = 0;
        return;
    }
    /* (fmeter.v's counts: 23.84 Hz a step; 4200000 is 100 MHz) */
    if (ref < 4200000 || (tx > ref ? tx - ref : ref - tx) < ref / 64) {
        bad = 0;
        return;
    }
    if (++bad < 4)
        return;
    bad = 0;
    if (reloads >= 3) {
        if (reloads++ == 3)
            ESP_LOGE(TAG, "the transmit clock is still wrong (%u for %u): no more reloads", (unsigned)tx, (unsigned)ref);
        return;
    }
    if (!jtag_take(false))
        return;                         /* (a PC has the JTAG port: its business) */
    gowin_reload();
    jtag_give();
    reloads++;
    ESP_LOGW(TAG, "the transmit clock at %u kHz for %u: the FPGA loads its image again (%d)",
             (unsigned)((uint64_t)tx * 800000 >> 25), (unsigned)((uint64_t)ref * 800000 >> 25), reloads);
}

/* ---- standing by ----
 * The board's supply has no switch: to stand by, the FPGA is given another image
 * (gateware/standby/standby.v: no clock, the HDMI redriver, the decoder and the DDR3 held off, the
 * carrier's LEDs dark, the buttons passed on to this link's interrupt line), carried here
 * deflated; to wake, the FPGA loads its flash's image again (RECONFIG's button does the same). */
extern const uint8_t sby_start[] asm("_binary_standby_z_start");
extern const uint8_t sby_end[] asm("_binary_standby_z_end");
static bool halt_want, halted;         /* stand by asked for from the page; the FPGA has the standby image */

static uint16_t sby_sum(void)
{
    uint16_t v;
    memcpy(&v, sby_start + 8, 2);
    return v;
}

/* the standby image into the FPGA (a minute: bit by bit); true: it is the one there now */
static bool standby_load(void)
{
    uint32_t len;
    size_t in = sby_end - sby_start - 12, out;
    char msg[500];
    bool ok = false;
    memcpy(&len, sby_start + 4, 4);
    out = len;
    uint8_t *buf = heap_caps_malloc(len, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    tinfl_decompressor *d = heap_caps_malloc(sizeof *d, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (buf && d) {
        tinfl_init(d);
        ok = tinfl_decompress(d, sby_start + 12, &in, buf, buf, &out, TINFL_FLAG_PARSE_ZLIB_HEADER |
                              TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF) == TINFL_STATUS_DONE && out == len;
    }
    free(d);
    if (ok && jtag_take(false)) {
        const struct gowin_opt o = {.reverse = true};
        ok = gowin_load(buf, len, sby_sum(), &o, msg, sizeof msg);
        jtag_give();
        ESP_LOGW(TAG, "stand by: the standby image %s", ok ? "is in the FPGA" : "did NOT go in");
    } else
        ok = false;
    free(buf);
    return ok;
}

static bool cpu_second(struct scaler_state *s)
{
    static uint32_t up_was;
    static int silent;
    static bool given;                  /* this CPU run has our settings */
    static bool seen_cpu;
    static int halt_tries;
    const uint8_t rq = LINK_STATUS;
    uint8_t a[1 + sizeof(struct link_status) + 8];      /* (room for more: a longer status is not ours) */
    struct link_status ls;
    struct scaler_settings mine;
    uint32_t id, built = 0;
    bool redo, meas, tun, host = console_busy();
    if (!link_reg_read(R_ID, &id) || id != MAGIC)
        return false;
    s->fpga = true;
    s->host = host;
    memcpy(&built, cpu_bin_start + 8, 4);
    bool alive = link_msg(&rq, 1, a, sizeof a, 300) == 1 + (int)sizeof ls && a[0] == (LINK_STATUS | 0x80);
    if (alive)
        memcpy(&ls, a + 1, sizeof ls);
    /* the CPU's program: ours if none answers (two seconds running), or the one that does is older */
    /* (not while a host tool is at it: it may be loading one itself: gateware/tools/cpu.py) */
    if (host)
        silent = 0;
    else if (alive ? ls.magic != LINK_MAGIC || ls.build < built : ++silent >= 2) {
        link_program(cpu_bin_start, cpu_bin_end - cpu_bin_start);
        silent = 0;
        given = false;
        seen_cpu = false;
        return true;
    }
    if (!alive)
        return true;
    silent = 0;
    /* stand by: asked by the board's button (the CPU says so) or by the page: the FPGA's configuration
     * taken away, once nothing waits to be kept in the board's flash (ten seconds for that at most) */
    if ((ls.standby || halt_want) && !host) {
        if (!(ls.store & LINK_STORE_BUSY) || ++halt_tries > 10) {
            halt_tries = 0;
            halt_want = false;
            halted = standby_load();
            if (halted) {
                s->fpga = false;
                return false;
            }
        }
    } else
        halt_tries = 0;
    if (host != (ls.host != 0))
        cmd(host ? LINK_CMD_HOST_ON : LINK_CMD_HOST_OFF);
    /* the settings: ours to a CPU that has just begun; after that the CPU's are the ones that count
     * (a tuned sampling phase): kept */
    xSemaphoreTake(lock, portMAX_DELAY);
    mine = set;
    redo = again, meas = measure, tun = tune;
    again = measure = tune = false;
    xSemaphoreGive(lock);
    /* (a board that keeps its own settings, gateware/sw/store.c: those count from its start, and ours
     * are only a copy; one that keeps none yet, or has no flash of its own: ours, as before) */
    bool cpu_new = ls.up_s < up_was || !seen_cpu;
    seen_cpu = true;
    if (!(ls.store & LINK_STORE_SET) && (!given || ls.up_s < up_was || ls.gen == 0)) {
        given = set_all(&mine);
        ESP_LOGI(TAG, "the CPU (program %u): the settings %s", (unsigned)ls.build, given ? "given" : "NOT taken");
    } else {
        given = true;
        struct link_settings l = to_link(&mine);
        if (memcmp(&l, &ls.set, sizeof l)) {
            mine = from_link(&ls.set);
            xSemaphoreTake(lock, portMAX_DELAY);
            set = mine;
            xSemaphoreGive(lock);
            save(&mine);
        }
    }
    up_was = ls.up_s;
    transmit_check(&ls, host);
    if (redo)
        cmd(LINK_CMD_AGAIN);
    if (meas)
        cmd(LINK_CMD_MEASURE);
    if (tun)
        cmd(LINK_CMD_TUNE);
    s->cpu = true;
    s->relay = true;
    s->cpu_build = ls.build;
    s->ok = ls.up_ok;
    s->hpd = ls.hpd;
    s->pll = ls.pll;
    s->hist = ls.hist;
    s->host = host || ls.host;
    s->build = ls.fpga_build;
    s->ups = ls.ups;
    s->pix = ls.pix;
    s->lines = ls.lines;
    s->fields_s = ls.fields_s;
    s->frames_s = ls.frames_s;
    s->llc_khz = ls.llc_hz / 1000;
    s->show_x = ls.show_x, s->show_w = ls.show_w, s->show_y = ls.show_y, s->show_h = ls.show_h;
    s->tune = tun ? 1 : ls.tune;
    s->tune_gain = ls.tune_gain;
    s->temp4 = ls.temp4;
    s->delay_us10 = ls.delay_us10;
    s->lock = ls.lock;
    s->lock_err = ls.lock_err;
    s->lock_ppm10 = ls.lock_ppm10;
    s->ll = ls.ll;
    s->ll_lines = ls.ll_lines;
    s->in_std = ls.in_std, s->in_ok = ls.in_ok, s->in_lines = ls.in_lines, s->in_hz100 = ls.in_hz100;
    s->pan = ls.pan, s->pan_dx = ls.pan_dx, s->pan_dy = ls.pan_dy, s->pan_ms10 = ls.pan_ms10;
    s->tab_have = ls.tab_have, s->tab_slot = ls.tab_slot, s->tab_state = ls.tab_state, s->tab_bad = ls.tab_bad, s->tab_ms = ls.tab_ms;
    s->net_there = ls.net_there, s->net_under = ls.net_under, s->net_state = ls.net_state, s->store = ls.store;
    tables_second(ls.tab_have, ls.tab_state, cpu_new, ls.net_state);
    return true;
}

bool scaler_cpu(void)
{
    return cpu_mode;
}

static void task(void *arg)
{
    int tick = 0, low = 0, dead = 0;
    bool ps_on = false;
    for (;;) {
        /* standing by: a button on the board (the standby image passes them on: the interrupt line
         * low while one is pressed) wakes it; looked at ten times a second, the rest once a second */
        if (halted) {
            vTaskDelay(pdMS_TO_TICKS(100));
            low = gpio_get_level(PIN_IRQ) ? 0 : low + 1;
            if (low == 3) {
                ESP_LOGW(TAG, "wake: a button on the board");
                scaler_standby(false);
                vTaskDelay(pdMS_TO_TICKS(1000));
            }
            if (++tick % 10)
                continue;
        } else
            vTaskDelay(pdMS_TO_TICKS(1000));
        if (halted != ps_on) {          /* (the radio saves power while the board stands by, and only then:
                                         * with it a load over the network's JTAG port fails: wifi.c) */
            ps_on = halted;
            wifi_power_save(ps_on);
        }
        struct scaler_state s = {0};
        crumb[0] = 1;
        if (web_loading())              /* (the FPGA is being loaded: nothing asked of it) */
            continue;
        crumb[0] = 2;
        cpu_mode = cpu_second(&s);
        crumb[0] = 3;
        if (cpu_mode)
            halted = false, dead = 0;
        else {
            /* (nothing answers: standing by?  The RECONFIG button, the power, or a wake from here end
             * it.  And a link that begins while the board stands by: nothing answers for three
             * seconds, and the image there is the standby one by its user code) */
            s.host = console_busy();
            if (!halted && !s.host && ++dead == 3 && jtag_take(false)) {
                halted = (gowin_usercode() & 0xFFFF) == sby_sum();
                jtag_give();
            }
        }
        s.standby = halted;
        xSemaphoreTake(lock, portMAX_DELAY);
        state = s;
        xSemaphoreGive(lock);
    }
}

void scaler_standby(bool on)
{
    if (on) {
        halt_want = true;
        return;
    }
    halt_want = false;
    if (jtag_take(false)) {
        gowin_reload();
        jtag_give();
        halted = false;
        ESP_LOGW(TAG, "wake: the FPGA loads its flash's image");
    }
}

void scaler_start(void)
{
    lock = xSemaphoreCreateMutex();
    scaler_defaults(&set);
    nvs_handle_t h;
    if (nvs_open("av", NVS_READONLY, &h) == ESP_OK) {
        /* (an older firmware's settings are shorter: they are taken as far as they go) */
        struct scaler_settings s = set;
        size_t n = sizeof s;
        if (nvs_get_blob(h, "video", &s, &n) == ESP_OK && n <= sizeof s)
            set = s;
        nvs_close(h);
    }
    tables_start();
    link_start();
    xTaskCreate(task, "scaler", 8192, NULL, 4, NULL);
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
    /* (to the CPU first: it applies them, and they are its own from here; then our copy, which
     * follows the CPU's) */
    if (cpu_mode)
        set_all(v);
    xSemaphoreTake(lock, portMAX_DELAY);
    set = *v;
    xSemaphoreGive(lock);
    save(v);
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
