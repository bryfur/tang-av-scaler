/* surround.c: two channels made five: a matrix decoder for sound mixed down the way Dolby Surround
 * and Pro Logic II mixes are (a game's "Pro Logic II" setting).  Its own design, from the mixes'
 * published matrix: not Dolby's decoder, and not to be called by their name.
 *
 * Such a mix puts each of five channels in the pair (Lt, Rt) at its own ratio: a direction in the
 * plane of the two (the surrounds a quarter turn late in both, which does not change the ratio):
 *
 *      left (1, 0)   centre (0.7071, 0.7071)   right (0, 1)
 *      right surround (-0.5774, 0.8165)   left surround (-0.8165, 0.5774)
 *
 * The plain decoder gives each channel the pair's part along its own direction; a sound in one
 * channel then comes out of all the others too, as far as their directions are alike (the two
 * surrounds are 19 degrees apart: 0.5 dB).  So, as every decoder that separates them must, this
 * one finds what direction most of the sound has now, and sends that part where it belongs:
 *
 * - the pair's powers and product, averaged (5 ms): Lt^2, Rt^2, Lt Rt.  Their principal axis is
 *   the direction u of most of the power, and m (0 to 1) how much of it is along u: 1 for one
 *   sound alone, 0 for two channels with nothing in common;
 * - u lies between two channels' directions: u = a e1 + b e2, and what is along it (u . pair)
 *   goes to those two, times a and b: a sound mixed between two neighbours comes out of the two
 *   as it went in, and of no other;
 * - what is left (across u) goes through the plain decoder;
 * - as far as m says: each channel's decoding direction is  d + f(m) (q - d . u) u,  q its a or b
 *   (0 for the other three), f(m) = m (2 - m).  With nothing in common (m 0), the plain decoder.
 * - the directions are worked out every 16 samples and followed smoothly (0.7 ms); the surrounds
 *   go out 10 ms late (the front is heard first: what leaks is not heard as coming from behind).
 *   No LFE: the receiver's own bass management has the front channels' bass.
 *
 * Whole numbers: samples 24 bits signed, directions in 1/32768.  No hardware in here:
 * sim/surround_test.py runs it on a PC. */
#include <stdint.h>
#include "surround.h"

#define Q        15
#define ONE      (1 << Q)
#define K_7071   23170          /* sqrt(1/2) */
#define K_8165   26755          /* sqrt(2/3) */
#define K_5774   18919          /* sqrt(1/3) */
#define DELAY    480            /* the surrounds' 10 ms at 48 kHz */
#define EVERY    16             /* samples between two looks at the direction */
#define AVG      8              /* the powers' average: 2^AVG samples */
#define FOLLOW   5              /* the decoding directions follow in 2^FOLLOW samples */
#define QUIET    (1 << 12)      /* (summed power under this is silence: the plain decoder) */

enum { L, R, C, LS, RS, N };
/* the channels' directions */
static const int32_t dir[N][2] = {
    {ONE, 0}, {0, ONE}, {K_7071, K_7071}, {-K_8165, K_5774}, {-K_5774, K_8165}
};
/* the half turn of directions with a positive first part, from (0, -1) round to (0, 1), as the
 * pairs of neighbours along it: each a channel and its direction's sign there */
static const struct { int8_t c1, s1, c2, s2; int32_t inv; } pairs[5] = {
    {R, -1, RS, -1, 56756},     /* (0, -1) to (0.5774, -0.8165); inv: 1 / the two's cross product */
    {RS, -1, LS, -1, 98304},    /* ... to (0.8165, -0.5774) */
    {LS, -1, L, 1, 56756},      /* ... to (1, 0) */
    {L, 1, C, 1, 46341},        /* ... to (0.7071, 0.7071) */
    {C, 1, R, 1, 46341},        /* ... to (0, 1) */
};

static int64_t p_ll, p_rr, p_lr;        /* the powers and the product, averaged */
static int32_t dec[N][2], goal[N][2];   /* the decoding directions, and where they are going */
static int32_t d_ls[DELAY], d_rs[DELAY];
static int d_at, every;

static int32_t mul(int32_t a, int32_t k)        /* a x k / 32768 */
{
    return (int32_t)(((int64_t)a * k) >> Q);
}

static int32_t sat(int32_t v)
{
    return v > 0x7FFFFF ? 0x7FFFFF : v < -0x800000 ? -0x800000 : v;
}

static uint32_t root(uint32_t v)
{
    uint32_t r = 0, b = 1u << 30;
    while (b) {
        if (v >= r + b) {
            v -= r + b;
            r = (r >> 1) + b;
        } else
            r >>= 1;
        b >>= 2;
    }
    return r;
}

