/* A bitstream into the FPGA's SRAM by the link itself: POST /api/load (web.c) gives the whole
 * bitstream, and the sequence runs here on jtag_shift(), with nothing of the network in it.
 *
 * Why not only through the XVC port: a PC's loader does the same sequence in small exchanges,
 * each a round trip over Wi-Fi.  After its SRAM is erased a GW5AST-138 tries its flash again
 * about every 100 ms; openFPGALoader's two erase passes took 150 ms over the link (30 ms over a
 * USB cable), and the FPGA was found with "Timeout" and "auto boot 2nd fail" set and took no
 * bitstream after that (2026-11-11: status 0x22638 after every load, DONE off).
 *
 * The sequence is openFPGALoader 1.1.1's for the GW5A family (src/gowin.cpp: programSRAM,
 * eraseSRAM, writeSRAM; Gowin TN653, UG290), which loads this board over a cable:
 *   reload (0x3C) and time for the flash's image; if Timeout, a 2nd boot failure or Bad Command is
 *   flagged: 0x15 0x3F 0x3A 0x02 0x11 0x02; erase (0x15, 0x05, 0x02, 10 ms of clocks, Memory Erase
 *   set, 0x09, 0x02, 0x3A, 0x02) until Done Final is off, twice at least; 0x15 0x12 0x17 and the
 *   bitstream through the data register, first bit first; 0x0A and the 16-bit sum of its
 *   configuration words; 0x08 0x3A 0x02; Done Final. */

#include "gowin.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "esp_task_wdt.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "jtag.h"

#define NOOP 0x02
#define ERASE_SRAM 0x05
#define XFER_DONE 0x09
#define INIT_ADDR 0x12
#define CONFIG_ENABLE 0x15
#define XFER_WRITE 0x17
#define CONFIG_DISABLE 0x3A
#define RELOAD 0x3C

#define ST_BAD_COMMAND (1u << 1)
#define ST_TIMEOUT (1u << 3)
#define ST_BOOT2_FAIL (1u << 4)
#define ST_MEMORY_ERASE (1u << 5)
#define ST_EDIT_MODE (1u << 7)
#define ST_DONE_FINAL (1u << 13)

static void tms_seq(uint32_t bits, uint32_t n)      /* n clocks of TMS (LSB first), TDI low */
{
    uint8_t m[4] = {bits, bits >> 8, bits >> 16, bits >> 24}, d[4] = {0}, q[4];
    jtag_shift(m, d, q, n);
}

static uint32_t scan(uint32_t out, uint32_t n)      /* in a shift state: n bits, left on the last */
{
    uint32_t last = 1u << (n - 1);
    uint8_t m[4] = {last, last >> 8, last >> 16, last >> 24};
    uint8_t d[4] = {out, out >> 8, out >> 16, out >> 24}, q[4] = {0};
    jtag_shift(m, d, q, n);
    return q[0] | q[1] << 8 | q[2] << 16 | (uint32_t)q[3] << 24;
}

static void idle(uint32_t clocks)                   /* clocks in Run-Test/Idle */
{
    static uint8_t z[512], q[512];
    while (clocks) {
        uint32_t n = clocks > sizeof z * 8 ? sizeof z * 8 : clocks;
        memset(z, 0, sizeof z);
        jtag_shift(z, z, q, n);
        clocks -= n;
    }
}

static void idle_us(uint32_t us)
{
    idle((uint64_t)us * 1000 / jtag_period() + 1);
}

static void command(uint8_t ir)                     /* from Run-Test/Idle, back to it; six clocks there */
{
    tms_seq(0x3, 4);                /* Select-DR, Select-IR, Capture-IR, Shift-IR */
    scan(ir, 8);
    tms_seq(0x1, 2);                /* Update-IR, Run-Test/Idle */
    idle(6);
}

static uint32_t read32(uint8_t ir)
{
    command(ir);
    tms_seq(0x1, 3);                /* Select-DR, Capture-DR, Shift-DR */
    uint32_t v = scan(0xFFFFFFFF, 32);
    tms_seq(0x1, 2);                /* Update-DR, Run-Test/Idle */
    return v;
}

static uint32_t status(void)
{
    return read32(GOWIN_STATUS);
}

static bool poll(uint32_t mask, uint32_t value)
{
    for (int k = 0; k < 2000; k++)
        if ((status() & mask) == value)
            return true;
    return false;
}

static int say(char *msg, size_t max, int at, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    if (at < (int)max)
        at += vsnprintf(msg + at, max - at, fmt, ap);
    va_end(ap);
    return at;
}

void gowin_reload(void)
{
    tms_seq(0x1F, 6);               /* Test-Logic-Reset, Run-Test/Idle */
    command(RELOAD);
    command(NOOP);
}

