#!/usr/bin/env python3
"""edid.py: the display's EDID through the monitor's DDC bus, decoded as far as bring-up needs:
name, detailed timings, the CEA block's video codes, the HDMI blocks' rate limits and SCDC."""
import sys
import time

import avb


def dtd(d):
    pc = (d[0] | d[1] << 8) * 10
    ha, hb = d[2] | (d[4] & 0xF0) << 4, d[3] | (d[4] & 0x0F) << 8
    va, vb = d[5] | (d[7] & 0xF0) << 4, d[6] | (d[7] & 0x0F) << 8
    return "%d x %d, %.2f MHz, %.2f Hz" % (ha, va, pc / 1000, pc * 1000 / ((ha + hb) * (va + vb)))


def read(m, start, n, tries=3):
    for k in range(tries):
        try:
            return m.i2c_read(2, 0x50, start, n)
        except IOError:
            time.sleep(0.3)
    raise IOError("no EDID at 0x50 (hot plug %d)" % (m.r(avb.STAT) >> 2 & 1))


def main():
    m = avb.Mon()
    e = read(m, 0, 128)
    ext = [read(m, 128, 128)] if e[126] else []
    scdc = m.i2c_probe(2, 0x54)
    m.close()
    mfg = e[8] << 8 | e[9]
    print("EDID header %s, checksum %s, %d extension(s); maker %s product %04x year %d; SCDC at 0x54: %s" % (
        "ok" if e[:8].hex() == "00ffffffffffff00" else "BAD", "ok" if sum(e) % 256 == 0 else "BAD", e[126],
        "".join(chr(64 + (mfg >> s & 31)) for s in (10, 5, 0)), e[10] | e[11] << 8, 1990 + e[17], "yes" if scdc else "no"))
    for o in (54, 72, 90, 108):
        d = e[o:o + 18]
        if d[0] or d[1]:
            print("  timing", dtd(d))
        elif d[3] == 0xFC:
            print("  name:", d[5:18].decode(errors="replace").strip())
        elif d[3] == 0xFD:
            print("  range: V %d-%d Hz, H %d-%d kHz, max %d MHz" % (d[5], d[6], d[7], d[8], d[9] * 10))
    for x in ext:
        print("  extension tag %02x rev %d, checksum %s" % (x[0], x[1], "ok" if sum(x) % 256 == 0 else "BAD"))
        if x[0] != 2:
            continue
        dd, i = x[2], 4
        while i < dd:
            tag, k = x[i] >> 5, x[i] & 31
            body = x[i + 1:i + 1 + k]
            if tag == 2:
                print("    video codes:", [b & 0x7F if b < 193 else b for b in body])
            elif tag == 3 and body[:3] == bytes([3, 0x0C, 0]):
                print("    HDMI 1.4 block: max TMDS clock %d MHz" % (body[6] * 5 if k > 6 else 165), body.hex())
            elif tag == 3 and body[:3] == bytes([0xD8, 0x5D, 0xC4]):
                print("    HDMI Forum block: max TMDS character rate %d MHz, SCDC %d" % (body[4] * 5, body[5] >> 7), body.hex())
            elif tag == 7:
                print("    extended tag %d: %s" % (body[0], body[1:].hex()))
            i += 1 + k
        for o in range(dd, 127 - 17, 18):
            if x[o] or x[o + 1]:
                print("    timing", dtd(x[o:o + 18]))


if __name__ == "__main__":
    main()
