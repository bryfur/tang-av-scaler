#!/usr/bin/env python3
"""video.py: the component input on the HDMI output (rtl/vcap.v, fbview.v).

    video.py [--load [FS]] [--swap] [--sd] [--mode M] [--thr T] [--top1] [--noaa] [--aa T] [--aadbg] [--nodiag] [--sharp N]
                                        # decoder to 480i component (CP core; --sd: the SD core, luma
                                        # only), HDMI up at 1080p60 if --load, show the input;
                                        # deinterlacing --mode 0 motion adaptive (default), 1 bob,
                                        # 2 weave; --thr the motion threshold (6); F = 0 the top
                                        # field (--top1: F = 1); SMAA on (--noaa), its edge
                                        # threshold --aa (20); sharpening --sharp 0-16 (8)
    video.py freeze | run               # the fields in memory kept as they are (a still picture) | not
    video.py stat                       # what the capture sees
    video.py raw [MODE]                 # 1024 raw samples of the pixel port (0 now, 1 from a sync code,
                                        # 2 from the start of a line of picture)
    video.py pattern                    # back to the test picture
"""
import subprocess
import sys
import os
import time

import adv
import avb

VID, CAP, FIELDS, RAW, RAWD, DEINT, DSTAT = 0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36
HERE = os.path.dirname(os.path.abspath(__file__))


def stat(m):
    a, n0 = m.r(CAP), m.r(FIELDS)
    time.sleep(0.5)
    n1 = m.r(FIELDS)
    print("capture: %d Y samples a line, %d lines a field (F %d), %.1f fields/s, LLC %.4f MHz"
          % (a & 0x7FF, a >> 11 & 0x3FF, a >> 21 & 1, ((n1 - n0) & 0xFFFF) / 0.5, m.freq(1) / 1e6))
    print("decoder status 10..13: %s" % " ".join("%02x" % x for x in adv.rd(m, 0x10, 4)))
    d, f0 = m.r(DSTAT), m.r(DSTAT) >> 16
    time.sleep(0.5)
    st = d >> 8 & 0xFF
    print("deinterlacer: %d fields seen, newest in slot %d, %.0f frames/s, %s, newest field %s, mode %d thr %d"
          % (d & 7, d >> 3 & 7, (((m.r(DSTAT) >> 16) - f0) & 0xFFFF) / 0.5, "four fields in order" if st >> 6 & 1 else "NO field history (bob)",
             "bottom" if st >> 5 & 1 else "top", m.r(DEINT) & 3, m.r(DEINT) >> 8 & 0xFF))


def raw(m, mode):
    m.w(RAW, mode)
    m.flush()
    t = time.time()
    while not m.r(CAP) >> 31:
        if time.time() - t > 1:
            sys.exit("raw capture: nothing after 1 s (no such event on the pixel port)")
    out = []
    for i in range(0, 1024, 128):           # 128 samples a round trip
        m.flush()
        m.out += b"".join(b"W" + bytes([RAWD]) + k.to_bytes(4, "little") + b"R" + bytes([RAWD]) for k in range(i, i + 128))
        m.flush()
        buf, t = b"", time.time()
        while len(buf) < 512:
            buf += m.read_raw()
            if time.time() - t > 4:
                sys.exit("raw capture: the monitor stopped answering")
            time.sleep(0.001)
        out += [int.from_bytes(buf[4 * k:4 * k + 4], "little") for k in range(128)]
    return out


def main():
    a = sys.argv[1:]
    if a[:1] == ["stat"]:
        stat(avb.Mon())
        return
    if a[:1] == ["raw"]:
        d = raw(avb.Mon(), int(a[1]) if len(a) > 1 else 1)
        for i in range(0, 1024, 16):
            print("%4d: %s" % (i, " ".join("%02x" % (x & 0xFF) for x in d[i:i + 16])))
        print("C pins seen: %s  HS %s VS %s DE %s" % (sorted({x >> 8 & 0xFF for x in d})[:8],
              {x >> 16 & 1 for x in d}, {x >> 17 & 1 for x in d}, {x >> 18 & 1 for x in d}))
        return
    if a[:1] in (["freeze"], ["run"]):
        m = avb.Mon()
        m.w(VID, m.r(VID) & ~2 | (2 if a[0] == "freeze" else 0))
        m.flush()
        return
    if a[:1] == ["pattern"]:
        avb.Mon().w(VID, 0)
        return
    if "--load" in a:
        k = a.index("--load")
        fs = a[k + 1] if len(a) > k + 1 and not a[k + 1].startswith("-") else None
        subprocess.check_call([sys.executable, os.path.join(HERE, "hdmi.py"), "--ntsc", "--load",
                               fs or os.path.join(HERE, "../gowin/build/vid/avb/impl/pnr/avb.fs")])
    m = avb.Mon()
    sd = "--sd" in a
    adv.setup(m, "sd" if sd else "cp480i")
    opt = lambda name, d: int(a[a.index(name) + 1]) if name in a else d
    # anti-aliasing: on unless --noaa, its edge threshold --aa (20)
    m.w(DEINT, opt("--aa", 20) << 24 | (0 if "--nodiag" in a else 1) << 18 | (1 if "--aadbg" in a else 0) << 17 | (0 if "--noaa" in a else 1) << 16 | opt("--thr", 6) << 8 | (4 if "--top1" in a else 0) | opt("--mode", 0))
    m.w(VID, opt("--sharp", 8) << 16 | (8 if "--swap" in a else 0) | (0 if sd else 4) | 1)
    m.flush()
    time.sleep(0.7)
    stat(m)
    m.close()


if __name__ == "__main__":
    main()
