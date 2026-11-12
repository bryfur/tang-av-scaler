#!/usr/bin/env python3
"""adv.py: the ADV7181D component decoder (I2C bus 3, 0x21) through the bring-up monitor.

    adv.py cp480i [REG=VAL ...]         # 480i component through the CP core: 16-bit 4:2:2 at 13.5 MHz,
                                        # sync codes on both buses (the one that gives colour)
    adv.py sd [REG=VAL ...]             # 480i/576i through the standard definition core: 8-bit BT.656 out
                                        # (luma only: this core gives no chroma for component)
    adv.py 480p | 480i [REG=VAL ...]    # reset, load that mode's register set (+ overrides), report
    adv.py stat                         # what the decoder measures on the input (STDI), LLC
    adv.py dump                         # all registers
    adv.py w REG VAL | r REG

Component input: Y AIN10, Pb AIN8, Pr AIN6 (schematic), CP core, 16-bit 4:2:2 out.
The register sets follow ADI's ADV7181D evaluation scripts ("525p/60Hz YPrPb In").
"""
import sys
import time

import avb

BUS, DEV = 3, 0x21

COMMON = [
    (0x1D, 0x47),   # 28.63636 MHz crystal
    (0x3A, 0x11),   # latch clock, ADC3 off
    (0x3B, 0x81),   # internal bias (80, the evaluation board's, blinds the sync slicer here)
    (0x3C, 0x52),   # PLL charge pump
    (0x6B, 0xC1),   # CP output: 16-bit 4:2:2
    (0xC3, 0x46),   # ADC1 <- AIN6 (Pr), ADC0 <- AIN10 (Y)
    (0xC4, 0xB5),   # manual mux, ADC2 <- AIN8 (Pb)
    (0x73, 0xCF),   # manual gain, channels A/B/C = 0x0FA
    (0x74, 0xA3),
    (0x75, 0xE8),
    (0x76, 0xFA),
    (0x7B, 0x06),
    (0x85, 0x19),   # no SSPD, sync on Y
    (0x86, 0x0B),   # STDI line count mode
    (0xBF, 0x06),   # free-run colour
    (0xC0, 0x40),
    (0xC1, 0xF0),
    (0xC2, 0x80),
    (0xC5, 0x01),
    (0xC9, 0x08),
    (0x0E, 0x80),   # ADI's recommended block
    (0x52, 0x46),
    (0x54, 0x00),
    (0xF6, 0x3B),
    (0x0E, 0x00),
]
# 480i/576i component through the standard definition core (SDP): locks by itself, 27 MHz LLC, 8-bit
# ITU-R BT.656 on P19-P12 with the syncs in the stream (the reset state of the output)
SD = [
    (0x00, 0x09),   # INSEL: YPrPb
    (0x1D, 0x47),   # 28.63636 MHz crystal
    (0x3A, 0x11),   # latch clock, ADC3 off
    (0x3B, 0x81),   # bias
    (0xC3, 0x46),   # ADC1 <- AIN6 (Pr), ADC0 <- AIN10 (Y)
    (0xC4, 0xB5),   # manual mux, ADC2 <- AIN8 (Pb)
    (0x0E, 0x80),   # ADI's recommended block
    (0x52, 0x46),
    (0x54, 0x00),
    (0x0E, 0x00),
]
# 480i component through the CP core, as found on the board: internal bias (3B = 81: with ADI's
# evaluation value 80 the sync slicer sees nothing), the free-run line length set to the input's
# (else the core free-runs: a blue screen), LLC 13.5 MHz, sync codes left on (7B at reset)
CP480I = [
    (0x05, 0x00), (0x06, 0x0A),     # SD, 525i 4x1
    (0x1D, 0x47),   # 28.63636 MHz crystal
    (0x3A, 0x11),   # latch clock, ADC3 off
    (0x3B, 0x81),   # internal bias
    (0x3C, 0x52),   # PLL charge pump
    (0x6B, 0xC1),   # CP output: 16-bit 4:2:2 (CPOP_SEL 0001; 0010 puts one chroma channel alone on the C pins)
    (0xC3, 0x46),   # ADC1 <- AIN6 (Pr), ADC0 <- AIN10 (Y)  [data sheet Table 8; the evaluation board's is the other way]
    (0xC4, 0xB5),   # manual mux, ADC2 <- AIN8 (Pb)
    (0x85, 0x19),   # no SSPD, sync on Y
    (0x86, 0x0B),   # STDI line count mode
    (0x8F, 0x07),   # free-run line length 1820 (of the crystal's clock)
    (0x90, 0x1C),
    (0x73, 0xCF),   # manual gain, channels A/B/C = 0x0FA
    (0x74, 0xA3),
    (0x75, 0xE8),
    (0x76, 0xFA),
    (0xC5, 0x01),   # clamp averaging
    (0x0E, 0x80),   # ADI's recommended block
    (0x52, 0x46),
    (0x54, 0x00),
    (0xF6, 0x3B),
    (0x0E, 0x00),
]
MODES = {
    "480p": [(0x05, 0x01), (0x06, 0x06)],   # component, 525p 2x1
    "480i": [(0x05, 0x00), (0x06, 0x0A)],   # SD, 525i 4x1
    "576p": [(0x05, 0x01), (0x06, 0x07)],
    "720p": [(0x05, 0x01), (0x06, 0x0A)],
    "1080i": [(0x05, 0x01), (0x06, 0x0C)],
}


