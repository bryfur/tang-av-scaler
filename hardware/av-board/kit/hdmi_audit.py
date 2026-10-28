#!/usr/bin/env python3
"""A routed board's HDMI lines against the published layout rules, each finding with its rule: the
TMDS pairs (transmitter to receptacle), on rev C-B also the transceivers' lanes into the retimer
and their reference clock.

    python3 kit/hdmi_audit.py rev-cb [BOARD.kicad_pcb]      (default: the revision's board)

The HDMI specification and its compliance tests are for HDMI Adopters only; these are the
vendors' layout rules that quote it:
  DP159  TI SN65DP159 data sheet (SLLSEJ2G) 12.1: the TMDS lines on the top layer, no vias, a
         solid ground plane next to them, lengths matched; 10.2.2: 2-3 inches with the receptacle
  AR7    TI SPRAAR7J, High-Speed Interface Layout Guidelines (HDMI among its signals, Table 1-1):
         2.3 P and N matched; 2.4 over solid ground, no voids; 3.1 pairs 5 W apart, other lines
         30 mil off, clocks and periodic lines 50 mil; 3.2 not near crystals, oscillators, clock
         generators, switchers or mounting holes, >= 1.5 W from plane voids, constant width;
         3.3 break-out within 0.25 in of a package (nearer, pins put other nets beside a pair:
         counted apart below); 3.4 pairs 30 mil apart; 3.9 equal via counts; 3.10 parts on a
         line 0402 or smaller, the plane voided under their pads two layers deep; 3.11 bends
         135 degrees or wider; 3.14 ESD at the connector, 60 % voids under its pads
  SKEW   TI HDMI Design Guide (from the HDMI specification): a source's skew within a pair
         0.15 Tbit, between pairs 0.2 Tchar: at 5.94 Gb/s (HDMI 2.0) 25 ps and 337 ps
  INTEL  Intel AN 837, HDMI board design tips: 100 R +-10 %, at most two vias a line
Impedance is the stack-up's (the README: JLCPCB's calculator), not measured here.
"""
import math
import os
import sys

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
import pcbnew  # noqa: E402
from pcbnew import ToMM  # noqa: E402
from rev import rev_dir  # noqa: E402

MIL = 0.0254
PS_PER_MM = 6.3             # an outer-layer line over 7628 prepreg (effective er about 3.4)
BREAKOUT = 6.35             # mm: 0.25 in round a pad the pair ends on or passes through (AR7 3.3)

d = rev_dir(sys.argv[1])
path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(d, [f for f in os.listdir(d) if f.endswith(".kicad_pcb")][0])
b = pcbnew.LoadBoard(path)
segs = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]
vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
L = lambda t: b.GetLayerName(t.GetLayer())             # noqa: E731
present = {t.GetNetname() for t in segs}


def pt(v):
    return ToMM(v.x), ToMM(v.y)


def seg_dist(p, a, z):
    dx, dy = z[0] - a[0], z[1] - a[1]
    n = dx * dx + dy * dy
    u = 0 if n == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / n))
    return math.hypot(p[0] - a[0] - u * dx, p[1] - a[1] - u * dy)


def samples(t, step=0.1):
    a, z = pt(t.GetStart()), pt(t.GetEnd())
    k = max(1, int(math.hypot(z[0] - a[0], z[1] - a[1]) / step))
    return [(a[0] + (z[0] - a[0]) * i / k, a[1] + (z[1] - a[1]) * i / k) for i in range(k + 1)]


def groups(fmt, chans):
    return [(fmt % c, fmt % c + "_P", fmt % c + "_N") for c in chans if fmt % c + "_P" in present]


TMDS = groups("TMDS_%s", ("D0", "D1", "D2", "CK"))
LANES = groups("SER_%s", ("D0", "D1", "D2", "CK")) + groups("DP_%s", ("D0", "D1", "D2", "CK"))
REFCLK = groups("SER_%s", ("REFCLK",))
FAST = {n for g in TMDS + LANES for n in g[1:]}         # multi-Gb/s lines
HS = FAST | {n for g in REFCLK for n in g[1:]}
# the reference clock's own chain (source resistors, AC capacitors) is not an aggressor to it
OWN = {"PLL_CLK0", "PLL_CLK1", "PLL_CLK0_S", "PLL_CLK1_S"}
cls = {}
for n in present | {v.GetNetname() for v in vias}:
    ni = b.FindNet(n)
    cls[n] = ni.GetNetClassName() if ni else ""
