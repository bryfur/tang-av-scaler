#!/usr/bin/env python3
"""pan_test.py: sw/pan.c on a PC: two fields of a picture that has moved put where the program
finds them (a memory of 1 GB mapped for it, the registers a page), and what it says the pan is:
right and given where the picture moves as one by whole pixels and lines; the nearest where it
moves by part of a line (the deinterlacer finds each block's own from there); none where the
picture does not move, or moves past what is searched; across only where the rows looked at are
plain down the picture."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build")
MAIN = r"""
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include "hw.h"
uint32_t core_hz = 800000000;
int mem_state = MEM_GOOD;
struct link_status st;
static uint32_t now;
uint32_t cycles(void) { return now += 1000; }
void audio_service(void) { }
bool board_ed(void) { return false; }
bool board_hd(void) { return false; }
static uint32_t rnd(uint32_t a) { a ^= a >> 16; a *= 0x7feb352du; a ^= a >> 15; a *= 0x846ca68bu; return a ^ a >> 16; }
/* the picture: smooth lumps of several sizes (kind 1: none down the picture), 0 to 255 */
static int tex(int kind, int x, int y)
{
    int v = 0;
    for (int o = 2; o < 6; o++) {
        int s = 1 << o, x0 = x >> o, y0 = kind ? 0 : y >> o, fx = x & (s - 1), fy = kind ? 0 : y & (s - 1);
        int a = rnd(x0 * 7919 + y0 * 104729 + o) & 255, b = rnd((x0 + 1) * 7919 + y0 * 104729 + o) & 255;
        int c = rnd(x0 * 7919 + (y0 + 1) * 104729 + o) & 255, d = rnd((x0 + 1) * 7919 + (y0 + 1) * 104729 + o) & 255;
        v += ((a * (s - fx) + b * fx) * (s - fy) + (c * (s - fx) + d * fx) * fy) >> (2 * o);
    }
    return v / 4;
}
static void field(int slot, int kind, int ox, int oy2, int still, uint32_t seed)
{
    /* oy2: the move down in half lines of the field (odd: the mean of two lines) */
    for (int r = 0; r < 240; r++)
        for (int q = 0; q < 360; q++) {
            uint32_t w = 0x80008000u;
            for (int k = 0; k < 2; k++) {
                int x = 2 * q + k, y;
                bool box = still && x >= 300 && x < 400 && r >= 90 && r < 150;
                int xx = box ? x : x + ox, rr = box ? 2 * r : 2 * r + oy2;
                y = (tex(kind, xx + 4096, (rr >> 1) + 4096) + tex(kind, xx + 4096, ((rr + 1) >> 1) + 4096)) >> 1;
                y += (int)(rnd(seed + r * 720 + x) & 3) - 1;
                y = y < 16 ? 16 : y > 235 ? 235 : y;
                w |= (uint32_t)y << (k ? 0 : 16);
            }
            ((uint32_t *)(MEM_BASE + (uint64_t)slot * 0x08000000u + r * 4096u))[q] = w;
        }
}
int main(void)
{
    int kind, dx, dy2, still;
    if (mmap((void *)MEM_BASE, 1ul << 30, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED | MAP_NORESERVE, -1, 0) == MAP_FAILED ||
        mmap((void *)0xe8000000ul, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0) == MAP_FAILED)
        return 1;
    /* the newest at (x, row) is the older at (x + dx, row + dy2 / 2) */
    while (scanf("%d %d %d %d", &kind, &dx, &dy2, &still) == 4) {
        field(5, kind, -dx, -dy2, still, 1);
        field(7, kind, 0, 0, still, 2);
        pan_service(7, 240, true);
        printf("%d %d %d %u\n", pan_ok, pan_dx, pan_dy, REG(R_MV) & 0x7FF);
    }
    return 0;
}
"""
# kind, dx, the move down in half lines, a still box in the middle; then: used, and what is found
# (None: whatever)
CASES = [
    ((0, 5, 0, 0), True, (5, 0)),
    ((0, -12, 4, 0), True, (-12, 2)),
    ((0, 7, -4, 1), True, (7, -2)),
    ((0, -3, 0, 1), True, (-3, 0)),
    ((0, 15, 4, 0), True, (15, 2)),
    ((0, 1, 0, 0), True, (1, 0)),
    ((0, 0, 4, 0), True, (0, 2)),
    ((0, 3, 2, 0), True, (3, 1)),
    ((0, 4, 1, 0), True, (4, None)),        # half a line: the nearest
    ((0, -6, 3, 0), True, (-6, None)),      # a line and a half
    ((0, 0, 0, 0), False, (0, 0)),          # still
    ((0, 16, 0, 0), False, None),           # at the search's end
    ((0, 24, 0, 0), False, None),           # past it
    ((1, 6, 0, 0), True, (6, 0)),           # nothing down the picture: across is all there is to know
    ((1, -9, 4, 0), True, (-9, None)),
]


def main():
    os.makedirs(WORK, exist_ok=True)
    src = os.path.join(WORK, "pan_main.c")
    open(src, "w").write(MAIN)
    exe = os.path.join(WORK, "pan_test")
    sw = os.path.join(HERE, "../sw")
    subprocess.check_call(["gcc", "-O2", "-Wall", "-DMEM_BASE=0x200000000ul", "-I", sw, "-o", exe, src, os.path.join(sw, "pan.c")])
    out = subprocess.run([exe], input="".join("%d %d %d %d\n" % c[0] for c in CASES), stdout=subprocess.PIPE, text=True).stdout.split("\n")
    bad = 0
    for (c, used, want), ln in zip(CASES, out):
        ok, dx, dy, reg = (int(v) for v in ln.split())
        good = ok == used and (want is None or ((want[0] is None or want[0] == dx) and (want[1] is None or want[1] == dy)))
        if ok:
            good = good and reg == (0x400 | (dy & 15) << 6 | (dx & 63))
        else:
            good = good and not reg & 0x400
        bad += not good
        print("%-18s %s (%d, %d)%s" % ("%s pan %d, %g%s" % ("plain rows" if c[0] else "picture", c[1], c[2] / 2, ", a still box" if c[3] else ""),
                                       "used" if ok else "not used", dx, dy, "" if good else "   WRONG"))
    print("PASS" if not bad and len(out) > len(CASES) else "FAIL")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
