#!/usr/bin/env python3
"""ddcci.py [CODE ...]: the monitor's own view over DDC/CI (address 0x37, MCCS VCP codes, hex;
default AC AE: the horizontal and vertical frequency it measures on its input, with 60 the input
it shows): a picture it accepts reads back with its frame rate."""
import sys
import time

import avb


def vcp(m, code):
    """(max, value) of a VCP code, or None."""
    msg = [0x51, 0x82, 0x01, code]
    chk = 0x6E
    for b in msg:
        chk ^= b
    for _ in range(3):
        if m.i2c_write(2, 0x37, msg + [chk]):
            time.sleep(0.06)
            r = m.i2c_recv(2, 0x37, 11)
            if r and r[1] == 0x88 and r[2] == 0x02 and r[3] == 0 and r[4] == code:
                return r[6] << 8 | r[7], r[8] << 8 | r[9]
        time.sleep(0.1)
    return None


def main():
    codes = [int(a, 16) for a in sys.argv[1:]] or [0x60, 0xAC, 0xAE]
    m = avb.Mon()
    print("  ".join("%02X: %s" % (c, "-" if v is None else "%d (max %d)" % (v[1], v[0])) for c, v in ((c, vcp(m, c)) for c in codes)))
    m.close()


if __name__ == "__main__":
    main()