CLOCKISH = {n for n in cls if (cls[n] == "CLOCK" or any(k in n for k in ("XTAL", "LLC", "SCKI", "BCK", "LRCK", "CLK"))
                               or n.startswith("SW_"))} - HS - OWN
QUIET = {"GND", ""} | OWN

findings = []


def flag(rule, text):
    findings.append((rule, text))


# --- the pairs themselves
def pair(name, p, n):
    sp, sn = [t for t in segs if t.GetNetname() == p], [t for t in segs if t.GetNetname() == n]
    vp, vn = [v for v in vias if v.GetNetname() == p], [v for v in vias if v.GetNetname() == n]
    lp, ln_ = sum(ToMM(t.GetLength()) for t in sp), sum(ToMM(t.GetLength()) for t in sn)
    widths = sorted({round(ToMM(t.GetWidth()), 3) for t in sp + sn})
    layers = sorted({L(t) for t in sp + sn})
    worst = 180.0                                       # the sharpest turn where two segments meet
    for grp in (sp, sn):
        ends = [(pt(t.GetStart()), pt(t.GetEnd()), L(t)) for t in grp]
        for i, (a1, z1, l1) in enumerate(ends):
            for a2, z2, l2 in ends[i + 1:]:
                if l1 != l2:
                    continue
                for e1, o1 in ((a1, z1), (z1, a1)):
                    for e2, o2 in ((a2, z2), (z2, a2)):
                        if math.hypot(e1[0] - e2[0], e1[1] - e2[1]) < 0.002:
                            v1, v2 = (o1[0] - e1[0], o1[1] - e1[1]), (o2[0] - e2[0], o2[1] - e2[1])
                            m = math.hypot(*v1) * math.hypot(*v2)
                            if m > 1e-9:
                                worst = min(worst, math.degrees(math.acos(max(-1, min(1, (v1[0] * v2[0] + v1[1] * v2[1]) / m)))))
    skew = abs(lp - ln_)
    print("%-11s P %.2f N %.2f mm, skew %.2f mm (%.0f ps), vias %d/%d, layers %s, widths %s, sharpest turn %.0f deg"
          % (name, lp, ln_, skew, skew * PS_PER_MM, len(vp), len(vn), ",".join(layers), widths, worst))
    if len(vp) != len(vn):
        flag("AR7 3.9", "%s: %d vias on P, %d on N" % (name, len(vp), len(vn)))
    if max(len(vp), len(vn)) > 2:
        flag("INTEL", "%s: more than two vias on a line" % name)
    if name.startswith("TMDS") and (vp or vn or layers != ["F.Cu"]):
        flag("DP159 12.1", "%s: off the top layer or through vias" % name)
    if len(widths) > 1:
        flag("AR7 3.2", "%s: line widths %s" % (name, widths))
    if worst < 135 - 0.5:
        flag("AR7 3.11", "%s: a %.0f-degree turn" % (name, worst))
    if name.startswith("TMDS") and skew * PS_PER_MM > 25:
        flag("SKEW", "%s: %.0f ps within the pair" % (name, skew * PS_PER_MM))
    return max(lp, ln_)


print("== the pairs")
lens = {g[0]: pair(*g) for g in TMDS + LANES + REFCLK}
if TMDS:
    t = [lens[g[0]] for g in TMDS]
    print("TMDS between pairs: %.1f mm (%.0f ps; 337 ps at 5.94 Gb/s), %.1f-%.1f mm long (DP159 10.2.2: 2-3 inches)"
          % (max(t) - min(t), (max(t) - min(t)) * PS_PER_MM, min(t), max(t)))
    if (max(t) - min(t)) * PS_PER_MM > 337:
        flag("SKEW", "TMDS between pairs %.0f ps" % ((max(t) - min(t)) * PS_PER_MM))

