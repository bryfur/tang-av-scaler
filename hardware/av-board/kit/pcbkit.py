"""The PCB generator every revision's gen_pcb.py is built on: a revision subclasses Layout, sets its
outline, hand placement and rules, and fills in the hooks for what is particular to its chips.

Coordinates are the Console's (Sipeed's PCB coordinates, mm, top view, y down), so the sockets sit
exactly over the Console's J9 and J10: each socket's pads are checked against the header pins'
positions and the script stops if one is off.

Placement: the big parts by hand (Layout.HAND), the small ones next to the pin they serve: each
two-terminal part, array or filter is put on the free spot nearest to its anchor (the IC pin it
connects to; a part board.py names a pad for, at=, that pad), on the side given for its group.
The ESD parts go first, at their connectors, then the small chips, each pin's capacitor as soon
as its chip is down, then the rest (rank in main()).

    python3 rev-x/gen_pcb.py            # rev-x/<name>.kicad_pcb, placed and unrouted
    python3 rev-x/gen_pcb.py --route    # ... routed by Freerouting (SES=file.ses: import that session
                                        # instead; ROUTER=deeppcb MINUTES=60: route on DeepPCB)
    python3 rev-x/gen_pcb.py --silk     # the silkscreen rules again, on the board as it is (routed)
    python3 rev-x/gen_pcb.py --move REF x y angle   # a part moved on the routed board (move_part),
    python3 rev-x/gen_pcb.py --complete             # then its connections made again, the stubs cleared

PCB=path puts a trial board elsewhere.
"""

import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile

import pcbnew
from pcbnew import VECTOR2I, FromMM, ToMM

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doubled  # noqa: E402

KIT = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(KIT), "lib")
SYSFP = "/usr/share/kicad/footprints"
# (JAVA, XVFB: the build host's Homebrew ones unless the environment names others, as the routing
# container on another host does)
JAVA = os.environ.get("JAVA", "/home/linuxbrew/.linuxbrew/opt/openjdk/bin/java")
# Freerouting: 1.9.0 by default. On rev A 2.3-2.5 oscillate between 120 and 220 unrouted
# connections pass after pass; 1.9.0 gets within ~10. 1.9.0 needs an X display even in batch mode:
# a private Xvfb (Homebrew's xorg-server) runs for it. FREEROUTING=2.5.0 picks the headless one;
# FREEROUTING_ARGS adds options of its own (2.x's -mt 1: one optimizer thread, for trials side by
# side; it takes all cores but one otherwise).
FREEROUTING_VERSION = os.environ.get("FREEROUTING", "1.9.0")
FREEROUTING = os.path.expanduser("~/tools/freerouting/freerouting-%s.jar" % FREEROUTING_VERSION)
FREEROUTING_ARGS = os.environ.get("FREEROUTING_ARGS", "").split()
XVFB = os.environ.get("XVFB", "/home/linuxbrew/.linuxbrew/bin/Xvfb")
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


