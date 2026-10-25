#!/usr/bin/env python3
"""Rev A's PCB: the ADV7842 (256-ball BGA) board, six layers. The generator is kit/pcbkit.py;
this is rev A's outline, hand placement and the ADV7842's own rules: its rail planes, its ball
fanout, the 75 R arrays under its pixel side, its decoupling round its balls.

    python3 rev-a/gen_pcb.py [--route]       (see kit/pcbkit.py)
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "kit"))
import board  # noqa: E402
import pcbkit  # noqa: E402
import pcbnew  # noqa: E402
from pcbkit import courtyard, fit_adv7511, fit_esd, inside, pad_pos  # noqa: E402
from pcbnew import VECTOR2I, FromMM, ToMM  # noqa: E402

# Copper layers: 6 (F.Cu / In1 ground / In2 signal / In3 rail planes + signal / In4 ground / B.Cu),
# or LAYERS=4 (F.Cu signal / In1 ground / In2 rail planes + signal / B.Cu signal), which does not
# route: under the ADV7842 the inner balls' escapes need In2 free (design.md "Stack-up")
LAYERS = int(os.environ.get("LAYERS", "6"))

# ADV7842 rail planes (on PLANE_LAYER), in ball-grid coordinates (r = row A..T as 0..15, c = column 1..16
# as 0..15; outside the array < 0 or > 15). Each rail's balls lie inside its plane; the planes do
# not touch; each reaches out of the BGA on its own side to its filter (FL1-FL6 above). Outside the
# BGA (its courtyard ends at about -1.6 and 16.6) each widens to hold its filter and every one of
# its decoupling caps on the bottom, so a cap's pads go straight down into its plane: up to the
# J9 bus band (c 28.5) above, to the supplies (r 30) on the right.
ROWS = "ABCDEFGHJKLMNPRT"
PLANES = {
    # AVDD (F12-L12), PVDD (D15, D16) and TVDD (A5, B5, A15, B15) out of the analog side (up):
    # AVDD over the BGA's top right, PVDD into the column above D-E, TVDD left of it and under the
    # jack strip
    "AV_AVDD": [(4.55, 10.55), (11.45, 10.55), (11.45, 16.6), (18.0, 16.6), (18.0, 28.5), (4.55, 28.5)],
    "AV_PVDD": [(1.6, 13.55), (4.45, 13.55), (4.45, 28.5), (-3.5, 28.5), (-3.5, 16.8), (1.6, 16.8)],
    "AV_TVDD": [(-14.0, 3.55), (1.45, 3.55), (1.45, 16.5), (-3.8, 16.5), (-3.8, 28.5), (-14.0, 28.5)],
    # VDD (J7, K6-K9, L6-L9) and DVDDIO (F5-M5) out to the right, side by side; past the BGA VDD
    # takes the upper part, DVDDIO (25 caps with VDD_SDRAM) the lower and larger one; the
    # VDD_SDRAM balls M6-M10 (on DVDDIO) join M5 on F.Cu instead (CHAINS), so VDD can pass over them
    "AV_VDD": [(7.55, 4.55), (7.55, 10.45), (16.6, 10.45), (16.6, 15.5), (18.5, 15.5), (18.5, 18.0),
               (30.0, 18.0), (30.0, 10.5), (19.5, 10.5), (19.5, 9.5), (16.6, 9.5), (16.6, 5.55),
               (10.45, 5.55), (10.45, 4.55)],
    "AV_DVDDIO": [(4.55, -1.0), (16.6, -1.0), (16.6, -2.5), (33.5, -2.5), (33.5, 9.95), (20.0, 9.95),
                  (20.0, 8.95), (17.1, 8.95), (17.1, 4.45), (4.55, 4.45)],
}
# Balls joined on F.Cu to a neighbour instead of getting their own via: (ball, ball it joins)
CHAINS = [("M6", "M5"), ("M7", "M6"), ("M8", "M7"), ("M9", "M8"), ("M10", "M9"),     # VDD_SDRAM -> DVDDIO
          # CVDD (comparators, HDMI only: no current here): one via at E11, its filter routed
          ("E12", "E11"), ("D12", "E12"), ("C12", "D12"), ("C13", "C12"), ("C14", "C13")]

U1_RING = 1.0       # mm round the ADV7842's courtyard kept free of small parts (its escape ring)
# outer-ring balls that take an escape via anyway (like the pull-down balls, PD_*): SYNC_Y (J15)
# leaves the chip's top edge under the analog inputs' terminations, which F.Cu cannot get past
RING_VIA_NETS = {"SYNC_Y"}
# Groups for the small parts: (side, anchor) by block / net
DECOUPLE_U1 = {"AV_TVDD", "AV_AVDD", "AV_CVDD", "AV_VDD", "AV_DVDDIO", "AV_PVDD"}
FL_PLANE = {"FL1": "AV_VDD", "FL2": "AV_AVDD", "FL5": "AV_DVDDIO", "FL4": "AV_PVDD", "FL6": "AV_TVDD"}
FL_AXIS = {"FL1": "x", "FL5": "x", "FL2": "y", "FL4": "y", "FL6": "y"}


def grid(fp):
    """(r, c) in the ADV7842's ball grid -> board mm."""
    a1, a16, t1 = pad_pos(fp, "A1"), pad_pos(fp, "A16"), pad_pos(fp, "T1")
    dc = ((a16[0] - a1[0]) / 15, (a16[1] - a1[1]) / 15)
    dr = ((t1[0] - a1[0]) / 15, (t1[1] - a1[1]) / 15)
    return lambda r, c: (a1[0] + c * dc[0] + r * dr[0], a1[1] + c * dc[1] + r * dr[1])


