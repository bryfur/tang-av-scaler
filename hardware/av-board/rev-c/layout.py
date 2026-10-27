"""Rev C's PCB, shared by both carriers: the SOM, its connectors and standoffs, the back edge's
jacks, the ADV7181D front end (kit/adv7181d_layout.py, rev B's), the HDMI block (kit/tmds_layout.py,
rev B's turned 90 degrees), the 5 V spine to the SOM, and the front edge. A revision's gen_pcb.py
subclasses RevC with its transmitter's parts (rev-ca: ADV7511; rev-cb: SN65DP159).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "kit"))
import floor  # noqa: E402
import pcbkit  # noqa: E402
import pcbnew  # noqa: E402
from adv7181d_layout import ADV7181D, AV_RAILS, U1_BIAS_NETS, U1_CLASSES, U1_PRE_ROUTE, fit_u1  # noqa: E402
from pcbkit import pad_pos  # noqa: E402,F401
from pcbnew import ToMM  # noqa: E402
from tmds_layout import TMDSLayout, _rot  # noqa: E402

class RevC(ADV7181D, TMDSLayout, pcbkit.Layout):
    # F.Cu signal / In1 GND / In2 GND / B.Cu signal (JLC04161H-7628), as rev B
    LAYERS = 4
    INNER_GND = True
    TMDS_W, TMDS_PAIR = 0.25, (0.25, 0.25)
    MIN_VIA = (0.4, 0.2)
    # (the USB-C receptacle's GND and VBUS pads are 0.1 mm apart: JLCPCB's four-layer minimum is 0.09)
    MIN_CLEAR = 0.1
    X0, Y0, X1, Y1 = floor.X0, floor.Y0, floor.X1, floor.Y1
    # the places a revision may move (C-B's board is narrower): the buttons' row, the S/PDIF
    # header (C-A: the optical module's; C-B: rev B's, coax and optical), the 3V6 buck and the 3V3 LDO ("at the right front, away from both analog
    # front ends")
    UI_AT = floor.UI_AT
    SPDIF_HEADER_AT = (183.0, 86.0)
    SUPPLIES = {"U4": (222.0, 136.0), "U5": (212.0, 136.0)}
    POWER_NETS = {"+5V", "VBUS_IN", "3V6", "3V3", "1V8A", "3V0", "2V5", "5VA", "HDMI_5V", "SW_3V6", "SPDIF_5V",
                  "XIAO_5V", "XIAO_3V3"} | AV_RAILS
    CLOCK_NETS = {"AV_LLC", "IN_LLC", "PLL_CLK2", "PLL_CLK2_S"}
    TMDS_NETS = {"TMDS_D2_P", "TMDS_D2_N", "TMDS_D1_P", "TMDS_D1_N", "TMDS_D0_P", "TMDS_D0_N", "TMDS_CK_P", "TMDS_CK_N"}
    CLASSES = list(U1_CLASSES)
    # (and the S/PDIF coax input's AC-coupled node, high impedance: its parts first, by its pin)
    BIAS_NETS = set(U1_BIAS_NETS) | {"FB_3V3", "FB_3V6", "FB_1V8A", "PLL_XA", "PLL_XB", "SPDIF_AC"}
    # (the SOM receptacles: 0.8 mm round them for their ground vias, som_fanout)
    KEEP = {"U1": 0.5, "J20": 0.8, "J21": 0.8, "J22": 0.8}
    BOTH_SIDES = {"U1", "U2"}
    PRE_ROUTE = list(U1_PRE_ROUTE)
    TMDS_ANGLE = 90
    FPGA_HEADERS = ("J20", "J21", "J22")
    SILK_LABELS = []
    SILK_NEAR = [("J1", "Y"), ("J2", "Pb"), ("J3", "Pr"), ("J4", "L"), ("J5", "R"), ("J14", "S/PDIF"),
                 ("J15", "5V"), ("J6", "HDMI"), ("J7", "SYNC"), ("J8", "VGA"), ("J13", "OPTICAL"), ("J16", "JTAG"),
                 ("SW3", "RECONFIG")]
    # (J13's labels left of it: its ESD diodes sit right of its pins)
    SILK_PINS = [("J16", {"1": "3V3", "2": "G", "3": "TCK", "4": "TDO", "5": "TDI", "6": "TMS"}),
                 ("J13", {"1": "OUT", "2": "G", "3": "5V"}, "left")]
    TITLE_AT = (floor.X0 + 50.0, floor.Y1 - 1.6)

    def hand(self):
        """The hand placement: ref -> (x, y, angle or None, side)."""
        h = {}
        for ref, x in floor.BACK.items():
            if ref != "J15" and ref in self.refs:          # (C-B has no S/PDIF jack, J14)
                h[ref] = (x, floor.JACK_Y, 0, "F")         # facing out of the back edge
        h["J15"] = (floor.BACK["J15"], floor.Y0 + 4.5, 180, "F")      # (mouth out; its shell's tabs 2 mm inside)
        h["U1"] = (floor.U1_AT[0], floor.U1_AT[1], None, "F")
        h["U3"] = floor.PCM1808_AT + (0, "F")                  # PCM1808 under the audio jacks
        for ref in ("J20", "J21", "J22"):
            h[ref] = floor.connector(ref) + ("F",)
        for k, (x, y) in enumerate(floor.holes()):
            h["SO%d" % (k + 1)] = (x, y, 0, "F")
        # the HDMI block, rev B's turned 90 degrees (rev B: the ESD arrays at -90, the receptacle
        # at 90): the TMDS ESD arrays in line before the receptacle's pads, the receptacle on the
        # back edge
        h["U9"] = self.hdmi_at(8.3, 11.75) + (0, "F")
        h["U10"] = self.hdmi_at(8.3, 14.75) + (0, "F")
        h["J6"] = self.hdmi_at(15.6, 15.0) + (180, "F")
        # the XIAO at the front left, USB-C out of the front edge: pin 1 of each socket (D0, 5V) at
        # the USB end (rotation 90: the sockets run front to back)
        xa, ya = floor.XIAO_AT
        h["J12"] = (xa + 7.62, ya, 90, "F")
        h["J11"] = (xa - 7.62, ya, 90, "F")
        h["J16"] = (133.0, 146.0, 0, "F")                      # JTAG header, front
        h["J7"] = (104.0, 84.0, 90, "F")                       # SYNC header, by the video ESD array
        h["J8"] = floor.VGA_AT + (90, "F")                     # VGA header
        h["J13"] = self.SPDIF_HEADER_AT + (90, "F")            # the S/PDIF header, by its inputs' parts
        ux, uy = self.UI_AT
        h["SW1"] = (ux - 8.0, uy, 0, "F")
        h["SW2"] = (ux, uy, 0, "F")
        h["SW3"] = (ux + 8.0, uy, 0, "F")
        h["U17"] = floor.CLOCK_AT + (0, "F")                   # the clock generator, by J21's top
        # the supplies at the right front, away from both analog front ends; 1V8A (quiet, LDO) by
        # the ADV7181D
        for ref, (x, y) in self.SUPPLIES.items():
            h[ref] = (x, y, 0, "F")
        h["U6"] = (110.0, 112.0, 0, "F")
        # the 5 V input in order straight under the USB-C: its TVS (as close to the receptacle as
        # the CC resistors leave room for: the jacks either side leave the placer none), then the
        # fuse, its output into the spine to the SOM
        h["D6"] = (floor.BACK["J15"], floor.Y0 + 11.2, 0, "F")
        h["F1"] = (floor.BACK["J15"], floor.Y0 + 15.7, None, "F")
        return h

    # the HDMI transmitter: the centre of the chip whose right side the TMDS lines leave, and how far
    # right of it their corridor starts (the revision's); the receptacle's block (floor.py)
    TX_CHIP = None
    HDMI_AT = floor.HDMI_AT

    def hdmi_at(self, dx, dy):
        """A point of rev B's HDMI block (relative to its ADV7511) on rev C: turned 90 degrees, from
        HDMI_AT."""
        x, y = _rot(dx, dy, 90)
        return self.HDMI_AT[0] + x, self.HDMI_AT[1] + y

    # room kept free of small parts: under the SOM (its own parts hang 3 mm over the board), the 5 V
    # spine's lane, the TMDS lines' corridor
    def reserved(self):
        sx, sy = floor.SOM_AT
        sp = floor.BACK["J15"]
        # (the SOM; the 5 V input's branches from the USB-C to the fuse, vbus_in; the spine)
        return [(sx - 17.5, sy - 22.5, sx + 17.5, sy + 22.5), (sp - 2.8, floor.Y0 + 7.6, sp + 3.4, floor.Y0 + 14.2),
                (sp - 1.2, floor.Y0 + 17.0, sp + 1.2, sy - 22.5)] + self.tmds_corridor()

    def tmds_corridor(self):
        """The TMDS lines' L: right from the transmitter's right side (y - 4 .. y + 4), then up the
        right edge to the ESD arrays before the receptacle."""
        (x, y), dx = self.TX_CHIP
        hx, hy = self.HDMI_AT
        return [(x + dx, y - 4.0, hx + 17.0, y + 4.0), (hx + 8.0, hy - 12.8, hx + 17.0, y + 4.0)]

    def __init__(self, board, here):
        pcbkit.Layout.__init__(self, board, here)
        # the board's own mounting holes (M2.5), in the corners clear of the edges' connectors
        self.HOLES = [(self.X0 + 4.0, self.Y0 + 22.0), (self.X1 - 4.0, self.Y0 + 34.0),
                      (self.X0 + 4.0, self.Y1 - 26.0), (self.X1 - 4.0, self.Y1 - 4.0)]
        self.refs = {p.ref for p in board.PARTS}
        self.SILK_NEAR = [(r, t) for r, t in self.SILK_NEAR if r in self.refs]
        # no label under the SOM (45 x 35 mm, turned)
        (sx, sy), (w, h) = floor.SOM_AT, floor.som.SIZE
        self.SILK_HIDDEN = [(sx - h / 2, sy - w / 2, sx + h / 2, sy + w / 2)]
        self.HAND = self.hand()
        self.RESERVED = self.reserved()
        self.FIT = {"U1": fit_u1, "F1": fit_fuse}
        self.u1_init()

    # --- hooks

    def after_hand(self, ref, fp, fps, occ):
        if ref == "U1":
            self.u1_after_hand(fp, fps, occ)
        elif ref == "J15":
            # the receptacle's pads are 0.1 mm apart (GND and VBUS pairs), inside JLCPCB's 0.09 mm;
            # its plastic posts' holes unplated
            for q in fp.Pads():
                q.SetLocalClearance(pcbnew.FromMM(0.1))
                if q.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and not q.GetNetname():
                    q.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
                    q.SetLayerSet(pcbnew.PAD.UnplatedHoleMask())
                    q.SetSize(q.GetDrillSize())

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
        for ref in ("J1", "J2", "J3", "J4", "J5", "J14", "J15", "J6"):
            if ref not in fps:
                continue
            bx = pcbkit.courtyard(fps[ref], 0)
            assert bx[1] < self.Y0 + 1.5, (ref, "not at the back edge", bx)

    def vbus_in(self, b, fps):
        """The 5 V input from the USB-C to the fuse, as wide as the board's 2 A wants (left to the
        router it was 0.25 mm, about 1 A at a 10 C rise by IPC-2221: 27 mR and 0.1 W in 14 mm at
        2 A): from each of the two VBUS pads a 0.7 mm branch (each carries half), the left one
        straight down and 45 degrees into the TVS's cathode, the TVS's cathode on to the fuse at the
        spine's 1.2 mm, the right one down, round the TVS's ground pad and into the fuse's pad. The
        CC lines cross the branches on B.Cu."""
        n = b.FindNet("VBUS_IN")
        (lx, ly), (rx, ry) = sorted((ToMM(q.GetPosition().x), ToMM(q.GetPosition().y))
                                    for q in fps["J15"].Pads() if q.GetNetname() == "VBUS_IN")
        rbot = max(ToMM(q.GetBoundingBox().GetBottom()) for q in fps["J15"].Pads() if q.GetNetname() == "VBUS_IN")
        (d,) = [q for q in fps["D6"].Pads() if q.GetNetname() == "VBUS_IN"]
        (g,) = [q for q in fps["D6"].Pads() if q.GetNetname() == "GND"]
        (f,) = [q for q in fps["F1"].Pads() if q.GetNetname() == "VBUS_IN"]
        dx, dy = ToMM(d.GetPosition().x), ToMM(d.GetPosition().y)
        fb, gb = f.GetBoundingBox(), g.GetBoundingBox()
        fy = (ToMM(fb.GetTop()) + ToMM(fb.GetBottom())) / 2
        w = 0.7
        left = [(lx, ly), (lx, dy - (dx - lx)), (dx, dy)]
        for a, z in zip(left, left[1:]):
            self.track(b, a, z, w, pcbnew.F_Cu, n)
        self.track(b, (dx, dy), (dx, ToMM(fb.GetTop()) + 0.5), 1.2, pcbnew.F_Cu, n)
        # right: 0.6 mm past the pads' end (clear of the ground pad beside it), 45 degrees out to
        # 0.4 mm clear of the TVS's ground pad, down, 45 degrees into the fuse's pad near its end
        xr = ToMM(gb.GetRight()) + 0.4 + w / 2
        xf = ToMM(fb.GetRight()) - 0.5
        pts = [(rx, ry), (rx, rbot + 0.6), (xr, rbot + 0.6 + (xr - rx)), (xr, fy - (xr - xf)), (xf, fy)]
        for a, z in zip(pts, pts[1:]):
            self.track(b, a, z, w, pcbnew.F_Cu, n)
        print("VBUS_IN: USB-C (%.1f, %.1f) and (%.1f, %.1f) to the fuse, %.1f mm and 1.2 mm wide" % (lx, ly, rx, ry, w))

    def spine(self, b, fps):
        """The SOM's 5 V: from the fuse straight down to J22's six VBUS pins (its inner row's top
        end), 1.2 mm wide (about 2 A), then along the pads at their own width."""
        n = b.FindNet("+5V")
        f = [q for q in fps["F1"].Pads() if q.GetNetname() == "+5V"][0]
        fx, fy = ToMM(f.GetPosition().x), ToMM(f.GetPosition().y)
        vb = sorted((ToMM(q.GetPosition().y), ToMM(q.GetPosition().x)) for q in fps["J22"].Pads() if q.GetNetname() == "+5V")
        (ytop, xrow), (ybot, _) = vb[0], vb[-1]
        knee = (fx, ytop - 2.5)
        self.track(b, (fx, fy), knee, 1.2, pcbnew.F_Cu, n)
        self.track(b, knee, (xrow, ytop - 0.9), 1.2, pcbnew.F_Cu, n)
        self.track(b, (xrow, ytop - 0.9), (xrow, ytop), 0.6, pcbnew.F_Cu, n)
        self.track(b, (xrow, ytop), (xrow, ybot), 0.2, pcbnew.F_Cu, n)
        print("5 V spine: fuse (%.1f, %.1f) to J22 pins at (%.2f, %.2f-%.2f)" % (fx, fy, xrow, ytop, ybot))

    def som_fanout(self, b, fps):
        """The SOM receptacles' ground pads: a stub straight out of the row (the inner row's under
        the SOM, the outer row's away from it) to a via, staggered 0.8 / 1.4 mm so that the vias of
        neighbouring ground pads (0.4 mm apart) clear each other."""
        g = b.FindNet("GND")
        n = 0
        inward = self.som_inward_gnd(fps)
        for ref in ("J20", "J21", "J22"):
            fp = fps[ref]
            cx, cy = ToMM(fp.GetPosition().x), ToMM(fp.GetPosition().y)
            vertical = int(round(fp.GetOrientationDegrees())) % 180 == 90
            for q in fp.Pads():
                if q.GetNetname() != "GND":
                    continue
                x, y = ToMM(q.GetPosition().x), ToMM(q.GetPosition().y)
                k = int(round((y if vertical else x) / 0.4))
                d = 0.8 if k % 2 == 0 else 1.4
                out = -1 if (ref, q.GetNumber()) in inward else 1     # (inward: under the receptacle's body)
                if vertical:
                    v = (x + out * (d if x > cx else -d), y)
                else:
                    v = (x, y + out * (d if y > cy else -d))
                self.track(b, (x, y), v, 0.2, pcbnew.F_Cu, g)
                self.via(b, v[0], v[1], g, *self.MIN_VIA)
                n += 1
        print("SOM receptacles: %d ground vias" % n)

    def som_inward_gnd(self, fps):
        """SOM ground pads whose via goes inwards (a revision's lines leave there outwards)."""
        return set()

    def fanout(self, b, fps):
        self.som_fanout(b, fps)
        self.esd_clearance(fps)
        self.fanout_u1(b, fps)
        self.crystal_lines(b, fps)
        self.vbus_in(b, fps)
        self.spine(b, fps)
        self.tx_fanout(b, fps)

    def tx_fanout(self, b, fps):
        """The transmitter's own fanout and the TMDS lines (the revision's)."""

    def fanout_skip(self):
        return self.u1_fanout_skip() | {"U9.3", "U9.8", "U10.3", "U10.8", "J20", "J21", "J22"}


def fit_fuse(fp, x, y):
    """The input fuse upright, its +5 V end down (towards the SOM: the spine leaves it there)."""
    (a,) = [pad_pos(fp, q.GetNumber()) for q in fp.Pads() if q.GetNetname() == "+5V"]
    (b,) = [pad_pos(fp, q.GetNumber()) for q in fp.Pads() if q.GetNetname() == "VBUS_IN"]
    return abs(a[0] - b[0]) < 0.01 and a[1] > b[1]


