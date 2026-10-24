#!/usr/bin/env python3
"""Write av-board.kicad_pcb from board.py: outline, footprints with their nets, placement.

Coordinates are the Console's (Sipeed's PCB coordinates, mm, top view, y down; design.md
"Mechanics"), so the sockets sit exactly over the Console's J9 and J10: each socket's pads are
checked against the header pins' positions and the script stops if one is off.

Placement: the big parts by hand (below), the small ones next to the pin they serve: each
two-terminal part, array or filter is put on the free spot nearest to its anchor (the IC pin it
connects to), on the side given for its group.

    python3 gen_pcb.py            # av-board.kicad_pcb, placed and unrouted
"""

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
OUT = os.path.join(HERE, NAME + ".kicad_pcb")
SYSFP = "/usr/share/kicad/footprints"
JAVA = "/home/linuxbrew/.linuxbrew/opt/openjdk/bin/java"
# Freerouting 1.9.0: 2.5.0 leaves about 100 connections of this board unrouted after its first pass
# and diverges in the next ones; 1.9.0 gets within ~20. 1.9.0 needs an X display even in batch
# mode: a private Xvfb (Homebrew's xorg-server) runs for it.
FREEROUTING = os.path.expanduser("~/tools/freerouting/freerouting-1.9.0.jar")
XVFB = "/home/linuxbrew/.linuxbrew/bin/Xvfb"

# Rules (JLCPCB 4-layer standard: 0.09 mm track/space, 0.3 mm drill; we stay well above)
TRACK, CLEAR, VIA_D, VIA_DRILL = 0.127, 0.127, 0.5, 0.3
POWER_NETS = {"+5V", "3V3", "2V5", "1V8A", "1V8B", "5VA", "HDMI_5V", "SW_2V5", "AV_VDD", "AV_AVDD", "AV_CVDD",
              "AV_PVDD", "AV_DVDDIO", "AV_TVDD", "TX_DVDD", "TX_AVDD", "TX_PLVDD"}
TMDS_NETS = {"TMDS_D2P", "TMDS_D2N", "TMDS_D1P", "TMDS_D1N", "TMDS_D0P", "TMDS_D0N", "TMDS_CKP", "TMDS_CKN"}

# ADV7842 rail planes on In3, in ball-grid coordinates (r = row A..T as 0..15, c = column 1..16
# as 0..15; outside the array < 0 or > 15). Each rail's balls lie inside its plane; the planes do
# not touch; each reaches out of the BGA on its own side to its filter (FL1-FL5 above).
ROWS = "ABCDEFGHJKLMNPRT"
PLANES = {
    "AV_AVDD": [(4.55, 10.55), (4.55, 19.5), (11.45, 19.5), (11.45, 10.55)],
    "AV_VDD": [(10.45, 4.55), (7.55, 4.55), (7.55, 5.55), (-9.0, 5.55), (-9.0, 9.45), (7.55, 9.45),
               (7.55, 10.45), (10.45, 10.45)],
    "AV_CVDD": [(-9.0, 9.55), (4.45, 9.55), (4.45, 13.45), (-9.0, 13.45)],
    # PVDD (D15, D16): a small plane out to the left, to its filter
    "AV_PVDD": [(1.6, 13.55), (4.45, 13.55), (4.45, 18.5), (1.6, 18.5)],
    "AV_DVDDIO": [(4.55, -1.0), (21.0, -1.0), (21.0, 4.45), (12.45, 4.45), (12.45, 10.45), (10.55, 10.45),
                  (10.55, 4.45), (4.55, 4.45)],
}

# Board: x 60-190, y 20.6-90 (the Console's y extent), a window over the SOM
X0, X1, Y0, Y1 = 60.0, 190.0, 20.6, 90.0
WIN = (102.0, 35.0, 151.0, 74.0)
WIN_POLY = [(WIN[0], WIN[1]), (WIN[2], WIN[1]), (WIN[2], WIN[3]), (WIN[0], WIN[3])]
NOTCHES = []
# M2.5 standoffs on two of the Console's four H7_* holes, diagonally: the other two, at J10's pin 1
# end (100, 79) and J9's (158, 30), sit where the video buses enter the headers
HOLES = [(100.0, 30.0), (158.0, 79.0)]
BUTTONS = [(160.5, 54.5)]                                               # SW2: a 7 mm access hole


