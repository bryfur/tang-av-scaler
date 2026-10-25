#!/usr/bin/env python3
"""Write av-board.kicad_pcb from board.py: outline, footprints with their nets, placement.

Coordinates are the Console's (Sipeed's PCB coordinates, mm, top view, y down; design.md
"Mechanics"), so the sockets sit exactly over the Console's J9 and J10: each socket's pads are
checked against the header pins' positions and the script stops if one is off.

Placement: the big parts by hand (below), the small ones next to the pin they serve: each
two-terminal part, array or filter is put on the free spot nearest to its anchor (the IC pin it
connects to), on the side given for its group.

    python3 gen_pcb.py            # av-board.kicad_pcb, placed and unrouted
    python3 gen_pcb.py --route    # ... routed by Freerouting (SES=file.ses: import that session instead;
                                  # ROUTER=deeppcb MINUTES=60: route on DeepPCB, see deeppcb.py)
"""

import json
import math
import os
import subprocess
import sys

import pcbnew
from pcbnew import VECTOR2I, FromMM, ToMM

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board  # noqa: E402

NAME = "av-board"
OUT = os.environ.get("PCB", os.path.join(HERE, NAME + ".kicad_pcb"))      # PCB=x.kicad_pcb: a trial elsewhere
SYSFP = "/usr/share/kicad/footprints"
JAVA = "/home/linuxbrew/.linuxbrew/opt/openjdk/bin/java"
# Freerouting: 1.9.0 by default. On this board 2.3-2.5 oscillate between 120 and 220 unrouted
# connections pass after pass; 1.9.0 gets within ~10. 1.9.0 needs an X display even in batch mode:
# a private Xvfb (Homebrew's xorg-server) runs for it. FREEROUTING=2.5.0 picks the headless one.
FREEROUTING_VERSION = os.environ.get("FREEROUTING", "1.9.0")
FREEROUTING = os.path.expanduser("~/tools/freerouting/freerouting-%s.jar" % FREEROUTING_VERSION)
XVFB = "/home/linuxbrew/.linuxbrew/bin/Xvfb"

# Copper layers: 6 (F.Cu / In1 ground / In2 signal / In3 rail planes + signal / In4 ground / B.Cu),
# or LAYERS=4 (F.Cu signal / In1 ground / In2 rail planes + signal / B.Cu signal), which does not
# route: under the ADV7842 the inner balls' escapes need In2 free (design.md "Stack-up")
LAYERS = int(os.environ.get("LAYERS", "6"))
PLANE_LAYER = pcbnew.In2_Cu if LAYERS == 4 else pcbnew.In3_Cu

# Rules (JLCPCB 4-layer standard: 0.09 mm track/space, 0.3 mm drill; we stay well above)
TRACK, CLEAR, VIA_D, VIA_DRILL = 0.127, 0.127, 0.5, 0.3
POWER_NETS = {"+5V", "3V3", "2V5", "1V8A", "1V8B", "5VA", "HDMI_5V", "SW_2V5", "AV_VDD", "AV_AVDD", "AV_CVDD",
              "AV_PVDD", "AV_DVDDIO", "AV_TVDD", "TX_DVDD", "TX_AVDD", "TX_PLVDD"}
CLOCK_NETS = {"OUT_CLK", "AV_LLC", "IN_LLC"}
TMDS_NETS = {"TMDS_D2_P", "TMDS_D2_N", "TMDS_D1_P", "TMDS_D1_N", "TMDS_D0_P", "TMDS_D0_N", "TMDS_CK_P", "TMDS_CK_N"}

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

# Board: x 60-190, y 20.6-90 (the Console's y extent), a window over the SOM
# The Console's outline, the SOM (nothing on it: about 7 mm tall) included, with the AV board's
# underside 11 mm up; plus 15 mm past the Console's left edge, where the RCA jacks sit, leaving
# room between them and the ADV7842 for the analog front end.
X0, X1, Y0, Y1 = 74.2, 168.8, 20.6, 90.0
WIN = (-10.0, -10.0, -9.0, -9.0)        # no window (outside the board: the checks never hit it)
WIN_POLY = []
NOTCHES = []
# M2.5 standoffs on the Console's four H7_* holes beside the headers
HOLES = [(100.0, 30.0), (158.0, 30.0), (100.0, 79.0), (158.0, 79.0)]
BUTTONS = []


