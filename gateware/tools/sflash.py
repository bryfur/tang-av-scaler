#!/usr/bin/env python3
"""sflash.py: the SOM's flash through the design's port (rtl/sflash.v), from the host's monitor: for
bringing the port up and for looking at what the board keeps (sw/store.c).

  sflash.py id                 the flash's identity and status
  sflash.py read ADDR [N]      N bytes (default 64) from ADDR, as hex
  sflash.py same FILE.fs       the flash's first bytes against a bitstream file's (the one flashed): the
                               port reads what the FPGA was configured from
  sflash.py blank [ADDR] [N]   are N bytes (default 4096) from ADDR (default 0xF00000) erased?
  sflash.py test [ADDR]        a sector well away from the store (default 0xF00000) erased, written,
                               read back, erased again; and a write below 0x800000 asked for: refused
  sflash.py store              what the board keeps: the settings' newest record, the tables, the weights

The monitor as tools/avb.py finds it (AVB_TTY).  While the monitor is open the board's CPU leaves the
flash alone."""
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
import avb

FLC, FLD, FLS = 0x68, 0x69, 0x6A
KEY = 0xA << 24


class Flash:
    def __init__(self):
        self.m = avb.Mon()
        time.sleep(2.5)                 # (the link tells the CPU a host is here: its own use of the port ends)

    def go(self, op, a=0):
        self.m.w(FLC, op << 28 | a)
        for _ in range(100):
            s = self.m.r(FLS)
            if not s & 1:
                return s
        sys.exit("sflash: the port stays busy (FLS %08x): is it in this design?" % s)

    def ident(self):
        self.go(7)
        return self.m.r(FLD)

    def status(self):
        self.go(6)
        return self.m.r(FLD)

    def read(self, a, n):
        out = b""
        self.go(1, a)
        for k in range((n + 3) // 4):
            out += struct.pack("<I", self.m.r(FLD))
            if 4 * k + 4 < n:
                self.go(2)
        self.go(3)
        return out[:n]

    def wait(self):
        t = time.time()
        while self.status() & 1:
            if time.time() - t > 5:
                sys.exit("sflash: the flash stays busy writing")
        return time.time() - t

    def erase(self, a):
        s = self.go(5, KEY | a)
        return None if s & 2 else self.wait()

    def prog(self, a, data):
        s = self.go(4, KEY | a)
        if s & 2:
            return None
        for k in range(0, len(data), 4):
            self.m.w(FLD, struct.unpack("<I", data[k:k + 4])[0])
            self.go(2)
        self.go(3)
        return self.wait()


def fsum(words):
    h = 2166136261
    for w in words:
        h = ((h ^ w) * 16777619) & 0xFFFFFFFF
    return h


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    f = Flash()
    num = lambda k, d: int(a[k], 0) if len(a) > k else d
    if a[0] == "id":
        i = f.ident()
        print("identity %06x (maker %02x, %d MB by its size byte), status %02x" % (i, i >> 16, 1 << max((i & 255) - 20, 0), f.status()))
    elif a[0] == "read":
        d = f.read(num(1, 0), num(2, 64))
        for k in range(0, len(d), 16):
            print("%06x  %s" % (num(1, 0) + k, d[k:k + 16].hex(" ")))
    elif a[0] == "same":
        # (a .fs is text: a line of 0s and 1s a row of the bitstream, comments with //)
        bits = "".join(t.strip() for t in open(a[1]) if t[:1] in "01")
        want = bytes(int(bits[k:k + 8], 2) for k in range(0, 2048 * 8, 8))
        got = f.read(0, len(want))
        n = sum(x != y for x, y in zip(got, want))
        print("the flash's first %d bytes: %s" % (len(want), "the file's" if not n else "%d differ from the file's (first: %s / %s)" % (n, got[:16].hex(), want[:16].hex())))
    elif a[0] == "blank":
        d = f.read(num(1, 0xF00000), num(2, 4096))
        print("%d bytes from %06x: %s" % (len(d), num(1, 0xF00000), "erased" if d == b"\xff" * len(d) else "%d not FF" % sum(x != 255 for x in d)))
    elif a[0] == "test":
        at = num(1, 0xF00000) & ~4095
        bad = 0
        if f.go(4, KEY | 0x000000) & 2 and f.go(5, KEY | 0x7FF000) & 2 and f.go(4, at) & 2 and f.go(5, at) & 2:
            print("a program and an erase below 0x800000, and ones without the key: refused")
        else:
            bad += 1
            print("WRONG: something that should be refused was not")
        f.go(3)
        t = f.erase(at)
        d = f.read(at, 512)
        print("sector %06x erased in %.0f ms: %s" % (at, 1000 * t, "blank" if d == b"\xff" * 512 else "NOT blank"))
        bad += d != b"\xff" * 512
        data = bytes((k * 37 + 11) & 255 for k in range(512))
        t = f.prog(at, data[:256]) + f.prog(at + 256, data[256:])
        d = f.read(at, 512)
        print("two pages written in %.0f ms: %s" % (1000 * t, "read back the same" if d == data else "read back WRONG (%d bytes)" % sum(x != y for x, y in zip(d, data))))
        bad += d != data
        f.erase(at)
        d = f.read(at, 512)
        print("erased again: %s" % ("blank" if d == b"\xff" * 512 else "NOT blank"))
        bad += d != b"\xff" * 512
        print("PASS" if not bad else "FAIL")
    elif a[0] == "store":
        best = None
        for k in range(1024):
            r = struct.unpack("<16I", f.read(0x801000 + 64 * k, 64))
            if r[0] == 0x31544553 and fsum(r[:15]) == r[15] and (best is None or r[1] > best[1][1]):
                best = (k, r)
        if best:
            k, r = best
            print("settings: record %d, number %d, %d bytes: %s" % (k, r[1], r[2], struct.pack("<11I", *r[3:14])[:r[2]].hex()))
        else:
            print("settings: none kept")
        name = lambda r: struct.pack("<6I", *r[3:9]).split(b"\0")[0].decode("ascii", "replace")
        r = struct.unpack("<16I", f.read(0x820000, 64))
        print("the network's weights: %s" % ("\"%s\", %d values, sum %08x" % (name(r), r[2], r[1]) if r[0] == 0x4B54454E and fsum(r[:15]) == r[15] else "none kept"))
        for s in range(1, 8):
            r = struct.unpack("<16I", f.read(0x840000 + 0x40000 * (s - 1), 64))
            print("table slot %d: %s" % (s, "\"%s\", sum %08x" % (name(r), r[1]) if r[0] == 0x4B424154 and fsum(r[:15]) == r[15] else "none kept"))
    else:
        sys.exit(__doc__)
    f.m.close()


if __name__ == "__main__":
    main()
