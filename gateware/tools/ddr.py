#!/usr/bin/env python3
"""ddr.py [test [N]]: the SOM's DDR3 through the monitor (rtl/top.v DDR, DDRD): its calibration's
state; test: N lines (256 bits each, default 2000) of random data written all over the 1 GB and read
back."""
import random
import sys
import time

import avb

DDR, DDRD = 0x40, 0x48


def state(m):
    v = m.r(DDR)
    return dict(ok=v & 1, fail=v >> 1 & 1, done=v >> 2 & 1, info=v >> 8 & 0xFF, dll=v >> 16 & 0xFF)


def wait(m):
    t = time.time()
    while not m.r(DDR) >> 2 & 1:
        if time.time() - t > 2:
            sys.exit("DDR3: the command did not finish: %s" % state(m))


def write(m, line, data):
    for k in range(8):
        m.w(DDRD + k, data >> 32 * k & 0xFFFFFFFF)
    m.w(DDR, 1 << 31 | line)
    wait(m)


def read(m, line):
    m.w(DDR, line)
    wait(m)
    return sum(m.r(DDRD + k) << 32 * k for k in range(8))


def main():
    m = avb.Mon()
    print("DDR3:", state(m))
    if sys.argv[1:2] == ["test"]:
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
        rnd = random.Random(1)
        want = {}
        for i in range(n):
            line = rnd.getrandbits(25) if i > 64 else (1 << (i % 25)) | (i >> 5)
            want[line] = rnd.getrandbits(256)
            write(m, line, want[line])
        bad = 0
        for line, d in want.items():
            got = read(m, line)
            if got != d:
                bad += 1
                if bad < 4:
                    print("  line %07x: xor %064x" % (line, got ^ d))
        print("DDR3 test: %d lines, %d wrong" % (len(want), bad))


if __name__ == "__main__":
    main()