def J9_PIN(n):
    return (153.13 - 2.54 * ((n - 1) // 2), 28.73 if n % 2 else 31.27)


def J10_PIN(n):
    return (104.87 + 2.54 * ((n - 1) // 2), 80.27 if n % 2 else 77.73)


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


def place_arrays(fps, u1, occ, value, edge, offset=10.1):
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
        HAND[ref] = None


def fit_u1(fp, x, y):
    """Pixel side (balls x1-5) down, towards J10 (row A then sits at the left)."""
    a1, a16 = pad_pos(fp, "A1"), pad_pos(fp, "A16")
    return a1[1] > y and a16[1] < y


def fit_u2(fp, x, y):
    """Data side (D8-D15, pins 81-88) up, towards J9; TMDS side down."""
    return pad_pos(fp, "84")[1] < y - 5 and pad_pos(fp, "36")[1] > y + 5


def fit_esd(fp, x, y):
    """Lines enter on pads 1-5 (U2's side, left) and leave on 10-6; pad 1 at the top."""
    p1, p10, p5 = pad_pos(fp, "1"), pad_pos(fp, "10"), pad_pos(fp, "5")
    return p1[0] < p10[0] and p1[1] < p5[1]


FL_PLANE = {"FL1": "AV_VDD", "FL2": "AV_AVDD", "FL5": "AV_DVDDIO", "FL4": "AV_PVDD", "FL6": "AV_TVDD"}
_u1_grid = []


FL_AXIS = {"FL1": "x", "FL5": "x", "FL2": "y", "FL4": "y", "FL6": "y"}


def fit_fl(ref):
    """The filter along its axis, its output pad (3) inside its rail's In3 plane, on the side
    nearer the ADV7842."""
    def f(fp, x, y):
        to_grid = _u1_grid[0]
        plane = PLANES[FL_PLANE[ref]]
        p1, p3 = pad_pos(fp, "1"), pad_pos(fp, "3")
        along = abs(p1[0] - p3[0]) > abs(p1[1] - p3[1])
        if along != (FL_AXIS[ref] == "x"):
            return False
        r3, c3 = to_grid(*p3)
        r1, c1 = to_grid(*p1)
        return inside(plane, r3, c3) and (r3 - 7.5) ** 2 + (c3 - 7.5) ** 2 < (r1 - 7.5) ** 2 + (c1 - 7.5) ** 2
    return f


FIT = {"U1": fit_u1, "U2": fit_u2, "U9": fit_esd, "U10": fit_esd}
FIT.update({r: fit_fl(r) for r in FL_PLANE})

U1_RING = 1.0       # mm round the ADV7842's courtyard kept free of small parts (its escape ring)
# outer-ring balls that take an escape via anyway (like the pull-down balls, PD_*): SYNC_Y (J15)
# leaves the chip's top edge under the analog inputs' terminations, which F.Cu cannot get past
RING_VIA_NETS = {"SYNC_Y"}
# room kept free of small parts for routing, both sides: the J10 bus's fan-out, from under the 75 R
# arrays to J10's pins 1-26
RESERVED = [(103.8, 72.4, 136.6, 76.9)]

# Groups for the small parts: (side, anchor) by block / net
DECOUPLE_U1 = {"AV_TVDD", "AV_AVDD", "AV_CVDD", "AV_VDD", "AV_DVDDIO", "AV_PVDD"}
# bias resistors, the ADC references' caps and the regulators' feedback dividers, placed before
# the decoupling takes their room: short traces [UG-214 Fig. 176, 177; HWG 7.6; TI TPS7A70,
# TLV62569 layout]
BIAS_NETS = {"RTERM", "R_EXT", "REFP", "REFN", "FB_3V3", "FB_2V5", "FB_1V8A", "FB_1V8B"}


def load(fp_id):
    lib, name = fp_id.split(":")
    path = os.path.join(HERE, "lib", "lcsc.pretty") if lib == "lcsc" else os.path.join(SYSFP, lib + ".pretty")
    fp = pcbnew.FootprintLoad(path, name)
    assert fp, fp_id
    return fp


def pad_pos(fp, num):
    for p in fp.Pads():
        if p.GetNumber() == num:
            v = p.GetPosition()
            return ToMM(v.x), ToMM(v.y)
    raise KeyError(num)


def outline(b):
    def seg(a, c):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(VECTOR2I(FromMM(a[0]), FromMM(a[1])))
        s.SetEnd(VECTOR2I(FromMM(c[0]), FromMM(c[1])))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(FromMM(0.1))
        b.Add(s)

    def rect(x0, y0, x1, y1):
        seg((x0, y0), (x1, y0))
        seg((x1, y0), (x1, y1))
        seg((x1, y1), (x0, y1))
        seg((x0, y1), (x0, y0))

    def circle(x, y, d):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_CIRCLE)
        s.SetCenter(VECTOR2I(FromMM(x), FromMM(y)))
        s.SetEnd(VECTOR2I(FromMM(x + d / 2), FromMM(y)))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(FromMM(0.1))
        b.Add(s)

    rect(X0, Y0, X1, Y1)
    for k in range(len(WIN_POLY)):
        seg(WIN_POLY[k], WIN_POLY[(k + 1) % len(WIN_POLY)])
    for x, y in BUTTONS:
        circle(x, y, 7.0)
    for x, y in HOLES:
        fp = load("MountingHole:MountingHole_2.7mm_M2.5")
        fp.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
        fp.SetReference("H%d" % (HOLES.index((x, y)) + 1))
        b.Add(fp)


# ---------------------------------------------------------------------------
# Small-part placer: free-spot search on an occupancy grid per side
# ---------------------------------------------------------------------------

STEP = 0.25


class Occ:
    def __init__(self):
        self.cells = {"F": set(), "B": set()}

    def _cells(self, box):
        x0, y0, x1, y1 = box
        for i in range(int(math.floor(x0 / STEP)), int(math.ceil(x1 / STEP))):
            for j in range(int(math.floor(y0 / STEP)), int(math.ceil(y1 / STEP))):
                yield (i, j)

    def free(self, side, box):
        x0, y0, x1, y1 = box
        if x0 < X0 + 0.5 or x1 > X1 - 0.5 or y0 < Y0 + 0.5 or y1 > Y1 - 0.5:
            return False
        for wx0, wy0, wx1, wy1 in [WIN] + NOTCHES:
            if x1 > wx0 - 0.5 and x0 < wx1 + 0.5 and y1 > wy0 - 0.5 and y0 < wy1 + 0.5:
                return False
        for bx, by in BUTTONS:
            if x1 > bx - 4 and x0 < bx + 4 and y1 > by - 4 and y0 < by + 4:
                return False
        for rx0, ry0, rx1, ry1 in RESERVED:
            if x1 > rx0 and x0 < rx1 and y1 > ry0 and y0 < ry1:
                return False
        for hx, hy in HOLES:
            if x1 > hx - 3 and x0 < hx + 3 and y1 > hy - 3 and y0 < hy + 3:
                return False
        c = self.cells[side]
        return not any(k in c for k in self._cells(box))

    def take(self, side, box):
        self.cells[side].update(self._cells(box))


def courtyard(fp, margin=0.25):
    """The footprint's courtyard (or pads') bounding box, both layers, mm."""
    bb = None
    for layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
        for item in fp.GraphicalItems():
            if item.GetLayer() == layer:
                r = item.GetBoundingBox()
                if bb is None:
                    bb = pcbnew.BOX2I(r.GetPosition(), r.GetSize())
                else:
                    bb.Merge(r)
    for pad in fp.Pads():
        r = pad.GetBoundingBox()
        if bb is None:
            bb = pcbnew.BOX2I(r.GetPosition(), r.GetSize())
        else:
            bb.Merge(r)
    return (ToMM(bb.GetLeft()) - margin, ToMM(bb.GetTop()) - margin,
            ToMM(bb.GetRight()) + margin, ToMM(bb.GetBottom()) + margin)


def crossings(hdr, ic, fps):
    """How many pairs of an IC's lines to a header must cross: each line's near end (the pad on
    its net nearest the header pin, within reach of the IC) in order round the IC, cut on the side
    away from the header, against the order of the header pins (pins in one column do not count)."""
    cx, cy = ToMM(ic.GetPosition().x), ToMM(ic.GetPosition().y)
    bx = courtyard(ic, 0)
    reach = math.hypot(bx[2] - bx[0], bx[3] - bx[1]) / 2 + 6
    above = ToMM(hdr.GetPosition().y) < cy
    pads = {}
    for fp in fps.values():
        if fp is not hdr:
            for pad in fp.Pads():
                v = pad.GetPosition()
                pads.setdefault(pad.GetNetname(), []).append((ToMM(v.x), ToMM(v.y)))
    lines = []
    for pad in hdr.Pads():
        n = pad.GetNetname()
        if n in ("GND", "+5V") or n not in pads:
            continue
        hx, hy = ToMM(pad.GetPosition().x), ToMM(pad.GetPosition().y)
        sx, sy = min(pads[n], key=lambda q: math.hypot(q[0] - hx, q[1] - hy))
        if math.hypot(sx - cx, sy - cy) > reach:
            continue
        # (the cut a little to the left of straight away from the header: lines from right under
        # the IC go round its right)
        t = math.atan2(sy - cy, sx - cx)
        key = (t - math.pi / 2 - 0.4) % (2 * math.pi) if above else -((t + math.pi / 2 - 0.4) % (2 * math.pi))
        lines.append((round(hx, 2), key))
    return sum(1 for i, a in enumerate(lines) for b in lines[i + 1:]
               if a[0] != b[0] and (a[0] < b[0]) != (a[1] < b[1]))


def place_near(occ, fp, side, anchor, angles=(0, 90), where=None):
    """Put fp on the free spot nearest anchor (spiral search)."""
    ax, ay = anchor
    if side == "B" and not fp.IsFlipped():
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    best = None
    for r in [k * 0.5 for k in range(0, 120)]:
        n = max(1, int(2 * math.pi * r / 0.5))
        for k in range(n):
            t = 2 * math.pi * k / n
            x, y = ax + r * math.cos(t), ay + r * math.sin(t)
            for ang in angles:
                fp.SetOrientationDegrees(ang)
                fp.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
                box = courtyard(fp)
                if occ.free(side, box) and (where is None or where(box)):
                    best = (x, y, ang, box)
                    break
            if best:
                break
        if best:
            break
    if not best and where is not None:
        print("note: %s placed off its plane (no room on it)" % fp.GetReference())
        return place_near(occ, fp, side, anchor, angles)
    assert best, "no room for %s near %s" % (fp.GetReference(), anchor)
    x, y, ang, box = best
    fp.SetOrientationDegrees(ang)
    fp.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
    occ.take(side, box)


def main():
    b = pcbnew.BOARD()
    b.SetCopperLayerCount(LAYERS)
    ds = b.GetDesignSettings()
    ds.SetBoardThickness(FromMM(1.6))
    outline(b)

    nets = {}

    def net(name):
        if name not in nets:
            nets[name] = pcbnew.NETINFO_ITEM(b, name)
            b.Add(nets[name])
        return nets[name]

    fps = {}
    for p in board.PARTS:
        fp = load(p.footprint)
        fp.SetReference(p.ref)
        fp.SetValue(p.value)
        fp.SetFPIDAsString(p.footprint)
        if p.lcsc:
            fp.SetField("LCSC", p.lcsc)
        if p.dnp:
            fp.SetDNP(True)
        for pad in fp.Pads():
            n = p.pins.get(pad.GetNumber())
            if n is None and pad.GetNumber() == "" and "9" in p.pins:
                n = p.pins["9"]                 # thermal vias in an exposed pad (SOIC-8 EP)
            if n is not None:
                pad.SetNet(net(n))
        b.Add(fp)
        fps[p.ref] = fp

    occ = Occ()

    # --- hand-placed parts
    for ref, spec in list(HAND.items()):
        if spec is None:
            continue
        x, y, ang, side = spec
        fp = fps[ref]
        if side == "B":
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
        if ang is None:
            for a in (0, 90, 180, 270):
                fp.SetOrientationDegrees(a)
                if FIT[ref](fp, x, y):
                    break
            else:
                raise SystemExit("no rotation of %s fits" % ref)
        else:
            fp.SetOrientationDegrees(ang)
        if ref == "U1":
            _u1_grid[:] = [inverse_grid(fp)]
            # the pixel port's 75 R arrays along its pixel side (down, towards J10)
            place_arrays(fps, fp, occ, "75", ((7.5, -1), (7.5, 0)))
        # the ADV7842 keeps a 1 mm ring clear of small parts on both sides: its outer two rings of
        # balls escape on the outer layers through there (the 75 R arrays are placed already)
        keep = U1_RING if ref == "U1" else 0.3
        occ.take(side, courtyard(fp, keep))
        if ref in ("U1", "U2"):
            occ.take("B" if side == "F" else "F", courtyard(fp, keep))
        # through-hole pads (jacks, sockets, thermal vias) block the other side too
        for pad in fp.Pads():
            if pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                r = pad.GetBoundingBox()
                m = 0.4
                occ.take("B" if side == "F" else "F", (ToMM(r.GetLeft()) - m, ToMM(r.GetTop()) - m,
                                                       ToMM(r.GetRight()) + m, ToMM(r.GetBottom()) + m))
    # The sockets sit on the bottom, so seen from the top their numbering is mirrored: the holes
    # just pass the Console's pins through. Renumber each socket pad after the Console pin under
    # it (so pad n carries pin n's net, as in the schematic), and stop if a pad is on no pin.
    for ref, where in (("J9", J9_PIN), ("J10", J10_PIN)):
        p = [q for q in board.PARTS if q.ref == ref][0]
        want = {n: where(n) for n in range(1, 41)}
        for pad in fps[ref].Pads():
            v = pad.GetPosition()
            x, y = ToMM(v.x), ToMM(v.y)
            hit = [n for n, (wx, wy) in want.items() if abs(wx - x) < 0.01 and abs(wy - y) < 0.01]
            if len(hit) != 1:
                raise SystemExit("%s pad at (%.2f, %.2f) is on no header pin" % (ref, x, y))
            pad.SetNumber(str(hit[0]))
            pad.SetNet(net(p.pins[str(hit[0])]))

    # --- small parts next to their anchors
    # pads already placed, by net: the hand-placed parts now, each small part as it is placed
    ic_pads = {}

    def add_pads(fp):
        for pad in fp.Pads():
            v = pad.GetPosition()
            ic_pads.setdefault(pad.GetNetname(), []).append((ToMM(v.x), ToMM(v.y), fp.GetReference()))
    for ref in HAND:
        add_pads(fps[ref])
    rr = {}
    net_pins = board.nets()

    def anchor_for(p):
        """Where a small part goes, or None while nothing it hangs on is placed yet."""
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
                    k = rr.get(n, 0)
                    rr[n] = k + 1
                    return balls[k % len(balls)], "B"
        # a part on a signal (a pull-up, a termination, a series resistor, a divider) goes where
        # that signal is: at the IC pin it serves, else beside the part it hangs on (a
        # termination's 51 R by its coupling cap), else at the connector pin. Its supply net does
        # not count: a pull-up to 3V3 belongs at its pin, not at the 3V3 regulator.
        sig = sorted((n for n in nets_ if n not in POWER_NETS), key=lambda n: len(net_pins.get(n, [])))
        # the unused SDRAM port's pull-downs (one 0402 each, no signal) go to the ADV7842's right
        # side, level with their balls, clear of the analog inputs above its top right corner
        if any(n.startswith("PD_SDRAM") for n in sig):
            bx, by = [(x, y) for x, y, r in ic_pads[[n for n in sig if n.startswith("PD_SDRAM")][0]] if r == "U1"][0]
            right = courtyard(fps["U1"], 0)[2] + U1_RING + 1.0
            return (right, min(by, courtyard(fps["U1"], 0)[3] - 1.0)), "F"
        # except a series resistor on a line the FPGA drives (OUT_*, to the ADV7511): it goes at
        # the source end, the header [HWG 7.3]
        drive = [n for n in sig if n.startswith("OUT_")]
        if p.ref.startswith("R") and len(sig) == 2 and drive:
            return [(x, y) for x, y, r in ic_pads[drive[0]] if r == "J9"][0], "F"
        if sig:
            for kind in (lambda r: r.startswith("U"), lambda r: r not in HAND, lambda r: True):
                for n in sig:
                    cands = [(x, y) for x, y, r in ic_pads.get(n, []) if kind(r) and r != p.ref]
                    if cands:
                        return cands[0], "F"
            return None
        # a part on supplies only (a regulator's caps): the IC or connector it was written down
        # with, the nearest one before it in board.py on one of its nets
        k = board.PARTS.index(p)
        for q in reversed(board.PARTS[:k]):
            if q.ref.startswith(("U", "J")) and q.ref in fps:
                shared = [n for n in nets_ if n in set(q.pins.values())]
                if shared:
                    shared.sort(key=lambda n: len(net_pins.get(n, [])))
                    pads = [(x, y) for x, y, r in ic_pads.get(shared[0], []) if r == q.ref]
                    if pads:
                        return pads[0], "F"
        # else whatever is placed on its most specific supply (the buck's output is its inductor)
        for n in sorted(nets_, key=lambda n: len(net_pins.get(n, []))):
            cands = [(x, y) for x, y, r in ic_pads.get(n, []) if r != p.ref]
            if cands:
                return cands[0], "F"
        return None

    order = [p for p in board.PARTS if p.ref not in HAND]

    def rank(p):
        """The order the small parts get their places in: inductors, filters, bias and reference
        parts first, then the ADV7842's per-ball decoupling (nearest the balls), then whatever
        serves an IC pin (in board.py order: the analog inputs before the SDRAM pull-downs), then
        plane caps and bulk, then the rest."""
        nets_ = set(p.pins.values())
        if p.ref.startswith(("FL", "L", "Y")) or nets_ & BIAS_NETS:
            return 0
        if p.ref.startswith("C") and nets_ & DECOUPLE_U1 and p.value in ("10n", "100n"):
            return 1
        if p.ref.startswith("C") and nets_ & DECOUPLE_U1:
            return 3
        if any(r.startswith("U") for n in nets_ - {"GND"} for _, _, r in ic_pads.get(n, [])):
            return 2
        return 4
    order.sort(key=rank)
    while order:
        # the first part in rank order whose anchor is placed (a chain fills in from its IC end)
        for p in order:
            a = anchor_for(p)           # (once per part: the rail-cap round robin counts calls)
            if a is not None:
                break
        else:
            raise SystemExit("nothing placed that %s hangs on" % order[0].ref)
        order.remove(p)
        (ax, ay), side = a
        # a rail's decoupling goes where its rail pad is over the rail's plane (0.3 mm in): a via
        # beside it then goes straight down (fanout_planes), with nothing for the router to do
        plane = [n for n in p.pins.values() if n in PLANES]
        where = None
        if plane and p.ref.startswith("C"):
            poly, to_grid = PLANES[plane[0]], _u1_grid[0]
            rail_pad = [q for q in fps[p.ref].Pads() if q.GetNetname() == plane[0]][0]

            def where(box, poly=poly, to_grid=to_grid, pad=rail_pad, m=0.3):
                r = pad.GetBoundingBox()            # (at the spot being tried)
                x0, y0, x1, y1 = ToMM(r.GetLeft()) - m, ToMM(r.GetTop()) - m, ToMM(r.GetRight()) + m, ToMM(r.GetBottom()) + m
                return all(inside(poly, *to_grid(x, y)) for x in (x0, x1) for y in (y0, y1))
        place_near(occ, fps[p.ref], side, (ax, ay), where=where)
        add_pads(fps[p.ref])

    for ref, ic in (("J10", "U1"), ("J9", "U2")):
        print("%s bus: %d crossings" % (ref, crossings(fps[ref], fps[ic], fps)))

    # orientation checks: the jacks open to the left edge, U2's data side faces J9 (above it)
    for ref in ("J1", "J2", "J3", "J4", "J5"):
        bx = courtyard(fps[ref], 0)
        assert bx[0] < X0 + 1.5, (ref, bx)
    assert fit_u2(fps["U2"], ToMM(fps["U2"].GetPosition().x), ToMM(fps["U2"].GetPosition().y)), "U2 rotation"
    hx = ToMM(fps["J6"].GetPosition().x)
    assert courtyard(fps["J6"], 0)[2] > X1 - 1.5, "HDMI not at the right edge"

    rules(b)
    silkscreen(b)
    fanout_u1(b, fps["U1"])
    fanout_planes(b, fps["U1"])
    planes(b, fps["U1"])
    pcbnew.SaveBoard(OUT, b)
    print("%s: %d footprints" % (OUT, len(fps)))
    if "--route" in sys.argv:
        route()


# ---------------------------------------------------------------------------
# Rules, fanout, planes, routing
# ---------------------------------------------------------------------------

# Silkscreen: designators only for the parts one finds by eye (ICs, connectors, filters,
# inductors, crystal, buttons, fuse, ferrite, holes); the passives' stay on the fab layer (JLCPCB
# places from the CPL, and 0402s leave no room). Labels by the inputs and outputs, and the board's.
SILK_KEEP = {"U", "J", "SW", "Y", "FL", "L", "F", "FB", "H"}
SILK_LABELS = [("J1", "Y"), ("J2", "Pb"), ("J3", "Pr"), ("J4", "L"), ("J5", "R")]
BOARD_LABEL = "tang-av-scaler AV board rev A"


_removed = []


def silkscreen(b):
    silk = (pcbnew.F_SilkS, pcbnew.B_SilkS)
    # copper a text must keep off, per side (through-hole pads on both)
    pads = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            r = pad.GetBoundingBox()
            box = (ToMM(r.GetLeft()) - 0.15, ToMM(r.GetTop()) - 0.15, ToMM(r.GetRight()) + 0.15, ToMM(r.GetBottom()) + 0.15)
            th = pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
            for side in ((pcbnew.F_SilkS, pcbnew.B_SilkS) if th else
                         ((pcbnew.B_SilkS,) if fp.IsFlipped() else (pcbnew.F_SilkS,))):
                pads[side].append(box)
    placed = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}

    def hits(box, boxes):
        return any(box[2] > q[0] and box[0] < q[2] and box[3] > q[1] and box[1] < q[3] for q in boxes)
    for fp in b.GetFootprints():
        prefix = "".join(ch for ch in fp.GetReference() if ch.isalpha())
        ref = fp.Reference()
        # the value and the other fields (the LCSC number) are for the BOM, not the silkscreen
        for fld in fp.GetFields():
            if not fld.IsReference() and fld.GetLayer() in silk:
                fld.SetVisible(False)
        if prefix not in SILK_KEEP:
            ref.SetVisible(False)
            continue
        # the designator where it is clear of copper and of the texts placed so far: above, below,
        # left or right of the part, or on its body; hidden if none is
        side = ref.GetLayer()
        ref.SetTextSize(VECTOR2I(FromMM(0.8), FromMM(0.8)))
        ref.SetTextThickness(FromMM(0.15))
        cy = courtyard(fp, 0.2)
        cx_, cy_ = (cy[0] + cy[2]) / 2, (cy[1] + cy[3]) / 2
        for x, y, ang in ((cx_, cy[1] - 0.6, 0), (cx_, cy[3] + 0.6, 0), (cy[0] - 0.6, cy_, 90),
                          (cy[2] + 0.6, cy_, 90), (cx_, cy_, 0)):
            ref.SetTextAngleDegrees(ang)
            ref.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
            r = ref.GetBoundingBox()
            box = (ToMM(r.GetLeft()), ToMM(r.GetTop()), ToMM(r.GetRight()), ToMM(r.GetBottom()))
            if box[0] > X0 + 0.3 and box[2] < X1 - 0.3 and box[1] > Y0 + 0.3 and box[3] < Y1 - 0.3 \
                    and not hits(box, pads[side]) and not hits(box, placed[side]):
                ref.SetVisible(True)
                placed[side].append(box)
                break
        else:
            ref.SetVisible(False)
    labels = {t for _, t in SILK_LABELS} | {"HDMI", BOARD_LABEL}
    for item in list(b.GetDrawings()):                  # (again on a re-run: no duplicates)
        if isinstance(item, pcbnew.PCB_TEXT) and item.GetText() in labels:
            b.Remove(item)
            _removed.append(item)       # (kept referenced: freed, they break pcbnew's later calls)

    def text(s_, x, y, size, angle=0, spots=None):
        """A label at (x, y), or at the first of spots [(x, y, angle)] clear of copper and texts."""
        t = pcbnew.PCB_TEXT(b)
        t.SetText(s_)
        t.SetLayer(pcbnew.F_SilkS)
        t.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
        t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size)))
        t.SetTextThickness(FromMM(0.18 if size >= 1.2 else 0.15))
        t.SetTextAngleDegrees(angle)
        for x_, y_, a_ in spots or []:
            t.SetPosition(VECTOR2I(FromMM(x_), FromMM(y_)))
            t.SetTextAngleDegrees(a_)
            r = t.GetBoundingBox()
            box = (ToMM(r.GetLeft()), ToMM(r.GetTop()), ToMM(r.GetRight()), ToMM(r.GetBottom()))
            if not hits(box, pads[pcbnew.F_SilkS]) and not hits(box, placed[pcbnew.F_SilkS]):
                placed[pcbnew.F_SilkS].append(box)
                break
        b.Add(t)
    for ref, label in SILK_LABELS:                      # on the jack's body by the board edge
        bb = b.FindFootprintByReference(ref).GetBoundingBox(False, False)
        text(label, X0 + 1.6, ToMM(bb.GetCenter().y), 1.4, 90)
    bb = b.FindFootprintByReference("J6").GetBoundingBox(False, False)
    l_, t_, r_, b_ = ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetRight()), ToMM(bb.GetBottom())
    text("HDMI", l_ + 3.5, t_ - 1.2, 1.2, spots=[(l_ + 3.5 + dx, t_ - 1.2 - dy, 0) for dy in (0, 0.8, 1.6, 2.4) for dx in (0, 1.5, -1.5)]
         + [(l_ + 3.5, b_ + 1.0 + dy, 0) for dy in (0, 0.8)])
    text(BOARD_LABEL, (X0 + X1) / 2 - 5, Y1 - 1.6, 1.2)


