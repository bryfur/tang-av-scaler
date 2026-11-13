/* pan.c: the picture's pan, for the deinterlacer (rtl/deint.v mv; MV): how far the newest field is
 * from the one two before it (the same lines), found from the fields themselves in the memory:
 * what is at (x, row) of the newest is at (x + dx, row + dyr) of the older.
 *
 * Six rows across the field, 384 pixels in its middle (every other one): the sum of |newest - older
 * moved| for dx of -16 to 16 with no move down; then for dyr of -4 to 4 at that dx; then dx again
 * at that dyr.  It counts where the least sum is clearly under no move's, and (the deinterlacer
 * can only use an even dyr: the field between has no line at half a line) clearly under its
 * neighbours' one line up and down: else the picture moves by part of a line, or not as one, and
 * there is no pan to use.  The rows are read as they are in the memory (the data cache is off
 * after sw/mem.c's test: the capture writes the memory behind it).
 */
#include "hw.h"

#ifndef MEM_BASE
#define MEM_BASE 0u                    /* (a test on a PC puts the memory elsewhere: sim/pan_test.py) */
#endif
#define NX   384
#define X0   168
#define RX   16
#define RY   4
#define ROWS 6

int8_t pan_dx, pan_dy;                  /* (for the on-screen text) */
bool pan_ok;
uint32_t pan_us;                        /* how long the last one took */

/* a row's luma, n pixels from x0, out of a field's slot (rtl/cap_ddr.v: a word a pair: Cb Y0 Cr Y1,
 * the first in the highest byte) */
static void row(uint8_t *dst, int slot, int r, int x0, int n)
{
    const volatile uint32_t *p = (const volatile uint32_t *)(MEM_BASE + (uint32_t)slot * 0x08000000u + (uint32_t)r * 4096u);
    for (int q = x0 >> 1; q < (x0 + n + 1) >> 1; q++) {
        uint32_t w = p[q];
        dst[2 * q - x0] = w >> 16;
        if (2 * q + 1 - x0 < n)
            dst[2 * q + 1 - x0] = w;
    }
}

static uint32_t sad(const uint8_t *a, const uint8_t *b)
{
    uint32_t s = 0;
    for (int i = 0; i < NX; i += 2) {
        int d = a[i] - b[i];
        s += d < 0 ? -d : d;
    }
    return s;
}

/* the sums for every dx at one dyr (down false), or every dyr at one dx; the least's place back */
static int sums(uint32_t *s, bool down, int latest, int older, int lines, int dx, int dy)
{
    static uint8_t a[NX], b[NX + 2 * RX];
    int n = down ? RY : RX, at = 0;

    for (int k = 0; k <= 2 * n; k++)
        s[k] = 0;
    for (int i = 1; i <= ROWS; i++) {
        int r = lines * i / (ROWS + 1);
        row(a, latest, r, X0, NX);
        if (down)
            for (int k = -RY; k <= RY; k++) {
                row(b, older, r + k, X0 - RX, NX + 2 * RX);
                s[k + RY] += sad(a, b + RX + dx);
            }
        else {
            row(b, older, r + dy, X0 - RX, NX + 2 * RX);
            for (int k = -RX; k <= RX; k++)
                s[k + RX] += sad(a, b + RX + k);
        }
        audio_service();
    }
    /* from no move outwards: a place further out must be an eighth better (plain rows are the same
     * at every place, but for the noise: no move then) */
    for (int k = 1; k <= n; k++)
        for (int sg = -1; sg <= 1; sg += 2)
            if (s[sg * k + n] * 8 < s[at + n] * 7)
                at = sg * k;
    return at;
}

/* a field has come in: the pan from it and the one two before */
void pan_service(int latest, int lines, bool on)
{
    uint32_t sx[2 * RX + 1], sy[2 * RY + 1], t0 = cycles(), zero, best, up, down;
    const uint32_t px = ROWS * (NX / 2);        /* the pixels in a sum */
    int older = (latest - 2) & 7, dx, dy;

    if (!on || mem_state != MEM_GOOD || lines < 200) {
        if (pan_ok || REG(R_MV))
            REG(R_MV) = 0;
        pan_ok = false;
        st.pan = 0;
        return;
    }
    /* across with no move down; down at that; and where it does move down, across again there, and
     * down once more if that moved it */
    dx = sums(sx, false, latest, older, lines, 0, 0);
    zero = sx[RX];
    dy = sums(sy, true, latest, older, lines, dx, 0);
    if (dy) {
        int was = dx;
        dx = sums(sx, false, latest, older, lines, 0, dy);
        if (dx != was)
            dy = sums(sy, true, latest, older, lines, dx, 0);
    }
    best = sy[dy + RY];
    up = dy > -RY ? sy[dy - 1 + RY] : best;
    down = dy < RY ? sy[dy + 1 + RY] : best;
    /* it counts: something moves (no move's sum is 3 a pixel or more), the least is under half of
     * that and not at the search's end (the true one may be past it), dyr even, and, where the sums
     * say anything about lines (the least over 2 a pixel: under that the rows looked at are plain,
     * and one line or another is the same to them), the least an eighth under the lines beside:
     * else the picture moves by part of a line.  (What the deinterlacer does with it, it tests
     * pixel by pixel itself: a wrong pan costs the lines it would have made, not a wrong picture.) */
    pan_ok = (dx || dy) && !(dy & 1) && zero >= 3 * px && best * 2 < zero && dx > -RX && dx < RX && dy > -RY && dy < RY &&
             (best < 2 * px || (best * 8 < up * 7 && best * 8 < down * 7));
    pan_dx = dx;
    pan_dy = dy;
    st.pan = pan_ok, st.pan_dx = dx, st.pan_dy = dy;
    pan_us = (cycles() - t0) / (core_hz / 1000000);
    st.pan_ms10 = pan_us / 100 > 255 ? 255 : pan_us / 100;
    /* (the upper half for a host: the time this took in 10 us; 15:11 what was found even when not used) */
    REG(R_MV) = (pan_us / 10 > 0xFFFF ? 0xFFFFu : pan_us / 10) << 16 | (pan_ok ? 0x400u : 0) | ((uint32_t)dy & 15) << 6 | ((uint32_t)dx & 63);
}
