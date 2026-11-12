#!/usr/bin/env python3
"""clkgen.py [MHZ]: the MS5351M (Si5351A register map [Skyworks AN619]) through the monitor's I2C:
CLK0 and CLK1 (inverted: the transceivers' REFCLK0 pair) and CLK2 (the FPGA's PLL_CLK2 pin) at MHZ
(default 148.5) from PLL A, the 25 MHz crystal with 10 pF load; then CLK2 as the FPGA measures it.
"""
import sys
import time
from fractions import Fraction

import avb

BUS, DEV, XTAL = 0, 0x60, Fraction(25000000)


def params(ratio):
    """(P1, P2, P3) of a divider a + b/c [AN619 3.2]."""
    ratio = Fraction(ratio).limit_denominator(1048575)
    a = ratio.numerator // ratio.denominator
    b, c = ratio.numerator - a * ratio.denominator, ratio.denominator
    f = 128 * b // c
    return 128 * a + f - 512, 128 * b - c * f, c


def reg8(p1, p2, p3, rdiv=0):
    return [p3 >> 8 & 255, p3 & 255, rdiv << 4 | p1 >> 16 & 3, p1 >> 8 & 255, p1 & 255,
            (p3 >> 16 & 15) << 4 | p2 >> 16 & 15, p2 >> 8 & 255, p2 & 255]


def setup(m, hz, drive=3):
    hz = Fraction(hz)
    # an even whole output divider with the VCO in 600-900 MHz, as high as it goes
    div = max(d for d in range(4, 901, 2) if 600e6 <= hz * d <= 900e6)
    vco = hz * div
    w = lambda reg, data: m.i2c_write(BUS, DEV, [reg] + list(data)) or sys.exit("MS5351M: no acknowledge at reg %d" % reg)
    w(3, [0xFF])                                    # outputs off
    w(16, [0x80] * 8)                               # all powered down
    w(183, [0xD2])                                  # crystal load 10 pF
    w(15, [0x00])                                   # both PLLs from the crystal
    w(26, reg8(*params(vco / XTAL)))                # PLL A
    ms = reg8(*params(div))
    for k in range(3):
        w(42 + 8 * k, ms)
    w(165, [0, 0, 0])                               # no phase offsets
    # CLKn control: whole-number mode, PLL A, its own divider; CLK1 inverted; 2/4/6/8 mA
    w(16, [0x4C | drive, 0x5C | drive, 0x4C | drive])
    w(177, [0xA0])                                  # reset both PLLs
    w(3, [0xF8])                                    # CLK0-2 on
    return float(vco), div


if __name__ == "__main__":
    mhz = Fraction(sys.argv[1]) if len(sys.argv) > 1 else Fraction("148.5")
    m = avb.Mon()
    vco, div = setup(m, mhz * 1000000)
    print("MS5351M: VCO %.3f MHz / %d = %s MHz; status reg0 %02x" % (vco / 1e6, div, mhz, m.i2c_read(BUS, DEV, 0)[0]))
    time.sleep(1.6)
    print("PLL_CLK2 measured: %.4f MHz" % (m.freq(0) / 1e6))
    m.close()