def rules(b):
    # The ground layers are power layers, so Freerouting never routes on them; the rail planes'
    # layer is mixed: signals may run there outside the planes (see LAYERS)
    b.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    if LAYERS == 6:
        b.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_SIGNAL)
        b.SetLayerType(pcbnew.In4_Cu, pcbnew.LT_POWER)
    b.SetLayerType(PLANE_LAYER, pcbnew.LT_MIXED)
    ds = b.GetDesignSettings()
    ns = ds.m_NetSettings
    nc = ns.GetDefaultNetclass()
    nc.SetTrackWidth(FromMM(TRACK))
    nc.SetClearance(FromMM(CLEAR))
    nc.SetViaDiameter(FromMM(VIA_D))
    nc.SetViaDrill(FromMM(VIA_DRILL))
    # power tracks 0.25 mm: they must reach 0.5 mm-pitch supply pins (ADV7511, TPD4E05U06); the big
    # currents run in planes (ADV7842) or are short
    # the pixel clocks keep other lines further off [HWG 7.2: nothing near the CLK trace]: 0.19 mm,
    # what the 0.2 mm gaps between their 0.5 mm-pitch pads (ADV7511 pin 79, the 75 R array) allow
    for name, width, clear, nets in (("POWER", 0.25, 0.15, POWER_NETS), ("TMDS", 0.2, 0.15, TMDS_NETS),
                                     ("CLOCK", TRACK, 0.19, CLOCK_NETS)):
        c = pcbnew.NETCLASS(name)
        c.SetTrackWidth(FromMM(width))
        c.SetClearance(FromMM(clear))
        c.SetViaDiameter(FromMM(VIA_D))
        c.SetViaDrill(FromMM(VIA_DRILL))
        if name == "TMDS":
            # 100 R differential, edge-coupled on F.Cu over In1 (JLC06161H-7628B: 0.218 mm prepreg,
            # er 4.4): 0.25 mm / 0.2 mm gives about 97 R, the class's 0.2 mm at the 0.15 mm gap the
            # routers keep about 103 R (IPC-2141); check in JLCPCB's impedance calculator before
            # ordering (a thin 2116 stack would want about 0.16 / 0.2 mm)
            c.SetDiffPairWidth(FromMM(0.25))
            c.SetDiffPairGap(FromMM(0.2))
        ns.SetNetclass(name, c)
        for n in nets:
            ns.SetNetclassPatternAssignment(n, name)
    ns.RecomputeEffectiveNetclasses()
    ds.m_MinClearance = FromMM(CLEAR)
    ds.m_TrackMinWidth = FromMM(0.1)
    ds.m_ViasMinSize = FromMM(0.45)
    ds.m_MinThroughDrill = FromMM(0.3)
    ds.m_CopperEdgeClearance = FromMM(0.3)
    ds.m_HoleClearance = FromMM(0.2)        # JLCPCB multilayer: 0.2 mm hole to copper
    ds.m_MinResolvedSpokes = 1              # pads on the outer pours have their own vias too


