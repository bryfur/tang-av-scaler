#!/usr/bin/env python3
"""Rev C-B's PCB: rev C's carrier (rev-c/layout.py) with the SN65DP159 retimer beside the SOM's J21:
the transceivers' four TX pairs straight across a 7 mm gap through their AC capacitors into its
inputs, its TMDS outputs to the ESD arrays and the receptacle on the back edge (kit/tmds_layout.py,
the same lines as rev B's).

    python3 rev-cb/gen_pcb.py [--route]       (see kit/pcbkit.py)
"""

import math
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
# the transceivers' reference clock, MS5351M CLK0 and CLK1 (its inverse) through 2.2 R and 100 nF
# into J21's REFCLK0 pair: laid by the generator as a pair (refclk()), at the lanes' 0.2 mm, the
# router keeping other lines 30 mil off and other clocks 50 mil [TI SPRAAR7 3.1] (CLASS_CLASS)
REFCLK_CHAIN = [("PLL_CLK0", "PLL_CLK0_S"), ("PLL_CLK1", "PLL_CLK1_S"),        # the resistors
                ("PLL_CLK0_S", "SER_REFCLK_P"), ("PLL_CLK1_S", "SER_REFCLK_N")]  # the capacitors
REFCLK_NETS = {n for pair in REFCLK_CHAIN for n in pair}


