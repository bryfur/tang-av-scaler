/* The scaler's CPU (the SOM's hard core, an Andes A25: rtl/cpu.v): what need not be logic.  It
 * brings the board up and looks after it (board.c), holds the settings (the link keeps a copy for
 * when the power is off), writes the on-screen text (osd.c), and answers the link (the XIAO, over
 * rtl/spis.v's SPI port: link.h).  No operating system: a loop, and waits that keep answering.
 *
 * For a host on the monitor: register 64 counts up while this runs, 65 says what it is, 66 and 67
 * a trap's cause and place (boot.S).
 */
#include "hw.h"

#ifndef BUILD
#define BUILD 0
#endif

static uint8_t rq[256];                 /* a request */
static uint32_t txw;                    /* the answer's bytes, a word at a time */
static int txn;

static void tx_begin(void)
{
    REG(R_SPITXA) = 0;
    txn = 0;
    txw = 0;
}

static void tx(uint8_t b)
{
    txw |= (uint32_t)b << 8 * (txn & 3);
    if ((++txn & 3) == 0) {
        REG(R_SPITXD) = txw;
        txw = 0;
    }
}

static void tx_bytes(const void *p, int n)
{
    for (int k = 0; k < n; k++)
        tx(((const uint8_t *)p)[k]);
}

/* (the answer there, the request done with) */
static void tx_end(void)
{
    if (txn & 3)
        REG(R_SPITXD) = txw;
    REG(R_SPIS) = 3u | (uint32_t)txn << 16;
}

/* pixels of the picture as it goes out (rtl/grab.v takes eight rows of a frame: row, row + step,
 * ...): the eight with this row in them asked for if they are not the ones there */
static void grab(int step, int y, int x, int n)
{
    static int have_y = -1, have_step;
    int first = y - y % 8;
    board_grab_seen();
    if (have_step != step || have_y != first) {
        uint32_t t = ms();
        REG(R_GRAB) = (uint32_t)step << 12 | (uint32_t)(first * step);
        while (!(REG(R_GRAB) >> 31) && ms() - t < 100)
            ;
        have_step = step;
        have_y = first;
    }
    for (int k = 0; k < n; k++) {
        REG(R_GRABD) = (uint32_t)(y - first) << 11 | (uint32_t)((x + k) * step);
        uint32_t p = REG(R_GRABD);
        tx(p);
        tx(p >> 8);
        tx(p >> 16);
    }
}

void service(void)
{
    static bool busy;
    uint32_t s = REG(R_SPIS);
    int n = s >> 8 & 0xFF;
    if (!(s & 1) || busy)
        return;
    busy = true;
    for (int k = 0; k < (n + 3) / 4; k++) {
        uint32_t w;
        REG(R_SPIRX) = k;
        w = REG(R_SPIRX);
        rq[4 * k] = w;
        rq[4 * k + 1] = w >> 8;
        rq[4 * k + 2] = w >> 16;
        rq[4 * k + 3] = w >> 24;
    }
    tx_begin();
    tx(rq[0] | 0x80);
    switch (rq[0]) {
    case LINK_STATUS:
        st.set = set;
        tx_bytes(&st, sizeof st);
        break;
    case LINK_SET_ALL:
        if (n == 1 + (int)sizeof set) {
            struct link_settings was = set;
            __builtin_memcpy(&set, rq + 1, sizeof set);
            board_apply(&was);
        }
        break;
    case LINK_SET_ONE:
        if (n == 5 && rq[1] + rq[2] <= sizeof set && (rq[2] == 1 || rq[2] == 2)) {
            struct link_settings was = set;
            ((uint8_t *)&set)[rq[1]] = rq[3];
            if (rq[2] == 2)
                ((uint8_t *)&set)[rq[1] + 1] = rq[4];
            board_apply(&was);
        }
        break;
    case LINK_CMD:
        if (n == 2)
            board_cmd(rq[1]);
        break;
    case LINK_GRAB: {
        int step = rq[1], y = rq[2] | rq[3] << 8, x = rq[4] | rq[5] << 8, px = rq[6] | rq[7] << 8;
        if (n == 8 && step >= 1 && step <= 8 && px <= 680)
            grab(step, y, x, px);
        break;
    }
    default:
        tx_begin();
        tx(LINK_BAD);
    }
    tx_end();
    busy = false;
}

void *memcpy(void *d, const void *s, size_t n)
{
    for (size_t k = 0; k < n; k++)
        ((uint8_t *)d)[k] = ((const uint8_t *)s)[k];
    return d;
}

int main(void)
{
    uint32_t t_sec, t_osd, t_lock, n = 0;

    REG(R_CPUM + 1) = LINK_MAGIC;
    REG(R_SPIS) = 1;                    /* (a request from before this began: gone) */
    st.build = BUILD;
    osd_init();
    board_init();
    t_sec = t_osd = t_lock = ms();
    for (;;) {
        service();
        if (ms() - t_lock >= 100) {
            t_lock = ms();
            board_lock();
        }
        if (ms() - t_osd >= 250) {
            t_osd += 250;
            REG(R_CPUM) = ++n;
            osd_update();
        }
        if (ms() - t_sec >= 1000) {
            /* (after something long, e.g. the phase's tuning: the seconds missed are counted, not made up) */
            do {
                t_sec += 1000;
                st.up_s++;
            } while (ms() - t_sec >= 1000);
            board_second();
        }
    }
}