def grid(fp):
    """(r, c) in the ADV7842's ball grid -> board mm."""
    a1, a16, t1 = pad_pos(fp, "A1"), pad_pos(fp, "A16"), pad_pos(fp, "T1")
    dc = ((a16[0] - a1[0]) / 15, (a16[1] - a1[1]) / 15)
    dr = ((t1[0] - a1[0]) / 15, (t1[1] - a1[1]) / 15)
    return lambda r, c: (a1[0] + c * dc[0] + r * dr[0], a1[1] + c * dc[1] + r * dr[1])


def inside(poly, r, c):
    n, hit = len(poly), False
    for i in range(n):
        (r0, c0), (r1, c1) = poly[i], poly[(i + 1) % n]
        if (c0 > c) != (c1 > c) and r < r0 + (r1 - r0) * (c - c0) / (c1 - c0):
            hit = not hit
    return hit


def track(b, a, z, width, layer, net):
    """A locked track: the fanout stays as placed (Freerouting reroutes unlocked copper)."""
    t = pcbnew.PCB_TRACK(b)
    t.SetLocked(True)
    t.SetStart(VECTOR2I(FromMM(a[0]), FromMM(a[1])))
    t.SetEnd(VECTOR2I(FromMM(z[0]), FromMM(z[1])))
    t.SetWidth(FromMM(width))
    t.SetLayer(layer)
    t.SetNet(net)
    b.Add(t)


