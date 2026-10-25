#!/usr/bin/env python3
"""Carry board.py's values and LCSC numbers over to a revision's board as it is (placed, routed),
for a change that keeps every footprint and net: a part swapped for an equal one in another
colour or price class needs no new placement or routing.

    python3 kit/sync_values.py rev-b [board.kicad_pcb]

Stops if a footprint or a pad's net differs from board.py (that change needs gen_pcb.py).
"""
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rev  # noqa: E402


def main():
    r, rest = rev.args(__doc__)
    board = rev.board(r)
    path = rest[0] if rest else os.path.join(rev.rev_dir(r), board.NAME + ".kicad_pcb")
    b = pcbnew.LoadBoard(path)
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    changed = 0
    for p in board.PARTS:
        fp = fps.get(p.ref)
        if fp is None or fp.GetFPIDAsString() != p.footprint:
            raise SystemExit("%s: footprint %s on the board, %s in board.py: run gen_pcb.py" % (
                p.ref, fp and fp.GetFPIDAsString(), p.footprint))
        for pad in fp.Pads():
            want = p.pins.get(pad.GetNumber())
            if want is not None and pad.GetNetname() != want:
                raise SystemExit("%s pad %s: net %s on the board, %s in board.py: run gen_pcb.py" % (
                    p.ref, pad.GetNumber(), pad.GetNetname(), want))
        old = (fp.GetValue(), fp.GetFieldText("LCSC") if fp.HasFieldByName("LCSC") else "", fp.IsDNP())
        if old != (p.value, p.lcsc, p.dnp):
            print("%-5s %s %s -> %s %s" % (p.ref, old[0], old[1], p.value, p.lcsc))
            fp.SetValue(p.value)
            fp.SetField("LCSC", p.lcsc)
            fp.SetDNP(p.dnp)
            changed += 1
    pcbnew.SaveBoard(path, b)
    print("%s: %d parts changed" % (path, changed))


if __name__ == "__main__":
    main()
