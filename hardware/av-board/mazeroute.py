#!/usr/bin/env python3
"""A small grid router (A*) for the last connections an autorouter leaves: one net between two
pads, round everything already on the board, changing layer through new vias where a via fits.

    python3 mazeroute.py dump BOARD REF.PAD REF.PAD out.json [PARTNER_NET]   # KiCad's python: the obstacles
                                    # (PARTNER_NET: route alongside that net's copper, a pair's other half)
    ~/tools/eda-venv/bin/python mazeroute.py route in.json out.json   # numpy: the path
    python3 mazeroute.py apply BOARD out.json                  # KiCad's python: tracks + vias in

Tracks go on F.Cu, In2.Cu and B.Cu (In3 holds the rail planes), 0.127 mm wide, CLEAR from every
other net's copper; a via (0.5/0.3 mm) needs CLEAR round it on those layers and HOLE between
its drill and every other drill. Pads are taken as their bounding boxes (on the safe side).
Check the result with kicad-cli pcb drc.
"""
import heapq
import json
import math
import os
import sys

# MAZE_LAYERS / MAZE_WIDTH: the layers to route on and the track width (a TMDS line: F.Cu,B.Cu at
# its class's 0.2 mm)
LAYERS = os.environ.get("MAZE_LAYERS", "F.Cu,In2.Cu,B.Cu").split(",")
TRACK = float(os.environ.get("MAZE_WIDTH", "0.127"))
CLEAR, VIA_D, VIA_DRILL, HOLE = 0.15, 0.5, 0.3, 0.25
RES = 0.025                                 # grid, mm
MARGIN = 4.0                                # round the two pads, mm
VIA_COST = 60                               # a via costs as much as 1.5 mm of track
FOLLOW_OFF = 3.0                            # off a pair partner's side, a step costs this much more


