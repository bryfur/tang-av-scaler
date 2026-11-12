#!/usr/bin/env python3
"""grab.py [OUT.png] [--step N] [--rows A:B] [--width W]: the picture as the FPGA sends it (rtl/grab.v),
read back through the monitor: with no display to look at.  Eight rows a frame, so a moving picture
is torn between groups of rows; --step N takes every Nth row and column (default 2: 960 x 540 in
about half a minute)."""
import sys
import time

from PIL import Image

import avb

GRAB, GRABD = 0x38, 0x39


def rows8(m, row, step, width):
    """rows row, row + step, ... (eight) of one frame: a list of lists of (r, g, b)"""
    m.w(GRAB, step << 12 | row)
    m.flush()
    t = time.time()
    while not m.r(GRAB) >> 31:
        if time.time() - t > 2:
            sys.exit("grab: no frame in 2 s (the lanes' clock is not running?)")
    out = []
    for k in range(8):
        m.w(GRABD, k << 11)
        buf = b""
        for i in range(0, width, 240):
            n = min(240, width - i)
            m.out += bytes([ord("R"), GRABD]) * n
            m.flush()
            t, want = time.time(), len(buf) + 4 * n
            while len(buf) < want:
                buf += m.read_raw()
                if time.time() - t > 5:
                    sys.exit("grab: the monitor stopped answering (%d of %d bytes)" % (len(buf), want))
                time.sleep(0.001)
        out.append([(buf[4 * i + 2], buf[4 * i + 1], buf[4 * i]) for i in range(width)])
    return out


def frame(m, step=2, first=0, last=1080, width=1920):
    img = Image.new("RGB", (width // step, (last - first + step - 1) // step))
    y = 0
    for row in range(first, last, 8 * step):
        for line in rows8(m, row, step, width):
            if y < img.height:
                for x, p in enumerate(line[::step]):
                    img.putpixel((x, y), p)
                y += 1
    return img


def main():
    a = sys.argv[1:]
    opt = lambda name, d: a[a.index(name) + 1] if name in a else d
    step = int(opt("--step", 2))
    first, last = (int(v) for v in opt("--rows", "0:1080").split(":"))
    out = next((v for v in a if v.endswith(".png")), "/tmp/grab.png")
    m = avb.Mon()
    t = time.time()
    img = frame(m, step, first, last, int(opt("--width", 1920)))
    img.save(out)
    print("%s: %d x %d in %.0f s" % (out, img.width, img.height, time.time() - t))


if __name__ == "__main__":
    main()
