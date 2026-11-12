#!/usr/bin/env python3
"""cpu.py: the SOM's hard CPU (rtl/cpu.v) through the monitor.

    cpu.py stat             # does its program run (register 64 counts), what it is, a trap's cause and place
    cpu.py load [BIN]       # a new program into its RAM (sw/build/cpu.bin): the core held in reset,
                            # the words written and read back by sum, the core let go
    cpu.py reset            # the program from its start
    cpu.py osd [0|1]        # the on-screen text on or off (the program writes it)

The program in the bitstream is the one built before the bitstream was (gowin/avb.tcl takes
sw/build/cpu.hex); a load lasts until the FPGA is loaded again."""
import os
import struct
import sys
import time

import avb

CPU, CPUA, CPUD, CPUM, OSD = 0x60, 0x61, 0x62, 0x64, 0x28
HERE = os.path.dirname(os.path.abspath(__file__))


def stat(m):
    a = m.r(CPUM)
    time.sleep(0.6)
    b = m.r(CPUM)
    name = struct.pack("<I", m.r(CPUM + 1)).decode("latin1")
    print("CPU: %s, program %r, count %d -> %d (%s)" % ("runs" if m.r(CPU) & 1 else "held in reset", name, a, b,
          "alive" if a != b else "NOT counting"))
    c, pc = m.r(CPUM + 2), m.r(CPUM + 3)
    if c >> 16 == 0xDEAD:
        print("  a trap: cause %d at %08x" % (c & 0xFFFF, pc))
    return a != b


def load(m, path):
    d = open(path, "rb").read()
    d += b"\0" * (-len(d) % 4)
    words = struct.unpack("<%dI" % (len(d) // 4), d)
    if len(words) > 8192:
        sys.exit("cpu.py: %d bytes, the program's RAM is 32 KB" % len(d))
    m.w(CPU, 0)
    m.w(CPUM + 2, 0)
    m.w(CPUA, 0)
    for k, w in enumerate(words):
        m.w(CPUD, w)
        if k % 256 == 255:
            m.flush()
    m.flush()
    if m.r(CPUA) != len(words):
        sys.exit("cpu.py: %d words sent, the address says %d" % (len(words), m.r(CPUA)))
    m.w(CPU, 1)
    m.flush()
    print("%s: %d bytes loaded" % (os.path.basename(path), len(d)))
    time.sleep(0.3)


def main():
    a = sys.argv[1:] or ["stat"]
    m = avb.Mon()
    if a[0] == "load":
        load(m, a[1] if len(a) > 1 else os.path.join(HERE, "../sw/build/cpu.bin"))
        stat(m)
    elif a[0] == "reset":
        m.w(CPU, 0)
        m.w(CPU, 1)
        m.flush()
        time.sleep(0.3)
        stat(m)
    elif a[0] == "osd":
        if len(a) > 1:
            m.w(OSD, int(a[1]) & 1)
            m.flush()
        print("on-screen text %s" % ("on" if m.r(OSD) & 1 else "off"))
    else:
        sys.exit(0 if stat(m) else 1)


if __name__ == "__main__":
    main()
