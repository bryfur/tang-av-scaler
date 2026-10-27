#!/usr/bin/env python3
"""Rev C-B's PCB: rev C's carrier (rev-c/layout.py) with the SN65DP159 retimer beside the SOM's J21:
the transceivers' four TX pairs straight across a 7 mm gap through their AC capacitors into its
inputs, its TMDS outputs to the ESD arrays and the receptacle on the back edge (kit/tmds_layout.py,
the same lines as rev B's).

    python3 rev-cb/gen_pcb.py [--route]       (see kit/pcbkit.py)
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "rev-c"))
import board  # noqa: E402
import floor  # noqa: E402
import pcbnew  # noqa: E402
from layout import RevC  # noqa: E402
from pcbkit import courtyard, pad_pos  # noqa: E402
from pcbnew import VECTOR2I, FromMM, ToMM  # noqa: E402

SER = [("D2", "35", "34"), ("D1", "32", "31"), ("D0", "29", "28"), ("CK", "26", "25")]
# the retimer's inputs (pins 1-12, top to bottom down its left side), per channel: P pin, N pin
DP_IN = {"D2": ("2", "3"), "D1": ("5", "6"), "D0": ("8", "9"), "CK": ("11", "12")}
CAP_X, CAP_PITCH = 175.0, 1.0          # the AC capacitors' column, between J21's pads and the retimer's
# the lanes: 0.2 mm lines 0.2 mm apart over In1's ground 0.21 mm down (7628, er 4.4), about 67 R
# single-ended and 105 R differential (IPC-2141): close to the pairs' 100 R. Seven millimetres at
# 5.94 Gb/s (edges about 40 ps, some 6 mm on the board) do not leave the impedance moot; 0.2 mm is
# also what J21's 0.4 mm pitch takes
SER_W = 0.2


SER_NETS = {"%s_%s_%s" % (side, ch, pol) for side in ("SER", "DP") for ch, _, _ in SER for pol in ("P", "N")}


class RevCB(RevC):
    POWER_NETS = RevC.POWER_NETS | {"1V1", "SW_1V1"}
    # the TX lanes: 0.2 mm lines, at J21's 0.4 mm pitch 0.2 mm apart (their pair gap's floor: 0.15)
    CLASSES = RevC.CLASSES + [("SERDES", SER_W, 0.15, SER_NETS, (SER_W, 0.15))]
    BIAS_NETS = RevC.BIAS_NETS | {"FB_1V1", "DP_VSADJ"}
    BUSES = [("J22", "U1")]
    # the retimer's TMDS outputs (pins 25-36 up its right side) to the ESD arrays and receptacle
    # where rev C-A's ADV7511 has its pairs
    TMDS = [("D2", "35", "34", "U9", "1", "10", "2", "9", "1", "3"),
            ("D1", "32", "31", "U9", "4", "7", "5", "6", "4", "6"),
            ("D0", "29", "28", "U10", "1", "10", "2", "9", "7", "9"),
            ("CK", "26", "25", "U10", "4", "7", "5", "6", "10", "12")]
    # the pins between the pairs, out to a via under the package (its pads end 3.07 mm from the
    # centre, its exposed pad at 2.05: the via at 2.47): GND and HPD_SNK among the outputs, HPD_SRC,
    # GND and I2C_EN among the inputs
    TMDS_INWARD = {"30": 1.0, "33": 1.0}
    INPUT_INWARD = {"4": 1.0, "7": 1.0, "10": 1.0}

    TX_CHIP = (floor.DP159_AT, 3.0)
    HDMI_AT = floor.HDMI_AT_CB
    # no S/PDIF jack (coax and optical on rev B's 5-pin header): the receptacle in its place and the
    # board 30 mm narrower (floor.py); what sat in the strip cut off comes in: the supplies below
    # the retimer's 1V1 buck, the buttons left of the corner hole, the S/PDIF header left of the
    # TMDS lines (which now run where it was), as high as the R jack lets it: both inputs' parts
    # below it then, left of the TMDS lines and right of the PCM1808's digital side (lower, the
    # optical input's buffer went above it, by the R audio input)
    X1 = floor.X1_CB
    UI_AT = floor.UI_AT_CB
    SPDIF_HEADER_AT = (179.0, 75.5)
    SUPPLIES = {"U4": (190.0, 140.0), "U5": (190.0, 131.0)}
    SILK_NEAR = [(r, "SPDIF" if r == "J13" else t) for r, t in RevC.SILK_NEAR]
    SILK_PINS = [(r, {"1": "COAX", "2": "G", "3": "OPT", "4": "G", "5": "5V"} if r == "J13" else pins, *side)
                 for r, pins, *side in RevC.SILK_PINS]

    def hand(self):
        h = RevC.hand(self)
        h["U2"] = floor.DP159_AT + (floor.DP159_ANGLE, "F")
        h["U7"] = (190.0, 122.0, 0, "F")                     # its 1V1 buck, below it
        return h

    def reserved(self):
        x, y = floor.DP159_AT
        # (and the AC capacitors' column, between J21 and the retimer)
        return RevC.reserved(self) + [(CAP_X - 4.0, y - 3.6, x - 3.0, y + 3.6)]

    def ser_caps(self):
        """{(channel, "P"/"N"): AC capacitor ref}."""
        out = {}
        for p in board.PARTS:
            ns = set(p.pins.values())
            for ch, _, _ in SER:
                for pol in ("P", "N"):
                    if ns == {"SER_%s_%s" % (ch, pol), "DP_%s_%s" % (ch, pol)}:
                        out[(ch, pol)] = p.ref
        return out

    def after_hand(self, ref, fp, fps, occ):
        RevC.after_hand(self, ref, fp, fps, occ)
        if ref != "U2":
            return
        # the AC capacitors in a column at CAP_PITCH, in the lines' order (D2 P, N, D1 P, ... top
        # to bottom), each across its line, its J21 end to the left
        caps = self.ser_caps()
        y0 = floor.DP159_AT[1] + 0.25 - 3.5 * CAP_PITCH
        k = 0
        for ch, _, _ in SER:
            for pol in ("P", "N"):
                f = fps[caps[(ch, pol)]]
                f.SetPosition(VECTOR2I(FromMM(CAP_X), FromMM(y0 + k * CAP_PITCH)))
                for a in (0, 180):
                    f.SetOrientationDegrees(a)
                    left = [q for q in f.Pads() if q.GetNetname().startswith("SER_")][0]
                    if ToMM(left.GetPosition().x) < CAP_X:
                        break
                occ.take("F", courtyard(f))
                self.HAND[f.GetReference()] = None
                k += 1

    def som_inward_gnd(self, fps):
        # J21's outer-row ground pins among and beside the TX lanes (69-99): their vias under the
        # receptacle, out of the lanes' way
        return {("J21", str(n)) for n in range(69, 100, 2)}

    def serdes(self, b, fps):
        """The TX lanes: from J21's pad straight out, 45 degrees onto the capacitor's line, through
        it, 45 degrees onto the retimer pin's line, into the pin."""
        caps = self.ser_caps()
        som = fps["J21"]
        dp = fps["U2"]

        def y_of(f, net):
            return [ToMM(q.GetPosition().y) for q in f.Pads() if q.GetNetname() == net][0]
        # the widest jog either side: how far the diagonals reach
        self.fan = (max(abs(y_of(fps[caps[(ch, pol)]], "SER_%s_%s" % (ch, pol)) - y_of(som, "SER_%s_%s" % (ch, pol)))
                        for ch, _, _ in SER for pol in ("P", "N")),
                    max(abs(pad_pos(dp, DP_IN[ch][k])[1] - y_of(fps[caps[(ch, pol)]], "DP_%s_%s" % (ch, pol)))
                        for ch, _, _ in SER for pol, k in (("P", 0), ("N", 1))))
        for ch, _, _ in SER:
            for pol, k in (("P", 0), ("N", 1)):
                net = b.FindNet("SER_%s_%s" % (ch, pol))
                dnet = b.FindNet("DP_%s_%s" % (ch, pol))
                (jx, jy), = [(ToMM(q.GetPosition().x), ToMM(q.GetPosition().y)) for q in som.Pads()
                             if q.GetNetname() == net.GetNetname()]
                cap = fps[caps[(ch, pol)]]
                (ax, ay), = [(ToMM(q.GetPosition().x), ToMM(q.GetPosition().y)) for q in cap.Pads()
                             if q.GetNetname() == net.GetNetname()]
                (bx, by), = [(ToMM(q.GetPosition().x), ToMM(q.GetPosition().y)) for q in cap.Pads()
                             if q.GetNetname() == dnet.GetNetname()]
                px, py = pad_pos(dp, DP_IN[ch][k])
                # J21's pad -> the capacitor: out, 45 degrees to its line; every line ends its
                # diagonal at the same x, so the diagonals run parallel and the lines only part
                x1 = jx + 0.6 + self.fan[0] - abs(ay - jy)
                pts = [(jx, jy), (x1, jy), (x1 + abs(ay - jy), ay), (ax, ay)]
                for a_, z_ in zip(pts, pts[1:]):
                    if abs(a_[0] - z_[0]) + abs(a_[1] - z_[1]) > 1e-6:
                        self.track(b, a_, z_, SER_W, pcbnew.F_Cu, net)
                # the capacitor -> the retimer's pin: every line starts its diagonal at the same x,
                # 45 degrees onto its pin's line, into the pin
                x2 = px - 0.6 - self.fan[1] + abs(py - by)
                pts = [(bx, by), (x2 - abs(py - by), by), (x2, py), (px, py)]
                for a_, z_ in zip(pts, pts[1:]):
                    if abs(a_[0] - z_[0]) + abs(a_[1] - z_[1]) > 1e-6:
                        self.track(b, a_, z_, SER_W, pcbnew.F_Cu, dnet)
        # its other GND pins (19, 41): straight in onto the exposed pad
        for num in ("19", "41"):
            q = [p for p in dp.Pads() if p.GetNumber() == num][0]
            qx, qy = ToMM(q.GetPosition().x), ToMM(q.GetPosition().y)
            cx_, cy_ = floor.DP159_AT
            dx, dy = cx_ - qx, cy_ - qy
            k = 1.2 / max(abs(dx), abs(dy))
            self.track(b, (qx, qy), (qx + dx * k * (abs(dx) > abs(dy)), qy + dy * k * (abs(dy) >= abs(dx))), 0.2,
                       pcbnew.F_Cu, q.GetNet())
        # the input side's pins between the pairs: inwards to a via each
        x, y = floor.DP159_AT
        for num, dist in self.INPUT_INWARD.items():
            q = [p for p in dp.Pads() if p.GetNumber() == num][0]
            qx, qy = ToMM(q.GetPosition().x), ToMM(q.GetPosition().y)
            v = (qx + dist if qx < x else qx - dist, qy)
            self.track(b, (qx, qy), v, 0.2, pcbnew.F_Cu, q.GetNet())
            self.via(b, v[0], v[1], q.GetNet(), *self.MIN_VIA)
        # the exposed pad: a 3 x 3 grid of ground vias
        g = b.FindNet("GND")
        for dx in (-1.2, 0.0, 1.2):
            for dy in (-1.2, 0.0, 1.2):
                self.via(b, x + dx, y + dy, g, *self.MIN_VIA)
        print("SerDes: 8 lines through their capacitors; retimer: %d inward vias, 9 pad vias" % len(self.INPUT_INWARD))

    def tx_fanout(self, b, fps):
        self.serdes(b, fps)
        self.tmds_fanout(b, fps)

    def fanout_skip(self):
        return RevC.fanout_skip(self) | {"U2"}


LAYOUT = RevCB(board, HERE)

if __name__ == "__main__":
    LAYOUT.cli(sys.argv)