class RevCB(RevC):
    POWER_NETS = RevC.POWER_NETS | {"1V1", "SW_1V1"}
    # the PCM1808's clocks too (12 MHz system clock, bit clock, word clock): periodic lines, which the
    # router keeps 50 mil from the reference pair (CLASS_CLASS; a route had the system clock 0.77 mm
    # from it)
    CLOCK_NETS = RevC.CLOCK_NETS | {"IN_SCKI", "IN_BCK", "IN_LRCK"}
    # the TX lanes: 0.2 mm lines, at J21's 0.4 mm pitch 0.2 mm apart (their pair gap's floor: 0.15)
    CLASSES = RevC.CLASSES + [("SERDES", SER_W, 0.15, SER_NETS, (SER_W, 0.15)),
                              ("REFCLK", SER_W, 0.15, REFCLK_NETS, (SER_W, 0.15))]
    CLASS_CLASS = RevC.CLASS_CLASS + [("REFCLK", "kicad_default", 0.76), ("REFCLK", "CLOCK", 1.27)]
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
    # 1.27 mm between the pairs along their run (5 W at 0.25 mm: TI SPRAAR7 3.1), up the 9 mm
    # corridor right of the retimer; the arrays' pins hold them 0.75 mm apart (kit/tmds_layout.py)
    TMDS_SPREAD = 0.52
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
    # (the debug header named, and each test pad its rail)
    SILK_NEAR = [(r, "SPDIF" if r == "J13" else t, *turn) for r, t, *turn in RevC.SILK_NEAR] + \
        [("J17", "DEBUG")] + list(board.TEST_PADS.items())
    SILK_PINS = [(r, {"1": "COAX", "2": "G", "3": "OPT", "4": "G", "5": "5V"} if r == "J13" else pins, *side)
                 for r, pins, *side in RevC.SILK_PINS] + \
        [("J17", {"1": "VREF", "2": "G", "3": "IN SCL", "4": "IN SDA", "5": "DP SCL", "6": "DP SDA", "7": "PLL SCL",
                  "8": "PLL SDA", "9": "D0", "10": "D1", "11": "D2", "12": "D3", "13": "D4", "14": "D5", "15": "G",
                  "16": "G"})]

    def hand(self):
        h = RevC.hand(self)
        h["U2"] = floor.DP159_AT + (floor.DP159_ANGLE, "F")
        # the clock generator 0.5 mm right of C-A's spot: room on its left for the reference clock's
        # resistors and capacitors before the SOM's edge (refclk()); its crystal held up against it,
        # off the lanes (where the placer put it, 1.6 mm from DP_D2_P: TI SPRAAR7 3.2, no high-speed
        # line near a crystal or clock generator). (Turned 180 degrees, its CLK2 and supply pins
        # would sit behind the reference pair.)
        ux, uy = floor.CLOCK_AT[0] + 0.5, floor.CLOCK_AT[1]
        h["U17"] = (ux, uy, 0, "F")
        h["Y2"] = (ux + 0.37, uy + 4.05, 0, "F")
        h["U7"] = (190.0, 122.0, 0, "F")                     # its 1V1 buck, below it
        h["J17"] = floor.DEBUG_AT_CB + (270, "F")            # the debug header, upright, pin 1 top left
        return h

    def reserved(self):
        x, y = floor.DP159_AT
        jx, jy = floor.DEBUG_AT_CB
        # (and the AC capacitors' column, between J21 and the retimer; room above the debug header
        # for its title, where SILK_NEAR puts it (left of C111, below C43): its pins' resistors would
        # take that spot first)
        cx, cy = floor.CLOCK_AT[0] + 0.5, floor.CLOCK_AT[1]
        # (and the reference pair's way out of U17's left top corner, past its resistors and
        # capacitors, to the SOM's edge: no other part on it)
        return RevC.reserved(self) + [(CAP_X - 4.0, y - 3.6, x - 3.0, y + 3.6), (jx - 4.1, jy - 13.4, jx + 3.2, jy - 10.3),
                                      (floor.SOM_AT[0] + 17.5, cy - 4.85, cx - 0.15, cy - 2.92)]

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

    # the reference pair: its two lines 0.4 mm apart (0.2 mm lines, 0.2 mm gap), spread to 1.0 mm
    # through the resistors and capacitors (side by side, symmetric: TI SPRAAR7 3.10)
    RC_PITCH, RC_SPREAD = 0.4, 0.3

    def refclk_parts(self):
        """{the part's U17-side net: ref} of the reference clock's resistors and capacitors."""
        return {a: p.ref for p in board.PARTS for a, z in REFCLK_CHAIN if set(p.pins.values()) == {a, z}}

    def refclk_geom(self, fps):
        """Where the reference pair runs: its lines' heights left of U17 (CLK0's, the lower, inner
        one, and CLK1's), the resistors' and capacitors' centres, the columns down J21's left side."""
        (x0, y0), = [pad_pos(fps["U17"], "10")]
        y_s = y0 - 0.81 - 0.63                  # CLK0's run: out of the pad's top end (0.81) and its corner
        y_n = y_s - self.RC_PITCH
        x_r = ToMM(fps["U17"].GetPosition().x) - 1.52 - 0.95 - 0.08    # left of U17's courtyard
        x_c = x_r - 0.95 - 0.94 - 0.31
        j21 = courtyard(fps["J21"], 0)
        xv_p = j21[0] - 0.25                    # down J21's left side, outside its body
        return y_s, y_n, x_r, x_c, xv_p, xv_p - self.RC_PITCH

    def after_hand(self, ref, fp, fps, occ):
        RevC.after_hand(self, ref, fp, fps, occ)
        if ref == "U17":
            # the reference clock's resistors, then its capacitors, side by side across the pair's
            # two lines (CLK1's above), U17's end of each to the right (left to the placer, they
            # went 20-30 mm off, past J21's top: a 45 mm loop, two single lines, one beside the
            # PCM1808's bit clock)
            y_s, y_n, x_r, x_c, _, _ = self.refclk_geom(fps)
            parts = self.refclk_parts()
            for net, x, y in (("PLL_CLK0", x_r, y_s + self.RC_SPREAD), ("PLL_CLK1", x_r, y_n - self.RC_SPREAD),
                              ("PLL_CLK0_S", x_c, y_s + self.RC_SPREAD), ("PLL_CLK1_S", x_c, y_n - self.RC_SPREAD)):
                f = fps[parts[net]]
                f.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
                f.SetOrientationDegrees(180)            # (pad 1, the U17 side, to the right)
                occ.take("F", courtyard(f))
                self.HAND[f.GetReference()] = None
            return
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
        # J21's outer-row ground pins among and beside the TX lanes (69-99), and the two beside the
        # reference pair's pins (94, 100): their vias under the receptacle, out of the lines' way
        return {("J21", str(n)) for n in range(69, 100, 2)} | {("J21", "94"), ("J21", "100")}

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
        # its other GND pins (19, 41): straight in onto the exposed pad, 0.3 mm into it (a stub of
        # 1.2 mm stopped 0.22 mm short of its edge: left dangling unless the router happened to join
        # it, the prune pass took it up and pin 19 was left unconnected)
        half = ToMM([p for p in dp.Pads() if p.GetNumber() == "49"][0].GetSize().x) / 2
        for num in ("19", "41"):
            q = [p for p in dp.Pads() if p.GetNumber() == num][0]
            qx, qy = ToMM(q.GetPosition().x), ToMM(q.GetPosition().y)
            cx_, cy_ = floor.DP159_AT
            dx, dy = cx_ - qx, cy_ - qy
            k = (max(abs(dx), abs(dy)) - half + 0.3) / max(abs(dx), abs(dy))
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

    def refclk(self, b, fps):
        """The reference pair, locked, on F.Cu at the lanes' 0.2 mm: out of CLK0's and CLK1's pads
        upwards, a corner onto the run left, spread through the resistors and capacitors and closed
        again, left under the SOM past J21's end, down outside its body, a corner into pins 98 (P)
        and 96 (N). CLK0's line, the P side, is the inner one at every corner; each corner is cut so
        the two diagonals lie the pitch apart, as the straight parts do."""
        y_s, y_n, x_r, x_c, xv_p, xv_n = self.refclk_geom(fps)
        u17, j21 = fps["U17"], fps["J21"]
        (p10x, p10y), (p9x, p9y) = pad_pos(u17, "10"), pad_pos(u17, "9")
        (jpx, jpy), = [pad_pos(j21, q.GetNumber()) for q in j21.Pads() if q.GetNetname() == "SER_REFCLK_P"]
        (jnx, jny), = [pad_pos(j21, q.GetNumber()) for q in j21.Pads() if q.GetNetname() == "SER_REFCLK_N"]
        assert jpy < jny and p10x < p9x, "the pair's order at J21 or U17 turned"
        s, d, d2 = self.RC_PITCH, self.RC_SPREAD, self.RC_PITCH * math.sqrt(2)
        c0 = c2 = c4 = 0.3
        c1 = c0 + (p9x - p10x) + (y_s - y_n) - d2           # (the outer line's corner, the longer)
        c3 = c2 + (xv_p - xv_n) + (y_s - y_n) - d2
        c5 = c4 + (xv_p - xv_n) + (jny - jpy) - d2
        xj = x_r + 0.51 + 0.1 + d                           # the spread's start, before the resistors
        xk = x_c - 0.48 - 0.1                               # its end, after the capacitors
        lines = [("PLL_CLK0", [(p10x, p10y), (p10x, y_s + c0), (p10x - c0, y_s), (xj, y_s), (xj - d, y_s + d),
                               (x_r + 0.51, y_s + d)]),
                 ("PLL_CLK0_S", [(x_r - 0.51, y_s + d), (x_c + 0.48, y_s + d)]),
                 ("SER_REFCLK_P", [(x_c - 0.48, y_s + d), (xk, y_s + d), (xk - d, y_s), (xv_p + c2, y_s),
                                   (xv_p, y_s + c2), (xv_p, jpy - c4), (xv_p + c4, jpy), (jpx, jpy)]),
                 ("PLL_CLK1", [(p9x, p9y), (p9x, y_n + c1), (p9x - c1, y_n), (xj, y_n), (xj - d, y_n - d),
                               (x_r + 0.51, y_n - d)]),
                 ("PLL_CLK1_S", [(x_r - 0.51, y_n - d), (x_c + 0.48, y_n - d)]),
                 ("SER_REFCLK_N", [(x_c - 0.48, y_n - d), (xk, y_n - d), (xk - d, y_n), (xv_n + c3, y_n),
                                   (xv_n, y_n + c3), (xv_n, jny - c5), (xv_n + c5, jny), (jnx, jny)])]
        length = {}
        for net, pts in lines:
            n = b.FindNet(net)
            for a_, z_ in zip(pts, pts[1:]):
                if abs(a_[0] - z_[0]) + abs(a_[1] - z_[1]) > 1e-6:
                    self.track(b, a_, z_, SER_W, pcbnew.F_Cu, n)
            side = "P" if "0" in net or net.endswith("_P") else "N"         # (CLK0's chain is the P side)
            length[side] = length.get(side, 0) + sum(math.hypot(z_[0] - a_[0], z_[1] - a_[1]) for a_, z_ in zip(pts, pts[1:]))
        print("reference pair: P %.1f mm, N %.1f mm laid (%.2f mm apart: %.0f ps)"
              % (length["P"], length["N"], abs(length["P"] - length["N"]), abs(length["P"] - length["N"]) * 6.3))

    # a fast line's keep-out to other lines [TI SPRAAR7 3.1: 30 mil]
    TMDS_KEEP = 0.76

    def hdmi_keepouts(self, b, fps):
        """Along the TMDS pairs' straight run (between the retimer's corners and the ESD arrays'
        break-out): strips on F.Cu beside and between the pairs keeping out other tracks, vias (and
        so their antipads in In1 under the pairs: >= 1.5 W from a void, 3.2) and the ground pour
        (a microstrip, as reckoned: 100 R). Under the lanes' AC capacitors' pads and the arrays'
        TMDS pads: In1 and In2 voided (all of a capacitor's pads, two layers deep, 3.10; 60 % of
        an ESD pad, 3.14), the pads' capacitance cut back."""
        hw = self.TMDS_W / 2
        runs = []
        for n in {"TMDS_%s_%s" % (p[0], s) for p in self.TMDS for s in ("P", "N")}:
            tr = [t for t in b.GetTracks() if t.GetNetname() == n and t.GetClass() == "PCB_TRACK"]
            t = max(tr, key=lambda t: t.GetLength())
            (x, ya), (_, yb) = (ToMM(t.GetStart().x), ToMM(t.GetStart().y)), (ToMM(t.GetEnd().x), ToMM(t.GetEnd().y))
            assert abs(ToMM(t.GetStart().x) - ToMM(t.GetEnd().x)) < 1e-3, (n, "the run is not upright")
            runs.append((x, min(ya, yb) + 0.1, max(ya, yb), tr))
        runs.sort(key=lambda r: r[0])
        # each strip as long as the run(s) beside it: outside the outer lines, between the pairs
        # (the innermost line's corner leaves its run's lower end on the outside: the strip stops short)
        strips = [(runs[0][0] - hw - self.TMDS_KEEP, runs[0][0] - hw - 0.01, runs[0][1], runs[0][2] - 0.4),
                  (runs[-1][0] + hw + 0.01, runs[-1][0] + hw + self.TMDS_KEEP, runs[-1][1], runs[-1][2])]
        strips += [(a[0] + hw + 0.01, z[0] - hw - 0.01, max(a[1], z[1]), min(a[2], z[2]))
                   for a, z in zip(runs, runs[1:]) if z[0] - a[0] > 1.0]                  # (between pairs)
        for sx0, sx1, sy0, sy1 in strips:
            self.rule_area(b, [(sx0, sy0), (sx1, sy0), (sx1, sy1), (sx0, sy1)], [pcbnew.F_Cu], tracks=True, vias=True,
                           fills=True)
        # and outside the outermost line's corner, its diagonal from the retimer's side up into the run
        x, _, y_low, tr = runs[-1]
        for t in tr:
            (ax, ay), (zx, zy) = sorted([(ToMM(t.GetStart().x), ToMM(t.GetStart().y)), (ToMM(t.GetEnd().x), ToMM(t.GetEnd().y))])
            if abs(zx - x) < 1e-3 and abs(zy - y_low) < 1e-3 and abs(ax - zx) > 1e-3 and abs(ay - zy) > 1e-3:
                n_ = (math.sqrt(0.5), math.sqrt(0.5))           # (outwards: down and to the right)
                i, o = hw + 0.01, hw + self.TMDS_KEEP
                self.rule_area(b, [(ax + n_[0] * i, ay + n_[1] * i), (zx + n_[0] * i, zy + n_[1] * i),
                                   (zx + n_[0] * o, zy + n_[1] * o), (ax + n_[0] * o, ay + n_[1] * o)],
                               [pcbnew.F_Cu], tracks=True, vias=True, fills=True)
                strips.append(None)
        y0, y1 = min(s[2] for s in strips if s), max(s[3] for s in strips if s)
        voids = [(q, 1.0) for c in self.ser_caps().values() for q in fps[c].Pads()]
        voids += [(q, math.sqrt(0.6)) for u in self.TMDS_ESD for q in fps[u].Pads() if q.GetNetname().startswith("TMDS_")]
        for q, k in voids:
            bb = q.GetBoundingBox()
            cx, cy = ToMM(bb.GetCenter().x), ToMM(bb.GetCenter().y)
            hx, hy = ToMM(bb.GetWidth()) * k / 2, ToMM(bb.GetHeight()) * k / 2
            self.rule_area(b, [(cx - hx, cy - hy), (cx + hx, cy - hy), (cx + hx, cy + hy), (cx - hx, cy + hy)],
                           [pcbnew.In1_Cu, pcbnew.In2_Cu], fills=True)
        print("HDMI keep-outs: %d strips along the TMDS run (y %.1f-%.1f), %d plane voids under pads"
              % (len(strips), y0, y1, len(voids)))

    def tx_fanout(self, b, fps):
        self.serdes(b, fps)
        self.refclk(b, fps)
        self.tmds_fanout(b, fps)
        self.hdmi_keepouts(b, fps)

    def fanout_skip(self):
        return RevC.fanout_skip(self) | {"U2"}


LAYOUT = RevCB(board, HERE)

if __name__ == "__main__":
    LAYOUT.cli(sys.argv)
