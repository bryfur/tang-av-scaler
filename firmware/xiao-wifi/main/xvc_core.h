/* Xilinx Virtual Cable 1.0, the server's side, on any byte stream and any JTAG (the firmware's
 * socket and pins; test/'s socket and a model TAP). */
#pragma once
#include <stddef.h>
#include <stdint.h>

#define XVC_VECTOR 16384            /* bytes of TMS (and of TDI) one shift may carry */

struct xvc_io {
    void *ctx;
    int (*rd)(void *ctx, uint8_t *buf, size_t n);          /* all n bytes: 0, or -1 (closed, error) */
    int (*wr)(void *ctx, const uint8_t *buf, size_t n);    /* all n bytes: 0, or -1 */
    void (*shift)(const uint8_t *tms, const uint8_t *tdi, uint8_t *tdo, uint32_t nbits);
    uint32_t (*set_period)(uint32_t ns);                   /* returns the period it got */
};

struct xvc_stats {
    uint64_t bits;
    uint32_t shifts;
};

/* Serves one client until it closes or sends something that is not XVC.  buf: 2 x XVC_VECTOR
 * bytes.  Returns 0 when the client closed between commands, -1 otherwise. */
int xvc_serve(const struct xvc_io *io, uint8_t *buf, struct xvc_stats *st);
