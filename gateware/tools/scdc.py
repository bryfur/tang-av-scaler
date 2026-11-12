#!/usr/bin/env python3
"""scdc.py [SECONDS]: what an HDMI 2.0 sink says of the link, over DDC (SCDC, address 0x54
[HDMI 2.0 10.4]): clock detected, the three channels' character lock, and the channels'
character error counts (they clear when read) over SECONDS (default 5)."""
import sys
import time

import avb


def rd(m, reg, n=1):
    return bytes(m.i2c_read(2, 0x54, reg + k, 1)[0] for k in range(n))


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 5
    m = avb.Mon()
    if not m.i2c_probe(2, 0x54):
        sys.exit("no SCDC at 0x54 (hot plug %d): not an HDMI 2.0 sink" % (m.r(avb.STAT) >> 2 & 1))
    st = rd(m, 0x40)[0]
    print("sink version %d; TMDS config %02x (bit 0 scrambling, bit 1 clock/40); scrambling seen %d" % (
        rd(m, 0x01)[0], rd(m, 0x20)[0], rd(m, 0x21)[0] & 1))
    print("clock detected %d, channels 0/1/2 locked %d %d %d" % (st & 1, st >> 1 & 1, st >> 2 & 1, st >> 3 & 1))
    rd(m, 0x50, 7)                              # clears the counts
    time.sleep(secs)
    c = rd(m, 0x50, 7)
    counts = [(c[2 * k] | (c[2 * k + 1] & 0x7F) << 8, c[2 * k + 1] >> 7) for k in range(3)]
    print("character errors in %.0f s: %s" % (secs, ", ".join(
        "channel %d: %s" % (k, n if valid else "not valid") for k, (n, valid) in enumerate(counts))))
    m.close()


if __name__ == "__main__":
    main()