def J9_PIN(n):
    return (153.13 - 2.54 * ((n - 1) // 2), 28.73 if n % 2 else 31.27)


def J10_PIN(n):
    return (104.87 + 2.54 * ((n - 1) // 2), 80.27 if n % 2 else 77.73)


# Hand placement: ref -> (x, y, angle, side).  angle in degrees (KiCad: counter-clockwise).
HAND = {
    "J9": (129.0, 30.0, 180, "B"),
    "J10": (129.0, 79.0, 0, "B"),
    # input wing: RCA jacks facing left, audio at the top, video at the bottom next to the ADV7842
    # (13 mm apart: the shell lugs are 10 mm apart with 2.6 mm holes)
    "J4": (71.0, 28.0, 90, "F"), "J5": (71.0, 41.0, 90, "F"),
    "J1": (71.0, 56.5, 90, "F"), "J2": (71.0, 69.5, 90, "F"), "J3": (71.0, 82.5, 90, "F"),
    # at J10's height: its pixel balls (right edge, y 71-82) face J10's pins (y 77.7/80.3) across
    # the series resistors, so the bus runs straight over
    "U1": (87.5, 75.5, None, "F"),          # rotation chosen below: analog side left, pixel side right
    "U3": (86.0, 33.0, 0, "F"),
    "Y1": (78.5, 87.0, 0, "F"),
    "U5": (95.0, 26.0, 0, "F"), "U4": (84.0, 47.0, 0, "F"), "U6": (95.0, 47.0, 0, "F"),
    # output wing: ADV7511 data side facing J9, TMDS side facing the HDMI connector
    "U2": (167.5, 35.0, 0, "F"),        # its data pins level with J9's
    # the scaler's buttons, bottom edge of the output wing (near J10 pins 31/32)
    "SW1": (172.0, 85.0, 0, "F"), "SW2": (181.0, 85.0, 0, "F"),
    "J6": (184.8, 37.0, 90, "F"),
    "U7": (170.0, 62.0, 0, "F"),
    # ADV7842 rail filters on the bottom, at the exits of their In2 planes (see PLANES)
    "FL1": (89.6, 87.7, None, "B"), "FL3": (81.0, 87.7, None, "B"),  # VDD, CVDD: below the BGA
    "FL2": (76.0, 75.0, None, "B"),                                  # AVDD: left of it
    "FL5": (93.5, 62.0, None, "B"),                                  # DVDDIO: above it
    "FL4": (78.0, 82.2, None, "B"),                                  # PVDD: left, below AVDD's
    "FL6": (89.0, 62.0, 90, "B"),                                    # TVDD: a routed rail
    # TMDS ESD, in line between U2's TMDS pins (x 176.6, y 37.5-43) and the HDMI pads (x 183.1)
    "U9": (178.8, 33.75, None, "F"), "U10": (178.8, 36.75, None, "F"),
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


def place_rn(fps, u1, occ):
    """The pixel port's 75 R arrays in a column beside the ADV7842's pixel balls, each level with
    the four balls it serves, its ADV7842 side (pads 1-4) towards the chip."""
    cx = ToMM(u1.GetPosition().x)
    want = []
    for p in board.PARTS:
        if not (p.ref.startswith("RN") and p.value == "75"):
            continue
        ys = []
        for pad in u1.Pads():
            if pad.GetNetname() in [p.pins[str(k)] for k in (1, 2, 3, 4)]:
                ys.append(ToMM(pad.GetPosition().y))
        want.append((sum(ys) / len(ys), p.ref))
    # spread to at least 2.3 mm apart, keeping the order and the mean
    want.sort()
    ys = [w[0] for w in want]
    for _ in range(50):
        for k in range(1, len(ys)):
            if ys[k] - ys[k - 1] < 2.3:
                d = (2.3 - (ys[k] - ys[k - 1])) / 2
                ys[k - 1] -= d
                ys[k] += d
    for (_, ref), y in zip(want, ys):
        fp = fps[ref]
        fp.SetPosition(VECTOR2I(FromMM(cx + 8.5 + 1.6), FromMM(y)))
        for a in (0, 90, 180, 270):
            fp.SetOrientationDegrees(a)
            # pads 1-4 face the chip; pad 1 (the lowest ball row, row B at the bottom) at the bottom
            if pad_pos(fp, "1")[0] < pad_pos(fp, "8")[0] and pad_pos(fp, "1")[1] - pad_pos(fp, "4")[1] > 1:
                break
        occ.take("F", courtyard(fp))
        HAND[ref] = None


def fit_u1(fp, x, y):
    """Analog side (balls x13-16) to the left, pixel side (x1-5) to the right."""
    a1, a16 = pad_pos(fp, "A1"), pad_pos(fp, "A16")
    return a1[0] > x and a16[0] < x and a1[1] > y


def fit_esd(fp, x, y):
    """Lines enter on pads 1-5 (U2's side, left) and leave on 10-6; pad 1 at the top."""
    p1, p10, p5 = pad_pos(fp, "1"), pad_pos(fp, "10"), pad_pos(fp, "5")
    return p1[0] < p10[0] and p1[1] < p5[1]


FL_PLANE = {"FL1": "AV_VDD", "FL2": "AV_AVDD", "FL3": "AV_CVDD", "FL5": "AV_DVDDIO", "FL4": "AV_PVDD"}
_u1_grid = []


FL_AXIS = {"FL1": "x", "FL3": "x", "FL2": "y", "FL5": "y", "FL4": "y"}


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


FIT = {"U1": fit_u1, "U9": fit_esd, "U10": fit_esd}
FIT.update({r: fit_fl(r) for r in FL_PLANE})

# Groups for the small parts: (side, anchor) by block / net
DECOUPLE_U1 = {"AV_TVDD", "AV_AVDD", "AV_CVDD", "AV_VDD", "AV_DVDDIO", "AV_PVDD"}


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


def place_near(occ, fp, side, anchor, angles=(0, 90)):
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
                if occ.free(side, box):
                    best = (x, y, ang, box)
                    break
            if best:
                break
        if best:
            break
    assert best, "no room for %s near %s" % (fp.GetReference(), anchor)
    x, y, ang, box = best
    fp.SetOrientationDegrees(ang)
    fp.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
    occ.take(side, box)


def main():
    b = pcbnew.BOARD()
    b.SetCopperLayerCount(6)
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
    # Bus corridors stay free of small parts: from the 75 R arrays (x 98) to J10's pins, and the
    # strips above and below J10 the bus runs along; likewise from J9's data end to the ADV7511.
    for side in ("F", "B"):
        occ.take(side, (98.6, 70.0, 104.0, 89.5))           # arrays -> J10's pin 1 end
        occ.take(side, (103.0, 74.5, 132.0, 77.0))          # above J10's even row
        occ.take(side, (103.0, 81.0, 132.0, 89.5))          # below J10's odd row
        occ.take(side, (141.0, 26.0, 160.5, 34.5))          # J9's data end -> ADV7511

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
            place_rn(fps, fp, occ)
        occ.take(side, courtyard(fp, 0.3))
        if ref in ("U1", "U2"):
            occ.take("B" if side == "F" else "F", courtyard(fp, 0.3))
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
    ic_pads = {}
    for ref in ("U1", "U2", "U3", "U4", "U5", "U6", "U7", "U9", "U10", "J6", "FL1", "FL2", "FL3", "FL4", "FL5", "FL6", "J9", "J10", "J1", "J2", "J3", "J4", "J5", "Y1"):
        for pad in fps[ref].Pads():
            v = pad.GetPosition()
            ic_pads.setdefault(pad.GetNetname(), []).append((ToMM(v.x), ToMM(v.y), ref))
    rr = {}

    def anchor_for(p):
        # decoupling for U1: spread over its rail's balls, bottom side
        nets_ = [n for n in p.pins.values() if n != "GND"]
        for n in nets_:
            if n in DECOUPLE_U1 and p.ref.startswith("C") and p.value in ("220p", "33u"):
                # plane caps and bulk: anywhere on the plane; by the rail's filter
                fl = [(x, y) for x, y, r in ic_pads.get(n, []) if r.startswith("FL")]
                if fl:
                    return fl[0], "B"
            if n in DECOUPLE_U1 and p.ref.startswith("C"):
                balls = [(x, y) for x, y, r in ic_pads.get(n, []) if r == "U1"]
                if balls:
                    k = rr.get(n, 0)
                    rr[n] = k + 1
                    return balls[k % len(balls)], "B"
        # otherwise the nearest IC pad among its nets (prefer the U pins)
        for pref in ("U", "Y", "J"):
            for n in nets_:
                cands = [(x, y) for x, y, r in ic_pads.get(n, []) if r.startswith(pref)]
                if cands:
                    return cands[0], "F"
        return ((X0 + X1) / 2, Y1 - 5), "F"

    order = [p for p in board.PARTS if p.ref not in HAND]
    order.sort(key=lambda p: (0 if p.ref.startswith(("RN", "FL", "L", "Y")) else 1))
    for p in order:
        (ax, ay), side = anchor_for(p)
        place_near(occ, fps[p.ref], side, (ax, ay))

    # orientation checks: the jacks open to the left edge, U2's data side faces J9
    for ref in ("J1", "J2", "J3", "J4", "J5"):
        bx = courtyard(fps[ref], 0)
        assert bx[0] < X0 + 1.5, (ref, bx)
    u2x = ToMM(fps["U2"].GetPosition().x)
    assert pad_pos(fps["U2"], "84")[0] < u2x - 7 and pad_pos(fps["U2"], "36")[0] > u2x + 7, "U2 rotation"
    hx = ToMM(fps["J6"].GetPosition().x)
    assert courtyard(fps["J6"], 0)[2] > X1 - 1.5, "HDMI not at the right edge"

    rules(b)
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

def rules(b):
    # Stack: F.Cu signal / In1 ground / In2 signal / In3 rail planes + signal / In4 ground / B.Cu
    # signal. The ground layers are power layers, so Freerouting never routes on them.
    b.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    b.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_SIGNAL)
    b.SetLayerType(pcbnew.In3_Cu, pcbnew.LT_MIXED)
    b.SetLayerType(pcbnew.In4_Cu, pcbnew.LT_POWER)
    ds = b.GetDesignSettings()
    ns = ds.m_NetSettings
    nc = ns.GetDefaultNetclass()
    nc.SetTrackWidth(FromMM(TRACK))
    nc.SetClearance(FromMM(CLEAR))
    nc.SetViaDiameter(FromMM(VIA_D))
    nc.SetViaDrill(FromMM(VIA_DRILL))
    # power tracks 0.25 mm: they must reach 0.5 mm-pitch supply pins (ADV7511, TPD4E05U06); the big
    # currents run in planes (ADV7842) or are short
    for name, width, clear, nets in (("POWER", 0.25, 0.15, POWER_NETS), ("TMDS", 0.2, 0.15, TMDS_NETS)):
        c = pcbnew.NETCLASS(name)
        c.SetTrackWidth(FromMM(width))
        c.SetClearance(FromMM(clear))
        c.SetViaDiameter(FromMM(VIA_D))
        c.SetViaDrill(FromMM(VIA_DRILL))
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
    for (r, c), pad in sorted(balls.items(), key=lambda kv: -max(abs(kv[0][0] - 7.5), abs(kv[0][1] - 7.5))):
        net = pad.GetNetname()
        if not net:
            continue
        # (+5V: the two HDMI 5 V detect balls, beside unused HDMI balls: they escape on F.Cu)
        power = net == "GND" or (net in POWER_NETS and net != "+5V")
        ring = min(r, c, 15 - r, 15 - c)
        if not power and (ring <= 1 or net == "+5V"):
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
            if net == "GND":
                pending_gnd.append((r, c, pad))
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
            if q is not None and q.GetNetname() == "GND":
                track(b, g(r, c), g(r + dr, c + dc), 0.2, pcbnew.F_Cu, pad.GetNet())
                break
        else:
            raise SystemExit("U1 ground ball %s: no via and no ground neighbour" % pad.GetNumber())
    print("U1 fanout: %d vias, %d ground balls joined to a neighbour" % (len(used), len(pending_gnd)))


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
        for t in [i / 10 for i in range(3, 10)]:
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
            for d in (0.0, 0.3, 0.6, 1.0, 1.5):
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1)):
                    x = px + dx * (hw + VIA_D / 2 + gap + d)
                    y = py + dy * (hh + VIA_D / 2 + gap + d)
                    if path_clear(px, py, x, y, net, k_self[0] if k_self else -1):
                        spot = (x, y)
                        break
                if spot:
                    break
            if not spot:
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
    keepout(b, wx0 - m, wy0 - m, wx1 + m, wy1 + m)
    for bx, by in BUTTONS:
        keepout(b, bx - 3.5 - m, by - 3.5 - m, bx + 3.5 + m, by + 3.5 + m)
    g = grid(fp)
    full = [(X0 + 0.3, Y0 + 0.3), (X1 - 0.3, Y0 + 0.3), (X1 - 0.3, Y1 - 0.3), (X0 + 0.3, Y1 - 0.3)]
    zone(b, "GND", pcbnew.In1_Cu, full)
    zone(b, "GND", pcbnew.In4_Cu, full)
    for net, poly in PLANES.items():
        pts = [g(r, c) for r, c in poly]
        pts = [(min(max(x, X0 + 0.5), X1 - 0.5), min(max(y, Y0 + 0.5), Y1 - 0.5)) for x, y in pts]
        zone(b, net, pcbnew.In3_Cu, pts, priority=1)
        # no signal tracks across a rail plane on In3 (vias may pass)
        keepout(b, 0, 0, 0, 0, pts=pts, layer=pcbnew.In3_Cu, vias=False)


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
            ok = ok and all(((x - hx) ** 2 + (y - hy) ** 2) ** 0.5 > 3.0 for hx, hy in HOLES)
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


def route():
    """Freerouting on the saved board, then the ground pours on the outer layers, filled."""
    b = pcbnew.LoadBoard(OUT)
    # KiCad's session import replaces every track and via with what Freerouting returns, which
    # leaves out some of the locked fanout: note it here and put back what is missing
    fixed = []
    for t in b.GetTracks():
        if t.IsLocked():
            if t.GetClass() == "PCB_VIA":
                fixed.append(("via", ToMM(t.GetPosition().x), ToMM(t.GetPosition().y), t.GetNetname()))
            else:
                fixed.append(("track", ToMM(t.GetStart().x), ToMM(t.GetStart().y), ToMM(t.GetEnd().x),
                              ToMM(t.GetEnd().y), ToMM(t.GetWidth()), t.GetLayer(), t.GetNetname()))
    dsn, ses = os.path.join(HERE, NAME + ".dsn"), os.path.join(HERE, NAME + ".ses")
    if not pcbnew.ExportSpecctraDSN(b, dsn):
        raise SystemExit("DSN export failed")
    display = ":%d" % (90 + os.getpid() % 100)
    xvfb = subprocess.Popen([XVFB, display, "-screen", "0", "1280x1024x24"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log = open(os.path.join(HERE, "route.log"), "w")
    try:
        # stage 1 routes the board; stage 2 starts from that result and works on what is left
        for stage in (1, 2):
            if stage == 2 and not pcbnew.ExportSpecctraDSN(b, dsn):
                raise SystemExit("DSN export failed")
            subprocess.run([JAVA, "-jar", FREEROUTING, "-de", dsn, "-do", ses,
                            "-mp", os.environ.get("PASSES", "100")],
                           check=True, stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ, DISPLAY=display))
            if not pcbnew.ImportSpecctraSES(b, ses):
                raise SystemExit("SES import failed")
            b.BuildConnectivity()
            print("stage %d: %d unrouted connections" % (stage, b.GetConnectivity().GetUnconnectedCount(False)))
    finally:
        xvfb.terminate()
    have = set()
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            have.add(("via", round(ToMM(t.GetPosition().x), 3), round(ToMM(t.GetPosition().y), 3)))
        else:
            a = (round(ToMM(t.GetStart().x), 3), round(ToMM(t.GetStart().y), 3))
            z = (round(ToMM(t.GetEnd().x), 3), round(ToMM(t.GetEnd().y), 3))
            have.add(("track", t.GetLayer()) + min(a, z) + max(a, z))
    back = 0
    for f in fixed:
        if f[0] == "via":
            if ("via", round(f[1], 3), round(f[2], 3)) not in have:
                via(b, f[1], f[2], b.FindNet(f[3]))
                back += 1
        else:
            a, z = (round(f[1], 3), round(f[2], 3)), (round(f[3], 3), round(f[4], 3))
            if ("track", f[6]) + min(a, z) + max(a, z) not in have:
                track(b, (f[1], f[2]), (f[3], f[4]), f[5], f[6], b.FindNet(f[7]))
                back += 1
    print("fanout items put back after the import:", back)
    full = [(X0 + 0.3, Y0 + 0.3), (X1 - 0.3, Y0 + 0.3), (X1 - 0.3, Y1 - 0.3), (X0 + 0.3, Y1 - 0.3)]
    zone(b, "GND", pcbnew.F_Cu, full)
    zone(b, "GND", pcbnew.B_Cu, full)
    stitch(b)
    pcbnew.SaveBoard(OUT, b)
    b = pcbnew.LoadBoard(OUT)
    b.BuildConnectivity()
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(OUT, b)
    print("routed:", OUT)


if __name__ == "__main__":
    main()