# --- other copper near the pairs, along their run and in the packages' break-outs apart
others = []
for t in segs:
    if t.GetNetname() not in QUIET:
        others.append((t.GetNetname(), L(t), pt(t.GetStart()), pt(t.GetEnd()), ToMM(t.GetWidth()) / 2))
for v in vias:
    if v.GetNetname() not in QUIET:
        p = pt(v.GetPosition())
        others.append((v.GetNetname(), "*", p, p, ToMM(v.GetWidth(pcbnew.F_Cu)) / 2))
for fp in b.GetFootprints():
    for q in fp.Pads():
        if q.GetNetname() not in QUIET:
            p = pt(q.GetPosition())
            bb = q.GetBoundingBox()
            lay = "*" if q.GetAttribute() == pcbnew.PAD_ATTRIB_PTH else ("F.Cu" if q.IsOnLayer(pcbnew.F_Cu) else "B.Cu")
            others.append((q.GetNetname(), lay, p, p, min(ToMM(bb.GetWidth()), ToMM(bb.GetHeight())) / 2))
grid = {}
for o in others:
    _, _, oa, oz, ohw = o
    for gx in range(int((min(oa[0], oz[0]) - ohw) // 2), int((max(oa[0], oz[0]) + ohw) // 2) + 1):
        for gy in range(int((min(oa[1], oz[1]) - ohw) // 2), int((max(oa[1], oz[1]) + ohw) // 2) + 1):
            grid.setdefault((gx, gy), []).append(o)


def in_breakout(p, nets):
    return any(math.hypot(p[0] - q[0], p[1] - q[1]) < BREAKOUT for q in OWNPADS[frozenset(nets)])


OWNPADS = {}
for g in TMDS + LANES + REFCLK:
    OWNPADS[frozenset(g[1:])] = [pt(q.GetPosition()) for fp in b.GetFootprints() for q in fp.Pads() if q.GetNetname() in g[1:]]

print("\n== other copper (edge to edge, same layer): along the run | in the break-outs; rules: pairs and lines 30 mil, clocks 50 mil")
for g in TMDS + LANES + REFCLK:
    nets = set(g[1:])
    near = {"run": {}, "bo": {}}
    for t in segs:
        if t.GetNetname() not in nets:
            continue
        hw = ToMM(t.GetWidth()) / 2
        for p in samples(t):
            where = "bo" if in_breakout(p, nets) else "run"
            gx, gy = int(p[0] // 2), int(p[1] // 2)
            seen = set()
            for cx in (gx - 1, gx, gx + 1):
                for cy in (gy - 1, gy, gy + 1):
                    for o in grid.get((cx, cy), ()):
                        if id(o) in seen or o[0] in nets or o[1] not in ("*", L(t)):
                            continue
                        seen.add(id(o))
                        kind = "pair" if o[0] in HS else "clock" if o[0] in CLOCKISH else "line"
                        dist = seg_dist(p, o[2], o[3]) - hw - o[4]
                        if dist < near[where].get(kind, (9, ""))[0]:
                            near[where][kind] = (dist, o[0])
    fmt = lambda m: "; ".join("%s %.2f (%s)" % (k, v[0], v[1]) for k, v in sorted(m.items())) or "-"    # noqa: E731
    print("%-11s %s | %s" % (g[0], fmt(near["run"]), fmt(near["bo"])))
    for kind, lim in (("pair", 30 * MIL), ("line", 30 * MIL), ("clock", 50 * MIL)):
        if kind in near["run"] and near["run"][kind][0] < lim - 0.005:
            flag("AR7 3.1/3.4", "%s: %s %s %.2f mm off along its run (%.2f)" % (g[0], kind, near["run"][kind][1],
                                                                             near["run"][kind][0], lim))

# --- what lies near the lines
print("\n== near the lines (AR7 3.2): crystals, clock generators, switchers (their courtyards); mounting holes (their edges)")
hs_pts = [p for t in segs if t.GetNetname() in FAST | {n for g in REFCLK for n in g[1:]} for p in samples(t, 0.5)]
for fp in b.GetFootprints():
    ref, val = fp.GetReference(), fp.GetValue()
    sw = any(q.GetNetname().startswith("SW_") for q in fp.Pads())
    kind = ("crystal" if ref.startswith("Y") else "mounting hole" if ref.startswith(("H", "SO")) else
            "switcher" if sw else "clock generator" if "MS5351" in val or "Si5351" in val else None)
    if not kind:
        continue
    if kind == "mounting hole":
        holes = [q for q in fp.Pads() if q.GetDrillSize().x > 0] or list(fp.Pads())
        c, r = pt(holes[0].GetPosition()), ToMM(max(holes[0].GetDrillSize().x, holes[0].GetSize().x)) / 2
        dist = min(math.hypot(p[0] - c[0], p[1] - c[1]) for p in hs_pts) - r
    else:
        bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox() if fp.GetCourtyard(pcbnew.F_CrtYd).OutlineCount() else fp.GetBoundingBox(False, False)
        x0, y0, x1, y1 = ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetRight()), ToMM(bb.GetBottom())
        dist = min(math.hypot(max(x0 - p[0], 0, p[0] - x1), max(y0 - p[1], 0, p[1] - y1)) for p in hs_pts)
    print("%-6s %-16s %-15s %5.2f mm" % (ref, val[:16], kind, dist))
    if dist < 2.0:
        flag("AR7 3.2", "%s (%s) %.2f mm from a fast line" % (ref, kind, dist))

# --- the reference plane under the fast lines: its edges and voids, the intended ones (under the
# pads of parts on the lines) apart
print("\n== In1 under the fast lines: its nearest edge or void (>= 1.5 W, AR7 3.2; the voids under pads on the lines apart)")
pad_boxes = []
for fp in b.GetFootprints():
    if fp.GetReference().startswith(("C", "U")) and any(q.GetNetname() in FAST for q in fp.Pads()):
        for q in fp.Pads():
            if q.GetNetname() in FAST:
                bb = q.GetBoundingBox()
                pad_boxes.append((ToMM(bb.GetLeft()) - 0.05, ToMM(bb.GetTop()) - 0.05, ToMM(bb.GetRight()) + 0.05,
                                  ToMM(bb.GetBottom()) + 0.05))
edges = []
for z in b.Zones():
    if z.GetNetname() == "GND" and z.IsOnLayer(pcbnew.In1_Cu) and not z.GetIsRuleArea() and z.HasFilledPolysForLayer(pcbnew.In1_Cu):
        poly = pcbnew.SHAPE_POLY_SET(z.GetFilledPolysList(pcbnew.In1_Cu))
        poly.Unfracture()               # (a fill is kept fractured: holes joined to the outline by slits)
        for i in range(poly.OutlineCount()):
            rings = [poly.Outline(i)] + [poly.Hole(i, j) for j in range(poly.HoleCount(i))]
            for k, ring in enumerate(rings):
                bb = ring.BBox()
                box = (ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetRight()), ToMM(bb.GetBottom()))
                if k and any(box[0] < p[2] and box[2] > p[0] and box[1] < p[3] and box[3] > p[1] for p in pad_boxes):
                    continue                            # (an intended void, under a pad on a line: the fill
                    # stands off the rule area a little, and neighbouring pads' voids merge)
                n = ring.PointCount()
                for j in range(n):
                    a, c = ring.CPoint(j), ring.CPoint((j + 1) % n)
                    edges.append(((ToMM(a.x), ToMM(a.y)), (ToMM(c.x), ToMM(c.y))))
for g in TMDS + LANES:
    best = (9e9, None)
    for t in segs:
        if t.GetNetname() not in g[1:]:
            continue
        hw = ToMM(t.GetWidth()) / 2
        for p in samples(t):
            for e0, e1 in edges:
                if min(e0[0], e1[0]) - 2 > p[0] or max(e0[0], e1[0]) + 2 < p[0] or min(e0[1], e1[1]) - 2 > p[1] or max(e0[1], e1[1]) + 2 < p[1]:
                    continue
                dist = seg_dist(p, e0, e1) - hw
                if dist < best[0]:
                    best = (dist, p, hw)
    if best[1]:
        print("%-11s %.2f mm at (%.1f, %.1f)" % (g[0], best[0], best[1][0], best[1][1]))
        if best[0] < 1.5 * 2 * best[2]:
            flag("AR7 2.4/3.2", "%s within 1.5 W of an In1 edge or void at (%.1f, %.1f)" % (g[0], best[1][0], best[1][1]))

# --- parts on the fast lines: size, the planes voided under their pads
print("\n== parts on the fast lines (AR7 3.10: 0402 or smaller, the plane voided under their pads two layers deep; 3.14: 60 % under an ESD array's)")
planes = {}
for lay in (pcbnew.In1_Cu, pcbnew.In2_Cu):
    planes[lay] = [z.GetFilledPolysList(lay) for z in b.Zones() if z.GetNetname() == "GND" and z.IsOnLayer(lay)
                   and not z.GetIsRuleArea() and z.HasFilledPolysForLayer(lay)]


def copper_under(q, lay):
    bb = q.GetBoundingBox()
    n = hit = 0
    for i in range(9):
        for j in range(9):
            p = pcbnew.VECTOR2I(int(bb.GetLeft() + (i + 0.5) * bb.GetWidth() / 9), int(bb.GetTop() + (j + 0.5) * bb.GetHeight() / 9))
            if q.HitTest(p):
                n += 1
                hit += any(poly.Contains(p) for poly in planes[lay])
    return hit / n if n else 0


for fp in b.GetFootprints():
    sig = [q for q in fp.Pads() if q.GetNetname() in FAST]
    ref = fp.GetReference()
    if not sig or not ref.startswith(("C", "U", "R")) or len({q.GetNetname() for q in fp.Pads()}) > 12:
        continue                                        # (the chips themselves, the connectors: not parts on a line)
    voided = [1 - max(copper_under(q, lay) for lay in (pcbnew.In1_Cu, pcbnew.In2_Cu)) for q in sig]
    size = fp.GetFPIDAsString().split(":")[-1]
    need = 0.6 if ref.startswith("U") else 1.0
    print("%-5s %-30s plane voided under its line pads %.0f-%.0f %% (%.0f %% asked)" % (ref, size[:30], 100 * min(voided),
                                                                                     100 * max(voided), 100 * need))
    if min(voided) < need - 0.05:
        flag("AR7 3.10/3.14", "%s: the plane under its line pads voided only %.0f %%" % (ref, 100 * min(voided)))
    if ref.startswith(("C", "R")) and not any(k in size for k in ("0402", "0201", "01005")):
        flag("AR7 3.10", "%s: %s, larger than 0402" % (ref, size))

# --- the outer ground pour beside the TMDS run (the pairs reckoned as microstrips)
print("\n== F.Cu ground pour beside the TMDS lines along their run")
pour = [z.GetFilledPolysList(pcbnew.F_Cu) for z in b.Zones() if z.GetNetname() == "GND" and z.IsOnLayer(pcbnew.F_Cu)
        and not z.GetIsRuleArea() and z.HasFilledPolysForLayer(pcbnew.F_Cu)]
for g in TMDS:
    best = None
    for t in segs:
        if t.GetNetname() not in g[1:]:
            continue
        hw = ToMM(t.GetWidth()) / 2
        a, z = pt(t.GetStart()), pt(t.GetEnd())
        ux, uy = (z[0] - a[0], z[1] - a[1])
        m = math.hypot(ux, uy)
        if m < 1e-6:
            continue
        nx, ny = -uy / m, ux / m                        # (across the line)
        for p in samples(t, 0.5):
            if in_breakout(p, set(g[1:])):
                continue
            for r in (0.1, 0.2, 0.3, 0.5, 0.76, 1.0):
                if any(poly.Contains(pcbnew.VECTOR2I(pcbnew.FromMM(p[0] + s * nx * (r + hw)), pcbnew.FromMM(p[1] + s * ny * (r + hw))))
                       for poly in pour for s in (-1, 1)):
                    best = r if best is None else min(best, r)
                    break
    print("%-11s %s" % (g[0], "nearest pour %.2f mm or less" % best if best is not None else "no pour within 1 mm"))

print("\n== findings")
for r, t in findings or [("-", "none")]:
    print("  [%s] %s" % (r, t))
