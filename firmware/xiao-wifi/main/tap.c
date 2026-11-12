/* Scans the firmware makes by itself (the web page's "FPGA" lines), on jtag_shift(): no chip
 * registers here, so test/ runs the same code against its model TAP. */

#include "jtag.h"

/* n clocks of TMS (LSB first), TDI low */
static void tms_seq(uint32_t bits, uint32_t n)
{
    uint8_t m[4] = {bits, bits >> 8, bits >> 16, bits >> 24}, d[4] = {0}, q[4];
    jtag_shift(m, d, q, n);
}

static uint32_t scan(uint32_t out, uint32_t n)      /* in Shift-IR or Shift-DR: n bits, leaves it on the last */
{
    uint32_t last = 1u << (n - 1);
    uint8_t m[4] = {last, last >> 8, last >> 16, last >> 24};
    uint8_t d[4] = {out, out >> 8, out >> 16, out >> 24}, q[4] = {0};
    jtag_shift(m, d, q, n);
    return q[0] | q[1] << 8 | q[2] << 16 | (uint32_t)q[3] << 24;
}

uint32_t jtag_gowin_read(uint8_t ir)
{
    tms_seq(0x1F, 6);               /* Test-Logic-Reset, Run-Test/Idle: the TAP only, not the FPGA */
    tms_seq(0x3, 4);                /* Select-DR, Select-IR, Capture-IR, Shift-IR */
    scan(ir, 8);
    tms_seq(0x1, 2);                /* Update-IR, Run-Test/Idle */
    tms_seq(0, 8);                  /* (Gowin: some clocks in Run-Test/Idle after an instruction) */
    tms_seq(0x1, 3);                /* Select-DR, Capture-DR, Shift-DR */
    uint32_t v = scan(0, 32);
    tms_seq(0x1, 2);                /* Update-DR, Run-Test/Idle */
    return v;
}
