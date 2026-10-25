#!/usr/bin/env python3
"""Compare the netlist KiCad makes from a revision's schematic with its board.py, pin by pin.

    kicad-cli sch export netlist -o /tmp/av.net rev-b/av-board-b.kicad_sch && python3 kit/check_netlist.py rev-b /tmp/av.net
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rev  # noqa: E402
from sexp import find, findall, parse  # noqa: E402

r, a = rev.args(__doc__)
board = rev.board(r)
net = parse(open(a[0]).read())
kicad = {}
for n in findall(find(net, "nets"), "net"):
    name = str(find(n, "name")[1]).lstrip("/")
    for node in findall(n, "node"):
        ref, pin = str(find(node, "ref")[1]), str(find(node, "pin")[1])
        if not ref.startswith("#"):
            kicad[(ref, pin)] = name
ours = {(p.ref, num): n for p in board.PARTS for num, n in p.pins.items()}
bad = 0
for k in sorted(set(ours) | set(kicad)):
    a, b = ours.get(k), kicad.get(k)
    if b is not None and b.startswith("unconnected-"):
        b = None
    if a != b:
        bad += 1
        if bad <= 20:
            print("MISMATCH %s pin %s: board.py %s, schematic %s" % (k[0], k[1], a, b))
print("%d pins compared, %d mismatches" % (len(ours), bad))
sys.exit(1 if bad else 0)
