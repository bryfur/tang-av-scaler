#!/usr/bin/env python3
"""Placement report: for every small part, how far each of its signal pins is from the nearest
other pad on the same net (a long one is a part placed by the wrong anchor).

    python3 placecheck.py [board.kicad_pcb] [--min 8]
"""
import math
import sys

import pcbnew

import gen_pcb


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    lim = float(sys.argv[sys.argv.index("--min") + 1]) if "--min" in sys.argv else 8.0
    b = pcbnew.LoadBoard(a[0] if a else gen_pcb.OUT)
    pads = {}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            v = p.GetPosition()
            pads.setdefault(p.GetNetname(), []).append((pcbnew.ToMM(v.x), pcbnew.ToMM(v.y), fp.GetReference()))
    rows = []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith(("U", "J", "H", "SW")) or len(fp.Pads()) > 10:
            continue
        for p in fp.Pads():
            n = p.GetNetname()
            if not n or n == "GND" or n in gen_pcb.POWER_NETS:
                continue
            v = p.GetPosition()
            x, y = pcbnew.ToMM(v.x), pcbnew.ToMM(v.y)
            others = [(math.hypot(ox - x, oy - y), r) for ox, oy, r in pads[n] if r != ref]
            if others:
                d, r = min(others)
                if d >= lim:
                    rows.append((d, ref, p.GetNumber(), n, r))
    for d, ref, num, n, r in sorted(rows, reverse=True):
        print("%6.1f mm  %-5s pad %-2s %-18s nearest %s" % (d, ref, num, n, r))


if __name__ == "__main__":
    main()