def via(b, x, y, net):
    v = pcbnew.PCB_VIA(b)
    v.SetLocked(True)
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
    v.SetWidth(FromMM(VIA_D))
    v.SetDrill(FromMM(VIA_DRILL))
    v.SetNet(net)
    b.Add(v)


def fanout_u1(b, fp):
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
        track(b, g(ROWS.index(a_[0]), int(a_[1:]) - 1), g(ROWS.index(z_[0]), int(z_[1:]) - 1), 0.15, pcbnew.F_Cu,
              by_name[a_].GetNet())
    for (r, c), pad in sorted(balls.items(), key=lambda kv: -max(abs(kv[0][0] - 7.5), abs(kv[0][1] - 7.5))):
        net = pad.GetNetname()
        if not net or pad.GetNumber() in chained:
            continue
        # (+5V: the two HDMI 5 V detect balls, RXA/RXB_5V, take a via like a signal ball)
        power = net == "GND" or (net in POWER_NETS and net != "+5V")
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
        w = 0.2 if power else TRACK
        track(b, (bx, by), (vx, vy), w, pcbnew.F_Cu, pad.GetNet())
        via(b, vx, vy, pad.GetNet())
    for r, c, pad in pending_gnd:
        for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            q = balls.get((r + dr, c + dc))
            if q is not None and q.GetNetname() == pad.GetNetname():
                track(b, g(r, c), g(r + dr, c + dc), 0.2, pcbnew.F_Cu, pad.GetNet())
                break
        else:
            raise SystemExit("U1 ball %s: no via site and no neighbour on its net" % pad.GetNumber())
    print("U1 fanout: %d vias, %d power balls joined to a neighbour" % (len(used), len(pending_gnd)))


