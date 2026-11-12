#!/usr/bin/env python3
"""linkq.py [REG=VALUE ...] [SECONDS]: the HDMI link's quality both sides of the SN65DP159, after
writing the retimer's registers named (hex, e.g. 0b=08): its own TMDS error counters on what the
FPGA sends it [SLLSEJ2G Table 10: BERT_CNT, 12 bits a lane], and the sink's character error counts
over SCDC, both over SECONDS (default 5)."""
import sys
import time

import avb
import scdc

DP = 0x5E


def measure(m, secs):
    m.i2c_write(1, DP, [0x16, 0xF0])            # the checker on, every lane: disparity or data errors
    m.i2c_write(1, DP, [0x15, 0x10])            # clear
    m.i2c_write(1, DP, [0x15, 0x00])
    has_scdc = m.i2c_probe(2, 0x54)
    if has_scdc:
        scdc.rd(m, 0x50, 7)
    time.sleep(secs)
    b = m.i2c_read(1, DP, 0x18, 6)
    bert = [b[2 * k] | (b[2 * k + 1] & 15) << 8 for k in range(3)]
    sink = None
    if has_scdc:
        c = scdc.rd(m, 0x50, 7)
        st = scdc.rd(m, 0x40)[0]
        sink = ([c[2 * k] | (c[2 * k + 1] & 0x7F) << 8 for k in range(3)], st)
    return bert, sink


def main():
    secs = 5.0
    m = avb.Mon()
    for a in sys.argv[1:]:
        if "=" in a:
            reg, val = (int(x, 16) for x in a.split("="))
            if not m.i2c_write(1, DP, [reg, val]):
                sys.exit("DP159: no acknowledge")
        else:
            secs = float(a)
    regs = m.i2c_read(1, DP, 0x09, 5)
    if len(sys.argv) > 1 and "=" in "".join(sys.argv[1:]):
        m.flush()
        time.sleep(3)                           # the sink locks again after a change
    bert, sink = measure(m, secs)
    print("DP159 09-0D: %s | its input errors (lanes 0-2, saturate at 4095): %s | %s" % (
        regs.hex(" "), bert,
        "no SCDC sink" if sink is None else "sink: clock %d locked %d%d%d, errors in %.0f s %s" % (
            sink[1] & 1, sink[1] >> 1 & 1, sink[1] >> 2 & 1, sink[1] >> 3 & 1, secs, sink[0])))
    m.close()


if __name__ == "__main__":
    main()