def inverse_grid(fp):
    """board mm -> (r, c) in the ADV7842's ball grid."""
    a1, a16, t1 = pad_pos(fp, "A1"), pad_pos(fp, "A16"), pad_pos(fp, "T1")
    dcx, dcy = (a16[0] - a1[0]) / 15, (a16[1] - a1[1]) / 15
    drx, dry = (t1[0] - a1[0]) / 15, (t1[1] - a1[1]) / 15
    det = dcx * dry - dcy * drx

    def f(x, y):
        u, v = x - a1[0], y - a1[1]
        return (dcx * v - dcy * u) / det, (u * dry - v * drx) / det
    return f


def fit_u1(fp, x, y):
    """Pixel side (balls x1-5) down, towards J10 (row A then sits at the left)."""
    a1, a16 = pad_pos(fp, "A1"), pad_pos(fp, "A16")
    return a1[1] > y and a16[1] < y


class RevA(pcbkit.Layout):
    LAYERS = LAYERS
    POWER_NETS = {"+5V", "3V3", "2V5", "1V8A", "1V8B", "5VA", "HDMI_5V", "SW_2V5", "AV_VDD", "AV_AVDD", "AV_CVDD",
                  "AV_PVDD", "AV_DVDDIO", "AV_TVDD", "TX_DVDD", "TX_AVDD", "TX_PLVDD"}
    CLOCK_NETS = {"OUT_CLK", "AV_LLC", "IN_LLC"}
    TMDS_NETS = {"TMDS_D2_P", "TMDS_D2_N", "TMDS_D1_P", "TMDS_D1_N", "TMDS_D0_P", "TMDS_D0_N", "TMDS_CK_P", "TMDS_CK_N"}
    # The Console's outline, the SOM (nothing on it: about 7 mm tall) included, with the AV board's
    # underside 11 mm up; plus 15 mm past the Console's left edge, where the RCA jacks sit, leaving
    # room between them and the ADV7842 for the analog front end.
    X0, Y0, X1, Y1 = 74.2, 20.6, 168.8, 90.0
    # Hand placement: ref -> (x, y, angle, side).  angle in degrees (KiCad: counter-clockwise).
    HAND = {
        "J9": (129.0, 30.0, 180, "B"),
        "J10": (129.0, 79.0, 0, "B"),
        # RCA jacks on the left edge, facing left: audio at the top, video below (13 mm apart: the
        # shell lugs are 10 mm apart with 2.6 mm holes), centred on the board's height: 1.9 mm from
        # the outer lugs' pads to the top and bottom edges
        "J4": (85.2, 29.3, 90, "F"), "J5": (85.2, 42.3, 90, "F"),
        "J1": (85.2, 55.3, 90, "F"), "J2": (85.2, 68.3, 90, "F"), "J3": (85.2, 81.3, 90, "F"),
        # ADV7842 above J10's data end, pixel side down: its 75 R arrays in a row under it, then J10
        "U1": (113.0, 61.0, None, "F"),
        "Y1": (105.0, 49.0, 0, "F"),          # beside XTALP/XTALN (B16, C16), the top-left corner,
                                              # leaving E15/E16 (REFP/REFN) their caps
        "U3": (95.0, 37.5, 0, "F"),          # PCM1808 beside the audio jacks
        # ADV7511 below J9's data end, data side up, TMDS side down towards the HDMI connector; the
        # band between it and J9 is its bus's (see board.J9_NET)
        "U2": (148.0, 47.0, None, "F"),
        # the supplies under it, past the ADV7842's VDD and DVDDIO planes (to x 135.5), clear of both
        # buses and of the TMDS lines: 1V8B under the ADV7511, 1V8A below it, 3V3 and the 2V5 buck
        # beside them; +5 V comes from J10 pin 11 along the edge below J10
        "U7": (142.5, 63.0, 0, "F"), "U6": (142.5, 71.0, 0, "F"),
        "U5": (149.0, 65.0, 0, "F"), "U4": (148.5, 74.0, 0, "F"),
        "J6": (163.6, 62.0, 90, "F"),
        # TMDS ESD, in line before the HDMI pads (pins 1-12 at x 160.2, y 57.5-63)
        "U9": (156.3, 58.75, None, "F"), "U10": (156.3, 61.75, None, "F"),
        # the scaler's buttons, bottom right (near J10 pins 31/32)
        "SW1": (164.0, 76.0, 0, "F"), "SW2": (164.0, 86.0, 0, "F"),
        # ADV7842 rail filters on the bottom, at the exits of their rail planes (see PLANES): VDD and
        # DVDDIO leave to the right, AVDD, PVDD and TVDD upwards. CVDD is a routed rail with no plane:
        # its filter sits left of the BGA, four rows from its balls (C12-E12, one via at E11), where
        # TVDD's plane has room to spare
        "FL1": (128.0, 57.0, None, "B"), "FL5": (126.0, 66.5, None, "B"),
        "FL3": (97.5, 49.0, 90, "B"),         # beside FL6, a short 1V8A branch from FL4
        "FL4": (108.5, 48.0, None, "B"), "FL2": (113.5, 48.2, None, "B"),
        "FL6": (100.5, 49.0, None, "B"),
    }
    # room kept free of small parts for routing, both sides: the J10 bus's fan-out, from under the 75 R
    # arrays to J10's pins 1-26
    RESERVED = [(103.8, 72.4, 136.6, 76.9)]
    # the ADV7842 keeps a 1 mm ring clear of small parts on both sides: its outer two rings of balls
    # escape on the outer layers through there (the 75 R arrays are placed already)
    KEEP = {"U1": U1_RING}
    BOTH_SIDES = {"U1", "U2"}
    # bias resistors, the ADC references' caps and the regulators' feedback dividers, placed before
    # the decoupling takes their room: short traces [UG-214 Fig. 176, 177; HWG 7.6; TI TPS7A70,
    # TLV62569 layout]
    BIAS_NETS = {"RTERM", "R_EXT", "REFP", "REFN", "FB_3V3", "FB_2V5", "FB_1V8A", "FB_1V8B"}
    BUSES = [("J10", "U1"), ("J9", "U2")]
    SILK_LABELS = [("J1", "Y"), ("J2", "Pb"), ("J3", "Pr"), ("J4", "L"), ("J5", "R")]
    SILK_NEAR = [("J6", "HDMI")]

    def __init__(self):
        super().__init__(board, HERE)
        self.FIT = {"U1": fit_u1, "U2": fit_adv7511, "U9": fit_esd, "U10": fit_esd}
        self.FIT.update({r: self.fit_fl(r) for r in FL_PLANE})
        self.to_grid = None         # board mm -> U1's ball grid, once U1 is placed
        self.rr = {}                # decoupling round robin over a rail's balls

    def fit_fl(self, ref):
        """The filter along its axis, its output pad (3) inside its rail's In3 plane, on the side
        nearer the ADV7842."""
        def f(fp, x, y):
            plane = PLANES[FL_PLANE[ref]]
            p1, p3 = pad_pos(fp, "1"), pad_pos(fp, "3")
            along = abs(p1[0] - p3[0]) > abs(p1[1] - p3[1])
            if along != (FL_AXIS[ref] == "x"):
                return False
            r3, c3 = self.to_grid(*p3)
            r1, c1 = self.to_grid(*p1)
            return inside(plane, r3, c3) and (r3 - 7.5) ** 2 + (c3 - 7.5) ** 2 < (r1 - 7.5) ** 2 + (c1 - 7.5) ** 2
        return f

    def place_arrays(self, fps, u1, occ, value, edge, offset=10.1):
        """A group of 4-resistor arrays (by value) in a row along one side of the ADV7842, each beside
        the four balls it serves, its ADV7842 side (pads 1-4) towards the chip, pad 1 at its first
        ball's end. edge: two ball-grid points, (outside, inside) the side, that give its direction;
        offset: the arrays' distance from the chip's centre, mm."""
        g = grid(u1)
        cx, cy = ToMM(u1.GetPosition().x), ToMM(u1.GetPosition().y)
        (r0, c0), (r1, c1) = edge
        ox, oy = g(r0, c0)[0] - g(r1, c1)[0], g(r0, c0)[1] - g(r1, c1)[1]     # out of that side
        ax, ay = -oy, ox                                                        # along it
        balls = {pad.GetNetname(): (ToMM(pad.GetPosition().x), ToMM(pad.GetPosition().y)) for pad in u1.Pads()}
        want = []
        for p in board.PARTS:
            if p.ref.startswith("RN") and p.value == value:
                pts = [balls[p.pins[str(k)]] for k in (1, 2, 3, 4)]
                t = sum((x - cx) * ax + (y - cy) * ay for x, y in pts) / 4
                first = (pts[0][0] - cx) * ax + (pts[0][1] - cy) * ay
                last = (pts[3][0] - cx) * ax + (pts[3][1] - cy) * ay
                want.append((t, p.ref, first < last))
        want.sort()
        ts = [w[0] for w in want]
        for _ in range(50):                 # at least 2.3 mm apart, in order
            for k in range(1, len(ts)):
                if ts[k] - ts[k - 1] < 2.3:
                    d = (2.3 - (ts[k] - ts[k - 1])) / 2
                    ts[k - 1] -= d
                    ts[k] += d
        for (_, ref, ascending), t in zip(want, ts):
            fp = fps[ref]
            fp.SetPosition(VECTOR2I(FromMM(cx + ox * offset + ax * t), FromMM(cy + oy * offset + ay * t)))
            for a in (0, 90, 180, 270):
                fp.SetOrientationDegrees(a)
                p1, p4, p8 = pad_pos(fp, "1"), pad_pos(fp, "4"), pad_pos(fp, "8")
                inward = (p1[0] - p8[0]) * ox + (p1[1] - p8[1]) * oy < 0
                order = ((p1[0] - p4[0]) * ax + (p1[1] - p4[1]) * ay < 0) == ascending
                if inward and order:
                    break
            occ.take("F", courtyard(fp))
            self.HAND[ref] = None

    # --- hooks

    def after_hand(self, ref, fp, fps, occ):
        if ref == "U1":
            self.to_grid = inverse_grid(fp)
            # the pixel port's 75 R arrays along its pixel side (down, towards J10)
            self.place_arrays(fps, fp, occ, "75", ((7.5, -1), (7.5, 0)))

    def anchor_special(self, p, ic_pads, fps):
        # decoupling for U1: spread over its rail's balls, bottom side
        nets_ = [n for n in p.pins.values() if n != "GND"]
        for n in nets_:
            if n in DECOUPLE_U1 and p.ref.startswith("C") and p.value in ("220p", "33u", "10u"):
                # plane caps and bulk (33 uF + 10 uF after each filter): anywhere on the plane; by
                # the rail's filter
                fl = [(x, y) for x, y, r in ic_pads.get(n, []) if r.startswith("FL")]
                if fl:
                    return fl[0], "B"
            if n in DECOUPLE_U1 and p.ref.startswith("C"):
                balls = [(x, y) for x, y, r in ic_pads.get(n, []) if r == "U1"]
                if balls:
                    k = self.rr.get(n, 0)
                    self.rr[n] = k + 1
                    return balls[k % len(balls)], "B"
        # the unused SDRAM port's pull-downs (one 0402 each, no signal) go to the ADV7842's right
        # side, level with their balls, clear of the analog inputs above its top right corner
        pd = [n for n in nets_ if n.startswith("PD_SDRAM")]
        if pd:
            bx, by = [(x, y) for x, y, r in ic_pads[pd[0]] if r == "U1"][0]
            right = courtyard(fps["U1"], 0)[2] + U1_RING + 1.0
            return (right, min(by, courtyard(fps["U1"], 0)[3] - 1.0)), "F"
        return None

    def rank_special(self, p, ic_pads):
        """The ADV7842's per-ball decoupling (nearest the balls) before the parts on IC pins (2);
        plane caps and bulk after them."""
        nets_ = set(p.pins.values())
        if p.ref.startswith("C") and nets_ & DECOUPLE_U1 and p.value in ("10n", "100n"):
            return 1
        if p.ref.startswith("C") and nets_ & DECOUPLE_U1:
            return 3
        return None

    def where_for(self, p, fps):
        # a rail's decoupling goes where its rail pad is over the rail's plane (0.3 mm in): a via
        # beside it then goes straight down (fanout_planes), with nothing for the router to do
        plane = [n for n in p.pins.values() if n in PLANES]
        if not (plane and p.ref.startswith("C")):
            return None
        poly, to_grid = PLANES[plane[0]], self.to_grid
        rail_pad = [q for q in fps[p.ref].Pads() if q.GetNetname() == plane[0]][0]

        def where(box, poly=poly, to_grid=to_grid, pad=rail_pad, m=0.3):
            r = pad.GetBoundingBox()            # (at the spot being tried)
            x0, y0, x1, y1 = ToMM(r.GetLeft()) - m, ToMM(r.GetTop()) - m, ToMM(r.GetRight()) + m, ToMM(r.GetBottom()) + m
            return all(inside(poly, *to_grid(x, y)) for x in (x0, x1) for y in (y0, y1))
        return where

    def checks(self, fps):
        # orientation checks: the jacks open to the left edge, U2's data side faces J9 (above it)
        for ref in ("J1", "J2", "J3", "J4", "J5"):
            bx = courtyard(fps[ref], 0)
            assert bx[0] < self.X0 + 1.5, (ref, bx)
        assert fit_adv7511(fps["U2"], ToMM(fps["U2"].GetPosition().x), ToMM(fps["U2"].GetPosition().y)), "U2 rotation"
        assert courtyard(fps["J6"], 0)[2] > self.X1 - 1.5, "HDMI not at the right edge"

    def fanout(self, b, fps):
        self.fanout_u1(b, fps["U1"])

    def fanout_skip(self):
        return {"U1"}

    def on_plane(self, net, x, y):
        return net in PLANES and inside(PLANES[net], *self.to_grid(x, y))

    def rail_planes(self, b, fps):
        g = grid(fps["U1"])
        for net, poly in PLANES.items():
            pts = [g(r, c) for r, c in poly]
            pts = [(min(max(x, self.X0 + 0.5), self.X1 - 0.5), min(max(y, self.Y0 + 0.5), self.Y1 - 0.5)) for x, y in pts]
            self.zone(b, net, self.PLANE_LAYER, pts, priority=1)
            # no signal tracks across a rail plane (vias may pass)
            self.keepout(b, 0, 0, 0, 0, pts=pts, layer=self.PLANE_LAYER, vias=False)

    def fanout_u1(self, b, fp):
        """A dogbone via for each ADV7842 ball that needs one: every power and ground ball (to the
        planes) and every signal ball inside the outer two rings (the outer ones escape on F.Cu).
        The via sits on one of the ball's four diagonals: inside the ball's own plane for a rail,
        pointing away from the centre otherwise. A ground ball with no free diagonal joins a
        neighbouring ground ball on F.Cu."""
        g = grid(fp)
        used = set()
        owner = {}
        balls = {}
        for pad in fp.Pads():
            name = pad.GetNumber()
            r, c = ROWS.index(name[0]), int(name[1:]) - 1
            balls[(r, c)] = pad
        pending_gnd = []
        by_name = {p.GetNumber(): p for p in fp.Pads()}
        chained = {}
        for a_, z_ in CHAINS:
            chained[a_] = z_
            self.track(b, g(ROWS.index(a_[0]), int(a_[1:]) - 1), g(ROWS.index(z_[0]), int(z_[1:]) - 1), 0.15, pcbnew.F_Cu,
                       by_name[a_].GetNet())
        for (r, c), pad in sorted(balls.items(), key=lambda kv: -max(abs(kv[0][0] - 7.5), abs(kv[0][1] - 7.5))):
            net = pad.GetNetname()
            if not net or pad.GetNumber() in chained:
                continue
            # (+5V: the two HDMI 5 V detect balls, RXA/RXB_5V, take a via like a signal ball)
            power = net == "GND" or (net in self.POWER_NETS and net != "+5V")
            ring = min(r, c, 15 - r, 15 - c)
            # a ball with only a pull-down on it (PD_*: unused inputs, no signal) takes a via even in the
            # outer two rings, so it drops to the inner layers and leaves the outer layers' escape
            # channels to the signals (the SDRAM pull-downs in the corner under the analog inputs)
            if not power and ring <= 1 and not net.startswith("PD_") and net not in RING_VIA_NETS:
                continue
            cands = [(r + dr, c + dc) for dr in (-0.5, 0.5) for dc in (-0.5, 0.5)]
            if net in PLANES:
                cands = [p for p in cands if inside(PLANES[net], *p)]
            elif power and ring <= 1:
                # ground on the outer two rings: via inwards, keeping the signals' escape channels open
                cands.sort(key=lambda p: (p[0] - 7.5) ** 2 + (p[1] - 7.5) ** 2)
            else:
                cands.sort(key=lambda p: -((p[0] - 7.5) ** 2 + (p[1] - 7.5) ** 2))
            cands = [p for p in cands if p not in used]
            if not cands:
                if power:
                    pending_gnd.append((r, c, pad))     # joins a neighbour on the same net (below)
                    continue
                raise SystemExit("U1 ball %s (%s): no free via site (taken by %s)" % (
                    pad.GetNumber(), net, [owner.get(p) for p in [(r + dr, c + dc) for dr in (-0.5, 0.5) for dc in (-0.5, 0.5)]]))
            vr, vc = cands[0]
            used.add((vr, vc))
            owner[(vr, vc)] = pad.GetNumber()
            bx, by = g(r, c)
            vx, vy = g(vr, vc)
            w = 0.2 if power else self.TRACK
            self.track(b, (bx, by), (vx, vy), w, pcbnew.F_Cu, pad.GetNet())
            self.via(b, vx, vy, pad.GetNet())
        for r, c, pad in pending_gnd:
            for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                q = balls.get((r + dr, c + dc))
                if q is not None and q.GetNetname() == pad.GetNetname():
                    self.track(b, g(r, c), g(r + dr, c + dc), 0.2, pcbnew.F_Cu, pad.GetNet())
                    break
            else:
                raise SystemExit("U1 ball %s: no via site and no neighbour on its net" % pad.GetNumber())
        print("U1 fanout: %d vias, %d power balls joined to a neighbour" % (len(used), len(pending_gnd)))


LAYOUT = RevA()

if __name__ == "__main__":
    LAYOUT.cli(sys.argv)
