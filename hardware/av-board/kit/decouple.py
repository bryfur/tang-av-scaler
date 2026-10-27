#!/usr/bin/env python3
"""Each chip's supply pins and their capacitors on a placed or routed board: for every IC supply
pin (a pad on one of the layout's POWER_NETS), the nearest small capacitor (10 nF - 1 uF) on that
net; for a regulator's input and output pins, the nearest capacitor of 1 uF or more. Centre to
centre, mm; the pins past the limit listed. (Rev B, C-A and C-B had an ADV7511's 100 nF 9-20 mm
from its pins and a TLV62569's input capacitor 5-14 mm from VIN until board.py named each
capacitor's pin, at=.)

    python3 kit/decouple.py rev-x board.kicad_pcb [limit, default 3]
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbkit  # noqa: E402
import pcbnew  # noqa: E402
from pcbnew import ToMM  # noqa: E402

SMALL = {"10n", "22n", "47n", "100n", "220n", "470n", "1u"}
REGULATORS = ("TLV6", "TPS7", "ME62")       # (value prefixes: the bucks and LDOs)


def at(p):
    return ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)


def main():
    lay = pcbkit.layout_of(sys.argv[1])
    b = pcbnew.LoadBoard(sys.argv[2])
    limit = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
    caps = {}
    for f in b.GetFootprints():
        if f.GetReference().startswith("C"):
            for p in f.Pads():
                caps.setdefault(p.GetNetname(), []).append((f.GetReference(), f.GetValue(), at(p)))
    rows = []
    for u in sorted((f for f in b.GetFootprints() if f.GetReference().startswith("U")), key=lambda f: f.GetReference()):
        regulator = u.GetValue().startswith(REGULATORS)
        for p in u.Pads():
            net = p.GetNetname()
            if net not in lay.POWER_NETS or net == "GND" or net.startswith(("FB_", "SW_")):
                continue
            x, y = at(p)
            near = [(math.hypot(cx - x, cy - y), r, v) for r, v, (cx, cy) in caps.get(net, [])
                    if (v.endswith("u") if regulator else v in SMALL)]
            d, r, v = min(near, default=(99.0, "-", "-"))
            rows.append((d, u.GetReference(), u.GetValue(), p.GetNumber(), net, r, v, regulator))
    for d, ref, value, pin, net, r, v, regulator in sorted(rows, reverse=True):
        if d > limit:
            print("%-4s %-18s pin %-3s %-10s %s %s %s %.1f mm" % (ref, value, pin, net,
                                                             "in/out cap" if regulator else "nearest",
                                                             r, v, d))
    dec = [d for d, *_, regulator in rows if not regulator]
    reg = [d for d, *_, regulator in rows if regulator]
    print("%d supply pins: mean %.1f mm, %d past %.1f mm, at most %.1f mm; %d regulator pins: at most %.1f mm" % (
        len(dec), sum(dec) / len(dec), sum(1 for d in dec if d > limit), limit, max(dec), len(reg), max(reg)))


if __name__ == "__main__":
    main()
