#!/usr/bin/env python3
"""Connections a router laid twice: same-net track segments side by side on one layer (both over
0.3 mm, within 10 degrees of each other, the shorter one's ends and middle within 0.35 mm of the
other, not neighbours along one path), summed per net. A second copy is a loop in the net, its
length counted twice in every length measured; where the copies meet at a sharp angle the copper
between them is a sliver (KiCad's sliver warning, which gives no position: rev C-B's VGA_G had
its whole run from R31 to U19, vias and all, laid twice).

    python3 kit/doubled.py board.kicad_pcb [-v]     (-v: each pair)
"""
import collections
import math
import sys

import pcbnew
from pcbnew import ToMM

SKIP = {"GND"}          # (the ground net's pours and stitching are meant to join up)


def dist(p, a, z):
    dx, dy = z[0] - a[0], z[1] - a[1]
    u = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - a[0] - u * dx, p[1] - a[1] - u * dy)


def pairs(b):
    """Each copy found beside another: ((net, layer name), the shorter track, the other, the
    shorter one's ends, the other's ends, the shorter one's length in mm). pcbkit's prune takes up
    the shorter of each (beside())."""
    by = collections.defaultdict(list)
    for t in b.GetTracks():
        if t.GetClass() != "PCB_TRACK" or t.GetNetname() in SKIP:
            continue
        a = (ToMM(t.GetStart().x), ToMM(t.GetStart().y))
        z = (ToMM(t.GetEnd().x), ToMM(t.GetEnd().y))
        if math.hypot(z[0] - a[0], z[1] - a[1]) > 0.3:
            by[(t.GetNetname(), b.GetLayerName(t.GetLayer()))].append((t, a, z))
    for key, segs in by.items():
        for i in range(len(segs)):
            for j in range(i + 1, len(segs)):
                (t1, a1, z1), (t2, a2, z2) = segs[i], segs[j]
                r1 = {(round(p[0], 3), round(p[1], 3)) for p in (a1, z1)}
                if r1 & {(round(p[0], 3), round(p[1], 3)) for p in (a2, z2)}:
                    continue                    # (neighbours along one path)
                d1, d2 = (z1[0] - a1[0], z1[1] - a1[1]), (z2[0] - a2[0], z2[1] - a2[1])
                l1, l2 = math.hypot(*d1), math.hypot(*d2)
                if abs(d1[0] * d2[0] + d1[1] * d2[1]) / (l1 * l2) < math.cos(math.radians(10)):
                    continue
                (st, sa, sz, sl), (lt, la, lz) = (((t1, a1, z1, l1), (t2, a2, z2)) if l1 < l2
                                                  else ((t2, a2, z2, l2), (t1, a1, z1)))
                mid = ((sa[0] + sz[0]) / 2, (sa[1] + sz[1]) / 2)
                if dist(mid, la, lz) < 0.3 and dist(sa, la, lz) < 0.35 and dist(sz, la, lz) < 0.35:
                    yield key, st, lt, sa + sz, la + lz, sl


def doubled(b, verbose=False):
    """{(net, layer name): length laid twice, mm}."""
    found = collections.defaultdict(float)
    for key, _, _, short, other, length in pairs(b):
        found[key] += length
        if verbose:
            print("   %s %s: (%.3f, %.3f)-(%.3f, %.3f) beside (%.3f, %.3f)-(%.3f, %.3f)" % (key + short + other))
    return found


if __name__ == "__main__":
    found = doubled(pcbnew.LoadBoard(sys.argv[1]), "-v" in sys.argv)
    for (net, layer), length in sorted(found.items(), key=lambda kv: -kv[1]):
        print("%-14s %-5s %.1f mm laid twice" % (net, layer, length))
    print("%d nets laid twice in places, %.1f mm in all" % (len({n for n, _ in found}), sum(found.values())))