bool gowin_load(const uint8_t *data, size_t len, uint16_t sum, const struct gowin_opt *o, char *msg, size_t max)
{
    uint32_t gap_ms = o->gap_ms, pre_ms = o->pre_ms;
    bool reverse = o->reverse;
    static const uint8_t rev4[16] = {0, 8, 4, 12, 2, 10, 6, 14, 1, 9, 5, 13, 3, 11, 7, 15};
    static uint8_t tdi[2048], tms[2048];
    int at = 0;
    uint32_t st;

    uint32_t check = 0;
    for (size_t k = 0; k < len; k++)
        check = check * 31 + data[k];
    at = say(msg, max, at, "received: %u bytes, check %08x, first %02x %02x %02x %02x, period %u ns\n", (unsigned)len,
             (unsigned)check, data[0], data[1], data[len - 2], data[len - 1], (unsigned)jtag_period());
    tms_seq(0x1F, 6);               /* Test-Logic-Reset, Run-Test/Idle */
    at = say(msg, max, at, "id %08x, status %08x\n", (unsigned)read32(GOWIN_IDCODE), (unsigned)status());

    /* the flash's image again, and time for it (a second of clocks at most) */
    command(RELOAD);
    command(NOOP);
    for (int k = 0; k < 10 && !((st = status()) & ST_DONE_FINAL); k++)
        idle_us(100000);
    st = status();
    at = say(msg, max, at, "after the reload %08x\n", (unsigned)st);

    if (st & (ST_TIMEOUT | ST_BOOT2_FAIL | ST_BAD_COMMAND)) {
        command(CONFIG_ENABLE);
        command(0x3F);
        command(CONFIG_DISABLE);
        command(NOOP);
        command(GOWIN_IDCODE);
        command(NOOP);
        idle(1000);
    }
    for (int pass = 0;; pass++) {
        command(CONFIG_ENABLE);
        if (!poll(ST_EDIT_MODE, ST_EDIT_MODE)) {
            say(msg, max, at, "erase: no edit mode, status %08x\n", (unsigned)status());
            return false;
        }
        command(ERASE_SRAM);
        command(NOOP);
        idle_us(10000);
        if (!poll(ST_MEMORY_ERASE, ST_MEMORY_ERASE)) {
            say(msg, max, at, "erase: not done, status %08x\n", (unsigned)status());
            return false;
        }
        command(XFER_DONE);
        command(NOOP);
        command(CONFIG_DISABLE);
        command(NOOP);
        if (!poll(ST_EDIT_MODE, 0)) {
            say(msg, max, at, "erase: edit mode stays, status %08x\n", (unsigned)status());
            return false;
        }
        st = status();
        at = say(msg, max, at, "erase pass %d: %08x\n", pass + 1, (unsigned)st);
        if ((pass >= 1 && !(st & ST_DONE_FINAL)) || pass == 5)
            break;
        if (gap_ms)
            idle_us(gap_ms * 1000);
        if (o->stop_ms)                     /* the clock stopped: other tasks run */
            vTaskDelay(pdMS_TO_TICKS(o->stop_ms));
    }
    if (pre_ms)
        idle_us(pre_ms * 1000);
    at = say(msg, max, at, "before the bitstream %08x\n", (unsigned)status());

    /* The bitstream in one run of clocks, nothing let in between (o->hold): above every task, the
     * idle task's watchdog off for the while.  Wi-Fi gets no time and may lose its network for the
     * minute; it joins again by itself afterwards. */
    UBaseType_t prio = uxTaskPriorityGet(NULL);
    if (o->hold) {
        esp_task_wdt_delete(xTaskGetIdleTaskHandleForCore(0));
        vTaskPrioritySet(NULL, configMAX_PRIORITIES - 1);
    }
    command(CONFIG_ENABLE);
    command(INIT_ADDR);
    command(XFER_WRITE);
    tms_seq(0x1, 3);                /* Select-DR, Capture-DR, Shift-DR */
    memset(tms, 0, sizeof tms);
    size_t done = 0;
    if (o->spi_hz && reverse && len > 64 && jtag_bulk_begin(o->spi_hz)) {
        /* all but the last byte by the SPI master (jtag.c); the last here, its last bit with TMS */
        jtag_bulk_send(data, len - 1);
        jtag_bulk_end();
        done = len - 1;
        at = say(msg, max, at, "the bitstream by SPI at %u Hz\n", (unsigned)o->spi_hz);
    }
    while (done < len) {
        size_t n = len - done > sizeof tdi ? sizeof tdi : len - done;
        for (size_t k = 0; k < n; k++)      /* a byte's first bit is its top one; jtag_shift's the low one */
            tdi[k] = reverse ? rev4[data[done + k] & 15] << 4 | rev4[data[done + k] >> 4] : data[done + k];
        done += n;
        if (done == len)
            tms[n - 1] = 0x80;              /* the last bit leaves Shift-DR */
        jtag_shift(tms, tdi, tdi, n * 8);
        if (!o->hold && (done & 0xFFFF) < sizeof tdi)
            vTaskDelay(1);                  /* the idle task its turn (the watchdog), each 64 KB */
    }
    tms_seq(0x1, 2);                /* Update-DR, Run-Test/Idle */
    command(0x0A);
    tms_seq(0x1, 3);
    scan(sum, 32);
    tms_seq(0x1, 2);
    command(0x08);
    command(CONFIG_DISABLE);
    command(NOOP);
    st = status();
    if (o->hold) {
        vTaskPrioritySet(NULL, prio);
        esp_task_wdt_add(xTaskGetIdleTaskHandleForCore(0));
    }
    at = say(msg, max, at, "after the bitstream %08x, user code %08x\n", (unsigned)st, (unsigned)read32(GOWIN_USERCODE));
    bool ok = (st & ST_DONE_FINAL) && !(st & (ST_TIMEOUT | ST_BAD_COMMAND | 1u));
    say(msg, max, at, ok ? "loaded\n" : "NOT loaded\n");
    return ok;
}