/* where the decoding directions should be, from the averages */
static void aim(void)
{
    int64_t s = p_ll + p_rr;
    int32_t x, y, m, f, c2, s2, uc, us, a, b, sh = 0;
    int p;

    for (int k = 0; k < N; k++) {
        goal[k][0] = dir[k][0];
        goal[k][1] = dir[k][1];
    }
    if (s < QUIET)
        return;
    while (s >> sh >= 1 << 16)
        sh++;
    /* (x, y) = m (cos, sin) of twice the direction's angle */
    x = (int32_t)(((p_ll - p_rr) >> sh) << Q) / (int32_t)(s >> sh);
    y = (int32_t)(((2 * p_lr) >> sh) << Q) / (int32_t)(s >> sh);
    m = root((uint32_t)(x * x + y * y));
    if (m < 512)
        return;
    if (m > ONE)
        m = ONE;
    c2 = x * ONE / m;
    s2 = y * ONE / m;
    c2 = c2 > ONE ? ONE : c2 < -ONE ? -ONE : c2;
    s2 = s2 > ONE ? ONE : s2 < -ONE ? -ONE : s2;
    /* the direction itself, its first part positive: the half angle, by its larger part first */
    if (c2 >= 0) {
        uc = root((uint32_t)(ONE + c2) << 14);
        us = s2 * (ONE / 2) / uc;
    } else {
        us = root((uint32_t)(ONE - c2) << 14);
        uc = (s2 < 0 ? -s2 : s2) * (ONE / 2) / us;
        if (s2 < 0)
            us = -us;
    }
    /* between which two neighbours */
    if (us >= 0)
        p = us <= uc ? 3 : 4;
    else if (mul(K_8165, us) + mul(K_5774, uc) > 0)
        p = 2;
    else if (mul(K_5774, us) + mul(K_8165, uc) > 0)
        p = 1;
    else
        p = 0;
    {
        int32_t e1c = pairs[p].s1 * dir[pairs[p].c1][0], e1s = pairs[p].s1 * dir[pairs[p].c1][1];
        int32_t e2c = pairs[p].s2 * dir[pairs[p].c2][0], e2s = pairs[p].s2 * dir[pairs[p].c2][1];
        a = (int32_t)(((int64_t)(mul(uc, e2s) - mul(us, e2c)) * pairs[p].inv) >> Q);
        b = (int32_t)(((int64_t)(mul(e1c, us) - mul(e1s, uc)) * pairs[p].inv) >> Q);
    }
    a = a < 0 ? 0 : a;
    b = b < 0 ? 0 : b;
    f = mul(m, 2 * ONE - m);
    for (int k = 0; k < N; k++) {
        int32_t q = k == pairs[p].c1 ? pairs[p].s1 * a : k == pairs[p].c2 ? pairs[p].s2 * b : 0;
        int32_t g = mul(f, q - mul(dir[k][0], uc) - mul(dir[k][1], us));
        goal[k][0] += mul(g, uc);
        goal[k][1] += mul(g, us);
    }
}

void surround_reset(void)
{
    p_ll = p_rr = p_lr = 0;
    for (int k = 0; k < N; k++) {
        dec[k][0] = goal[k][0] = dir[k][0];
        dec[k][1] = goal[k][1] = dir[k][1];
    }
    for (int k = 0; k < DELAY; k++)
        d_ls[k] = d_rs[k] = 0;
    d_at = every = 0;
}

void surround(int32_t lt, int32_t rt, int32_t out[6])
{
    int32_t o[N];

    p_ll += ((int64_t)lt * lt - p_ll) >> AVG;
    p_rr += ((int64_t)rt * rt - p_rr) >> AVG;
    p_lr += ((int64_t)lt * rt - p_lr) >> AVG;
    if (++every == EVERY) {
        every = 0;
        aim();
    }
    for (int k = 0; k < N; k++) {
        dec[k][0] += (goal[k][0] - dec[k][0]) >> FOLLOW;
        dec[k][1] += (goal[k][1] - dec[k][1]) >> FOLLOW;
        o[k] = sat(mul(lt, dec[k][0]) + mul(rt, dec[k][1]));
    }
    out[0] = o[L];
    out[1] = o[R];
    out[2] = o[C];
    out[3] = 0;
    out[4] = d_ls[d_at];
    out[5] = d_rs[d_at];
    d_ls[d_at] = o[LS];
    d_rs[d_at] = o[RS];
    d_at = d_at == DELAY - 1 ? 0 : d_at + 1;
}