def clip_line(a, z, w, boxes, keep, shortest=0.2):
    """The pieces of the line a-z (mm, w wide) that stay inside keep and out of every box (each
    (x0, y0, x1, y1)), its edges w / 2 off them; pieces cut shorter than shortest are dropped (the
    whole line, left as it is, stays)."""
    dx, dy = z[0] - a[0], z[1] - a[1]

    def span(q, grow):
        # the stretch [t0, t1] of a + t (z - a) inside the box q grown by grow (Liang-Barsky)
        x0, y0, x1, y1 = q[0] - grow, q[1] - grow, q[2] + grow, q[3] + grow
        t0, t1 = 0.0, 1.0
        for p, d in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
            if abs(p) < 1e-12:
                if d < 0:
                    return None
            elif p < 0:
                t0 = max(t0, d / p)
            else:
                t1 = min(t1, d / p)
        return (t0, t1) if t0 < t1 else None
    # (a line cut once ends on a box's edge, rounded to 1 nm: only what reaches more than eps past
    # an edge is cut, and then at the edge itself)
    eps = 1e-4
    k = span(keep, eps - w / 2)
    if k is None:
        return []
    if k != (0.0, 1.0):
        k = span(keep, -w / 2) or k
    pieces, t = [], k[0]
    for c0, c1 in sorted(span(q, w / 2) for q in boxes if span(q, w / 2 - eps)):
        if c0 > t:
            pieces.append((t, min(c0, k[1])))
        t = max(t, c1)
        if t >= k[1]:
            break
    if t < k[1]:
        pieces.append((t, k[1]))
    n = math.hypot(dx, dy)
    if pieces == [(0.0, 1.0)]:
        return [(a, z)]
    return [((a[0] + dx * t0, a[1] + dy * t0), (a[0] + dx * t1, a[1] + dy * t1))
            for t0, t1 in pieces if (t1 - t0) * n >= shortest]


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
    away from the header, against the order of the header pins along the header (pins side by side
    across its rows do not count). Any header orientation (rev C's SOM receptacles stand upright).
    On a fine-pitch header (rev C's: 0.4 mm) only pairs from one row count: a line from the inner
    row cannot pass between the outer row's pads, so it leaves on the other layer."""
    cx, cy = ToMM(ic.GetPosition().x), ToMM(ic.GetPosition().y)
    bx = courtyard(ic, 0)
    reach = math.hypot(bx[2] - bx[0], bx[3] - bx[1]) / 2 + 6
    hp = [(ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)) for p in hdr.Pads()]
    upright = max(y for _, y in hp) - min(y for _, y in hp) > max(x for x, _ in hp) - min(x for x, _ in hp)

    def along(x, y):
        return round(y if upright else x, 2)

    def across(x, y):
        return round(x if upright else y, 1)
    steps = sorted({along(*q) for q in hp})
    fine = min(b - a for a, b in zip(steps, steps[1:])) < 1.0
    # the cut: square away from the header, a little to the left (lines from right under the IC go
    # round its right); the order round the IC runs the way the header's pins do
    hx0, hy0 = ToMM(hdr.GetPosition().x), ToMM(hdr.GetPosition().y)
    away = (0.0 if hx0 < cx else math.pi) if upright else (math.pi / 2 if hy0 < cy else -math.pi / 2)
    cut = away + 0.4

    def rel(x, y):
        return (math.atan2(y - cy, x - cx) - cut) % (2 * math.pi)
    lo, hi = min(hp, key=lambda q: along(*q)), max(hp, key=lambda q: along(*q))
    sign = 1 if rel(*hi) > rel(*lo) else -1
    pads = {}
    for fp in fps.values():
        if fp is not hdr:
            for pad in fp.Pads():
                v = pad.GetPosition()
                pads.setdefault(pad.GetNetname(), []).append((ToMM(v.x), ToMM(v.y)))
    lines = []
    for pad in hdr.Pads():
        n = pad.GetNetname()
        if not n or n in ("GND", "+5V") or n not in pads:
            continue
        hx, hy = ToMM(pad.GetPosition().x), ToMM(pad.GetPosition().y)
        sx, sy = min(pads[n], key=lambda q: math.hypot(q[0] - hx, q[1] - hy))
        if math.hypot(sx - cx, sy - cy) > reach:
            continue
        lines.append((along(hx, hy), sign * rel(sx, sy), across(hx, hy) if fine else 0))
    return sum(1 for i, a in enumerate(lines) for b in lines[i + 1:]
               if a[0] != b[0] and a[2] == b[2] and (a[0] < b[0]) != (a[1] < b[1]))


def copper_key(t):
    """A track or via, by layer and position to 10 um (routers round coordinates)."""
    if t.GetClass() == "PCB_VIA":
        return ("via", round(ToMM(t.GetPosition().x), 2), round(ToMM(t.GetPosition().y), 2))
    a = (round(ToMM(t.GetStart().x), 2), round(ToMM(t.GetStart().y), 2))
    z = (round(ToMM(t.GetEnd().x), 2), round(ToMM(t.GetEnd().y), 2))
    return ("track", t.GetLayer()) + min(a, z) + max(a, z)


def covered(b, eps=0.03):
    """Copper the router laid twice over: each unlocked segment lying wholly on another of its net
    and layer, at least as wide (both its ends within (wB - wA) / 2 + eps mm of the other's centre
    line); of two identical ones, one. It joins nothing the wider one does not (freerouting leaves
    such copies where it routes over its own track; the side-by-side ones: beside())."""
    by = {}
    for t in b.GetTracks():
        if t.GetClass() == "PCB_TRACK":
            by.setdefault((t.GetNetCode(), t.GetLayer()), []).append(
                (t, ToMM(t.GetWidth()), [ToMM(v) for v in (t.GetStart().x, t.GetStart().y,
                                                           t.GetEnd().x, t.GetEnd().y)]))
    gone = []
    for segs in by.values():
        out = set()
        for i, (t, wa, (ax, ay, az, aw)) in enumerate(segs):
            if t.IsLocked() or wa / 2 <= eps:
                continue
            for j, (_, wb, s) in enumerate(segs):
                tol = (wb - wa) / 2 + eps
                if (j != i and j not in out and wb >= wa and seg_dist(ax, ay, *s) <= tol
                        and seg_dist(az, aw, *s) <= tol):
                    out.add(i)
                    gone.append(t)
                    break
    return gone


def beside(b):
    """Copper the router laid twice side by side: the shorter of each pair kit/doubled.py finds
    (same net and layer, within 10 degrees, the shorter within 0.35 mm of the other), unless
    locked. Taking one up leaves its path's stubs dangling, for the next round of prune()."""
    out = {}
    for _, short, _, _, _, _ in doubled.pairs(b):
        if not short.IsLocked():
            out.setdefault(short.m_Uuid.AsString(), short)
    return list(out.values())


TRACK = re.compile(r"^\t\((?:segment|via|arc)\n.*?^\t\)\n", re.M | re.S)


def save_without(path, items, out):
    """A copy of the board at path, its project file beside it, without the given tracks: taken out
    of the file's text (each track a block of its own, tab-indented), no pcbnew board touched."""
    gone = {t.m_Uuid.AsString() for t in items}
    left = set(gone)

    def drop(m):
        uuid = re.search(r'^\t\t\(uuid "([^"]+)"\)$', m.group(0), re.M).group(1)
        if uuid not in gone:
            return m.group(0)
        left.discard(uuid)
        return ""
    with open(path) as f:
        text = TRACK.sub(drop, f.read())
    if left:
        raise RuntimeError("%d of the tracks to take out not found in %s" % (len(left), path))
    with open(out, "w") as f:
        f.write(text)
    pro = os.path.splitext(path)[0] + ".kicad_pro"
    if os.path.exists(pro):
        shutil.copy(pro, os.path.splitext(out)[0] + ".kicad_pro")


def removable(path, rpt, items, loose_ok):
    """Of the tracks given (copper laid twice), the ones that can go: all of them if DRC of the board
    without them (save_without()) finds no more connections missing, nor, unless loose_ok, ends
    left dangling (a copy lying on a track may stick out past it: a pad touching only that end);
    else each that can, one by one. rpt: the board's DRC report as it is, nothing dangling."""
    def fine(sub):
        with tempfile.TemporaryDirectory() as tmp:
            check = os.path.join(tmp, "prune.kicad_pcb")
            save_without(path, sub, check)
            after = drc_report(check, "--severity-all")
        cut = len(after["unconnected_items"]) - len(rpt["unconnected_items"])
        loose = sum(1 for v in after["violations"] if v["type"] in ("via_dangling", "track_dangling"))
        return cut <= 0 and (loose_ok or not loose)
    if not items or fine(items):
        return items
    can = []
    for t in items:
        if fine(can + [t]):
            can.append(t)
    print("copper laid twice kept: %d of %d copies, without them DRC finds connections missing%s"
          % (len(items) - len(can), len(items), "" if loose_ok else " or ends dangling"))
    return can


def drc_report(path, *flags):
    """kicad-cli's DRC of the board at path (its JSON report: violations, unconnected_items). No
    report means kicad-cli could not load the board (a save cut short by a full disk): an error
    with kicad-cli's own words, which the routing steps' "no path" handlers (SystemExit) let pass."""
    with tempfile.TemporaryDirectory() as tmp:
        rpt = os.path.join(tmp, "drc.json")
        r = subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json"] + list(flags) + ["-o", rpt, path],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            with open(rpt) as f:
                return json.load(f)
        except (OSError, ValueError):
            raise RuntimeError("DRC of %s gave no report (kicad-cli exit %d): %s"
                               % (path, r.returncode, r.stdout.strip()[-400:]))


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
    # four layers: In2 a second ground plane (signals on F.Cu and B.Cu only, each over its own
    # plane) instead of a signal layer with the rail planes
    INNER_GND = False
    # Rules (JLCPCB standard: 0.09 mm track/space, 0.3 mm drill; we stay well above)
    TRACK, CLEAR, VIA_D, VIA_DRILL = 0.127, 0.127, 0.5, 0.3
    POWER_NETS = set()
    CLOCK_NETS = set()
    TMDS_NETS = set()
    TMDS_W, TMDS_PAIR = 0.2, (0.25, 0.2)    # the TMDS class's track width; a pair's width and gap
    MIN_VIA = (0.45, 0.3)                   # the smallest via (diameter, drill) the rules allow
    MIN_CLEAR = None                        # the board's minimum clearance, if below CLEAR (a part's own pads)
    CLASSES = []                            # a revision's own net classes: (name, width, clearance, nets)
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
    FPGA_HEADERS = ("J9", "J10")    # the FPGA's side: a series resistor on a line it drives sits there
    # Silkscreen: designators only for the parts one finds by eye; labels by the jacks (inboard of
    # the jack's body, at its board edge), near parts (ref, text[, angle]: turned that much, beside the
    # part rather than above or below it), a header's pins (ref, {pad: text}[,
    # "left"]: see pin_labels; the header's designator then hidden), and the board's name (TITLE_AT:
    # (x, y[, angle]) its centre, else near the bottom edge's middle). SILK_HIDDEN: boxes a label
    # would be hidden in once the parts are fitted, besides their bodies (rev C: under the SOM)
    SILK_KEEP = {"U", "J", "SW", "Y", "FL", "L", "F", "FB", "H"}
    SILK_LABELS = []
    SILK_NEAR = []
    SILK_PINS = []
    TITLE_AT = None
    SILK_HIDDEN = []
    # [JLCPCB's capabilities: silkscreen lines 0.15 mm wide at least, 0.15 mm from pads; text 1 mm
    # high at least, its stroke 1:6 of that]
    SILK_W, SILK_PAD, SILK_TEXT = 0.15, 0.15, 1.0

    @staticmethod
    def stroke(size):
        """A silkscreen text's stroke for its height (mm): JLCPCB's 1:6, 0.15 mm at least."""
        return max(0.15, round(size / 6, 3))

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

    @property
    def ROUTE_LAYERS(self):
        """The layers tracks may use (mazeroute.py's MAZE_LAYERS)."""
        if self.LAYERS == 4 and self.INNER_GND:
            return "F.Cu,B.Cu"
        return "F.Cu,In2.Cu,B.Cu"

    # --- hooks --------------------------------------------------------------

    def after_hand(self, ref, fp, fps, occ):
        """Called after each hand-placed part is put down (before its margin is taken)."""

    def anchor_special(self, p, ic_pads, fps):
        """A revision's own rule for where a small part goes: ((x, y), side), or None."""
        return None

    def rank_special(self, p, ic_pads):
        """A revision's own placing order for a small part (0 first .. 4 last), or None."""
        return None

    def bias_rank(self, p):
        """The order among the first-placed parts (bias, references, filters): with the parts board.py
        names a pin for (at=), in board.py's order, the circuits' own order of importance (a
        regulator's input capacitor, its inductor, output capacitor, feedback divider; R_EXT before
        the ADV7511's decoupling). Ranked after those parts they lost their pins' room (the
        feedback dividers 11-13 mm off, R_EXT 7.5 mm)."""
        return -1

    # ESD parts, by value: TI's TPDxE05U06 diodes and arrays, the SMF TVS diodes
    ESD_VALUES = ("TPD", "SMF")

    def esd(self, p):
        """Is p an ESD part (placed first, at its connector)?"""
        return p.value.startswith(self.ESD_VALUES)

    def where_for(self, p, fps):
        """A test box -> bool a small part's spot must pass (a rail cap over its plane), or None."""
        return None

    def checks(self, fps):
        """Assertions on the finished placement."""

    def fanout(self, b, fps):
        """Locked fanout copper laid before routing (a BGA's dogbones)."""

    def fanout_skip(self):
        """Parts (REF) or pads (REF.PAD) fanout_planes leaves alone (fanned out by fanout())."""
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
        # (the nearest free spot may lie across a reserved area from the anchor - a corridor, the
        # SOM - once the room by it has run out: noted, as its lines must then cross that area; a
        # millimetre at least, not a corner clipped)
        d = math.hypot(x - ax, y - ay)
        pts = [(ax + (x - ax) * k / max(1, int(d / 0.25)), ay + (y - ay) * k / max(1, int(d / 0.25)))
               for k in range(max(1, int(d / 0.25)) + 1)]
        for rx0, ry0, rx1, ry1 in self.RESERVED:
            def inside(p):
                return rx0 < p[0] < rx1 and ry0 < p[1] < ry1
            if not inside(pts[0]) and not inside(pts[-1]) and sum(map(inside, pts)) * d / len(pts) >= 1.0:
                print("note: %s placed across a reserved area from its anchor (%.1f, %.1f)" % (fp.GetReference(), ax, ay))

    def main(self):
        board = self.board
        # the board with its project, where its net classes and rules are kept (KiCad 10 writes no
        # .kicad_pro for a bare BOARD(): they were lost); the project written anew, as before
        pro = os.path.splitext(self.OUT)[0] + ".kicad_pro"
        if os.path.exists(pro):
            os.remove(pro)
        b = pcbnew.NewBoard(self.OUT)
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
                if str(hit[0]) in p.pins:           # (a pin left open has no net)
                    pad.SetNet(net(p.pins[str(hit[0])]))
        # the labelled headers' pin labels: their room kept free of parts (pin_labels)
        for ref, names, *side in self.SILK_PINS:
            if ref in fps:
                for _, (x0, y0, x1, y1) in self.pin_labels(b, fps[ref], names, *side):
                    occ.take("F", (x0 - 0.15, y0 - 0.15, x1 + 0.15, y1 + 0.15))

        # --- small parts next to their anchors
        # pads already placed, by net: the hand-placed parts now, each small part as it is placed
        ic_pads = {}
        placed = set()

        def add_pads(fp):
            placed.add(fp.GetReference())
            for pad in fp.Pads():
                v = pad.GetPosition()
                ic_pads.setdefault(pad.GetNetname(), []).append((ToMM(v.x), ToMM(v.y), fp.GetReference()))
        for ref in HAND:
            add_pads(fps[ref])
        net_pins = board.nets()

        def anchor_for(p):
            """Where a small part goes, or None while nothing it hangs on is placed yet."""
            # a part for one pad (board.py's at="REF.PAD": a supply pin's decoupling, a regulator's
            # input or output capacitor) at that pad, once its part is placed: by the rules below
            # every capacitor on a rail went to the chip's first pin on it (an ADV7511's 100 nF all
            # by its pin 24, 9-20 mm from the pins on its other sides [HWG 7.1: each "as close to
            # the supply pin as possible"]; a TLV62569's input capacitor by EN, pin 1, its VIN on
            # the package's other side, 5-14 mm off)
            if p.at:
                ref, pad = p.at.split(".")
                return (pad_pos(fps[ref], pad), "F") if ref in placed else None
            special = self.anchor_special(p, ic_pads, fps)
            if special is not None:
                return special
            nets_ = [n for n in p.pins.values() if n != "GND"]
            # an ESD part at its connector [TI-ESD: as close to the connector as possible]: from the
            # middle of the pins it guards there (on the connector with most of them) 2.5 mm towards
            # where its lines go (the middle of their pads placed so far), so it sits on their way
            # with room for them and its ground via to reach it (right under a header's pins, rev B's
            # VGA array left one of its three lines no way in). By the signal rule below an array
            # went to the chip at the lines' other end (the HDMI DDC/CEC array 50-60 mm from its
            # connector on rev C)
            if self.esd(p):
                pins_ = {}
                for n in nets_:
                    for x, y, r in ic_pads.get(n, []):
                        if r.startswith("J"):
                            pins_.setdefault(r, []).append((x, y))
                if pins_:
                    pts = max(pins_.values(), key=len)
                    cx, cy = sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)
                    far = [(x, y) for n in nets_ for x, y, r in ic_pads.get(n, []) if not r.startswith("J") and r != p.ref]
                    if far:
                        fx, fy = sum(x for x, _ in far) / len(far), sum(y for _, y in far) / len(far)
                        d = math.hypot(fx - cx, fy - cy)
                        if d > 2.5:
                            cx, cy = cx + 2.5 * (fx - cx) / d, cy + 2.5 * (fy - cy) / d
                    return (cx, cy), "F"
            # a part on a signal (a pull-up, a termination, a series resistor, a divider) goes where
            # that signal is: at the IC pin it serves, else beside the part it hangs on (a
            # termination's 51 R by its coupling cap), else at the connector pin. Its supply net does
            # not count: a pull-up to 3V3 belongs at its pin, not at the 3V3 regulator.
            sig = sorted((n for n in nets_ if n not in self.POWER_NETS), key=lambda n: len(net_pins.get(n, [])))
            # except a series resistor on a line the FPGA drives (OUT_*, to the ADV7511): it goes at
            # the source end, the header [HWG 7.3]
            drive = [n for n in sig if n.startswith("OUT_")]
            if p.ref.startswith("R") and len(sig) == 2 and drive:
                return [(x, y) for x, y, r in ic_pads[drive[0]] if r in self.FPGA_HEADERS][0], "F"
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
            """The order the small parts get their places in: the ESD parts at their connectors
            first, the small chips, then a pin's own parts in board.py's order (its capacitor, at=,
            each as soon as its chip is placed; the bias, reference and filter parts, bias_rank),
            a regulator or filter for one chip (at= that chip's pin) beside it, then the
            revision's own ranks, then whatever serves an IC pin (in board.py order), the rest."""
            nets_ = set(p.pins.values())
            if self.esd(p):
                return -2               # (before anything else takes the room at its connector)
            if p.ref.startswith("U") and not p.at:
                return -1.5             # (a small chip by its partners, before parts crowd round them)
            if p.at:
                # (a pin's own capacitor before anything takes its room; anything else at= - a
                # regulator for one chip, a rail's filter - beside the pin, its capacitors placed)
                return -1 if p.ref.startswith("C") else -0.5
            if p.ref.startswith(("FL", "L", "Y")) or nets_ & self.BIAS_NETS:
                return self.bias_rank(p)
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
        if os.path.exists(self.OUT + ".before-rip"):    # (an older board's unfinished rip-up, which
            os.remove(self.OUT + ".before-rip")         # finish_unconnected would put back over this one)
        print("%s: %d footprints" % (self.OUT, len(fps)))
        if "--route" in sys.argv:
            self.route()

    # --- silkscreen ---------------------------------------------------------

    _removed = []

    def pin_labels(self, b, fp, names, side=None):
        """A labelled header's pin labels (SILK_PINS): [(text, box)], not yet on the board. Pins in a
        row: each label under its pin, below the body, every other one above it where neighbours
        would run together (1 mm text at 2.54 mm: TCK TDO TDI TMS); pins in a column: each beside
        its pin, right of the body (side "left": left of it); pins in two columns (a two-row header
        stood upright): each beside its pin on its column's own side. The placer keeps their boxes
        free of parts, so that no label ends up under a part or over a pad."""
        bb = fp.GetBoundingBox(False, False)
        l_, t_, r_, b_ = ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetRight()), ToMM(bb.GetBottom())
        pins = sorted((ToMM(p.GetPosition().x), ToMM(p.GetPosition().y), names[p.GetNumber()])
                      for p in fp.Pads() if p.GetNumber() in names)

        def label(s_, x, y, just):
            t = pcbnew.PCB_TEXT(b)
            t.SetText(s_)
            t.SetLayer(pcbnew.F_SilkS)
            t.SetTextSize(VECTOR2I(FromMM(self.SILK_TEXT), FromMM(self.SILK_TEXT)))
            t.SetTextThickness(FromMM(self.stroke(self.SILK_TEXT)))
            t.SetHorizJustify(just)
            t.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
            r = t.GetBoundingBox()
            return t, (ToMM(r.GetLeft()), ToMM(r.GetTop()), ToMM(r.GetRight()), ToMM(r.GetBottom()))
        if pins[-1][0] - pins[0][0] < 0.01:
            if side == "left":
                return [label(s_, l_ - 0.5, y, pcbnew.GR_TEXT_H_ALIGN_RIGHT) for _, y, s_ in pins]
            return [label(s_, r_ + 0.5, y, pcbnew.GR_TEXT_H_ALIGN_LEFT) for _, y, s_ in pins]
        xs = sorted({round(x, 2) for x, _, _ in pins})
        if len(xs) == 2 and len({round(y, 2) for _, y, _ in pins}) > 2:
            return [label(s_, l_ - 0.5, y, pcbnew.GR_TEXT_H_ALIGN_RIGHT) if round(x, 2) == xs[0]
                    else label(s_, r_ + 0.5, y, pcbnew.GR_TEXT_H_ALIGN_LEFT) for x, y, s_ in pins]
        row = [label(s_, x, b_ + 0.75, pcbnew.GR_TEXT_H_ALIGN_CENTER) for x, _, s_ in pins]
        if any(a[1][2] > z[1][0] for a, z in zip(row, row[1:])):
            row = [label(s_, x, t_ - 0.75 if k % 2 else b_ + 0.75, pcbnew.GR_TEXT_H_ALIGN_CENTER)
                   for k, (x, _, s_) in enumerate(pins)]
        return row

    def silkscreen(self, b):
        """Designators only for the parts one finds by eye (SILK_KEEP); the passives' stay on the
        fab layer (JLCPCB places from the CPL, and 0402s leave no room). Labels by the inputs and
        outputs, and the board's. Each text on the board, 1 mm high at least (SILK_TEXT), clear of
        the pads, of the texts before it and of the other parts' bodies (and for a label of
        SILK_HIDDEN: where it would be hidden once they are fitted): the headers' pin labels first
        (each belongs at its pin), then the board's name, the jacks' and parts' labels, last the
        designators (hidden where there is no room); a label left with no clear place is
        reported. Then the parts' own silkscreen, cut back around it all (silk_tidy())."""
        silk = (pcbnew.F_SilkS, pcbnew.B_SilkS)
        X0, Y0, X1, Y1 = self.X0, self.Y0, self.X1, self.Y1
        # copper a text must keep off, per side (through-hole pads on both); the parts' bodies
        pads = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
        bodies = {pcbnew.F_SilkS: list(self.SILK_HIDDEN), pcbnew.B_SilkS: []}
        for fp in b.GetFootprints():
            bodies[pcbnew.B_SilkS if fp.IsFlipped() else pcbnew.F_SilkS].append(courtyard(fp, 0))
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

        def clear(box, side=pcbnew.F_SilkS, label=True, own=None, gap=0.0, hidden=True):
            """On the board, clear of the pads and of the texts placed (a label also of the parts'
            bodies but own, and if hidden of SILK_HIDDEN), gap apart from texts and bodies."""
            g = (box[0] - gap, box[1] - gap, box[2] + gap, box[3] + gap)
            return box[0] > X0 + 0.3 and box[2] < X1 - 0.3 and box[1] > Y0 + 0.3 and box[3] < Y1 - 0.3 \
                and not hits(box, pads[side]) and not hits(g, placed[side]) \
                and not (label and hits(g, [q for q in bodies[side] if q != own
                                            and (hidden or q not in self.SILK_HIDDEN)]))
        labels = {t for _, t in self.SILK_LABELS} | {e[1] for e in self.SILK_NEAR} | \
            {self.BOARD_LABEL, self.BOARD_LABEL.replace(" AV board", "\nAV board")} | \
            {t for _, names, *_ in self.SILK_PINS for t in names.values()}
        for item in list(b.GetDrawings()):                  # (again on a re-run: no duplicates)
            if isinstance(item, pcbnew.PCB_TEXT) and item.GetText() in labels:
                b.Remove(item)
                self._removed.append(item)  # (kept referenced: freed, they break pcbnew's later calls)
        for ref, names, *side in self.SILK_PINS:
            fp = b.FindFootprintByReference(ref)
            for t, box in self.pin_labels(b, fp, names, *side):
                if not clear(box, own=courtyard(fp, 0)):
                    print("silkscreen: %s's pin label %s is not clear" % (ref, t.GetText()))
                placed[pcbnew.F_SilkS].append(box)
                b.Add(t)

        def text(s_, size, spots, just=pcbnew.GR_TEXT_H_ALIGN_CENTER, must=True, reach=6.0, shrink=True,
                 gaps=(0.3, 0.0)):
            """A label at the first of spots [(x, y, angle)] that is clear (0.3 mm from other texts
            and bodies), else at the nearest clear place within reach of the first or the last; the
            same at 1 mm if it is larger (shrink: JLCPCB's smallest legible height); then both
            again with no gap kept (gaps); if there is none, at the last spot, reported (must), or
            not at all (False returned)."""
            t = pcbnew.PCB_TEXT(b)
            t.SetText(s_)
            t.SetLayer(pcbnew.F_SilkS)
            t.SetHorizJustify(just)
            n = int(reach / 0.5)
            near = sorted(((i * 0.5, j * 0.5) for i in range(-n, n + 1) for j in range(-n, n + 1)), key=lambda d: math.hypot(*d))

            def fit(size_, gap):
                t.SetTextSize(VECTOR2I(FromMM(size_), FromMM(size_)))
                t.SetTextThickness(FromMM(self.stroke(size_)))
                for x_, y_, a_ in spots + [(s[0] + dx, s[1] + dy, s[2]) for s in (spots[0], spots[-1]) for dx, dy in near[1:]]:
                    t.SetPosition(VECTOR2I(FromMM(x_), FromMM(y_)))
                    t.SetTextAngleDegrees(a_)
                    r = t.GetBoundingBox()
                    if clear((ToMM(r.GetLeft()), ToMM(r.GetTop()), ToMM(r.GetRight()), ToMM(r.GetBottom())), gap=gap):
                        return True
                return False
            sizes = [size] + ([self.SILK_TEXT] if shrink and size > self.SILK_TEXT else [])
            if not any(fit(s_, g_) for g_ in gaps for s_ in sizes):
                if not must:
                    return False
                t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size)))
                t.SetTextThickness(FromMM(self.stroke(size)))
                t.SetPosition(VECTOR2I(FromMM(spots[-1][0]), FromMM(spots[-1][1])))
                t.SetTextAngleDegrees(spots[-1][2])
                print("silkscreen: no clear place for %s" % s_)
            r = t.GetBoundingBox()
            placed[pcbnew.F_SilkS].append((ToMM(r.GetLeft()), ToMM(r.GetTop()), ToMM(r.GetRight()), ToMM(r.GetBottom())))
            b.Add(t)
            return True
        # the board's name, on two lines where one does not fit
        tx, ty, ta = (tuple(self.TITLE_AT) + (0,))[:3] if self.TITLE_AT else ((X0 + X1) / 2 - 5, Y1 - 1.6, 0)
        if not text(self.BOARD_LABEL, 1.2, [(tx, ty, ta)], must=False, shrink=False, gaps=(0.3,)):
            text(self.BOARD_LABEL.replace(" AV board", "\nAV board"), 1.2, [(tx, ty, ta)])
        for ref, label in self.SILK_LABELS:
            # inboard of the jack at its board edge, on its middle (along the edge at most a little
            # either side, short of the next jack's), else there, reported
            l_, t_, r_, b_ = courtyard(b.FindFootprintByReference(ref), 0)
            edge = min((l_ - X0, "L"), (X1 - r_, "R"), (t_ - Y0, "T"), (Y1 - b_, "B"))[1]
            cx, cy = (l_ + r_) / 2, (t_ + b_) / 2
            out = {"L": (r_ + 0.8, cy, 1, 0), "R": (l_ - 0.8, cy, -1, 0), "T": (cx, b_ + 1.0, 0, 1),
                   "B": (cx, t_ - 1.0, 0, -1)}[edge]
            spots = [(out[0] + out[2] * k + out[3] * a, out[1] + out[3] * k + out[2] * a, 0)
                     for k in (0, 0.8, 1.6) for a in (0, 0.8, -0.8, 1.6, -1.6, 2.4, -2.4, 3.2, -3.2)]
            text(label, 1.4, spots + spots[:1], {"L": pcbnew.GR_TEXT_H_ALIGN_LEFT, "R": pcbnew.GR_TEXT_H_ALIGN_RIGHT}.get(
                edge, pcbnew.GR_TEXT_H_ALIGN_CENTER), reach=2.5)
        for ref, label, *turn in self.SILK_NEAR:            # above the part, else below it
            bb = b.FindFootprintByReference(ref).GetBoundingBox(False, False)
            l_, t_, b_ = ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetBottom())
            if turn:                                        # (turned: right of the part, else left,
                r_, mid = ToMM(bb.GetRight()), (t_ + b_) / 2    # along its middle)
                text(label, 1.2, [(x, mid + dy, turn[0]) for x in (r_ + 1.2, r_ + 2.0, l_ - 1.2, l_ - 2.0)
                                  for dy in (0, 1.0, -1.0, 2.0, -2.0)])
                continue
            text(label, 1.2, [(l_ + 3.5 + dx, t_ - 1.2 - dy, 0) for dy in (0, 0.8, 1.6, 2.4) for dx in (0, 1.5, -1.5)]
                 + [(l_ + 3.5, b_ + 1.0 + dy, 0) for dy in (0, 0.8)])
        for fp in b.GetFootprints():
            prefix = "".join(ch for ch in fp.GetReference() if ch.isalpha())
            ref = fp.Reference()
            # the value and the other fields (the LCSC number) are for the BOM, not the silkscreen
            for fld in fp.GetFields():
                if not fld.IsReference() and fld.GetLayer() in silk:
                    fld.SetVisible(False)
            # (a header with labelled pins: its labels and name say what it is)
            if prefix not in self.SILK_KEEP or fp.GetReference() in {r for r, *_ in self.SILK_PINS}:
                ref.SetVisible(False)
                continue
            # the designator where it is clear of copper, of the texts placed so far and of the other
            # parts' bodies (under one it is hidden once that part is fitted): above, below, left or
            # right of the part, its middle first, then along that side, then a little further out;
            # last on its own body; hidden if none is
            side = ref.GetLayer()
            ref.SetTextSize(VECTOR2I(FromMM(self.SILK_TEXT), FromMM(self.SILK_TEXT)))
            ref.SetTextThickness(FromMM(self.stroke(self.SILK_TEXT)))
            l_, t_, r_, b_ = courtyard(fp, 0.2)
            spots = []
            for d in (0.7, 1.2):
                for f in (0.5, 0.25, 0.75, 0.0, 1.0):
                    x, y = l_ + f * (r_ - l_), t_ + f * (b_ - t_)
                    spots += [(x, t_ - d, 0), (x, b_ + d, 0), (l_ - d, y, 90), (r_ + d, y, 90)]
            for x, y, ang in spots + [((l_ + r_) / 2, (t_ + b_) / 2, 0)]:
                ref.SetTextAngleDegrees(ang)
                ref.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
                r = ref.GetBoundingBox()
                box = (ToMM(r.GetLeft()), ToMM(r.GetTop()), ToMM(r.GetRight()), ToMM(r.GetBottom()))
                if clear(box, side, own=courtyard(fp, 0), hidden=False):
                    ref.SetVisible(True)
                    placed[side].append(box)
                    break
            else:
                ref.SetVisible(False)
        self.silk_tidy(b)

    def silk_tidy(self, b):
        """The parts' own silkscreen as JLCPCB prints it (SILK_W, SILK_PAD): lines widened to
        0.15 mm; marks too small to print taken out (EasyEDA's pin 1 dots, 0.12 mm across); each
        line cut back where it would come within 0.15 mm of a pad, run past the board's edge (0.3 mm
        inside it, as the texts), under a text, or onto another part's silkscreen (the bigger parts
        first: a small part's outline gives way). A circle, arc or polygon that would: moved up to
        0.5 mm clear if it is a mark (pin 1's, 1 mm across at most), else taken out. Once the texts
        are placed (silkscreen()); a second run changes nothing."""
        silk = (pcbnew.F_SilkS, pcbnew.B_SilkS)

        def box(r):
            return (ToMM(r.GetLeft()), ToMM(r.GetTop()), ToMM(r.GetRight()), ToMM(r.GetBottom()))

        def grow(q, g):
            return (q[0] - g, q[1] - g, q[2] + g, q[3] + g)

        def hits(q, walls):
            return any(q[2] > w[0] and q[0] < w[2] and q[3] > w[1] and q[1] < w[3] for w in walls)
        keep = (self.X0 + 0.3, self.Y0 + 0.3, self.X1 - 0.3, self.Y1 - 0.3)

        def onboard(q):
            return q[0] >= keep[0] and q[1] >= keep[1] and q[2] <= keep[2] and q[3] <= keep[3]
        pads = {s: [] for s in silk}
        texts = {s: [] for s in silk}
        for fp in b.GetFootprints():
            for pad in fp.Pads():
                th = pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
                for s in (silk if th else ((pcbnew.B_SilkS,) if fp.IsFlipped() else (pcbnew.F_SilkS,))):
                    pads[s].append(grow(box(pad.GetBoundingBox()), self.SILK_PAD))
            ref = fp.Reference()
            if ref.IsVisible() and ref.GetLayer() in silk:
                texts[ref.GetLayer()].append(grow(box(ref.GetBoundingBox()), 0.1))
        for d in b.GetDrawings():
            if isinstance(d, pcbnew.PCB_TEXT) and d.GetLayer() in silk:
                texts[d.GetLayer()].append(grow(box(d.GetBoundingBox()), 0.1))
        kept = {s: [] for s in silk}
        n_cut = n_gone = n_moved = 0
        rings = [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a)))
                 for r in (0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5) for a in range(0, 360, 30)]

        def area(fp):
            c = courtyard(fp, 0)
            return (c[2] - c[0]) * (c[3] - c[1])
        for fp in sorted(b.GetFootprints(), key=lambda f: (-area(f), f.GetReference())):
            mine = {s: [] for s in silk}
            for g in list(fp.GraphicalItems()):
                s = g.GetLayer()
                if s not in silk or not isinstance(g, pcbnew.PCB_SHAPE):
                    continue
                walls = pads[s] + texts[s] + kept[s]
                if g.GetShape() == pcbnew.SHAPE_T_SEGMENT:
                    w = max(ToMM(g.GetWidth()), self.SILK_W)
                    a, z = g.GetStart(), g.GetEnd()
                    a, z = (ToMM(a.x), ToMM(a.y)), (ToMM(z.x), ToMM(z.y))
                    span = grow((min(a[0], z[0]), min(a[1], z[1]), max(a[0], z[0]), max(a[1], z[1])), w)
                    pieces = clip_line(a, z, w, [q for q in walls if hits(q, [span])], keep)
                    if not pieces:
                        fp.Remove(g)
                        self._removed.append(g)
                        n_gone += 1
                        continue
                    if ToMM(g.GetWidth()) < w:
                        g.SetWidth(FromMM(w))
                    if pieces == [(a, z)]:          # (as it is: not set again, which would round it)
                        mine[s].append(grow(span, 0.1 - w / 2))
                        continue
                    n_cut += 1
                    for k, (p, q) in enumerate(pieces):
                        if k:
                            g = pcbnew.PCB_SHAPE(fp)
                            g.SetShape(pcbnew.SHAPE_T_SEGMENT)
                            g.SetLayer(s)
                            g.SetWidth(FromMM(w))
                            fp.Add(g)
                        g.SetStart(VECTOR2I(FromMM(p[0]), FromMM(p[1])))
                        g.SetEnd(VECTOR2I(FromMM(q[0]), FromMM(q[1])))
                        mine[s].append(grow((min(p[0], q[0]), min(p[1], q[1]), max(p[0], q[0]), max(p[1], q[1])), w / 2 + 0.1))
                    continue
                filled = g.GetFillMode() != pcbnew.FILL_T_NO_FILL     # (KiCad 10 has no IsFilled)
                if g.GetShape() == pcbnew.SHAPE_T_CIRCLE:
                    r, w = ToMM(g.GetRadius()), ToMM(g.GetWidth())
                    if 2 * (r + w / 2) < 0.2:
                        fp.Remove(g)                # (too small to print)
                        self._removed.append(g)
                        n_gone += 1
                        continue
                if not filled and ToMM(g.GetWidth()) < self.SILK_W:
                    g.SetWidth(FromMM(self.SILK_W))
                q = box(g.GetBoundingBox())
                if not hits(q, walls) and onboard(q):
                    mine[s].append(grow(q, 0.1))
                    continue
                if max(q[2] - q[0], q[3] - q[1]) <= 1.0:
                    for dx, dy in rings:
                        m = (q[0] + dx, q[1] + dy, q[2] + dx, q[3] + dy)
                        if not hits(m, walls) and onboard(m):
                            g.Move(VECTOR2I(FromMM(dx), FromMM(dy)))
                            mine[s].append(grow(m, 0.1))
                            n_moved += 1
                            break
                    else:
                        fp.Remove(g)
                        self._removed.append(g)
                        n_gone += 1
                    continue
                fp.Remove(g)
                self._removed.append(g)
                n_gone += 1
            for s in silk:
                kept[s] += mine[s]
        print("silkscreen: parts' lines cut back %d, marks moved %d, taken out %d" % (n_cut, n_moved, n_gone))

    # --- rules, fanout, planes ----------------------------------------------

    def rules(self, b):
        # The ground layers are power layers, so Freerouting never routes on them; the rail planes'
        # layer is mixed: signals may run there outside the planes
        b.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
        if self.LAYERS == 6:
            b.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_SIGNAL)
            b.SetLayerType(pcbnew.In4_Cu, pcbnew.LT_POWER)
        b.SetLayerType(self.PLANE_LAYER, pcbnew.LT_POWER if self.INNER_GND else pcbnew.LT_MIXED)
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
        for entry in (("POWER", 0.25, 0.15, self.POWER_NETS), ("TMDS", self.TMDS_W, 0.15, self.TMDS_NETS),
                      ("CLOCK", self.TRACK, 0.19, self.CLOCK_NETS)) + tuple(self.CLASSES):
            # (a revision's class may give its pairs' width and gap: (name, width, clearance, nets, (w, gap)))
            name, width, clear, nets = entry[:4]
            c = pcbnew.NETCLASS(name)
            c.SetTrackWidth(FromMM(width))
            c.SetClearance(FromMM(clear))
            c.SetViaDiameter(FromMM(self.VIA_D))
            c.SetViaDrill(FromMM(self.VIA_DRILL))
            if name == "TMDS":
                # 100 R differential, edge-coupled on the outer layers over In1 (0.2 mm at the 0.15 mm
                # gap the routers keep: about 103 R over 7628 prepreg, IPC-2141); check in JLCPCB's
                # impedance calculator before ordering
                c.SetDiffPairWidth(FromMM(self.TMDS_PAIR[0]))
                c.SetDiffPairGap(FromMM(self.TMDS_PAIR[1]))
            elif len(entry) > 4:
                c.SetDiffPairWidth(FromMM(entry[4][0]))
                c.SetDiffPairGap(FromMM(entry[4][1]))
            ns.SetNetclass(name, c)
            for n in sorted(nets):              # (sorted: the project file the same on every run)
                ns.SetNetclassPatternAssignment(n, name)
        ns.RecomputeEffectiveNetclasses()
        ds.m_MinClearance = FromMM(self.MIN_CLEAR or self.CLEAR)
        ds.m_TrackMinWidth = FromMM(0.1)
        ds.m_ViasMinSize = FromMM(self.MIN_VIA[0])
        ds.m_MinThroughDrill = FromMM(self.MIN_VIA[1])
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

    def via(self, b, x, y, net, d=None, drill=None):
        v = pcbnew.PCB_VIA(b)
        v.SetLocked(True)
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
        v.SetWidth(FromMM(d or self.VIA_D))
        v.SetDrill(FromMM(drill or self.VIA_DRILL))
        v.SetNet(net)
        b.Add(v)

    def fanout_planes(self, b, refs=None):
        """A via next to every surface pad on a plane net (ground; a rail where its plane reaches):
        the router then only routes signals. Each via goes on the first spot, walking out from the
        pad, that clears every other pad, track, via and edge; where the standard via finds none,
        the smallest the rules allow (MIN_VIA) on a 0.2 mm track (a ground pad mid-row in a 0.5 mm
        pitch part, its neighbours' lines either side). refs: only these parts' pads (a part moved
        on a routed board: move_part)."""
        VIA_D = self.VIA_D
        obst = []                       # (x0, y0, x1, y1, net, is_hole, is_smd_pad) boxes
        for fp in b.GetFootprints():
            for pad in fp.Pads():
                r = pad.GetBoundingBox()
                smd = pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
                obst.append((ToMM(r.GetLeft()), ToMM(r.GetTop()), ToMM(r.GetRight()), ToMM(r.GetBottom()),
                             pad.GetNetname(), not smd, smd))
        for t in b.GetTracks():
            r = t.GetBoundingBox()
            obst.append((ToMM(r.GetLeft()), ToMM(r.GetTop()), ToMM(r.GetRight()), ToMM(r.GetBottom()),
                         t.GetNetname(), t.GetClass() == "PCB_VIA", False))
        gap = 0.2
        # (a net in a class with a wider clearance keeps the vias that much further off)
        extra = {}
        for c_ in self.CLASSES:
            for n_ in c_[3]:
                extra[n_] = max(extra.get(n_, 0.0), c_[2] - gap)

        def clear(x, y, net, skip, rv, hole):
            """Is a circle of radius rv at (x, y) clear of everything but its own net (and, for a
            hole, of other holes and of its own net's surface pads too: a via in a pad, which this
            board's vias are not filled for, wicks the pad's solder away)?"""
            if x - rv < self.X0 + 0.5 or x + rv > self.X1 - 0.5 or y - rv < self.Y0 + 0.5 or y + rv > self.Y1 - 0.5:
                return False
            wx0, wy0, wx1, wy1 = self.WIN
            if x + rv > wx0 - 0.3 and x - rv < wx1 + 0.3 and y + rv > wy0 - 0.3 and y - rv < wy1 + 0.3:
                return False
            for k, (x0, y0, x1, y1, n, ishole, smd) in enumerate(obst):
                if k == skip:
                    continue
                # (the circle's distance to the box: a box test would see a via a gap from a pad's
                # side clash with its row neighbour's corner)
                if math.hypot(max(x0 - x, 0.0, x - x1), max(y0 - y, 0.0, y - y1)) < rv + extra.get(n, 0.0):
                    if n == net and n and not (hole and (ishole or smd)):
                        continue
                    return False
            return True

        def path_clear(px, py, x, y, net, skip, vd, tw):
            for t in [i / 20 for i in range(1, 20)]:
                if not clear(px + (x - px) * t, py + (y - py) * t, net, skip, tw / 2 + gap, False):
                    return False
            return clear(x, y, net, skip, vd / 2 + gap, True)

        def at(q):
            return ToMM(q.GetPosition().x), ToMM(q.GetPosition().y)

        def self_index(px, py):
            k = [i for i, o in enumerate(obst) if abs((o[0] + o[2]) / 2 - px) < 1e-3 and abs((o[1] + o[3]) / 2 - py) < 1e-3]
            return k[0] if k else -1

        n = 0
        skip_refs = self.fanout_skip()
        # An ESD array first: its two ground pads (facing each other across the package) joined
        # through it, one via straight out of the pad farther from its connector [TI-ESD Fig. 7-11:
        # the ground runs straight through, between the lines]. The lines come in from the
        # connector's side, where a via sits in their way at the pads' 0.5 mm pitch (rev C-A's VGA
        # array left one of its lines no way in). Where that spot is taken, the pads are left to the
        # search below
        conn = {}
        for fp in b.GetFootprints():
            if fp.GetReference().startswith("J"):
                for q in fp.Pads():
                    conn.setdefault(q.GetNetname(), []).append(at(q))
        for p in self.board.PARTS:
            if refs is not None and p.ref not in refs:
                continue
            fp = b.FindFootprintByReference(p.ref)
            g = [q for q in fp.Pads() if q.GetNetname() == "GND"] if self.esd(p) and p.ref not in skip_refs else []
            if len(g) != 2 or any("%s.%s" % (p.ref, q.GetNumber()) in skip_refs for q in g):
                continue
            pins = [xy for q in fp.Pads() if q.GetNetname() not in ("GND", "") for xy in conn.get(q.GetNetname(), [])]
            if not pins:
                continue
            jx, jy = sum(x for x, _ in pins) / len(pins), sum(y for _, y in pins) / len(pins)
            near, far = sorted(g, key=lambda q: math.hypot(at(q)[0] - jx, at(q)[1] - jy))
            (nx, ny), (fx, fy) = at(near), at(far)
            ln = math.hypot(fx - nx, fy - ny)
            ux, uy = (fx - nx) / ln, (fy - ny) / ln
            r = far.GetBoundingBox()
            ext = abs(ux) * ToMM(r.GetWidth()) / 2 + abs(uy) * ToMM(r.GetHeight()) / 2
            k_far = self_index(fx, fy)
            spot = None
            if path_clear(nx, ny, fx, fy, "GND", k_far, 0.0, 0.2):
                for vd, drill, tw in ((VIA_D, self.VIA_DRILL, 0.25), self.MIN_VIA + (0.2,)):
                    for d in (0.0, 0.3, 0.6, 1.0):
                        x, y = fx + ux * (ext + vd / 2 + gap + d), fy + uy * (ext + vd / 2 + gap + d)
                        if path_clear(fx, fy, x, y, "GND", k_far, vd, tw):
                            spot = (x, y, vd, drill, tw)
                            break
                    if spot:
                        break
            if not spot:
                continue
            x, y, vd, drill, tw = spot
            self.track(b, (nx, ny), (fx, fy), 0.2, pcbnew.F_Cu, far.GetNet())
            self.track(b, (fx, fy), (x, y), tw, pcbnew.F_Cu, far.GetNet())
            self.via(b, x, y, far.GetNet(), vd, drill)
            obst.append((x - vd / 2, y - vd / 2, x + vd / 2, y + vd / 2, "GND", True, False))
            obst.append((min(fx, x) - tw / 2, min(fy, y) - tw / 2, max(fx, x) + tw / 2, max(fy, y) + tw / 2, "GND", False, False))
            skip_refs = skip_refs | {"%s.%s" % (p.ref, q.GetNumber()) for q in g}
            n += 1
        for fp in b.GetFootprints():
            if fp.GetReference() in skip_refs or (refs is not None and fp.GetReference() not in refs):
                continue
            for pad in fp.Pads():
                net = pad.GetNetname()
                if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or not net or \
                        "%s.%s" % (fp.GetReference(), pad.GetNumber()) in skip_refs:
                    continue
                px, py = ToMM(pad.GetPosition().x), ToMM(pad.GetPosition().y)
                if net != "GND" and not self.on_plane(net, px, py):
                    continue
                onf = pad.IsOnLayer(pcbnew.F_Cu)
                k_self = [k for k, o in enumerate(obst) if abs((o[0] + o[2]) / 2 - px) < 1e-3 and abs((o[1] + o[3]) / 2 - py) < 1e-3]
                r = pad.GetBoundingBox()
                hw, hh = ToMM(r.GetWidth()) / 2, ToMM(r.GetHeight()) / 2
                spot = None
                for vd, drill, tw in ((VIA_D, self.VIA_DRILL, 0.25), self.MIN_VIA + (0.2,)):
                    for d in (0.0, 0.3, 0.6, 1.0, 1.5, 2.0, 2.5):
                        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1),
                                       (1, 0.5), (-1, 0.5), (1, -0.5), (-1, -0.5), (0.5, 1), (-0.5, 1), (0.5, -1), (-0.5, -1)):
                            x = px + dx * (hw + vd / 2 + gap + d)
                            y = py + dy * (hh + vd / 2 + gap + d)
                            # (a rail pad's via must land on its plane too, or it connects nothing)
                            on_plane = net == "GND" or all(self.on_plane(net, x + ex, y + ey)
                                                           for ex in (-0.35, 0.35) for ey in (-0.35, 0.35))
                            if on_plane and path_clear(px, py, x, y, net, k_self[0] if k_self else -1, vd, tw):
                                spot = (x, y)
                                break
                        if spot:
                            break
                    if spot:
                        break
                if not spot:
                    # (a ground pad may still meet an outer pour; one boxed in by other nets' pads
                    # will not, and stays unconnected)
                    print("note: no plane via for %s pad %s (%s)" % (fp.GetReference(), pad.GetNumber(), net))
                    continue
                x, y = spot
                self.track(b, (px, py), (x, y), tw, pcbnew.F_Cu if onf else pcbnew.B_Cu, pad.GetNet())
                self.via(b, x, y, pad.GetNet(), vd, drill)
                obst.append((x - vd / 2, y - vd / 2, x + vd / 2, y + vd / 2, net, True, False))
                obst.append((min(px, x) - tw / 2, min(py, y) - tw / 2, max(px, x) + tw / 2, max(py, y) + tw / 2, net, False, False))
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
        # (KiCad 10 names it zone fills)
        (z.SetDoNotAllowZoneFills if hasattr(z, "SetDoNotAllowZoneFills") else z.SetDoNotAllowCopperPour)(False)
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
        if self.INNER_GND:
            self.zone(b, "GND", self.PLANE_LAYER, self.full())
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

    def prune(self, path, rounds=10):
        """Remove the vias and track ends KiCad's DRC reports as dangling (fanout the router did not
        use, stubs it left) and the copper it laid twice, round after round, refilling the zones
        each time: each round in a process of its own (gen_pcb.py --prune-round), as pcbnew, once
        it has filled zones, hands back the next board it loads without its type. A round that
        crashes or hangs (pcbnew is native code) runs once more: the crashes seen were in pcbnew's
        worker threads (a std::map walked in its thread pool), the hang in its zone filler, neither
        the board's doing, and a round saves the board only at its end. A second failure shows its
        signal and, from faulthandler, where every thread was."""
        def one_round():
            try:
                return subprocess.run([sys.executable, "-X", "faulthandler", os.path.join(self.DIR, "gen_pcb.py"),
                                       "--prune-round"], env=dict(os.environ, PCB=path), capture_output=True,
                                      text=True, timeout=1800)
            except subprocess.TimeoutExpired as e:      # (killed: as a crash, by SIGKILL; its output bytes)
                out = [x.decode(errors="replace") if isinstance(x, bytes) else x or "" for x in (e.stdout, e.stderr)]
                return subprocess.CompletedProcess(e.cmd, -signal.SIGKILL, *out)
        removed, twice = 0, 0
        for _ in range(rounds):
            r = one_round()
            if r.returncode < 0:
                print("prune round killed by %s, once more" % signal.Signals(-r.returncode).name)
                r = one_round()
            if r.returncode:
                how = ("killed by %s" % signal.Signals(-r.returncode).name if r.returncode < 0
                       else "exit %d" % r.returncode)
                out = (r.stdout + r.stderr).strip()
                k = out.find("Fatal Python error")
                raise RuntimeError("prune round on %s failed (%s):\n%s" % (path, how, out[k:] if k >= 0 else out[-3000:]))
            for line in r.stdout.splitlines():
                if line.startswith("copper laid twice kept"):
                    print(line)
            n, d = map(int, re.search(r"pruned (\d+) \((\d+) laid twice\)", r.stdout).groups())
            removed += n
            twice += d
            if not n:
                break
        print("dangling vias and stubs removed: %d; segments laid twice over: %d" % (removed - twice, twice))

    def prune_round(self, path):
        """One round of prune(): the dangling items DRC lists taken out; once none are left, the
        copper laid twice that removable() lets go, the copies lying on another track of their net
        (covered()) first, then the ones beside one (beside()); the zones filled again. What is
        to go is checked on a copy of the file first, so nothing taken out is ever put back."""
        rpt = drc_report(path, "--severity-all")
        dead = {it["uuid"] for v in rpt["violations"] if v["type"] in ("via_dangling", "track_dangling")
                for it in v["items"]}
        b = pcbnew.LoadBoard(path)
        gone = [t for t in list(b.GetTracks()) if t.m_Uuid.AsString() in dead]
        twice = []
        if not gone:
            twice = removable(path, rpt, covered(b), False) or removable(path, rpt, beside(b), True)
        for t in gone + twice:
            b.Remove(t)
        if gone or twice:
            b.BuildConnectivity()
            pcbnew.ZONE_FILLER(b).Fill(b.Zones())
            pcbnew.SaveBoard(path, b)
        print("pruned %d (%d laid twice)" % (len(gone) + len(twice), len(twice)))

    @staticmethod
    def freerouting(dsn, ses):
        """Route a DSN with Freerouting (1.x under a private Xvfb, 2.x headless); copper the DSN marks
        fixed (KiCad's locked tracks and vias) stays as it is."""
        log = open(os.path.splitext(ses)[0] + "-route.log", "w")
        if FREEROUTING_VERSION.startswith("1."):
            # Xvfb takes the first free display and names it on the pipe once it takes connections:
            # trials side by side never share one, and Java never starts before it
            r, w = os.pipe()
            xvfb = subprocess.Popen([XVFB, "-displayfd", str(w), "-screen", "0", "1280x1024x24"], pass_fds=(w,),
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.close(w)
            with os.fdopen(r) as f:
                n = f.readline().strip()
            try:
                if not n:
                    raise RuntimeError("Xvfb (%s) did not start" % XVFB)
                subprocess.run([JAVA, "-jar", FREEROUTING, "-de", dsn, "-do", ses, "-mp", os.environ.get("PASSES", "100")]
                               + FREEROUTING_ARGS,
                               check=True, stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ, DISPLAY=":" + n))
            finally:
                xvfb.terminate()
        else:
            subprocess.run([JAVA, "-jar", FREEROUTING, "-de", dsn, "-do", ses, "-mp", os.environ.get("PASSES", "100"),
                            "--gui.enabled=false", "--usage_and_diagnostic_data.disable_analytics=true"] + FREEROUTING_ARGS,
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
                    fixed.append(("via", ToMM(t.GetPosition().x), ToMM(t.GetPosition().y), t.GetNetname(),
                                  ToMM(t.GetWidth(pcbnew.F_Cu)), ToMM(t.GetDrillValue())))
                else:
                    fixed.append(("track", ToMM(t.GetStart().x), ToMM(t.GetStart().y), ToMM(t.GetEnd().x),
                                  ToMM(t.GetEnd().y), ToMM(t.GetWidth()), t.GetLayer(), t.GetNetname()))
        dsn = os.path.splitext(self.OUT)[0] + ".dsn"    # (named after the board: trials can run side by side)
        if not pcbnew.ExportSpecctraDSN(b, dsn):
            raise SystemExit("DSN export failed")
        self.dsn_class_rules(dsn)
        ses = ses_for(dsn)
        # start from no copper: some sessions carry the locked copper (DeepPCB), some leave part of it
        # out (Freerouting)
        for t in copper:
            b.Remove(t)
        if not pcbnew.ImportSpecctraSES(b, ses):
            raise SystemExit("SES import failed")
        have = {copper_key(t) for t in b.GetTracks()}
        vias_now = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
        back = 0
        for f in fixed:
            if f[0] == "via":
                same = [t for t in vias_now if abs(ToMM(t.GetPosition().x) - f[1]) < 0.02 and abs(ToMM(t.GetPosition().y) - f[2]) < 0.02]
                if not same:
                    self.via(b, f[1], f[2], b.FindNet(f[3]), f[4], f[5])
                    back += 1
                for t in same:              # (the import gives every via the default size)
                    t.SetWidth(FromMM(f[4]))
                    t.SetDrill(FromMM(f[5]))
            else:
                a, z = (round(f[1], 2), round(f[2], 2)), (round(f[3], 2), round(f[4], 2))
                if ("track", f[6]) + min(a, z) + max(a, z) not in have:
                    self.track(b, (f[1], f[2]), (f[3], f[4]), f[5], f[6], b.FindNet(f[7]))
                    back += 1
        return back

    # spacing between two net classes for the router only: [(class, class, mm)], as Freerouting's
    # class_class rules (the DSN's names: KiCad's Default class is kicad_default). KiCad's DRC keeps
    # the classes' own clearances, which pins at a fine pitch need
    CLASS_CLASS = []

    def dsn_class_rules(self, dsn):
        """Write CLASS_CLASS into an exported DSN's network scope (KiCad's export has no way to)."""
        if not self.CLASS_CLASS:
            return
        s = open(dsn).read()
        i = s.index("(network")
        depth, quoted, j = 0, False, i
        while True:                             # (the scope's own closing paren; quoted names, such
            c = s[j]                            # as KiCad's "unconnected-(U1-Pad9)", hold parens)
            if c == '"':
                quoted = not quoted
            elif not quoted and c == "(":
                depth += 1
            elif not quoted and c == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        add = "".join("    (class_class (classes %s %s) (rule (clearance %d)))\n" % (a, z, round(mm * 1000))
                      for a, z, mm in self.CLASS_CLASS)
        open(dsn, "w").write(s[:j] + add + "  " + s[j:])
        print("router spacing between classes:", ", ".join("%s/%s %.2f mm" % c for c in self.CLASS_CLASS))

    def route(self):
        """Route the saved board (Freerouting, DeepPCB or a given session), finish what another router
        left with Freerouting, then the ground pours on the outer layers, filled. Each step runs in a
        process of its own: after a DSN export, pcbnew can no longer list a board's tracks, nor load
        one."""
        me = os.path.join(self.DIR, "gen_pcb.py")
        if self.PRE_ROUTE:
            subprocess.run([sys.executable, me, "--pre"], check=True)
        b = pcbnew.LoadBoard(self.OUT)

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
        subprocess.run([sys.executable, me, "--post"], check=True)
        subprocess.run([sys.executable, me, "--complete"], check=True)

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
        print("poured:", self.OUT)

    def post_route(self):
        """A revision's own pass on the routed, poured board (route()'s last step)."""

    def mazeroute(self, a, z, partner=None, layers=None, width=None, cost="", lock=False, margin=None):
        """One connection by kit/mazeroute.py (pad REF.PAD to pad), each step in a process of its own;
        cost: MAZE_COST, e.g. "F.Cu:20" to keep the path off F.Cu but at its ends; lock: the copper
        locked (a pre-route the router keeps); margin: MAZE_MARGIN, the window round the two pads.
        Its files in a temporary directory, gone whatever happens."""
        env = dict(os.environ, MAZE_LAYERS=layers or self.ROUTE_LAYERS, MAZE_WIDTH=str(width or self.TRACK),
                   MAZE_COST=cost, MAZE_LOCK="1" if lock else "")
        if margin:
            env["MAZE_MARGIN"] = str(margin)
        mz = os.path.join(KIT, "mazeroute.py")
        with tempfile.TemporaryDirectory() as tmp:
            m, p, before_pcb = (os.path.join(tmp, f) for f in ("m.json", "p.json", "before.kicad_pcb"))
            subprocess.run([sys.executable, mz, "dump", self.OUT, a, z, m] + ([partner] if partner else []),
                           check=True, env=env, stdout=subprocess.DEVNULL)
            r = subprocess.run([os.path.expanduser("~/tools/eda-venv/bin/python"), mz, "route", m, p],
                               env=env, capture_output=True, text=True)
            print((r.stdout + r.stderr).strip().splitlines()[-1])
            if r.returncode:
                raise SystemExit("mazeroute: no path %s - %s" % (a, z))
            # (a guard: a path that adds a short or a clearance error is taken back. One run, on rev B,
            # once laid a track over another net's; the same connection routed again came out clean)
            shutil.copy(self.OUT, before_pcb)
            before = self.copper_errors()
            try:
                # (KiCad's zone filler, run once the path is laid, has hung on one board, a worker
                # of its thread pool spinning: the path is taken back, rather than the run waiting)
                subprocess.run([sys.executable, mz, "apply", self.OUT, p], check=True, env=env,
                               stdout=subprocess.DEVNULL, timeout=600)
            except subprocess.TimeoutExpired:
                shutil.copy(before_pcb, self.OUT)
                raise SystemExit("mazeroute: %s - %s: the zone fill hung (KiCad), taken back" % (a, z))
            after = self.copper_errors()
            if after > before:
                shutil.copy(before_pcb, self.OUT)
                raise SystemExit("mazeroute: %s - %s added %d copper errors: taken back" % (a, z, after - before))

    def copper_errors(self):
        """Shorts and copper clearance errors on the board as saved (kicad-cli DRC)."""
        v = drc_report(self.OUT, "--severity-error")["violations"]
        return sum(1 for x in v if x["type"] in ("shorting_items", "clearance", "tracks_crossing", "hole_clearance"))

    PRE_ROUTE = []      # before the router: [(nets, width, layers, MAZE_COST)], laid by mazeroute, locked

    @staticmethod
    def tree(b, net, root_ref=None):
        """A net's pads joined nearest first (Prim's tree), from a pad on root_ref if it has one:
        [(REF.PAD, REF.PAD)]."""
        pads = [("%s.%s" % (fp.GetReference(), p.GetNumber()), ToMM(p.GetPosition().x), ToMM(p.GetPosition().y))
                for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname() == net and p.GetNumber()]
        if len(pads) < 2:
            return []
        start = [p for p in pads if p[0].split(".")[0] == root_ref] or pads[:1]
        done, rest, edges = [start[0]], [p for p in pads if p is not start[0]], []
        while rest:
            d, a, z = min((math.hypot(a[1] - z[1], a[2] - z[2]), a, z) for a in done for z in rest)
            edges.append((a[0], z[0]))
            done.append(z)
            rest.remove(z)
        return edges

    def route_nets(self, nets, width, layers, cost, lock, rip=False):
        """Each net's tree by mazeroute.py (a wider window when the first finds no path); with rip,
        the net's unlocked copper taken up first. width, layers, cost: one for all, or {net: value}.
        What finds no path is left to the finishing step."""
        def of(v, n):
            return v.get(n) if isinstance(v, dict) else v
        b = pcbnew.LoadBoard(self.OUT)
        if rip:
            gone = [t for t in b.GetTracks() if t.GetNetname() in nets and not t.IsLocked()]
            for t in gone:
                b.Remove(t)
            pcbnew.SaveBoard(self.OUT, b)
            print("ripped up %s: %d tracks and vias" % (sorted(nets), len(gone)))
        jobs = [(n, e) for n in sorted(nets) for e in self.tree(b, n, "U1")]
        # each net's way out of the chip first, in the order of the pins round it (so that no line
        # fences its neighbour in), then the rest of each tree
        u1 = b.FindFootprintByReference("U1")
        cx, cy = (ToMM(u1.GetPosition().x), ToMM(u1.GetPosition().y)) if u1 else (0, 0)

        def around(job):
            a = job[1][0]
            if not a.startswith("U1."):
                return (1, 0)
            p = [q for q in u1.Pads() if q.GetNumber() == a.split(".")[1]][0]
            return (0, math.atan2(ToMM(p.GetPosition().y) - cy, ToMM(p.GetPosition().x) - cx))
        jobs.sort(key=around)
        del b
        for n, (a, z) in jobs:
            for margin in (4, 8):
                try:
                    self.mazeroute(a, z, None, of(layers, n), of(width, n), of(cost, n), lock, margin)
                    break
                except SystemExit as e:
                    print(e)

    def pre_route(self):
        """All PRE_ROUTE groups in one pass (their pins' ways out first, see route_nets), each net
        with its group's width, layers and cost."""
        groups = {n: g for g in self.PRE_ROUTE for n in g[0]}
        self.route_nets(set(groups), {n: g[1] for n, g in groups.items()}, {n: g[2] for n, g in groups.items()},
                        {n: g[3] for n, g in groups.items()}, True)

    def unconnected(self):
        """DRC's unconnected items on the board as saved (kicad-cli)."""
        return drc_report(self.OUT)["unconnected_items"]

    def maze_try(self, a, z, w, env):
        """mazeroute with these MAZE_* settings: True if it laid a path."""
        os.environ.update(env)
        try:
            self.mazeroute(a, z, None, None, w)
            return True
        except SystemExit as e:
            print(e)
            return False
        finally:
            for k in env:
                os.environ.pop(k, None)

    def finish_unconnected(self, rounds=6, rip=True):
        """Whatever DRC still reports unconnected, by mazeroute.py: for each gap, the pads on its
        two sides (a pad named, or the pads of the copper island a named track belongs to), the
        nearest three pairs tried in turn (the nearest can be walled in where the next is not: rev
        B's TX_PLVDD pin 21, 3.87 mm from pin 26 round the chip's corner, 3.91 mm from its own
        capacitor), each once more over a wider window if the first try finds no path; then
        by rip-up (mazeroute.py MAZE_SOFT: through other signal nets' unlocked copper, which is
        taken up), what it took up joined again at once, and all of it taken back unless fewer
        gaps are left: a gap walled in by other nets' tracks stayed open otherwise (rev B's
        left-side pixel lines, round after round), and rip-up let loose in a crowded corner only
        moved the gaps around, more of them each round."""
        given_up = set()                        # (the gaps whose rip-up was taken back: not again)
        keep = self.OUT + ".before-rip"         # (beside the board: a run stopped mid rip-up is undone
        if rip and os.path.exists(keep):        # at the next start, its nets not left in pieces)
            shutil.copy(keep, self.OUT)
            os.remove(keep)
            print("a rip-up left unfinished taken back")
        for _ in range(rounds):
            gaps = self.unconnected()
            if not gaps:
                return 0
            b = pcbnew.LoadBoard(self.OUT)
            pairs = []
            for g in gaps:
                net = g["items"][0]["description"].split("[")[1].split("]")[0]
                isl = self.islands(b, net)
                sides = []
                for it in g["items"]:
                    x, y = it["pos"]["x"], it["pos"]["y"]
                    hit = [k for k, isl_ in enumerate(isl) if any(math.hypot(x - px, y - py) < 0.05 for px, py in isl_["pts"])]
                    sides.append(isl[hit[0]]["pads"] if hit else [])
                cands = sorted((math.hypot(a[1] - c[1], a[2] - c[2]), a[0], c[0]) for a in sides[0] for c in sides[1])
                if cands:
                    pairs.append((net, [(a, z) for _, a, z in cands[:3]]))
            del b
            for net, tries in pairs:
                w = 0.25 if net in self.POWER_NETS else self.TRACK
                if any(self.maze_try(a, z, w, {"MAZE_MARGIN": "4"}) or self.maze_try(a, z, w, {"MAZE_MARGIN": "8"})
                       for a, z in tries):
                    continue
                a, z = tries[0]
                if not rip or net in self.POWER_NETS | {"GND"} or (a, z) in given_up:
                    continue
                kept = False
                shutil.copy(self.OUT, keep)
                before = len(self.unconnected())
                if self.maze_try(a, z, w, {"MAZE_MARGIN": "8", "MAZE_SOFT": "1",
                                           "MAZE_HARD": ",".join(sorted(self.POWER_NETS | {"GND"}))}):
                    self.finish_unconnected(rounds=2, rip=False)
                    after = len(self.unconnected())
                    kept = after < before
                    if not kept:
                        shutil.copy(keep, self.OUT)
                    print("rip-up for %s - %s %s: %d gaps after it, %d before" % (
                        a, z, "kept" if kept else "taken back", after, before))
                os.remove(keep)
                if not kept:
                    given_up.add((a, z))
                if kept:
                    break                       # (the gaps listed this round have moved: list them again)
        return len(self.unconnected())

    @staticmethod
    def islands(b, net):
        """A net's copper in connected islands: [{"pads": [(REF.PAD, x, y)], "pts": [(x, y)]}], the
        points being every pad centre, track end and via; pieces join where a track end or via lies
        on a pad or on another piece's end (no zones: not for GND)."""
        items = []
        for fp in b.GetFootprints():
            for p in fp.Pads():
                if p.GetNetname() == net:
                    r = p.GetBoundingBox()
                    items.append(("pad", "%s.%s" % (fp.GetReference(), p.GetNumber()),
                                  [(ToMM(p.GetPosition().x), ToMM(p.GetPosition().y))],
                                  (ToMM(r.GetLeft()), ToMM(r.GetTop()), ToMM(r.GetRight()), ToMM(r.GetBottom())),
                                  p.GetLayerSet()))
        for t in b.GetTracks():
            if t.GetNetname() != net:
                continue
            if t.GetClass() == "PCB_VIA":
                items.append(("via", None, [(ToMM(t.GetPosition().x), ToMM(t.GetPosition().y))], None, None))
            else:
                items.append(("track", b.GetLayerName(t.GetLayer()), [(ToMM(t.GetStart().x), ToMM(t.GetStart().y)),
                                                                     (ToMM(t.GetEnd().x), ToMM(t.GetEnd().y))], None, None))
        parent = list(range(len(items)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for i, a in enumerate(items):
            for j in range(i + 1, len(items)):
                c = items[j]
                touch = False
                for k1, k2 in ((a, c), (c, a)):
                    if k1[0] == "pad" and k2[0] != "pad":
                        x0, y0, x1, y1 = k1[3]
                        touch = touch or any(x0 - 0.01 <= x <= x1 + 0.01 and y0 - 0.01 <= y <= y1 + 0.01 for x, y in k2[2])
                if a[0] != "pad" and c[0] != "pad":
                    touch = any(math.hypot(p[0] - q[0], p[1] - q[1]) < 0.01 for p in a[2] for q in c[2]) and \
                        (a[0] == "via" or c[0] == "via" or a[1] == c[1])
                if touch:
                    parent[find(i)] = find(j)
        groups = {}
        for i, it in enumerate(items):
            g = groups.setdefault(find(i), {"pads": [], "pts": []})
            g["pts"] += it[2]
            if it[0] == "pad":
                g["pads"].append((it[1],) + it[2][0])
        return list(groups.values())

    def move_part(self, ref, x, y, angle):
        """A part moved on the routed board (where the placer now puts it, after a change that
        moves only it): the copper ending on its pads taken up, its plane pads given their vias
        again; --complete then joins its connections and clears the stubs left. Other nets' copper
        at the new spot stays where it is: DRC after. A full route for one moved part would give a
        whole new board to check."""
        b = pcbnew.LoadBoard(self.OUT)
        fp = b.FindFootprintByReference(ref)
        pads = [(p.GetNetname(), p.GetBoundingBox()) for p in fp.Pads()]

        def on(pt, net):
            return any(n == net and bb.Contains(pt) for n, bb in pads)
        gone = [t for t in b.GetTracks() if (on(t.GetPosition(), t.GetNetname()) if t.GetClass() == "PCB_VIA" else
                                             on(t.GetStart(), t.GetNetname()) or on(t.GetEnd(), t.GetNetname()))]
        for t in gone:
            b.Remove(t)
            self._removed.append(t)
        fp.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
        fp.SetOrientationDegrees(angle)
        self.fanout_planes(b, {ref})
        pcbnew.SaveBoard(self.OUT, b)
        print("%s moved to (%.3f, %.3f) at %g: %d tracks and vias taken up" % (ref, x, y, angle, len(gone)))

    def cli(self, argv):
        if "--move" in argv:
            k = argv.index("--move")
            self.move_part(argv[k + 1], *(float(v) for v in argv[k + 2:k + 5]))
        elif "--pre" in argv:
            self.pre_route()
        elif "--post" in argv:
            self.post_route()
        elif "--complete" in argv:          # the last connections, then the stubs (mazeroute.py's
            left = self.finish_unconnected()    # apply has filled the zones after each)
            self.prune(self.OUT)
            print("routed: %s, %d connections left" % (self.OUT, left))
        elif "--prune-round" in argv:
            self.prune_round(self.OUT)
        elif "--finish" in argv:            # route()'s steps, each in a process of its own
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