def wr(m, reg, val):
    if not m.i2c_write(BUS, DEV, [reg, val]):
        sys.exit("ADV7181D: no ack writing %02x" % reg)


def rd(m, reg, n=1):
    return m.i2c_read(BUS, DEV, reg, n)


def reset(m):
    c = m.r(avb.CTRL)
    m.w(avb.CTRL, c & ~8)
    m.flush()
    time.sleep(0.02)
    m.w(avb.CTRL, c | 8)
    m.flush()
    time.sleep(0.05)


def setup(m, mode, extra=()):
    reset(m)
    for reg, val in (SD if mode == "sd" else CP480I if mode == "cp480i" else MODES[mode] + COMMON) + list(extra):
        wr(m, reg, val)


def stat(m):
    b = rd(m, 0xB1, 4)
    bl = (b[0] & 0x3F) << 8 | b[1]
    lcf = (b[2] & 7) << 8 | b[3]
    line = 28.63636e6 * 8 / bl if bl else 0
    print("STDI: valid %d  interlaced %d  BL %d (line %.3f kHz)  LCVS %d  LCF %d"
          % (b[0] >> 7, b[0] >> 6 & 1, bl, line / 1e3, b[2] >> 3, lcf))
    print("status 10..13: %s   LLC %.4f MHz  IN_INT %d"
          % (" ".join("%02x" % x for x in rd(m, 0x10, 4)), m.freq(1) / 1e6, m.r(avb.STAT) >> 3 & 1))


def main():
    a = sys.argv[1:] or ["stat"]
    m = avb.Mon()
    if a[0] in MODES or a[0] in ("sd", "cp480i"):
        extra = [tuple(int(x, 16) for x in s.split("=")) for s in a[1:]]
        setup(m, a[0], extra)
        time.sleep(0.5)
        stat(m)
    elif a[0] == "stat":
        stat(m)
    elif a[0] == "dump":
        d = rd(m, 0, 256)
        for i in range(0, 256, 16):
            print("%02x: %s" % (i, " ".join("%02x" % x for x in d[i:i + 16])))
    elif a[0] == "w":
        wr(m, int(a[1], 16), int(a[2], 16))
    elif a[0] == "r":
        print("%02x" % rd(m, int(a[1], 16))[0])
    m.close()


if __name__ == "__main__":
    main()