def fanout_planes(b, u1):
    """A via next to every surface pad on a plane net (ground; an ADV7842 rail where its In3 plane
    reaches): the router then only routes signals. Each via goes on the first spot, walking out
    from the pad, that clears every other pad, track, via and edge."""
    g = grid(u1)
    a1, a16, t1 = pad_pos(u1, "A1"), pad_pos(u1, "A16"), pad_pos(u1, "T1")

    def to_grid(x, y):
        # invert g: solve x = a1x + c*dcx + r*drx, y = a1y + c*dcy + r*dry
        dcx, dcy = (a16[0] - a1[0]) / 15, (a16[1] - a1[1]) / 15
        drx, dry = (t1[0] - a1[0]) / 15, (t1[1] - a1[1]) / 15
        det = dcx * dry - dcy * drx
        u, v = x - a1[0], y - a1[1]
        return (dcx * v - dcy * u) / det, (u * dry - v * drx) / det     # r, c

    obst = []                       # (x0, y0, x1, y1, net, is_hole) boxes
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            r = pad.GetBoundingBox()
            obst.append((ToMM(r.GetLeft()), ToMM(r.GetTop()), ToMM(r.GetRight()), ToMM(r.GetBottom()),
                         pad.GetNetname(), pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD))
    for t in b.GetTracks():
        r = t.GetBoundingBox()
        obst.append((ToMM(r.GetLeft()), ToMM(r.GetTop()), ToMM(r.GetRight()), ToMM(r.GetBottom()),
                     t.GetNetname(), t.GetClass() == "PCB_VIA"))
    gap = 0.2

    def clear(x, y, net, skip, rv, hole):
        """Is a circle of radius rv at (x, y) clear of everything but its own net (and, for a
        hole, of other holes too)?"""
        if x - rv < X0 + 0.5 or x + rv > X1 - 0.5 or y - rv < Y0 + 0.5 or y + rv > Y1 - 0.5:
            return False
        wx0, wy0, wx1, wy1 = WIN
        if x + rv > wx0 - 0.3 and x - rv < wx1 + 0.3 and y + rv > wy0 - 0.3 and y - rv < wy1 + 0.3:
            return False
        for k, (x0, y0, x1, y1, n, ishole) in enumerate(obst):
            if k == skip:
                continue
            if x + rv > x0 and x - rv < x1 and y + rv > y0 and y - rv < y1:
                if n == net and n and not (hole and ishole):
                    continue
                return False
        return True

    def path_clear(px, py, x, y, net, skip):
        for t in [i / 20 for i in range(1, 20)]:
            if not clear(px + (x - px) * t, py + (y - py) * t, net, skip, 0.125 + gap, False):
                return False
        return clear(x, y, net, skip, VIA_D / 2 + gap, True)

    n = 0
    for fp in b.GetFootprints():
        if fp.GetReference() == "U1":
            continue
        for pad in fp.Pads():
            net = pad.GetNetname()
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or not net:
                continue
            px, py = ToMM(pad.GetPosition().x), ToMM(pad.GetPosition().y)
            if net == "GND":
                pass
            elif net in PLANES and inside(PLANES[net], *to_grid(px, py)):
                pass
            else:
                continue
            onf = pad.IsOnLayer(pcbnew.F_Cu)
            k_self = [k for k, o in enumerate(obst) if abs((o[0] + o[2]) / 2 - px) < 1e-3 and abs((o[1] + o[3]) / 2 - py) < 1e-3]
            r = pad.GetBoundingBox()
            hw, hh = ToMM(r.GetWidth()) / 2, ToMM(r.GetHeight()) / 2
            spot = None
            for d in (0.0, 0.3, 0.6, 1.0, 1.5, 2.0, 2.5):
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1),
                               (1, 0.5), (-1, 0.5), (1, -0.5), (-1, -0.5), (0.5, 1), (-0.5, 1), (0.5, -1), (-0.5, -1)):
                    x = px + dx * (hw + VIA_D / 2 + gap + d)
                    y = py + dy * (hh + VIA_D / 2 + gap + d)
                    # (a rail pad's via must land on its plane too, or it connects nothing)
                    on_plane = net not in PLANES or all(inside(PLANES[net], *to_grid(x + ex, y + ey))
                                                        for ex in (-0.35, 0.35) for ey in (-0.35, 0.35))
                    if on_plane and path_clear(px, py, x, y, net, k_self[0] if k_self else -1):
                        spot = (x, y)
                        break
                if spot:
                    break
            if not spot:
                if net != "GND":            # (a ground pad has the outer pours as well)
                    print("note: no plane via for %s pad %s (%s)" % (fp.GetReference(), pad.GetNumber(), net))
                continue
            x, y = spot
            track(b, (px, py), (x, y), 0.25, pcbnew.F_Cu if onf else pcbnew.B_Cu, pad.GetNet())
            via(b, x, y, pad.GetNet())
            obst.append((x - VIA_D / 2, y - VIA_D / 2, x + VIA_D / 2, y + VIA_D / 2, net, True))
            obst.append((min(px, x) - 0.125, min(py, y) - 0.125, max(px, x) + 0.125, max(py, y) + 0.125, net, False))
            n += 1
    print("plane fanout: %d vias" % n)


