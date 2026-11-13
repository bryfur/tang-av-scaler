/* pan.c: the picture's pan, for the deinterlacer's motion compensation (rtl/deint.v mv; MV): how far the newest field is
 * from the one two before it (the same lines), found from the fields themselves in the memory:
 * what is at (x, row) of the newest is at (x + dx, row + dyr) of the older.
 *
 * Six rows across the field, 384 pixels in its middle (every other one): the sum of |newest - older
 * moved| for dx of -16 to 16 with no move down; then for dyr of -4 to 4 at that dx; then dx again
 * at that dyr.  It counts where something moves and the least sum is clearly under no move's.
 * The deinterlacer finds each block's own vector and tests every pixel: this is one more vector
 * for its blocks to try and what a frame's first line begins from, so it need not be exact.  The
 * rows are read as they are in the memory (the data cache is off after sw/mem.c's test: the
 * capture writes the memory behind it).
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

/* MV's upper part: where the frame's lines begin.  17:11: the first line made, in eights: the part
 * shown's first line less 24 or more (the anti-aliasing and the scaler look that far up); 27:18: the
 * first line that wants vectors: 4 above the part shown (the lines between are made the quick way:
 * they are wanted fast at a frame's start and are not seen). */
uint32_t pan_first(void)
{
    uint32_t y = board_ed() || board_hd() ? 0 : st.show_y;     /* (480i and 576i only) */
    return (y > 4 ? (y - 4) & 0x3FEu : 0) << 18 | (y >= 24 ? (y - 24) >> 3 : 0) << 11;
}

/* a field has come in: the pan from it and the one two before */
void pan_service(int latest, int lines, bool on)
{
    uint32_t sx[2 * RX + 1], sy[2 * RY + 1], t0 = cycles(), zero, best;
    const uint32_t px = ROWS * (NX / 2);        /* the pixels in a sum */
    int older = (latest - 2) & 7, dx, dy;

    if (!on || mem_state != MEM_GOOD || lines < 200) {
        if (REG(R_MV) != pan_first())
            REG(R_MV) = pan_first();
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
    /* it counts: something moves (no move's sum is 3 a pixel or more), and the least is under half
     * of that and not at the search's end (the true one may be past it).  The deinterlacer takes
     * it as one more vector for its blocks to try, and what they begin a frame with: it finds each
     * block's own, and tests every pixel, so a pan that is not quite the picture's costs nothing. */
    pan_ok = (dx || dy) && zero >= 3 * px && best * 2 < zero && dx > -RX && dx < RX && dy > -RY && dy < RY;
    pan_dx = dx;
    pan_dy = dy;
    st.pan = pan_ok, st.pan_dx = dx, st.pan_dy = dy;
    pan_us = (cycles() - t0) / (core_hz / 1000000);
    st.pan_ms10 = pan_us / 100 > 255 ? 255 : pan_us / 100;
    REG(R_MV) = pan_first() | (pan_ok ? 0x400u : 0) | ((uint32_t)dy & 15) << 6 | ((uint32_t)dx & 63);
}
