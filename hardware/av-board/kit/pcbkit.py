"""The PCB generator every revision's gen_pcb.py is built on: a revision subclasses Layout, sets its
outline, hand placement and rules, and fills in the hooks for what is particular to its chips.

Coordinates are the Console's (Sipeed's PCB coordinates, mm, top view, y down), so the sockets sit
exactly over the Console's J9 and J10: each socket's pads are checked against the header pins'
positions and the script stops if one is off.

Placement: the big parts by hand (Layout.HAND), the small ones next to the pin they serve: each
two-terminal part, array or filter is put on the free spot nearest to its anchor (the IC pin it
connects to), on the side given for its group.

    python3 rev-x/gen_pcb.py            # rev-x/<name>.kicad_pcb, placed and unrouted
    python3 rev-x/gen_pcb.py --route    # ... routed by Freerouting (SES=file.ses: import that session
                                        # instead; ROUTER=deeppcb MINUTES=60: route on DeepPCB)
    python3 rev-x/gen_pcb.py --silk     # the silkscreen rules again, on the board as it is (routed)

PCB=path puts a trial board elsewhere.
"""

import json
import math
import os
import subprocess
import sys

import pcbnew
from pcbnew import VECTOR2I, FromMM, ToMM

KIT = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(KIT), "lib")
SYSFP = "/usr/share/kicad/footprints"
JAVA = "/home/linuxbrew/.linuxbrew/opt/openjdk/bin/java"
# Freerouting: 1.9.0 by default. On rev A 2.3-2.5 oscillate between 120 and 220 unrouted
# connections pass after pass; 1.9.0 gets within ~10. 1.9.0 needs an X display even in batch mode:
# a private Xvfb (Homebrew's xorg-server) runs for it. FREEROUTING=2.5.0 picks the headless one.
FREEROUTING_VERSION = os.environ.get("FREEROUTING", "1.9.0")
FREEROUTING = os.path.expanduser("~/tools/freerouting/freerouting-%s.jar" % FREEROUTING_VERSION)
XVFB = "/home/linuxbrew/.linuxbrew/bin/Xvfb"
STEP = 0.25                 # the placer's occupancy grid, mm


