#!/usr/bin/env python3
"""jtagtest.py [MBIT [PERIOD_NS]]: the link's JTAG wires, tried without touching the FPGA's
configuration: random bits through the FPGA's one-bit BYPASS register (instruction 0xFF) over the
XVC port, MBIT megabits (default 8) at PERIOD_NS a clock (default: as fast as the link goes); what
comes back must be what went in, a bit later.  A clock counted twice or missed shows as the rest of
that shift coming back displaced; a wrong bit as itself."""
import os
import random
import socket
import struct
import sys

HOST = os.environ.get("AVX_HOST", "avscaler.local")


def main():
    mbit = float(sys.argv[1]) if len(sys.argv) > 1 else 8
    s = socket.create_connection((socket.gethostbyname(HOST), 2542), timeout=30)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def rd(n):
        b = b""
        while len(b) < n:
            c = s.recv(n - len(b))
            if not c:
                sys.exit("the link closed the connection")
            b += c
        return b

    def shift(tms, tdi, nbits):
        nb = (nbits + 7) // 8
        s.sendall(b"shift:" + struct.pack("<I", nbits) + tms.to_bytes(nb, "little") + tdi.to_bytes(nb, "little"))
        return int.from_bytes(rd(nb), "little")

    s.sendall(b"getinfo:")
    info = b""
    while not info.endswith(b"\n"):
        info += rd(1)
    vec = int(info.split(b":")[1]) // 2
    if len(sys.argv) > 2:
        s.sendall(b"settck:" + struct.pack("<I", int(sys.argv[2])))
        print("clock period %d ns" % struct.unpack("<I", rd(4))[0])
    shift(0x1F, 0, 6)                       # Test-Logic-Reset, Run-Test/Idle
    shift(0x3, 0, 4)                        # ... Shift-IR
    shift(0x80, 0xFF, 8)                    # BYPASS, leaving on the last bit
    shift(0x1, 0, 2)                        # Update-IR, Run-Test/Idle
    shift(0x1, 0, 3)                        # Select-DR, Capture-DR, Shift-DR
    random.seed(1)
    total = bad_shifts = bad_bits = 0
    nbits = vec * 8
    carry = 0                               # the bypass register's bit from the shift before
    first = True
    while total < mbit * 1e6:
        v = random.getrandbits(nbits)
        got = shift(0, v, nbits)
        want = (v << 1 | carry) & ((1 << nbits) - 1)
        if first:                           # (Capture-DR loads a 0)
            want &= ~1
            first = False
        carry = v >> (nbits - 1)
        diff = got ^ want
        if diff:
            bad_shifts += 1
            n = bin(diff).count("1")
            bad_bits += n
            if bad_shifts <= 5:
                low = (diff & -diff).bit_length() - 1
                print("  shift %d: %d bits differ, the first at bit %d of %d%s" % (
                    total // nbits, n, low, nbits, " (displaced from there on: a clock too many or too few)" if n > nbits // 8 else ""))
        total += nbits
    shift(0x3, 0, 3)                        # Exit1-DR, Update-DR, Run-Test/Idle
    print("%.1f Mbit through BYPASS in shifts of %d bits: %d shifts with differences, %d bits" % (
        total / 1e6, nbits, bad_shifts, bad_bits))
    return 1 if bad_shifts else 0


if __name__ == "__main__":
    sys.exit(main())
