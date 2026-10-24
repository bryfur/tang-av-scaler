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
JAVA = os.path.expanduser("~/tools/jdk17/bin/java")
FREEROUTING = os.path.expanduser("~/tools/freerouting/freerouting-2.5.0.jar")

# Rules (JLCPCB 4-layer standard: 0.09 mm track/space, 0.3 mm drill; we stay well above)
TRACK, CLEAR, VIA_D, VIA_DRILL = 0.127, 0.127, 0.5, 0.3
POWER_NETS = {"+5V", "3V3", "2V5", "1V8A", "1V8B", "5VA", "HDMI_5V", "SW_2V5", "AV_VDD", "AV_AVDD", "AV_CVDD",
              "AV_PVDD", "AV_DVDDIO", "AV_TVDD", "TX_DVDD", "TX_AVDD", "TX_PLVDD"}
TMDS_NETS = {"TMDS_D2P", "TMDS_D2N", "TMDS_D1P", "TMDS_D1N", "TMDS_D0P", "TMDS_D0N", "TMDS_CKP", "TMDS_CKN"}

# ADV7842 rail planes on In2, in ball-grid coordinates (r = row A..T as 0..15, c = column 1..16
# as 0..15; outside the array < 0 or > 15). Each rail's balls lie inside its plane; the planes do
# not touch; each reaches out of the BGA on its own side to its filter (FL1-FL5 above).
ROWS = "ABCDEFGHJKLMNPRT"
PLANES = {
    "AV_AVDD": [(4.55, 10.55), (4.55, 19.5), (11.45, 19.5), (11.45, 10.55)],
    "AV_VDD": [(10.45, 4.55), (7.55, 4.55), (7.55, 5.55), (-9.0, 5.55), (-9.0, 9.45), (7.55, 9.45),
               (7.55, 10.45), (10.45, 10.45)],
    "AV_CVDD": [(-9.0, 9.55), (4.45, 9.55), (4.45, 13.45), (-9.0, 13.45)],
    "AV_DVDDIO": [(4.55, -4.5), (4.55, 4.45), (10.55, 4.45), (10.55, 10.45), (12.45, 10.45), (12.45, -4.5)],
}

# Board: x 60-190, y 20.6-90 (the Console's y extent), a window over the SOM
X0, X1, Y0, Y1 = 60.0, 190.0, 20.6, 90.0
WIN = (102.0, 35.0, 151.0, 74.0)
# the window reaches out to the Console's buttons S1 (98.9, 38.0) and S2 (98.9, 71.0)
WIN_POLY = [(96.4, 35.0), (151.0, 35.0), (151.0, 74.0), (96.4, 74.0), (96.4, 68.0), (102.0, 68.0),
            (102.0, 41.0), (96.4, 41.0)]
NOTCHES = [(96.4, 35.0, 102.0, 41.0), (96.4, 68.0, 102.0, 74.0)]
HOLES = [(100.0, 30.0), (158.0, 30.0), (100.0, 79.0), (158.0, 79.0)]     # Console H7_*: M2.5 standoffs
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
    "J1": (71.0, 54.0, 90, "F"), "J2": (71.0, 67.0, 90, "F"), "J3": (71.0, 80.0, 90, "F"),
    "U1": (87.5, 60.5, None, "F"),          # rotation chosen below: analog side left, pixel side right
    "U3": (86.0, 33.0, 0, "F"),
    "Y1": (80.5, 72.5, 0, "F"),
    "U5": (95.0, 26.0, 0, "F"), "U4": (84.0, 47.0, 0, "F"), "U6": (95.0, 47.0, 0, "F"),
    # output wing: ADV7511 data side facing J9, TMDS side facing the HDMI connector
    "U2": (167.5, 40.0, 0, "F"),
    "J6": (184.8, 42.0, 90, "F"),
    "U7": (170.0, 62.0, 0, "F"),
    # ADV7842 rail filters on the bottom, at the exits of their In2 planes (see PLANES)
    "FL1": (87.5, 73.5, 90, "B"), "FL3": (83.5, 73.5, 90, "B"),      # VDD, CVDD: below the BGA
    "FL2": (77.0, 60.0, 90, "B"),                                    # AVDD: left of it
    "FL5": (99.5, 59.5, 90, "B"),                                    # DVDDIO: right of it
    "FL4": (78.5, 78.5, 0, "B"), "FL6": (93.0, 77.0, 0, "B"),        # PVDD, TVDD: routed rails
    # TMDS ESD, in line between U2's TMDS pins (x 176.6, y 37.5-43) and the HDMI pads (x 183.1)
    "U9": (178.8, 38.75, None, "F"), "U10": (178.8, 41.75, None, "F"),
}


def fit_u1(fp, x, y):
    """Analog side (balls x13-16) to the left, pixel side (x1-5) to the right."""
    a1, a16 = pad_pos(fp, "A1"), pad_pos(fp, "A16")
    return a1[0] > x and a16[0] < x and a1[1] > y