def J9_PIN(n):
    """The Console's J9 pin n (Sipeed's PCB coordinates)."""
    return (153.13 - 2.54 * ((n - 1) // 2), 28.73 if n % 2 else 31.27)


def J10_PIN(n):
    return (104.87 + 2.54 * ((n - 1) // 2), 80.27 if n % 2 else 77.73)


def load(fp_id):
    lib, name = fp_id.split(":")
    path = os.path.join(LIB, "lcsc.pretty") if lib == "lcsc" else os.path.join(SYSFP, lib + ".pretty")
    fp = pcbnew.FootprintLoad(path, name)
    assert fp, fp_id
    return fp


def pad_pos(fp, num):
    for p in fp.Pads():
        if p.GetNumber() == num:
            v = p.GetPosition()
            return ToMM(v.x), ToMM(v.y)
    raise KeyError(num)


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


def inside(poly, r, c):
    """Point in polygon (any 2D coordinates: rev A's planes use the BGA's ball grid)."""
    n, hit = len(poly), False
    for i in range(n):
        (r0, c0), (r1, c1) = poly[i], poly[(i + 1) % n]
        if (c0 > c) != (c1 > c) and r < r0 + (r1 - r0) * (c - c0) / (c1 - c0):
            hit = not hit
    return hit


def fit_adv7511(fp, x, y):
    """ADV7511 (LQFP-100): data side (D8-D15, pins 81-88) up, towards J9; TMDS side down."""
    return pad_pos(fp, "84")[1] < y - 5 and pad_pos(fp, "36")[1] > y + 5


def fit_esd(fp, x, y):
    """TPD4E05U06 (flow-through): lines enter on pads 1-5 (the ADV7511's side, left) and leave on
    10-6; pad 1 at the top."""
    p1, p10, p5 = pad_pos(fp, "1"), pad_pos(fp, "10"), pad_pos(fp, "5")
    return p1[0] < p10[0] and p1[1] < p5[1]


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


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


def copper_key(t):
    """A track or via, by layer and position to 10 um (routers round coordinates)."""
    if t.GetClass() == "PCB_VIA":
        return ("via", round(ToMM(t.GetPosition().x), 2), round(ToMM(t.GetPosition().y), 2))
    a = (round(ToMM(t.GetStart().x), 2), round(ToMM(t.GetStart().y), 2))
    z = (round(ToMM(t.GetEnd().x), 2), round(ToMM(t.GetEnd().y), 2))
    return ("track", t.GetLayer()) + min(a, z) + max(a, z)


class Occ:
    """Occupancy of each side on a grid, for the small-part placer."""

    def __init__(self, lay):
        self.lay = lay
        self.cells = {"F": set(), "B": set()}

    def _cells(self, box):
        x0, y0, x1, y1 = box
        for i in range(int(math.floor(x0 / STEP)), int(math.ceil(x1 / STEP))):
            for j in range(int(math.floor(y0 / STEP)), int(math.ceil(y1 / STEP))):
                yield (i, j)

    def free(self, side, box):
        L = self.lay
        x0, y0, x1, y1 = box
        if x0 < L.X0 + 0.5 or x1 > L.X1 - 0.5 or y0 < L.Y0 + 0.5 or y1 > L.Y1 - 0.5:
            return False
        for wx0, wy0, wx1, wy1 in [L.WIN] + L.NOTCHES:
            if x1 > wx0 - 0.5 and x0 < wx1 + 0.5 and y1 > wy0 - 0.5 and y0 < wy1 + 0.5:
                return False
        for bx, by in L.BUTTONS:
            if x1 > bx - 4 and x0 < bx + 4 and y1 > by - 4 and y0 < by + 4:
                return False
        for rx0, ry0, rx1, ry1 in L.RESERVED:
            if x1 > rx0 and x0 < rx1 and y1 > ry0 and y0 < ry1:
                return False
        for hx, hy in L.HOLES:
            if x1 > hx - 3 and x0 < hx + 3 and y1 > hy - 3 and y0 < hy + 3:
                return False
        c = self.cells[side]
        return not any(k in c for k in self._cells(box))

    def take(self, side, box):
        self.cells[side].update(self._cells(box))


class Layout:
    """One revision's board. Subclasses set the class attributes and override the hooks
    (after_hand, anchor_special, rank_special, where_for, checks, fanout, on_plane, rail_planes)."""

    # Copper layers: 4 (F.Cu signal / In1 ground / In2 rail planes + signal / B.Cu signal) or 6
    # (F.Cu / In1 ground / In2 signal / In3 rail planes + signal / In4 ground / B.Cu)
    LAYERS = 4
    # Rules (JLCPCB standard: 0.09 mm track/space, 0.3 mm drill; we stay well above)
    TRACK, CLEAR, VIA_D, VIA_DRILL = 0.127, 0.127, 0.5, 0.3
    POWER_NETS = set()
    CLOCK_NETS = set()
    TMDS_NETS = set()
    # Board outline (x0, y0, x1, y1), a window cut out of it (none: outside the board), notches,
    # standoff holes, the Console's buttons left reachable through holes
    X0, Y0, X1, Y1 = 74.2, 20.6, 168.8, 90.0
    WIN = (-10.0, -10.0, -9.0, -9.0)
    WIN_POLY = []
    NOTCHES = []
    HOLES = [(100.0, 30.0), (158.0, 30.0), (100.0, 79.0), (158.0, 79.0)]    # the Console's H7_* (M2.5)
    BUTTONS = []
    HAND = {}               # ref -> (x, y, angle or None (FIT decides), side); None: placed by a hook
    FIT = {}                # ref -> fit(fp, x, y): is this rotation the right one?
    RESERVED = []           # boxes kept free of small parts, both sides
    KEEP = {}               # ref -> margin kept free of small parts round a hand-placed part (0.3)
    BOTH_SIDES = set()      # hand-placed parts whose margin is kept on the other side too
    BIAS_NETS = set()       # nets whose parts are placed first, nearest their pins
    BUSES = []              # (header, IC): crossings reported after placement
    # Silkscreen: designators only for the parts one finds by eye; labels by the jacks (on the
    # jack's body by the left edge), near parts (ref, text), and the board's name
    SILK_KEEP = {"U", "J", "SW", "Y", "FL", "L", "F", "FB", "H"}
    SILK_LABELS = []
    SILK_NEAR = []

    def __init__(self, board, here):
        self.board = board
        self.DIR = here
        self.NAME = board.NAME
        self.HAND = dict(self.HAND)
        self.OUT = os.environ.get("PCB", os.path.join(here, self.NAME + ".kicad_pcb"))
        self.FANOUT_JSON = self.OUT + ".fanout.json"        # the finishing pass's note of the locked fanout
        self.BOARD_LABEL = "tang-av-scaler AV board rev %s" % board.REV

    @property
    def PLANE_LAYER(self):
        return pcbnew.In2_Cu if self.LAYERS == 4 else pcbnew.In3_Cu

    # --- hooks --------------------------------------------------------------

    def after_hand(self, ref, fp, fps, occ):
        """Called after each hand-placed part is put down (before its margin is taken)."""

    def anchor_special(self, p, ic_pads, fps):
        """A revision's own rule for where a small part goes: ((x, y), side), or None."""
        return None

    def rank_special(self, p, ic_pads):
        """A revision's own placing order for a small part (0 first .. 4 last), or None."""
        return None

    def where_for(self, p, fps):
        """A test box -> bool a small part's spot must pass (a rail cap over its plane), or None."""
        return None

    def checks(self, fps):
        """Assertions on the finished placement."""

    def fanout(self, b, fps):
        """Locked fanout copper laid before routing (a BGA's dogbones)."""

    def fanout_skip(self):
        """Parts fanout_planes leaves alone (fanned out by fanout())."""
        return set()

    def on_plane(self, net, x, y):
        """Is (x, y) over net's rail plane? (a pad there gets a via straight down)"""
        return False

    def rail_planes(self, b, fps):
        """Rail planes on PLANE_LAYER (zones, and keepouts so no signal crosses them)."""

    # --- outline ------------------------------------------------------------

    def outline(self, b):
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

        rect(self.X0, self.Y0, self.X1, self.Y1)
        for k in range(len(self.WIN_POLY)):
            seg(self.WIN_POLY[k], self.WIN_POLY[(k + 1) % len(self.WIN_POLY)])
        for x, y in self.BUTTONS:
            circle(x, y, 7.0)
        for x, y in self.HOLES:
            fp = load("MountingHole:MountingHole_2.7mm_M2.5")
            fp.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
            fp.SetReference("H%d" % (self.HOLES.index((x, y)) + 1))
            b.Add(fp)

    # --- placement ----------------------------------------------------------

    def place_near(self, occ, fp, side, anchor, angles=(0, 90), where=None):
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
            return self.place_near(occ, fp, side, anchor, angles)
        assert best, "no room for %s near %s" % (fp.GetReference(), anchor)
        x, y, ang, box = best
        fp.SetOrientationDegrees(ang)
        fp.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
        occ.take(side, box)

    def main(self):
        board = self.board
        b = pcbnew.BOARD()
        b.SetCopperLayerCount(self.LAYERS)
        ds = b.GetDesignSettings()
        ds.SetBoardThickness(FromMM(1.6))
        self.outline(b)

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

        occ = Occ(self)
        HAND = self.HAND

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
                    if self.FIT[ref](fp, x, y):
                        break
                else:
                    raise SystemExit("no rotation of %s fits" % ref)
            else:
                fp.SetOrientationDegrees(ang)
            self.after_hand(ref, fp, fps, occ)
            keep = self.KEEP.get(ref, 0.3)
            occ.take(side, courtyard(fp, keep))
            if ref in self.BOTH_SIDES:
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
            if ref not in fps:
                continue
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
        net_pins = board.nets()

        def anchor_for(p):
            """Where a small part goes, or None while nothing it hangs on is placed yet."""
            special = self.anchor_special(p, ic_pads, fps)
            if special is not None:
                return special
            nets_ = [n for n in p.pins.values() if n != "GND"]
            # a part on a signal (a pull-up, a termination, a series resistor, a divider) goes where
            # that signal is: at the IC pin it serves, else beside the part it hangs on (a
            # termination's 51 R by its coupling cap), else at the connector pin. Its supply net does
            # not count: a pull-up to 3V3 belongs at its pin, not at the 3V3 regulator.
            sig = sorted((n for n in nets_ if n not in self.POWER_NETS), key=lambda n: len(net_pins.get(n, [])))
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
            parts first, then the revision's own ranks, then whatever serves an IC pin (in board.py
            order), then the rest."""
            nets_ = set(p.pins.values())
            if p.ref.startswith(("FL", "L", "Y")) or nets_ & self.BIAS_NETS:
                return 0
            s = self.rank_special(p, ic_pads)
            if s is not None:
                return s
            if any(r.startswith("U") for n in nets_ - {"GND"} for _, _, r in ic_pads.get(n, [])):
                return 2
            return 4
        order.sort(key=rank)
        while order:
            # the first part in rank order whose anchor is placed (a chain fills in from its IC end)
            for p in order:
                a = anchor_for(p)           # (once per part: a round robin may count calls)
                if a is not None:
                    break
            else:
                raise SystemExit("nothing placed that %s hangs on" % order[0].ref)
            order.remove(p)
            (ax, ay), side = a
            self.place_near(occ, fps[p.ref], side, (ax, ay), where=self.where_for(p, fps))
            add_pads(fps[p.ref])

        for hdr, ic in self.BUSES:
            print("%s bus: %d crossings" % (hdr, crossings(fps[hdr], fps[ic], fps)))
        self.checks(fps)

        self.rules(b)
        self.silkscreen(b)
        self.fanout(b, fps)
        self.fanout_planes(b)
        self.planes(b, fps)
        pcbnew.SaveBoard(self.OUT, b)
        print("%s: %d footprints" % (self.OUT, len(fps)))
        if "--route" in sys.argv:
            self.route()

    # --- silkscreen ---------------------------------------------------------

    _removed = []

    def silkscreen(self, b):
        """Designators only for the parts one finds by eye (SILK_KEEP); the passives' stay on the
        fab layer (JLCPCB places from the CPL, and 0402s leave no room). Labels by the inputs and
        outputs, and the board's."""
        silk = (pcbnew.F_SilkS, pcbnew.B_SilkS)
        X0, Y0, X1, Y1 = self.X0, self.Y0, self.X1, self.Y1
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
            if prefix not in self.SILK_KEEP:
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
        labels = {t for _, t in self.SILK_LABELS} | {t for _, t in self.SILK_NEAR} | {self.BOARD_LABEL}
        for item in list(b.GetDrawings()):                  # (again on a re-run: no duplicates)
            if isinstance(item, pcbnew.PCB_TEXT) and item.GetText() in labels:
                b.Remove(item)
                self._removed.append(item)  # (kept referenced: freed, they break pcbnew's later calls)

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
        for ref, label in self.SILK_LABELS:                 # on the jack's body by the board edge
            bb = b.FindFootprintByReference(ref).GetBoundingBox(False, False)
            text(label, X0 + 1.6, ToMM(bb.GetCenter().y), 1.4, 90)
        for ref, label in self.SILK_NEAR:                   # above the part, else below it
            bb = b.FindFootprintByReference(ref).GetBoundingBox(False, False)
            l_, t_, b_ = ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetBottom())
            text(label, l_ + 3.5, t_ - 1.2, 1.2, spots=[(l_ + 3.5 + dx, t_ - 1.2 - dy, 0) for dy in (0, 0.8, 1.6, 2.4)
                                                       for dx in (0, 1.5, -1.5)]
                 + [(l_ + 3.5, b_ + 1.0 + dy, 0) for dy in (0, 0.8)])
        text(self.BOARD_LABEL, (X0 + X1) / 2 - 5, Y1 - 1.6, 1.2)

    # --- rules, fanout, planes ----------------------------------------------

    def rules(self, b):
        # The ground layers are power layers, so Freerouting never routes on them; the rail planes'
        # layer is mixed: signals may run there outside the planes
        b.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
        if self.LAYERS == 6:
            b.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_SIGNAL)
            b.SetLayerType(pcbnew.In4_Cu, pcbnew.LT_POWER)
        b.SetLayerType(self.PLANE_LAYER, pcbnew.LT_MIXED)
        ds = b.GetDesignSettings()
        ns = ds.m_NetSettings
        nc = ns.GetDefaultNetclass()
        nc.SetTrackWidth(FromMM(self.TRACK))
        nc.SetClearance(FromMM(self.CLEAR))
        nc.SetViaDiameter(FromMM(self.VIA_D))
        nc.SetViaDrill(FromMM(self.VIA_DRILL))
        # power tracks 0.25 mm: they must reach 0.5 mm-pitch supply pins (ADV7511, TPD4E05U06); the
        # big currents run in planes or are short
        # the pixel clocks keep other lines further off [HWG 7.2: nothing near the CLK trace]: 0.19 mm,
        # what the 0.2 mm gaps between their 0.5 mm-pitch pads (ADV7511 pin 79, a 0402 array) allow
        for name, width, clear, nets in (("POWER", 0.25, 0.15, self.POWER_NETS), ("TMDS", 0.2, 0.15, self.TMDS_NETS),
                                         ("CLOCK", self.TRACK, 0.19, self.CLOCK_NETS)):
            c = pcbnew.NETCLASS(name)
            c.SetTrackWidth(FromMM(width))
            c.SetClearance(FromMM(clear))
            c.SetViaDiameter(FromMM(self.VIA_D))
            c.SetViaDrill(FromMM(self.VIA_DRILL))
            if name == "TMDS":
                # 100 R differential, edge-coupled on the outer layers over In1 (0.2 mm at the 0.15 mm
                # gap the routers keep: about 103 R over 7628 prepreg, IPC-2141); check in JLCPCB's
                # impedance calculator before ordering
                c.SetDiffPairWidth(FromMM(0.25))
                c.SetDiffPairGap(FromMM(0.2))
            ns.SetNetclass(name, c)
            for n in nets:
                ns.SetNetclassPatternAssignment(n, name)
        ns.RecomputeEffectiveNetclasses()
        ds.m_MinClearance = FromMM(self.CLEAR)
        ds.m_TrackMinWidth = FromMM(0.1)
        ds.m_ViasMinSize = FromMM(0.45)
        ds.m_MinThroughDrill = FromMM(0.3)
        ds.m_CopperEdgeClearance = FromMM(0.3)
        ds.m_HoleClearance = FromMM(0.2)        # JLCPCB multilayer: 0.2 mm hole to copper
        ds.m_MinResolvedSpokes = 1              # pads on the outer pours have their own vias too

    def track(self, b, a, z, width, layer, net):
        """A locked track: the fanout stays as placed (Freerouting reroutes unlocked copper)."""
        t = pcbnew.PCB_TRACK(b)
        t.SetLocked(True)
        t.SetStart(VECTOR2I(FromMM(a[0]), FromMM(a[1])))
        t.SetEnd(VECTOR2I(FromMM(z[0]), FromMM(z[1])))
        t.SetWidth(FromMM(width))
        t.SetLayer(layer)
        t.SetNet(net)
        b.Add(t)

    def via(self, b, x, y, net):
        v = pcbnew.PCB_VIA(b)
        v.SetLocked(True)
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
        v.SetWidth(FromMM(self.VIA_D))
        v.SetDrill(FromMM(self.VIA_DRILL))
        v.SetNet(net)
        b.Add(v)

    def fanout_planes(self, b):
        """A via next to every surface pad on a plane net (ground; a rail where its plane reaches):
        the router then only routes signals. Each via goes on the first spot, walking out from the
        pad, that clears every other pad, track, via and edge."""
        VIA_D = self.VIA_D
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
            if x - rv < self.X0 + 0.5 or x + rv > self.X1 - 0.5 or y - rv < self.Y0 + 0.5 or y + rv > self.Y1 - 0.5:
                return False
            wx0, wy0, wx1, wy1 = self.WIN
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
        skip_refs = self.fanout_skip()
        for fp in b.GetFootprints():
            if fp.GetReference() in skip_refs:
                continue
            for pad in fp.Pads():
                net = pad.GetNetname()
                if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or not net:
                    continue
                px, py = ToMM(pad.GetPosition().x), ToMM(pad.GetPosition().y)
                if net != "GND" and not self.on_plane(net, px, py):
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
                        on_plane = net == "GND" or all(self.on_plane(net, x + ex, y + ey)
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
                self.track(b, (px, py), (x, y), 0.25, pcbnew.F_Cu if onf else pcbnew.B_Cu, pad.GetNet())
                self.via(b, x, y, pad.GetNet())
                obst.append((x - VIA_D / 2, y - VIA_D / 2, x + VIA_D / 2, y + VIA_D / 2, net, True))
                obst.append((min(px, x) - 0.125, min(py, y) - 0.125, max(px, x) + 0.125, max(py, y) + 0.125, net, False))
                n += 1
        print("plane fanout: %d vias" % n)

    def zone(self, b, netname, layer, pts, clearance=None, priority=0):
        z = pcbnew.ZONE(b)
        z.SetLayer(layer)
        z.SetNet(b.FindNet(netname))
        inner = layer not in (pcbnew.F_Cu, pcbnew.B_Cu)
        # inner planes: 0.127 mm, or the other nets' via holes (1 mm apart under a BGA) would leave no
        # copper between them and cut the planes into islands
        z.SetLocalClearance(FromMM(clearance if clearance is not None else 0.127 if inner else 0.25))
        z.SetMinThickness(FromMM(0.15 if inner else 0.2))
        z.SetAssignedPriority(priority)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if inner else pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        o = z.Outline()
        o.NewOutline()
        for x, y in pts:
            o.Append(FromMM(x), FromMM(y))
        b.Add(z)
        return z

    def keepout(self, b, x0, y0, x1, y1, pts=None, layer=None, vias=True):
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

    def full(self):
        return [(self.X0 + 0.3, self.Y0 + 0.3), (self.X1 - 0.3, self.Y0 + 0.3),
                (self.X1 - 0.3, self.Y1 - 0.3), (self.X0 + 0.3, self.Y1 - 0.3)]

    def planes(self, b, fps):
        X0, Y0, X1, Y1 = self.X0, self.Y0, self.X1, self.Y1
        m = 0.45
        for x0, y0, x1, y1 in ((X0, Y0, X1, Y0 + m), (X0, Y1 - m, X1, Y1), (X0, Y0, X0 + m, Y1), (X1 - m, Y0, X1, Y1)):
            self.keepout(b, x0, y0, x1, y1)
        wx0, wy0, wx1, wy1 = self.WIN
        if wx0 > X0:
            self.keepout(b, wx0 - m, wy0 - m, wx1 + m, wy1 + m)
        for bx, by in self.BUTTONS:
            self.keepout(b, bx - 3.5 - m, by - 3.5 - m, bx + 3.5 + m, by + 3.5 + m)
        for hx, hy in self.HOLES:               # standoffs: the M2.5 head and the standoff sit there
            self.keepout(b, hx - 3.0, hy - 3.0, hx + 3.0, hy + 3.0)
        self.zone(b, "GND", pcbnew.In1_Cu, self.full())
        if self.LAYERS == 6:
            self.zone(b, "GND", pcbnew.In4_Cu, self.full())
        self.rail_planes(b, fps)

    def stitch(self, b, pitch=2.5, gap=0.3):
        """Ground vias on a grid wherever they clear every pad, track, via, edge and the window: they
        tie the outer pours to the ground planes (and the islands the tracks cut out of them)."""
        VIA_D = self.VIA_D
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
        y = self.Y0 + 1.5
        while y < self.Y1 - 1.4:
            x = self.X0 + 1.5
            while x < self.X1 - 1.4:
                wx0, wy0, wx1, wy1 = self.WIN
                ok = not (wx0 - 1.0 < x < wx1 + 1.0 and wy0 - 1.0 < y < wy1 + 1.0)
                # (the standoffs' keepouts are 6 mm squares, see planes())
                ok = ok and all(abs(x - hx) > 3.0 + VIA_D / 2 or abs(y - hy) > 3.0 + VIA_D / 2 for hx, hy in self.HOLES)
                ok = ok and all(((x - hx) ** 2 + (y - hy) ** 2) ** 0.5 > 4.5 for hx, hy in self.BUTTONS)
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
                    self.via(b, x, y, gnd)
                    pts.append((x, y, VIA_D / 2))
                    n += 1
                x += pitch
            y += pitch
        print("stitching vias:", n)

    # --- routing ------------------------------------------------------------

    def prune(self, path, rounds=5):
        """Remove the vias and track ends KiCad's DRC reports as dangling (fanout the router did not
        use, stubs it left), round after round, refilling the zones each time."""
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

    @staticmethod
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

    def session(self, b, ses_for):
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
        dsn = os.path.splitext(self.OUT)[0] + ".dsn"    # (named after the board: trials can run side by side)
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
                    self.via(b, f[1], f[2], b.FindNet(f[3]))
                    back += 1
            else:
                a, z = (round(f[1], 2), round(f[2], 2)), (round(f[3], 2), round(f[4], 2))
                if ("track", f[6]) + min(a, z) + max(a, z) not in have:
                    self.track(b, (f[1], f[2]), (f[3], f[4]), f[5], f[6], b.FindNet(f[7]))
                    back += 1
        return back

    def route(self):
        """Route the saved board (Freerouting, DeepPCB or a given session), finish what another router
        left with Freerouting, then the ground pours on the outer layers, filled. Each step runs in a
        process of its own: after a DSN export, pcbnew can no longer list a board's tracks, nor load
        one."""
        b = pcbnew.LoadBoard(self.OUT)
        me = os.path.join(self.DIR, "gen_pcb.py")

        def first(dsn):
            if os.environ.get("SES"):
                return os.environ["SES"]        # a session routed elsewhere (another router, by hand)
            ses = os.path.splitext(self.OUT)[0] + ".ses"
            if os.environ.get("ROUTER") == "deeppcb":
                subprocess.run([sys.executable, os.path.join(KIT, "deeppcb.py"), "run", dsn, ses, "--minutes",
                                os.environ.get("MINUTES", "60")], check=True)
            else:
                self.freerouting(dsn, ses)
            return ses
        print("fanout items put back after the import:", self.session(b, first))
        pcbnew.SaveBoard(self.OUT, b)
        if (os.environ.get("SES") or os.environ.get("ROUTER") == "deeppcb") and os.environ.get("FINISH", "1") == "1":
            subprocess.run([sys.executable, me, "--finish"], check=True)
        subprocess.run([sys.executable, me, "--pour"], check=True)

    def finish(self):
        """What another router left unconnected: Freerouting with all of its copper fixed (the fanout,
        noted, is unlocked again by pour())."""
        b = pcbnew.LoadBoard(self.OUT)
        tracks = list(b.GetTracks())
        with open(self.FANOUT_JSON, "w") as f:
            json.dump([list(copper_key(t)) for t in tracks if t.IsLocked()], f)
        for t in tracks:
            t.SetLocked(True)

        def ses_for(dsn):
            ses = os.path.splitext(self.OUT)[0] + "-finish.ses"
            self.freerouting(dsn, ses)
            return ses
        print("finishing pass: items put back after the import:", self.session(b, ses_for))
        pcbnew.SaveBoard(self.OUT, b)

    def pour(self):
        """Ground pours on the outer layers, stitching, fill, prune; only the fanout stays locked."""
        b = pcbnew.LoadBoard(self.OUT)
        if os.path.exists(self.FANOUT_JSON):
            with open(self.FANOUT_JSON) as f:
                fanout = {tuple(k) for k in json.load(f)}
            for t in b.GetTracks():
                t.SetLocked(copper_key(t) in fanout)
            os.remove(self.FANOUT_JSON)
        self.zone(b, "GND", pcbnew.F_Cu, self.full())
        self.zone(b, "GND", pcbnew.B_Cu, self.full())
        self.stitch(b)
        pcbnew.SaveBoard(self.OUT, b)
        b = pcbnew.LoadBoard(self.OUT)
        b.BuildConnectivity()
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        pcbnew.SaveBoard(self.OUT, b)
        self.prune(self.OUT)
        print("routed:", self.OUT)

    def cli(self, argv):
        if "--finish" in argv:              # route()'s steps, each in a process of its own
            self.finish()
        elif "--pour" in argv:
            self.pour()
        elif "--silk" in argv:              # the silkscreen rules on a board as it is (routed)
            b = pcbnew.LoadBoard(self.OUT)
            self.silkscreen(b)
            pcbnew.SaveBoard(self.OUT, b)
        else:
            self.main()


def layout_of(rev):
    """The Layout of a revision directory (rev-a, or a path to one), for the kit's tools."""
    d = rev if os.path.isdir(rev) else os.path.join(os.path.dirname(KIT), rev)
    d = os.path.abspath(d)
    sys.path.insert(0, d)
    import gen_pcb  # noqa: E402  (the revision's)
    return gen_pcb.LAYOUT
