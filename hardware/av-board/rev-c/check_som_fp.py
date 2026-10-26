#!/usr/bin/env python3
"""Check rev C's SOM footprints against the Tang Console's own board: every pad of each DF40HC-*-SOM
footprint, placed as som.CONNECTORS says relative to the SOM's holes, must sit where the Console's
pad of the same number sits (refs/ibom_C.html, its interactive BOM: pads in name order, 1, 10, 100,
11, ...).

    python3 rev-c/check_som_fp.py
"""
import json
import math
import os
import re
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import som  # noqa: E402
from ibom import lz_decompress_b64  # noqa: E402

src = open(os.path.join(som.ROOT, "refs", "ibom_C.html")).read()
data = json.loads(lz_decompress_b64(re.search(r'LZString\.decompressFromBase64\("([^"]+)"\)', src).group(1)))
fps = {f["ref"]: f for f in data["footprints"]}
holes = [fps[h]["bbox"]["pos"] for h in ("H1", "H2", "H3", "H4")]
cx, cy = sum(h[0] for h in holes) / 4, sum(h[1] for h in holes) / 4
bad = 0
for ref, (console, count, (dx, dy), angle) in som.CONNECTORS.items():
    names = sorted(str(n) for n in range(1, count + 1))
    theirs = {n: p["pos"] for n, p in zip(names, fps[console]["pads"])}
    fp = pcbnew.FootprintLoad(som.LIB, som.FOOTPRINT[count])
    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(cx + dx), pcbnew.FromMM(cy + dy)))
    fp.SetOrientationDegrees(angle)
    ours = {p.GetNumber(): (pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)) for p in fp.Pads()}
    off = [n for n in theirs if math.dist(theirs[n], ours[n]) > 0.01]
    print("%s (Console %s): %d pads, %d off" % (ref, console, len(ours), len(off)), off[:6])
    bad += len(off) + abs(len(ours) - count)
holes_ok = all(min(math.dist((cx + hx, cy + hy), h) for h in holes) < 0.01 for hx, hy in som.HOLES)
print("holes", "match" if holes_ok else "DIFFER")
sys.exit(1 if bad or not holes_ok else 0)