def fit_esd(fp, x, y):
    """Lines enter on pads 1-5 (U2's side, left) and leave on 10-6; pad 1 at the top."""
    p1, p10, p5 = pad_pos(fp, "1"), pad_pos(fp, "10"), pad_pos(fp, "5")
    return p1[0] < p10[0] and p1[1] < p5[1]


FIT = {"U1": fit_u1, "U9": fit_esd, "U10": fit_esd}

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
    b.SetCopperLayerCount(4)
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
    for ref, (x, y, ang, side) in HAND.items():
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
    for ref in ("U1", "U2", "U3", "U4", "U5", "U6", "U7", "U9", "U10", "J6", "J9", "J10", "J1", "J2", "J3", "J4", "J5", "Y1"):
        for pad in fps[ref].Pads():
            v = pad.GetPosition()
            ic_pads.setdefault(pad.GetNetname(), []).append((ToMM(v.x), ToMM(v.y), ref))
    rr = {}

    def anchor_for(p):
        # decoupling for U1: spread over its rail's balls, bottom side
        nets_ = [n for n in p.pins.values() if n != "GND"]
        for n in nets_:
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
    planes(b, fps["U1"])
    pcbnew.SaveBoard(OUT, b)
    print("%s: %d footprints" % (OUT, len(fps)))
    if "--route" in sys.argv:
        route()


# ---------------------------------------------------------------------------
# Rules, fanout, planes, routing
# ---------------------------------------------------------------------------

def rules(b):
    ds = b.GetDesignSettings()
    ns = ds.m_NetSettings
    nc = ns.GetDefaultNetclass()
    nc.SetTrackWidth(FromMM(TRACK))
    nc.SetClearance(FromMM(CLEAR))
    nc.SetViaDiameter(FromMM(VIA_D))
    nc.SetViaDrill(FromMM(VIA_DRILL))
    for name, width, clear, nets in (("POWER", 0.4, 0.2, POWER_NETS), ("TMDS", 0.2, 0.15, TMDS_NETS)):
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
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(VECTOR2I(FromMM(a[0]), FromMM(a[1])))
    t.SetEnd(VECTOR2I(FromMM(z[0]), FromMM(z[1])))
    t.SetWidth(FromMM(width))
    t.SetLayer(layer)
    t.SetNet(net)
    b.Add(t)


def via(b, x, y, net):
    v = pcbnew.PCB_VIA(b)
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
        power = net == "GND" or net in POWER_NETS
        ring = min(r, c, 15 - r, 15 - c)
        if not power and ring <= 1:
            continue
        cands = [(r + dr, c + dc) for dr in (-0.5, 0.5) for dc in (-0.5, 0.5)]
        if net in PLANES:
            cands = [p for p in cands if inside(PLANES[net], *p)]
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


def zone(b, netname, layer, pts, clearance=0.25, priority=0):
    z = pcbnew.ZONE(b)
    z.SetLayer(layer)
    z.SetNet(b.FindNet(netname))
    z.SetLocalClearance(FromMM(clearance))
    z.SetMinThickness(FromMM(0.2))
    z.SetAssignedPriority(priority)
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if layer in (pcbnew.In1_Cu, pcbnew.In2_Cu)
                       else pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    o = z.Outline()
    o.NewOutline()
    for x, y in pts:
        o.Append(FromMM(x), FromMM(y))
    b.Add(z)
    return z


def planes(b, fp):
    g = grid(fp)
    full = [(X0 + 0.3, Y0 + 0.3), (X1 - 0.3, Y0 + 0.3), (X1 - 0.3, Y1 - 0.3), (X0 + 0.3, Y1 - 0.3)]
    zone(b, "GND", pcbnew.In1_Cu, full)
    for net, poly in PLANES.items():
        zone(b, net, pcbnew.In2_Cu, [g(r, c) for r, c in poly], priority=1)


def route():
    """Freerouting on the saved board, then the ground pours on the outer layers, filled."""
    b = pcbnew.LoadBoard(OUT)
    dsn, ses = os.path.join(HERE, NAME + ".dsn"), os.path.join(HERE, NAME + ".ses")
    if not pcbnew.ExportSpecctraDSN(b, dsn):
        raise SystemExit("DSN export failed")
    subprocess.run([JAVA, "-jar", FREEROUTING, "-de", dsn, "-do", ses, "-mp", "200", "-mt", "1",
                    "--gui.enabled=false", "--usage_and_diagnostic_data.disable_analytics=true"],
                   check=True, stdout=open(os.path.join(HERE, "route.log"), "w"), stderr=subprocess.STDOUT)
    if not pcbnew.ImportSpecctraSES(b, ses):
        raise SystemExit("SES import failed")
    full = [(X0 + 0.3, Y0 + 0.3), (X1 - 0.3, Y0 + 0.3), (X1 - 0.3, Y1 - 0.3), (X0 + 0.3, Y1 - 0.3)]
    zone(b, "GND", pcbnew.F_Cu, full)
    zone(b, "GND", pcbnew.B_Cu, full)
    pcbnew.SaveBoard(OUT, b)
    b = pcbnew.LoadBoard(OUT)
    b.BuildConnectivity()
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(OUT, b)
    print("routed:", OUT)


if __name__ == "__main__":
    main()
