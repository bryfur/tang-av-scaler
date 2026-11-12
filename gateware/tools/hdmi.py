#!/usr/bin/env python3
"""hdmi.py [--ntsc] [--audio] [--retimer] [--no-scramble] [--frame] [--opt N] [--load [FS]]: the test picture out of the HDMI port, from a loaded bring-up
image (or after loading it): the MS5351M's 148.5 MHz to the transceivers, the lanes out of reset,
their PLL checked, the PCS resets pulsed, data valid, then the SN65DP159's outputs on. Prints what
it finds, with an HDMI 2.0 sink its lock and character errors over 5 s (SCDC).

2160p60 is sent scrambled with HDMI's video preamble and guard band (--no-scramble: neither); the
slower pictures plain, as DVI (--frame: with the preamble and guard band). --opt N: the scrambler's
open choices (rtl/hdmi_scr.v opt).

The SN65DP159 is set to a redriver (DEV_FUNC_MODE 00); --retimer leaves its default (a retimer
above 1 Gb/s). As a retimer it gets all three data lanes without an error (its own counters) and
sends 2.97 Gb/s on with hundreds of character errors a second on every channel, the sink in and
out of lock, with the lanes on one PLL or each on its own, whatever its output settings and the
cable; as a redriver none in 30 s (2026-11-11, tools/linkq.py). Its PLL is the suspect: the 1.1 V
supply (rev-cb review: the buck's output capacitance is under TI's table).
"""
import os
import subprocess
from fractions import Fraction
import sys
import time

import avb
import clkgen
import scdc

HERE = os.path.dirname(os.path.abspath(__file__))
GT_CTRL, GT_STAT = 0x20, 0x21
DP_OE, IN_RESET_N = 1 << 2, 1 << 3


