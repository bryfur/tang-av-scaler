/* gowin.c: a bitstream into the FPGA's SRAM, the whole sequence run by the link. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* How the load goes (web.c: POST /api/load's query):
 *   gap_ms   clocks in Run-Test/Idle for that long between the erase passes
 *   stop_ms  the clock stopped for that long between them
 *   pre_ms   clocks for that long before the bitstream
 *   reverse  each byte's top bit first (the .fs file's order): true
 *   hold     the bitstream without a pause in the clock (the task above all others: Wi-Fi starved
 *            for a minute; the link has reset on it)
 *   spi_hz   the bitstream by the SPI master at this clock (0: bit-banged) */
struct gowin_opt {
    uint32_t gap_ms, stop_ms, pre_ms, spi_hz;
    bool reverse, hold;
};

/* data: the bitstream as the .fs file gives it, each byte's first bit its top one; sum: the 16-bit
 * sum of its configuration words (tools/avx.py works it out as openFPGALoader does).  msg: what
 * happened, a few lines, the last "loaded" or "NOT loaded".  The caller holds the JTAG port
 * (jtag_take). */
bool gowin_load(const uint8_t *data, size_t len, uint16_t sum, const struct gowin_opt *o, char *msg, size_t max);
