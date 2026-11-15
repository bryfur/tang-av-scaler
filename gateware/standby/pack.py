#!/usr/bin/env python3
"""pack.py [STANDBY.fs] [OUT]: the standby image as the link's firmware carries it
(firmware/xiao-wifi/main/standby.z): "SBY1", the bitstream's length, the sum of its configuration
words (as the FPGA's user code says it once loaded), then the bitstream deflated (zlib): nearly all
of it is zeros, 4.3 MB as some 30 kB.

Build the image first (on a build machine, from gateware/):
    GW_STANDBY=1 GW_SRCS=standby/standby.v GW_CST=standby/standby.cst GW_MODE=1080p60 \\
        GW_OUT=$PWD/gowin/build/standby gowin/build.sh
The packed file is in the repository, so the firmware builds without the FPGA's tools."""
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../../firmware/xiao-wifi/tools"))
import avx


def main():
    fs = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "../gowin/build/standby/avb/impl/pnr/avb.fs")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "../../firmware/xiao-wifi/main/standby.z")
    data, total = avx.bitstream(fs)
    z = zlib.compress(data, 9)
    open(out, "wb").write(b"SBY1" + struct.pack("<IHH", len(data), total, 0) + z)
    print("%s: %d bytes, sum %04x, deflated %d: %s" % (os.path.basename(fs), len(data), total, len(z), out))


if __name__ == "__main__":
    main()