def main():
    if "--load" in sys.argv:
        k = sys.argv.index("--load")
        fs = sys.argv[k + 1:k + 2] or [os.path.join(HERE, "../gowin/build/hdmi/avb/impl/pnr/avb.fs")]
        if subprocess.call([os.path.join(HERE, "load.sh"), fs[0]]):
            sys.exit(1)
        time.sleep(0.3)
    m = avb.Mon()
    if m.r(avb.ID) != 0x31425641:
        sys.exit("no bring-up image answers")
    mode = m.r(0x25)                            # pixels a word clock: 4 = 5.94 Gb/s, HDMI 2.0 rules
    m.w(avb.CTRL, IN_RESET_N)                   # the retimer's outputs off (OE low clears its registers)
    m.w(GT_CTRL, 0)                             # lanes in reset: nothing sent while the sink is told the rate
    # --ntsc: the picture rate 60/1.001 Hz (59.94: a 480i/480p source's), the clocks that much lower
    clkgen.setup(m, Fraction(148500000) * (Fraction(1000, 1001) if "--ntsc" in sys.argv else 1))
    m.w(avb.CTRL, IN_RESET_N | DP_OE)           # the retimer on: DDC passes
    m.flush()
    time.sleep(0.05)
    if "--retimer" not in sys.argv:
        m.i2c_write(1, 0x5E, [0x0A, 0x38])      # DEV_FUNC_MODE 00: a redriver; PD_EN toggled, it takes
        m.i2c_write(1, 0x5E, [0x09, 0x0A])
        m.flush()
        time.sleep(0.1)
        # (bit 2, HPD_AUTO_PWRDWN_DISABLE: the outputs stay on with hot plug low: a capture dongle
        # raises hot plug only once it sees a signal)
        m.i2c_write(1, 0x5E, [0x09, 0x06])
    # its outputs' termination by rate [SLLSEJ2G Table 8]: none to 2 Gb/s, 150-300 R to 3.4, 75-150 R above
    m.i2c_write(1, 0x5E, [0x0B, {1: 0x00, 2: 0x08}.get(mode, 0x18)])
    m.flush()
    time.sleep(0.3)
    # an HDMI 2.0 sink is told the clock's ratio and whether characters are scrambled before any are
    # sent [HDMI 2.0 6.1.3.2, 10.4.1.4: SCDC TMDS_Config]; the retimer hears the same write on DDC
    scramble = mode == 4 and "--no-scramble" not in sys.argv
    audio = "--audio" in sys.argv               # data islands: the sound and the InfoFrames (1080p60)
    frame = scramble or audio or "--frame" in sys.argv   # the video preamble and guard band (else DVI's blanking)
    opt = int(sys.argv[sys.argv.index("--opt") + 1], 0) if "--opt" in sys.argv else 0
    config = (2 if mode == 4 else 0) | (1 if scramble else 0)
    has_scdc = m.i2c_probe(2, 0x54)
    m.w(0x26, (1 if scramble else 0) | (2 if frame else 0) | (4 if audio else 0) | opt << 4)
    if has_scdc:
        m.i2c_write(2, 0x54, [0x02, 0x01])      # Source Version 1
        m.i2c_write(2, 0x54, [0x20, config])
    elif mode == 4:
        print("no SCDC answers: the sink is not told the 1/40 clock")
    # the signal must follow the write within 100 ms [HDMI 2.0 6.1.3.2] (a sink left waiting goes
    # back to 1/10, unscrambled: this one then finds the picture "out of range"): the lanes are
    # started straight away, the PLL given 20 ms, its lock looked at afterwards
    m.w(GT_CTRL, 0x00F)                         # lanes released: the quad's PLL locks on the reference
    m.flush()
    time.sleep(0.02)
    m.w(GT_CTRL, 0x0FF)                         # the transmit PCS resets, a pulse
    m.w(GT_CTRL, 0x00F)
    m.w(GT_CTRL, 0xF0F)                         # data valid
    m.flush()
    stat = m.r(GT_STAT)
    if not stat >> 13 & 1 and stat & 0xF != 0xF:    # the quad's LC PLL (or, a "cpll" build, each lane's)
        sys.exit("transceiver PLL not locked: GT_STAT %08x" % stat)
    time.sleep(1.6)
    edid = m.i2c_read(2, 0x50, 0, 8) if m.r(avb.STAT) & 4 else b""
    print("%s: word clock %.3f MHz, reference %.3f MHz, PLLs: quad %x lanes %x, hot plug %d%s, retimer \"%s\"" % (
        {1: "1080p60", 2: "2160p30", 4: "2160p60"}.get(mode, "?"),
        m.freq(2) / 1e6, m.freq(3) / 1e6, m.r(GT_STAT) >> 12 & 3, m.r(GT_STAT) & 0xF, m.r(avb.STAT) >> 2 & 1,
        ", EDID answers" if edid == bytes.fromhex("00ffffffffffff00") else "",
        m.i2c_read(1, 0x5E, 0, 8).decode(errors="replace").strip()))
    dp = m.i2c_read(1, 0x5E, 0x0A, 2)
    print("SN65DP159: %s, clock ratio heard 1/%d" % (
        {0: "redriver", 1: "retimer above 1 Gb/s", 2: "retimer for HDMI 2.0", 3: "retimer"}[dp[0] & 3],
        40 if dp[1] & 2 else 10))
    if m.i2c_probe(2, 0x54):
        time.sleep(3)                           # the sink locks
        scdc.rd(m, 0x50, 7)
        time.sleep(5)
        c, st = scdc.rd(m, 0x50, 7), scdc.rd(m, 0x40)[0]
        print("sink (SCDC): TMDS config %02x, scrambling seen %d, clock detected %d, channels locked %d%d%d, "
              "character errors in 5 s: %s" % (
                  scdc.rd(m, 0x20)[0], scdc.rd(m, 0x21)[0] & 1, st & 1, st >> 1 & 1, st >> 2 & 1, st >> 3 & 1,
                  [c[2 * k] | (c[2 * k + 1] & 0x7F) << 8 for k in range(3)]))
    m.close()


if __name__ == "__main__":
    main()
