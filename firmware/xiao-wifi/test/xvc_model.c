/* The firmware's XVC server (main/xvc_core.c) and its own scans (main/tap.c) on a PC, against a
 * model of the FPGA's TAP: test/run.sh points openFPGALoader at it.
 *
 *   xvc_model PORT        serve one client after another on PORT; a line of counts after each
 *   xvc_model self        main/tap.c's scans against the model: the ID code and status it reads
 *
 * The model: one TAP, an 8-bit instruction register, Gowin's instructions 0x11 (ID code), 0x41
 * (status), 0x13 (user code), 32 bits each; anything else is BYPASS.  The status register follows
 * the instructions as far as openFPGALoader's SRAM load looks at it [openFPGALoader gowin.cpp]:
 * 0x15/0x3A set and clear "edit mode", 0x05 erases (DONE off, "memory erase" on), 0x17 takes the
 * bitstream (its bits counted), and DONE comes back when edit mode is left after a bitstream. */

#include <arpa/inet.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#include "jtag.h"
#include "xvc_core.h"

#define IDCODE 0x0001081b           /* GW5AST-138 */
#define USERCODE 0x12345678
#define ST_ERASE (1u << 5)
#define ST_EDIT (1u << 7)
#define ST_DONE (1u << 13)
static uint32_t status_reg = 0x0003f020;        /* running the flash's image: DONE, READY, valid */
static unsigned long long stream_bits;
static int stream_loaded;

enum { TLR, RTI, SEL_DR, CAP_DR, SH_DR, EX1_DR, PAU_DR, EX2_DR, UPD_DR, SEL_IR, CAP_IR, SH_IR, EX1_IR, PAU_IR, EX2_IR, UPD_IR };
static const unsigned char next[16][2] = {
    [TLR] = {RTI, TLR},       [RTI] = {RTI, SEL_DR},    [SEL_DR] = {CAP_DR, SEL_IR}, [CAP_DR] = {SH_DR, EX1_DR},
    [SH_DR] = {SH_DR, EX1_DR}, [EX1_DR] = {PAU_DR, UPD_DR}, [PAU_DR] = {PAU_DR, EX2_DR}, [EX2_DR] = {SH_DR, UPD_DR},
    [UPD_DR] = {RTI, SEL_DR},  [SEL_IR] = {CAP_IR, TLR},  [CAP_IR] = {SH_IR, EX1_IR},  [SH_IR] = {SH_IR, EX1_IR},
    [EX1_IR] = {PAU_IR, UPD_IR}, [PAU_IR] = {PAU_IR, EX2_IR}, [EX2_IR] = {SH_IR, UPD_IR}, [UPD_IR] = {RTI, SEL_DR}};

static int state = TLR, ir = 0x11, dr_len = 32;
static unsigned long long sr;
static unsigned long resets, ir_updates;
static unsigned period = 1000;

static int clock_tap(int tms, int tdi)
{
    int tdo = 1;                    /* not driven outside the shift states: the pull-up */
    if (state == SH_DR || state == SH_IR) {
        int len = state == SH_IR ? 8 : dr_len;
        tdo = sr & 1;
        sr = sr >> 1 | (unsigned long long)tdi << (len - 1);
        if (state == SH_DR && ir == 0x17)
            stream_bits++;
    } else if (state == CAP_IR)
        sr = 0x01;
    else if (state == CAP_DR) {
        dr_len = ir == 0x11 || ir == 0x41 || ir == 0x13 ? 32 : 1;
        sr = ir == 0x11 ? IDCODE : ir == 0x41 ? status_reg : ir == 0x13 ? USERCODE : 0;
    }
    state = next[state][tms];
    if (state == UPD_IR) {
        ir = sr & 0xFF;
        ir_updates++;
        if (ir == 0x15)
            status_reg |= ST_EDIT;
        else if (ir == 0x3A) {
            status_reg &= ~ST_EDIT;
            if (stream_loaded)
                status_reg |= ST_DONE;
        } else if (ir == 0x05) {
            status_reg = (status_reg | ST_ERASE) & ~ST_DONE;
            stream_loaded = 0;
        } else if (ir == 0x17) {
            stream_bits = 0;
            stream_loaded = 1;
        }
    } else if (state == TLR) {
        if (ir != 0x11 || tms == 0)
            resets++;
        ir = 0x11;
    }
    return tdo;
}

void jtag_shift(const uint8_t *tms, const uint8_t *tdi, uint8_t *tdo, uint32_t nbits)
{
    for (uint32_t i = 0; i < nbits; i += 8) {
        unsigned m = tms[i >> 3], d = tdi[i >> 3], q = 0;
        for (uint32_t b = 0; b < 8 && i + b < nbits; b++)
            q |= clock_tap(m >> b & 1, d >> b & 1) << b;
        tdo[i >> 3] = q;
    }
}

static uint32_t set_period(uint32_t ns)
{
    return period = ns < 100 ? 100 : ns;
}

static int rd(void *ctx, uint8_t *buf, size_t n)
{
    while (n) {
        ssize_t r = recv(*(int *)ctx, buf, n, 0);
        if (r <= 0)
            return -1;
        buf += r;
        n -= r;
    }
    return 0;
}

static int wr(void *ctx, const uint8_t *buf, size_t n)
{
    while (n) {
        ssize_t r = send(*(int *)ctx, buf, n, MSG_NOSIGNAL);
        if (r <= 0)
            return -1;
        buf += r;
        n -= r;
    }
    return 0;
}

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "self")) {
        uint32_t id = jtag_gowin_read(GOWIN_IDCODE), st = jtag_gowin_read(GOWIN_STATUS),
                 uc = jtag_gowin_read(GOWIN_USERCODE);
        printf("idcode %08x status %08x usercode %08x\n", id, st, uc);
        return id == IDCODE && st == status_reg && uc == USERCODE ? 0 : 1;
    }
    if (argc != 2)
        return 2;
    static uint8_t buf[2 * XVC_VECTOR];
    int ls = socket(AF_INET, SOCK_STREAM, 0), one = 1;
    setsockopt(ls, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    struct sockaddr_in a = {.sin_family = AF_INET, .sin_port = htons(atoi(argv[1])), .sin_addr.s_addr = htonl(INADDR_ANY)};
    if (bind(ls, (struct sockaddr *)&a, sizeof a) || listen(ls, 1)) {
        perror("listen");
        return 1;
    }
    for (;;) {
        int fd = accept(ls, NULL, NULL);
        if (fd < 0)
            return 1;
        setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
        struct xvc_stats st = {0};
        const struct xvc_io io = {.ctx = &fd, .rd = rd, .wr = wr, .shift = jtag_shift, .set_period = set_period};
        ir_updates = 0;
        int rc = xvc_serve(&io, buf, &st);
        close(fd);
        printf("client: rc %d, %u shifts, %llu bits, %lu instructions, period %u ns; bitstream %llu bits, status %08x\n",
               rc, st.shifts, (unsigned long long)st.bits, ir_updates, period, stream_bits, status_reg);
        fflush(stdout);
    }
}
