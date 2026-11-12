#!/usr/bin/env python3
"""audio.py [SECONDS]: the PCM1808 as the FPGA hears it (rtl/audio_in.v, top.v AUD, AUDPK): the last
words of both channels as they came and, each half second, the peaks in dB below full scale."""
import math
import sys
import time

import avb

AUD, AUDPK = 0x50, 0x52


def sample(word):
    """the 24-bit sample of a word (I2S: a clock late)"""
    v = word >> 7 & 0xFFFFFF
    return v - (1 << 24) if v >> 23 else v


def main():
    m = avb.Mon()
    l, r = m.r(AUD), m.r(AUD + 1)
    print("words %08x %08x: samples %d, %d of +-8388608" % (l, r, sample(l), sample(r)))
    seen = set()
    for _ in range(40):
        seen.add(m.r(AUD) >> 7 & 0xFFFFFF)
    print("left: %d different values in 40 reads (%s)" % (len(seen), "alive" if len(seen) > 3 else "stuck: no clocks or no converter?"))
    m.r(AUDPK)
    t = float(sys.argv[1]) if len(sys.argv) > 1 else 3
    end = time.time() + t
    db = lambda v: "-inf" if v == 0 else "%6.1f" % (20 * math.log10(v / 32768))
    while time.time() < end:
        time.sleep(0.5)
        p = m.r(AUDPK)
        print("peak  L %s dBFS   R %s dBFS" % (db(p & 0xFFFF), db(p >> 16)))


if __name__ == "__main__":
    main()
