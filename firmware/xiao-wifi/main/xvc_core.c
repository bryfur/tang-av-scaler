/* Xilinx Virtual Cable 1.0 [Xilinx XVC protocol, xvcServer.c]:
 *
 *   "getinfo:"                          -> "xvcServer_v1.0:<vector bytes>\n"
 *   "settck:" period (ns, 4 bytes LE)   -> the period set (4 bytes LE)
 *   "shift:"  bits (4 bytes LE), TMS, TDI (each (bits + 7) / 8 bytes, LSB first)
 *                                       -> TDO, as many bytes
 *
 * The length told is the bytes of TMS and TDI together, as Xilinx's server tells it and as
 * openFPGALoader reads it (it sends half of it for each). */

#include "xvc_core.h"

#include <stdio.h>
#include <string.h>

static uint32_t le32(const uint8_t *p)
{
    return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24;
}

int xvc_serve(const struct xvc_io *io, uint8_t *buf, struct xvc_stats *st)
{
    uint8_t cmd[16];
    for (;;) {
        /* "ge", "se", "sh": two letters tell the command, and so how much more to read */
        if (io->rd(io->ctx, cmd, 2))
            return 0;
        if (cmd[0] == 'g' && cmd[1] == 'e') {
            if (io->rd(io->ctx, cmd + 2, 6) || memcmp(cmd, "getinfo:", 8))
                return -1;
            char info[40];
            int n = snprintf(info, sizeof info, "xvcServer_v1.0:%u\n", 2 * XVC_VECTOR);
            if (io->wr(io->ctx, (const uint8_t *)info, n))
                return -1;
        } else if (cmd[0] == 's' && cmd[1] == 'e') {
            if (io->rd(io->ctx, cmd + 2, 5 + 4) || memcmp(cmd, "settck:", 7))
                return -1;
            uint32_t got = io->set_period(le32(cmd + 7));
            uint8_t r[4] = {got, got >> 8, got >> 16, got >> 24};
            if (io->wr(io->ctx, r, 4))
                return -1;
        } else if (cmd[0] == 's' && cmd[1] == 'h') {
            if (io->rd(io->ctx, cmd + 2, 4 + 4) || memcmp(cmd, "shift:", 6))
                return -1;
            uint32_t bits = le32(cmd + 6);
            uint32_t bytes = (bits + 7) / 8;
            if (bits > XVC_VECTOR * 8u)
                return -1;
            if (io->rd(io->ctx, buf, 2 * bytes))
                return -1;
            io->shift(buf, buf + bytes, buf, bits);       /* TDO over TMS */
            if (st) {
                st->bits += bits;
                st->shifts++;
            }
            if (io->wr(io->ctx, buf, bytes))
                return -1;
        } else
            return -1;
    }
}
