#!/usr/bin/env python3
"""Rev B's PCB: the ADV7181D (64-lead LFCSP) board, four layers. The generator is kit/pcbkit.py;
this is rev B's outline, hand placement and the ADV7181D's own rules: its rotation (analog side
up, towards the jacks; pixel side down, towards J10), its decoupling round its supply pins, its
exposed pad (thermal vias, a paste grid).

    python3 rev-b/gen_pcb.py [--route]       (see kit/pcbkit.py)
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "kit"))
import board  # noqa: E402
import pcbkit  # noqa: E402
from adv7181d_layout import ADV7181D, AV_RAILS, U1_BIAS_NETS, U1_CLASSES, U1_PRE_ROUTE, fit_u1  # noqa: E402
from pcbkit import courtyard, fit_adv7511, fit_esd  # noqa: E402
from pcbnew import FromMM, ToMM  # noqa: E402
from tmds_layout import TMDSLayout  # noqa: E402


class RevB(ADV7181D, TMDSLayout, pcbkit.Layout):
    # F.Cu signal / In1 GND / In2 GND / B.Cu signal (JLC04161H-7628): each signal layer 0.21 mm over
    # its own solid plane, so tracks on either side have the same controlled impedance and return
    # path [HWG 7.2: a solid reference under the pixel clock; 6.3.2: 100 R TMDS pairs]
    LAYERS = 4
    INNER_GND = True
    # the TMDS pairs at the ADV7511's own 0.5 mm pin pitch: 0.25 mm lines, 0.25 mm gap, 103 R
    # differential over 0.21 mm of 7628 (IPC-2141; confirm in JLCPCB's calculator)
    TMDS_W, TMDS_PAIR = 0.25, (0.25, 0.25)
    # (0.4/0.2 mm vias at the ESD arrays' GND pads, between the pairs; JLCPCB's four-layer minimum
    # is 0.3/0.15)
    MIN_VIA = (0.4, 0.2)
    POWER_NETS = {"+5V", "3V6", "3V3", "1V8A", "1V8B", "5VA", "HDMI_5V", "SW_3V6", "TX_DVDD", "TX_AVDD", "TX_PLVDD",
                  "SPDIF_5V", "XIAO_5V", "XIAO_3V3"} | AV_RAILS
    CLOCK_NETS = {"OUT_CLK", "AV_LLC", "IN_LLC"}
    TMDS_NETS = {"TMDS_D2_P", "TMDS_D2_N", "TMDS_D1_P", "TMDS_D1_N", "TMDS_D0_P", "TMDS_D0_N", "TMDS_CK_P", "TMDS_CK_N"}
    # Rev A's outline: the Console's, plus 15 mm past its left edge for the jacks
    X0, Y0, X1, Y1 = 74.2, 20.6, 168.8, 90.0
    # Hand placement: ref -> (x, y, angle, side).  angle in degrees (KiCad: counter-clockwise).
    HAND = {
        "J9": (129.0, 30.0, 180, "B"),
        "J10": (129.0, 79.0, 0, "B"),
        # RCA jacks on the left edge, facing left, as on rev A: audio at the top, video below
        "J4": (85.2, 29.3, 90, "F"), "J5": (85.2, 42.3, 90, "F"),
        "J1": (85.2, 55.3, 90, "F"), "J2": (85.2, 68.3, 90, "F"), "J3": (85.2, 81.3, 90, "F"),
        # ADV7181D above J10's data end: its left side's lines (control, Y7-Y4, DE, VS) go to J10
        # pins 1-10 below its left, its bottom side's (INT, HS, Y3-Y0, C7-C5) to pins 13-19 under
        # it, its right side's (C4-C0, LLC) to pins 20-26 below its right; the analog inputs leave
        # its top towards the video jacks
        "U1": (116.0, 63.0, None, "F"),
        "U3": (95.0, 37.5, 0, "F"),          # PCM1808 beside the audio jacks
        # ADV7511 below J9's data end, data side up, TMDS side down towards the HDMI connector; the
        # band between it and J9 is its bus's (see board.J9_NET)
        "U2": (148.0, 47.0, None, "F"),
        # the supplies in a row below the TMDS corridor, above J10: 1V8A nearest the ADV7181D,
        # 1V8B under the ADV7511, 3V3, and the buck furthest right, away from the analog side and
        # the TMDS lines
        "U6": (137.0, 68.5, 0, "F"), "U7": (143.5, 68.5, 0, "F"),
        # (the buck turned over: SW faces the 3V3 LDO, its inductor between them; VIN and FB face
        # the free board right of it. The other way up its inductor's place above SW was the HDMI
        # DDC array's, placed first at the receptacle: SW ran 9 mm to it [TI-BUCK 10.1])
        "U5": (150.0, 68.5, 0, "F"), "U4": (156.5, 70.0, 180, "F"),
        "J6": (163.6, 62.0, 90, "F"),
        # TMDS ESD, in line before the HDMI pads (pins 1-12 at x 160.2, y 57.5-63)
        "U9": (156.3, 58.75, None, "F"), "U10": (156.3, 61.75, None, "F"),
        # the XIAO's sockets, in the free space between J9 and the ADV7181D, its USB-C pointing
        # right: the plug (about 11 mm up) then runs over low SMT parts only, 44 mm to the edge and
        # clear of the HDMI plug; to the left the jacks' 12 mm backs would leave it 16 mm. Rotated
        # 180, pad 1 of each (D0, 5V) at the USB end; the module spans x 103-125, y 33-51, 8.5 mm
        # up, SMT parts under it. J7's plug stands just past its left end
        "J12": (113.62, 34.4, 180, "F"), "J11": (113.62, 49.64, 180, "F"),
        "J7": (100.0, 47.4, 90, "F"),
        # the VGA header upright in the strip between the jacks and the ADV7181D, between the Y
        # line (above) and the Pr line (below), clear of the Console's hole at (100, 79)
        "J8": (95.5, 66.0, 90, "F"),
        # S/PDIF header in the strip under J10, under its pins 27-29 (the FPGA side of the
        # slicer) and far from the analog side; cables leave over the bottom edge
        "J13": (133.0, 85.4, 0, "F"),
        # the scaler's buttons, bottom right (near J10 pins 31/32)
        "SW1": (164.0, 76.0, 0, "F"), "SW2": (164.0, 86.0, 0, "F"),
    }
    # room kept free of small parts for routing, both sides: the J10 bus's fan-out, from under the
    # ADV7181D's series resistors to J10's pins 1-26
    # and the TMDS corridor, from under the ADV7511's TMDS pins to the HDMI connector (the pairs are
    # laid there before routing, see tmds())
    # and the bottom edge under J10: the board's name, and J13's pin labels and name
    RESERVED = [(103.8, 72.4, 136.6, 76.9), (144.55, 55.4, 158.9, 63.6),
                (94.0, 86.8, 139.5, 90.0), (126.0, 81.6, 139.5, 84.2)]
    KEEP = {"U1": 0.5}
    BOTH_SIDES = {"U1", "U2"}       # (under U1: its exposed pad's vias)
    # the ADV7511's bias resistor and the regulators' feedback dividers, placed with the pins' own
    # capacitors in board.py's order (R_EXT before the ADV7511's decoupling, a divider before its
    # regulator's output capacitor): short traces [HWG 7.6; TI TPS7A70, TLV62569 layout] (the
    # ADV7181D's references and loop filter are laid out, kit/adv7181d_layout.py)
    # (and the S/PDIF coax input's AC-coupled node, high impedance: its chain from the connector end,
    # by its pin; else from the FPGA's, along the bottom edge, U13 and U14 12 mm apart)
    BIAS_NETS = U1_BIAS_NETS | {"R_EXT", "FB_3V3", "FB_3V6", "FB_1V8A", "FB_1V8B", "SPDIF_AC"}
    BUSES = [("J10", "U1"), ("J9", "U2")]
    CLASSES = U1_CLASSES
    SILK_LABELS = [("J1", "Y"), ("J2", "Pb"), ("J3", "Pr"), ("J4", "L"), ("J5", "R")]
    SILK_NEAR = [("J6", "HDMI"), ("J11", "XIAO, USB >"), ("J13", "SPDIF")]
    SILK_PINS = [("J13", {"1": "COAX", "2": "G", "3": "OPT", "4": "G", "5": "5V"})]
    TITLE_AT = (110.0, 88.6)
    def __init__(self):
        super().__init__(board, HERE)
        self.FIT = {"U1": fit_u1, "U2": fit_adv7511, "U9": fit_esd, "U10": fit_esd}
        self.u1_init()

    # --- hooks

    def after_hand(self, ref, fp, fps, occ):
        if ref == "U1":
            self.u1_after_hand(fp, fps, occ)

    def anchor_special(self, p, ic_pads, fps):
        if p.ref == "D1":                   # (the 1V8A-to-3V3 clamp: at the 1V8A LDO's output)
            return [(x, y) for x, y, r in ic_pads["1V8A"] if r == "U6"][0], "F"
        return self.u1_anchor(p, ic_pads)

    def where_for(self, p, fps):
        return self.u1_where(p, fps)

    def rank_special(self, p, ic_pads):
        if p.ref == "D1":
            return 0
        return self.u1_rank(p)

    def checks(self, fps):
        # the jacks open to the left edge, U2's data side faces J9 (above it), HDMI at the right
        for ref in ("J1", "J2", "J3", "J4", "J5"):
            bx = courtyard(fps[ref], 0)
            assert bx[0] < self.X0 + 1.5, (ref, bx)
        assert fit_adv7511(fps["U2"], ToMM(fps["U2"].GetPosition().x), ToMM(fps["U2"].GetPosition().y)), "U2 rotation"
        assert courtyard(fps["J6"], 0)[2] > self.X1 - 1.5, "HDMI not at the right edge"

    # The TMDS pairs (kit/tmds_layout.py): pair, the ADV7511's P and N pins, the ESD array and its P
    # and N pads in and out (flow-through), the connector's P and N pins; the ADV7511 pins between
    # the pairs: out inwards, under the package, to a via each (pin: via's distance in from the
    # pad's centre)
    TMDS = [("D2", "43", "42", "U9", "1", "10", "2", "9", "1", "3"),
            ("D1", "40", "39", "U9", "4", "7", "5", "6", "4", "6"),
            ("D0", "36", "35", "U10", "1", "10", "2", "9", "7", "9"),
            ("CK", "33", "32", "U10", "4", "7", "5", "6", "10", "12")]
    TMDS_INWARD = {"34": 1.7, "37": 1.7, "38": 2.4, "41": 1.7}

    def fanout(self, b, fps):
        self.esd_clearance(fps)
        self.fanout_u1(b, fps)
        self.crystal_lines(b, fps)
        self.tmds_fanout(b, fps)

    PRE_ROUTE = U1_PRE_ROUTE

    def fanout_skip(self):
        return self.u1_fanout_skip() | {"U2.37", "U9.3", "U9.8", "U10.3", "U10.8"}


LAYOUT = RevB()

if __name__ == "__main__":
    LAYOUT.cli(sys.argv)