def zone(b, netname, layer, pts, clearance=None, priority=0):
    z = pcbnew.ZONE(b)
    z.SetLayer(layer)
    z.SetNet(b.FindNet(netname))
    inner = layer not in (pcbnew.F_Cu, pcbnew.B_Cu)
    # inner planes: 0.127 mm, or the other nets' via holes (1 mm apart under the BGA) would leave no
    # copper between them and cut the planes into islands
    z.SetLocalClearance(FromMM(clearance if clearance is not None else 0.127 if inner else 0.25))
    z.SetMinThickness(FromMM(0.15 if inner else 0.2))
    z.SetAssignedPriority(priority)
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if layer not in (pcbnew.F_Cu, pcbnew.B_Cu)
                       else pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    o = z.Outline()
    o.NewOutline()
    for x, y in pts:
        o.Append(FromMM(x), FromMM(y))
    b.Add(z)
    return z


def keepout(b, x0, y0, x1, y1, pts=None, layer=None, vias=True):
    """A rule area with no tracks (and no vias unless vias=False) on all copper layers or one:
    Freerouting keeps neither the edge clearance nor the planes free by itself."""
    z = pcbnew.ZONE(b)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(vias)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    z.SetDoNotAllowCopperPour(False)
    if layer is None:
        z.SetLayerSet(pcbnew.LSET.AllCuMask())
    else:
        z.SetLayer(layer)
    o = z.Outline()
    o.NewOutline()
    for x, y in pts or ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        o.Append(FromMM(x), FromMM(y))
    b.Add(z)


def planes(b, fp):
    m = 0.45
    for x0, y0, x1, y1 in ((X0, Y0, X1, Y0 + m), (X0, Y1 - m, X1, Y1), (X0, Y0, X0 + m, Y1), (X1 - m, Y0, X1, Y1)):
        keepout(b, x0, y0, x1, y1)
    wx0, wy0, wx1, wy1 = WIN
    if wx0 > X0:
        keepout(b, wx0 - m, wy0 - m, wx1 + m, wy1 + m)
    for bx, by in BUTTONS:
        keepout(b, bx - 3.5 - m, by - 3.5 - m, bx + 3.5 + m, by + 3.5 + m)
    for hx, hy in HOLES:                    # standoffs: the M2.5 head and the standoff sit there
        keepout(b, hx - 3.0, hy - 3.0, hx + 3.0, hy + 3.0)
    g = grid(fp)
    full = [(X0 + 0.3, Y0 + 0.3), (X1 - 0.3, Y0 + 0.3), (X1 - 0.3, Y1 - 0.3), (X0 + 0.3, Y1 - 0.3)]
    zone(b, "GND", pcbnew.In1_Cu, full)
    if LAYERS == 6:
        zone(b, "GND", pcbnew.In4_Cu, full)
    for net, poly in PLANES.items():
        pts = [g(r, c) for r, c in poly]
        pts = [(min(max(x, X0 + 0.5), X1 - 0.5), min(max(y, Y0 + 0.5), Y1 - 0.5)) for x, y in pts]
        zone(b, net, PLANE_LAYER, pts, priority=1)
        # no signal tracks across a rail plane (vias may pass)
        keepout(b, 0, 0, 0, 0, pts=pts, layer=PLANE_LAYER, vias=False)


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


def stitch(b, pitch=2.5, gap=0.3):
    """Ground vias on a grid wherever they clear every pad, track, via, edge and the window: they
    tie the outer pours to the two ground planes (and the islands the tracks cut out of them)."""
    gnd = b.FindNet("GND")
    pts, segs = [], []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            r = p.GetBoundingBox()
            pts.append((ToMM(p.GetPosition().x), ToMM(p.GetPosition().y),
                        (ToMM(r.GetWidth()) ** 2 + ToMM(r.GetHeight()) ** 2) ** 0.5 / 2))
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            pts.append((ToMM(t.GetPosition().x), ToMM(t.GetPosition().y), VIA_D / 2))
        else:
            segs.append((ToMM(t.GetStart().x), ToMM(t.GetStart().y), ToMM(t.GetEnd().x), ToMM(t.GetEnd().y),
                         ToMM(t.GetWidth()) / 2))
    n = 0
    y = Y0 + 1.5
    while y < Y1 - 1.4:
        x = X0 + 1.5
        while x < X1 - 1.4:
            wx0, wy0, wx1, wy1 = WIN
            ok = not (wx0 - 1.0 < x < wx1 + 1.0 and wy0 - 1.0 < y < wy1 + 1.0)
            # (the standoffs' keepouts are 6 mm squares, see planes())
            ok = ok and all(abs(x - hx) > 3.0 + VIA_D / 2 or abs(y - hy) > 3.0 + VIA_D / 2 for hx, hy in HOLES)
            ok = ok and all(((x - hx) ** 2 + (y - hy) ** 2) ** 0.5 > 4.5 for hx, hy in BUTTONS)
            if ok:
                for px, py, r in pts:
                    if abs(px - x) < 4 and abs(py - y) < 4 and ((x - px) ** 2 + (y - py) ** 2) ** 0.5 < VIA_D / 2 + gap + r:
                        ok = False
                        break
            if ok:
                for ax, ay, bx, by, hw in segs:
                    if min(ax, bx) - 2 < x < max(ax, bx) + 2 and min(ay, by) - 2 < y < max(ay, by) + 2 and \
                            seg_dist(x, y, ax, ay, bx, by) < VIA_D / 2 + gap + hw:
                        ok = False
                        break
            if ok:
                via(b, x, y, gnd)
                pts.append((x, y, VIA_D / 2))
                n += 1
            x += pitch
        y += pitch
    print("stitching vias:", n)


def prune(path, rounds=5):
    """Remove the vias and track ends KiCad's DRC reports as dangling (fanout the router did not
    use, stubs it left), round after round, refilling the zones each time."""
    import json
    import tempfile
    removed = 0
    for _ in range(rounds):
        rpt = tempfile.mktemp(suffix=".json")
        subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "-o", rpt, path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        dead = {it["uuid"] for v in json.load(open(rpt))["violations"]
                if v["type"] in ("via_dangling", "track_dangling") for it in v["items"]}
        os.unlink(rpt)
        if not dead:
            break
        b = pcbnew.LoadBoard(path)
        gone = [t for t in list(b.GetTracks()) if t.m_Uuid.AsString() in dead]
        for t in gone:
            b.Remove(t)
        removed += len(gone)
        b.BuildConnectivity()
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        pcbnew.SaveBoard(path, b)
    print("dangling vias and stubs removed:", removed)


