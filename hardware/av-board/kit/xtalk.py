#!/usr/bin/env python3
"""Analog lines against digital ones on a routed board: for each analog net, its length and layers
and every digital net within 1 mm of it on the same layer (the closest gap, the length run that
close). Analog: the revision's ANALOG, AREF and XTAL classes, the PLL filter, the analog supplies
(AVDD, PVDD, the PCM1808's VREF and 5VA). Digital: every other net but ground and the DC rails
(a switching node is digital) and the static ties (STATIC). Tracks on the other side of the two
ground planes are not counted.

    python3 kit/xtalk.py rev-b [BOARD.kicad_pcb]      (default: the revision's board)

The review's rule (rev-b/review.md): nothing digital within 1 mm of an analog line but where a pin
or an ESD array puts them side by side.
"""
import math
import os
import sys

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
import pcbnew  # noqa: E402
from pcbnew import ToMM  # noqa: E402
from rev import board, layout, rev_dir  # noqa: E402

NEAR = 1.0                  # mm: the gaps reported
STEP = 0.1                  # mm: the sampling along an analog track


# nets that never switch in operation: pins tied off through resistors, straps, feedback nodes, a
# source's 5 V, LED anodes, the ADV7181D's reset (released once)
STATIC = {"ALSB", "PWRDWN", "PD_FB", "MD0", "MD1", "FMT", "VGA_5V", "CEC_PU", "MODE0", "MODE1", "MODE2",
          "DP_A0", "DP_I2C_EN", "DP_VSADJ", "R_EXT", "CC1", "CC2", "LED_A", "D4_A", "D5_A", "IN_RESET_N",
          "DBG_VREF"}


def classify(lay):
    analog = {"ELPF", "ELPF_RC", "AV_AVDD", "AV_PVDD", "VREF", "5VA"}
    for c in lay.CLASSES:
        if c[0] in ("ANALOG", "AREF", "XTAL"):
            analog |= set(c[3])
    quiet = {n for n in lay.POWER_NETS if not n.startswith("SW_")} | STATIC | {"GND", ""}
    return analog, quiet


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    rev = sys.argv[1]
    lay = layout(rev)
    path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(rev_dir(rev), board(rev).NAME + ".kicad_pcb")
    analog, quiet = classify(lay)
    b = pcbnew.LoadBoard(path)
    segs = []
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            continue
        segs.append((t.GetNetname(), t.GetLayer(), ToMM(t.GetStart().x), ToMM(t.GetStart().y),
                     ToMM(t.GetEnd().x), ToMM(t.GetEnd().y), ToMM(t.GetWidth()) / 2))
    aggr = [s for s in segs if s[0] not in analog and s[0] not in quiet and not s[0].startswith("FB_")]

    def dist(px, py, s):
        ax, ay, zx, zy = s[2], s[3], s[4], s[5]
        dx, dy = zx - ax, zy - ay
        ll = dx * dx + dy * dy or 1e-12
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
        return math.hypot(px - ax - t * dx, py - ay - t * dy)

    report, worst = {}, []
    for s in segs:
        if s[0] not in analog:
            continue
        r = report.setdefault(s[0], {"len": 0.0, "layers": set(), "near": {}})
        length = math.hypot(s[4] - s[2], s[5] - s[3])
        r["len"] += length
        r["layers"].add(b.GetLayerName(s[1]))
        k = max(1, int(length / STEP))
        lo_x, hi_x = min(s[2], s[4]) - NEAR - 1, max(s[2], s[4]) + NEAR + 1
        lo_y, hi_y = min(s[3], s[5]) - NEAR - 1, max(s[3], s[5]) + NEAR + 1
        near = [a for a in aggr if a[1] == s[1] and max(a[2], a[4]) > lo_x and min(a[2], a[4]) < hi_x
                and max(a[3], a[5]) > lo_y and min(a[3], a[5]) < hi_y]
        for i in range(k):
            px = s[2] + (s[4] - s[2]) * (i + 0.5) / k
            py = s[3] + (s[5] - s[3]) * (i + 0.5) / k
            # (each point counted once per digital net, at its nearest segment: a net's several
            # short segments by one analog segment were each adding its length)
            best = {}
            for a in near:
                gap = dist(px, py, a) - s[6] - a[6]
                if gap < NEAR and gap < best.get(a[0], NEAR):
                    best[a[0]] = gap
            for m, gap in best.items():
                e = r["near"].setdefault(m, [9.0, 0.0, 0.0])
                e[0] = min(e[0], gap)
                e[1] += length / k
                if gap < 0.5:
                    e[2] += length / k
    for n in sorted(report):
        r = report[n]
        near = sorted(r["near"].items(), key=lambda kv: kv[1][0])
        txt = "; ".join("%s %.2f mm gap, %.1f mm within 1 mm, %.1f within 0.5" % (m, g, ln, ln5)
                        for m, (g, ln, ln5) in near) or "nothing digital within 1 mm"
        print("%-12s %5.1f mm %-12s %s" % (n, r["len"], ",".join(sorted(r["layers"])), txt))
        worst += [(g, ln5, n, m) for m, (g, ln, ln5) in near]
    close = [w for w in worst if w[0] < 0.5]
    print("\n%d analog nets; %d digital neighbours within 1 mm, %d within 0.5 mm%s" % (
        len(report), len(worst), len(close),
        (" (gap x length within 0.5 mm): " + ", ".join("%s/%s %.2f x %.1f" % (n, m, g, ln) for g, ln, n, m in sorted(close)))
        if close else ""))


if __name__ == "__main__":
    main()