def dump(board, a, z, out, partner=None):
    import pcbnew
    from pcbnew import ToMM
    b = pcbnew.LoadBoard(board)

    def find(spec):
        ref, num = spec.split(".")
        fp = b.FindFootprintByReference(ref)
        return fp, [p for p in fp.Pads() if p.GetNumber() == num][0]
    ends = []
    for spec in (a, z):
        fp, p = find(spec)
        r = p.GetBoundingBox()
        ends.append({"layer": "B.Cu" if fp.IsFlipped() else "F.Cu",
                     "box": [ToMM(r.GetLeft()), ToMM(r.GetTop()), ToMM(r.GetRight()), ToMM(r.GetBottom())],
                     "c": [ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)]})
    net = find(a)[1].GetNetname()
    x0 = min(e["box"][0] for e in ends) - MARGIN
    y0 = min(e["box"][1] for e in ends) - MARGIN
    x1 = max(e["box"][2] for e in ends) + MARGIN
    y1 = max(e["box"][3] for e in ends) + MARGIN

    def near(bx):
        return bx[2] > x0 - 1 and bx[0] < x1 + 1 and bx[3] > y0 - 1 and bx[1] < y1 + 1
    obst, follow = [], []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == net and p.GetNetname():
                continue
            r = p.GetBoundingBox()
            bx = [ToMM(r.GetLeft()), ToMM(r.GetTop()), ToMM(r.GetRight()), ToMM(r.GetBottom())]
            if not near(bx):
                continue
            tht = p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
            layers = LAYERS if tht else ["B.Cu" if fp.IsFlipped() else "F.Cu"]
            hole = ToMM(p.GetDrillSize().x) / 2 if tht else 0
            obst.append({"kind": "box", "box": bx, "layers": layers, "hole": hole,
                         "c": [(bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2]})
    for t in b.GetTracks():
        if t.GetNetname() == net:
            continue
        if partner and t.GetNetname() == partner and t.GetClass() != "PCB_VIA":
            follow.append({"layer": b.GetLayerName(t.GetLayer()),
                           "a": [ToMM(t.GetStart().x), ToMM(t.GetStart().y)], "b": [ToMM(t.GetEnd().x), ToMM(t.GetEnd().y)]})
        if t.GetClass() == "PCB_VIA":
            c = [ToMM(t.GetPosition().x), ToMM(t.GetPosition().y)]
            if not near([c[0], c[1], c[0], c[1]]):
                continue
            obst.append({"kind": "via", "c": c, "r": ToMM(t.GetWidth()) / 2, "hole": ToMM(t.GetDrillValue()) / 2,
                         "layers": LAYERS})
        else:
            s = [ToMM(t.GetStart().x), ToMM(t.GetStart().y)]
            e = [ToMM(t.GetEnd().x), ToMM(t.GetEnd().y)]
            if not near([min(s[0], e[0]), min(s[1], e[1]), max(s[0], e[0]), max(s[1], e[1])]):
                continue
            layer = b.GetLayerName(t.GetLayer())
            # (a track on a layer not routed here still stands in a new via's way)
            obst.append({"kind": "seg", "a": s, "b": e, "w": ToMM(t.GetWidth()) / 2,
                         "layers": [layer] if layer in LAYERS else [], "via": True})
    json.dump({"net": net, "region": [x0, y0, x1, y1], "ends": ends, "obst": obst, "follow": follow}, open(out, "w"))
    print("%s: %d obstacles round %s - %s" % (net, len(obst), a, z))


def route(inp, out):
    import numpy as np
    d = json.load(open(inp))
    x0, y0, x1, y1 = d["region"]
    nx, ny = int((x1 - x0) / RES) + 1, int((y1 - y0) / RES) + 1
    X = x0 + np.arange(nx) * RES
    Y = y0 + np.arange(ny) * RES
    gx, gy = np.meshgrid(X, Y, indexing="ij")
    L = {name: k for k, name in enumerate(LAYERS)}
    tblock = np.zeros((len(LAYERS), nx, ny), bool)     # no track centre here
    vblock = np.zeros((nx, ny), bool)                  # no via centre here

    def dist(o):
        if o["kind"] == "box":
            bx = o["box"]
            dx = np.maximum(np.maximum(bx[0] - gx, gx - bx[2]), 0)
            dy = np.maximum(np.maximum(bx[1] - gy, gy - bx[3]), 0)
            return np.hypot(dx, dy)
        if o["kind"] == "via":
            return np.maximum(np.hypot(gx - o["c"][0], gy - o["c"][1]) - o["r"], 0)
        (ax, ay), (bx_, by) = o["a"], o["b"]
        vx, vy = bx_ - ax, by - ay
        ll = vx * vx + vy * vy or 1e-12
        t = np.clip(((gx - ax) * vx + (gy - ay) * vy) / ll, 0, 1)
        return np.maximum(np.hypot(gx - (ax + t * vx), gy - (ay + t * vy)) - o["w"], 0)
    for o in d["obst"]:
        dd = dist(o)
        for layer in o["layers"]:
            tblock[L[layer]] |= dd < CLEAR + TRACK / 2
        vblock |= dd < CLEAR + VIA_D / 2            # (vias go through every layer)
        if o.get("hole"):                              # drill to drill
            vblock |= np.hypot(gx - o["c"][0], gy - o["c"][1]) < o["hole"] + VIA_DRILL / 2 + HOLE

    # a pair's second half: a step costs FOLLOW_OFF times as much away from its partner (on the
    # same layer, 0.3-0.6 mm off its centreline: coupled at about the pairs' pitch)
    cost_x = np.ones((len(LAYERS), nx, ny))
    if d.get("follow"):
        near = np.zeros((len(LAYERS), nx, ny), bool)
        for f in d["follow"]:
            if f["layer"] in L:
                dd = dist({"kind": "seg", "a": f["a"], "b": f["b"], "w": 0})
                near[L[f["layer"]]] |= (dd > 0.3) & (dd < 0.6)
        cost_x = np.where(near, 1.0, FOLLOW_OFF)

    def cells(e):
        bx = e["box"]
        return [(L[e["layer"]], i, j) for i in range(nx) for j in range(ny)
                if bx[0] <= X[i] <= bx[2] and bx[1] <= Y[j] <= bx[3]]
    start, goal = cells(d["ends"][0]), set(cells(d["ends"][1]))
    for k, i, j in start + list(goal):                 # (the pads themselves are the net's own)
        tblock[k, i, j] = False
    gi = [(i, j) for _, i, j in goal]
    tx, ty = sum(X[i] for i, _ in gi) / len(gi), sum(Y[j] for _, j in gi) / len(gi)

    def h(i, j):
        return math.hypot(X[i] - tx, Y[j] - ty) / RES
    openq, came, cost = [], {}, {}
    for s in start:
        cost[s] = 0
        heapq.heappush(openq, (h(s[1], s[2]), 0, s))
    steps = [(1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
    end = None
    while openq:
        _, g, cur = heapq.heappop(openq)
        if cur in goal:
            end = cur
            break
        if g > cost.get(cur, 1e18):
            continue
        k, i, j = cur
        nbrs = [((k, i + di, j + dj), w) for di, dj, w in steps]
        if not vblock[i, j]:
            nbrs += [((kk, i, j), VIA_COST) for kk in range(len(LAYERS)) if kk != k]
        for (kk, ii, jj), w in nbrs:
            if not (0 <= ii < nx and 0 <= jj < ny) or tblock[kk, ii, jj]:
                continue
            ng = g + w * (cost_x[kk, ii, jj] if kk == k else 1)
            if ng < cost.get((kk, ii, jj), 1e18):
                cost[(kk, ii, jj)] = ng
                came[(kk, ii, jj)] = cur
                heapq.heappush(openq, (ng + h(ii, jj), ng, (kk, ii, jj)))
    if end is None:
        raise SystemExit("no path for %s" % d["net"])
    path = [end]
    while path[-1] in came:
        path.append(came[path[-1]])
    path.reverse()
    # into tracks and vias: each run on one layer pulled into the fewest straight segments that
    # stay on free cells (line of sight over the grid), then a via where the layer changes
    def clear_line(k, a_, b_):
        n = max(abs(b_[0] - a_[0]), abs(b_[1] - a_[1]))
        return all(not tblock[k, int(round(a_[0] + (b_[0] - a_[0]) * t / n)), int(round(a_[1] + (b_[1] - a_[1]) * t / n))]
                   for t in range(1, n))

    def straighten(run):
        k = run[0][0]
        pts, i = [run[0]], 0
        while i < len(run) - 1:
            j = len(run) - 1
            while j > i + 1 and not clear_line(k, run[i][1:], run[j][1:]):
                j -= 1
            pts.append(run[j])
            i = j
        return pts
    parts, run = [], [path[0]]
    for p in path[1:]:
        if p[0] != run[-1][0]:
            parts.append(("track", straighten(run)))
            parts.append(("via", p))
            run = [p]
            continue
        run.append(p)
    parts.append(("track", straighten(run)))
    res = {"net": d["net"], "tracks": [], "vias": []}
    # (from and to the pads' centres: a grid cell in a round pad's bounding box can lie off it)
    first = [p for p in parts if p[0] == "track"][0][1]
    last = [p for p in parts if p[0] == "track"][-1][1]
    ci = lambda c: (int(round((c[0] - x0) / RES)), int(round((c[1] - y0) / RES)))
    first.insert(0, (first[0][0],) + ci(d["ends"][0]["c"]))
    last.append((last[-1][0],) + ci(d["ends"][1]["c"]))
    for kind, data in parts:
        if kind == "via":
            res["vias"].append([float(X[data[1]]), float(Y[data[2]])])
        elif len(data) > 1:
            res["tracks"].append({"layer": LAYERS[data[0][0]],
                                  "pts": [[float(X[i]), float(Y[j])] for _, i, j in data]})
    json.dump(res, open(out, "w"))
    length = sum(math.hypot(a[0] - b_[0], a[1] - b_[1]) for t in res["tracks"] for a, b_ in zip(t["pts"], t["pts"][1:]))
    print("%s: %.1f mm, %d vias, layers %s" % (d["net"], length, len(res["vias"]),
                                                 sorted({t["layer"] for t in res["tracks"]})))


def apply(board, inp):
    import pcbnew
    from pcbnew import VECTOR2I, FromMM
    r = json.load(open(inp))
    b = pcbnew.LoadBoard(board)
    n = b.FindNet(r["net"])
    for x, y in r["vias"]:
        v = pcbnew.PCB_VIA(b)
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
        v.SetWidth(FromMM(VIA_D))
        v.SetDrill(FromMM(VIA_DRILL))
        v.SetNet(n)
        b.Add(v)
    for t in r["tracks"]:
        for a, z in zip(t["pts"], t["pts"][1:]):
            s = pcbnew.PCB_TRACK(b)
            s.SetStart(VECTOR2I(FromMM(a[0]), FromMM(a[1])))
            s.SetEnd(VECTOR2I(FromMM(z[0]), FromMM(z[1])))
            s.SetWidth(FromMM(TRACK))
            s.SetLayer(b.GetLayerID(t["layer"]))
            s.SetNet(n)
            b.Add(s)
    pcbnew.SaveBoard(board, b)
    b = pcbnew.LoadBoard(board)
    b.BuildConnectivity()
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(board, b)
    print("applied %s: %d track runs, %d vias" % (r["net"], len(r["tracks"]), len(r["vias"])))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["dump"]:
        dump(*a[1:6])
    elif a[:1] == ["route"]:
        route(a[1], a[2])
    elif a[:1] == ["apply"]:
        apply(a[1], a[2])
    else:
        raise SystemExit(__doc__)