def freerouting(dsn, ses):
    """Route a DSN with Freerouting (1.x under a private Xvfb, 2.x headless); copper the DSN marks
    fixed (KiCad's locked tracks and vias) stays as it is."""
    log = open(os.path.splitext(ses)[0] + "-route.log", "w")
    if FREEROUTING_VERSION.startswith("1."):
        display = ":%d" % (90 + os.getpid() % 100)
        xvfb = subprocess.Popen([XVFB, display, "-screen", "0", "1280x1024x24"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            subprocess.run([JAVA, "-jar", FREEROUTING, "-de", dsn, "-do", ses, "-mp", os.environ.get("PASSES", "100")],
                           check=True, stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ, DISPLAY=display))
        finally:
            xvfb.terminate()
    else:
        subprocess.run([JAVA, "-jar", FREEROUTING, "-de", dsn, "-do", ses, "-mp", os.environ.get("PASSES", "100"),
                        "--gui.enabled=false", "--usage_and_diagnostic_data.disable_analytics=true"],
                       check=True, stdout=log, stderr=subprocess.STDOUT)


def copper_key(t):
    """A track or via, by layer and position to 10 um (routers round coordinates)."""
    if t.GetClass() == "PCB_VIA":
        return ("via", round(ToMM(t.GetPosition().x), 2), round(ToMM(t.GetPosition().y), 2))
    a = (round(ToMM(t.GetStart().x), 2), round(ToMM(t.GetStart().y), 2))
    z = (round(ToMM(t.GetEnd().x), 2), round(ToMM(t.GetEnd().y), 2))
    return ("track", t.GetLayer()) + min(a, z) + max(a, z)


def session(b, ses_for):
    """Export the board's copper, get a session for it (ses_for(dsn) -> path), import it. KiCad's
    session import replaces every track and via with the session's, which leaves out some of the
    locked copper: what is missing is put back."""
    copper = list(b.GetTracks())            # (after ExportSpecctraDSN the track list cannot be iterated)
    fixed = []
    for t in copper:
        if t.IsLocked():
            if t.GetClass() == "PCB_VIA":
                fixed.append(("via", ToMM(t.GetPosition().x), ToMM(t.GetPosition().y), t.GetNetname()))
            else:
                fixed.append(("track", ToMM(t.GetStart().x), ToMM(t.GetStart().y), ToMM(t.GetEnd().x),
                              ToMM(t.GetEnd().y), ToMM(t.GetWidth()), t.GetLayer(), t.GetNetname()))
    dsn = os.path.splitext(OUT)[0] + ".dsn"     # (named after the board: trials can run side by side)
    if not pcbnew.ExportSpecctraDSN(b, dsn):
        raise SystemExit("DSN export failed")
    ses = ses_for(dsn)
    # start from no copper: some sessions carry the locked copper (DeepPCB), some leave part of it
    # out (Freerouting)
    for t in copper:
        b.Remove(t)
    if not pcbnew.ImportSpecctraSES(b, ses):
        raise SystemExit("SES import failed")
    have = {copper_key(t) for t in b.GetTracks()}
    vias_now = [(ToMM(t.GetPosition().x), ToMM(t.GetPosition().y)) for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
    back = 0
    for f in fixed:
        if f[0] == "via":
            if not any(abs(x - f[1]) < 0.02 and abs(y - f[2]) < 0.02 for x, y in vias_now):
                via(b, f[1], f[2], b.FindNet(f[3]))
                back += 1
        else:
            a, z = (round(f[1], 2), round(f[2], 2)), (round(f[3], 2), round(f[4], 2))
            if ("track", f[6]) + min(a, z) + max(a, z) not in have:
                track(b, (f[1], f[2]), (f[3], f[4]), f[5], f[6], b.FindNet(f[7]))
                back += 1
    return back


def route():
    """Route the saved board (Freerouting, DeepPCB or a given session), finish what another router
    left with Freerouting, then the ground pours on the outer layers, filled. Each step runs in a
    process of its own: after a DSN export, pcbnew can no longer list a board's tracks, nor load
    one."""
    b = pcbnew.LoadBoard(OUT)

    def first(dsn):
        if os.environ.get("SES"):
            return os.environ["SES"]        # a session routed elsewhere (another router, by hand)
        ses = os.path.splitext(OUT)[0] + ".ses"
        if os.environ.get("ROUTER") == "deeppcb":
            subprocess.run([sys.executable, os.path.join(HERE, "deeppcb.py"), "run", dsn, ses, "--minutes",
                            os.environ.get("MINUTES", "60")], check=True)
        else:
            freerouting(dsn, ses)
        return ses
    print("fanout items put back after the import:", session(b, first))
    pcbnew.SaveBoard(OUT, b)
    if (os.environ.get("SES") or os.environ.get("ROUTER") == "deeppcb") and os.environ.get("FINISH", "1") == "1":
        subprocess.run([sys.executable, os.path.abspath(__file__), "--finish"], check=True)
    subprocess.run([sys.executable, os.path.abspath(__file__), "--pour"], check=True)


FANOUT_JSON = OUT + ".fanout.json"          # the finishing pass's note of the locked fanout


def finish():
    """What another router left unconnected: Freerouting with all of its copper fixed (the fanout,
    noted, is unlocked again by pour())."""
    b = pcbnew.LoadBoard(OUT)
    tracks = list(b.GetTracks())
    with open(FANOUT_JSON, "w") as f:
        json.dump([list(copper_key(t)) for t in tracks if t.IsLocked()], f)
    for t in tracks:
        t.SetLocked(True)

    def ses_for(dsn):
        ses = os.path.splitext(OUT)[0] + "-finish.ses"
        freerouting(dsn, ses)
        return ses
    print("finishing pass: items put back after the import:", session(b, ses_for))
    pcbnew.SaveBoard(OUT, b)


def pour():
    """Ground pours on the outer layers, stitching, fill, prune; only the fanout stays locked."""
    b = pcbnew.LoadBoard(OUT)
    if os.path.exists(FANOUT_JSON):
        with open(FANOUT_JSON) as f:
            fanout = {tuple(k) for k in json.load(f)}
        for t in b.GetTracks():
            t.SetLocked(copper_key(t) in fanout)
        os.remove(FANOUT_JSON)
    full = [(X0 + 0.3, Y0 + 0.3), (X1 - 0.3, Y0 + 0.3), (X1 - 0.3, Y1 - 0.3), (X0 + 0.3, Y1 - 0.3)]
    zone(b, "GND", pcbnew.F_Cu, full)
    zone(b, "GND", pcbnew.B_Cu, full)
    stitch(b)
    pcbnew.SaveBoard(OUT, b)
    b = pcbnew.LoadBoard(OUT)
    b.BuildConnectivity()
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(OUT, b)
    prune(OUT)
    print("routed:", OUT)


if __name__ == "__main__":
    if "--finish" in sys.argv:              # route()'s steps, each in a process of its own
        finish()
    elif "--pour" in sys.argv:
        pour()
    elif "--silk" in sys.argv:              # the silkscreen rules on a board as it is (routed)
        b = pcbnew.LoadBoard(OUT)
        silkscreen(b)
        pcbnew.SaveBoard(OUT, b)
    else:
        main()
