#!/usr/bin/env python3
"""JLCPCB files from a revision's board: Gerbers + drill (zipped), BOM and CPL (placement).

    python3 kit/gen_fab.py rev-b     # rev-b/fab/<name>-gerbers.zip, <name>-bom.csv, <name>-cpl.csv

BOM: one line per LCSC part (Comment, Designator, Footprint, LCSC Part #); DNP parts left out.
Variants (board.py VARIANTS): <name>-<variant>-bom.csv / -cpl.csv without the parts listed there
(soldered by hand); the Gerbers are the same.
CPL: Designator, Mid X, Mid Y, Layer, Rotation, in mm from the board's lower-left corner, y up
(JLCPCB's convention). Check the rotations in JLCPCB's placement preview before ordering: their
library sometimes turns a part 90 or 180 degrees from KiCad's.
"""

import csv
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

import pcbnew
from pcbnew import VECTOR2I, ToMM

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rev  # noqa: E402

HERE = rev.rev_dir(rev.args(__doc__)[0])
board = rev.board(HERE)
NAME = board.NAME
PCB = os.path.join(HERE, NAME + ".kicad_pcb")
FAB = os.path.join(HERE, "fab")
COPPER = {4: "F.Cu,In1.Cu,In2.Cu,B.Cu", 6: "F.Cu,In1.Cu,In2.Cu,In3.Cu,In4.Cu,B.Cu"}
OTHER = "F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"


def main():
    os.makedirs(FAB, exist_ok=True)
    gdir = os.path.join(FAB, "gerbers")
    shutil.rmtree(gdir, ignore_errors=True)
    os.makedirs(gdir)
    # Gerbers, drills and CPL all from one origin, the board's lower-left corner: set as the
    # drill/place origin on a copy of the board, the Gerbers and drills plotted from it (JLCPCB
    # lays the CPL over the Gerbers' coordinates)
    b = pcbnew.LoadBoard(PCB)
    n = b.GetCopperLayerCount()
    edge = b.GetBoardEdgesBoundingBox()
    b.GetDesignSettings().SetAuxOrigin(VECTOR2I(edge.GetLeft(), edge.GetBottom()))
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, NAME + ".kicad_pcb")
    pcbnew.SaveBoard(src, b)
    subprocess.run(["kicad-cli", "pcb", "export", "gerbers", "-l", COPPER[n] + "," + OTHER, "--subtract-soldermask",
                    "--use-drill-file-origin", "-o", gdir + "/", src], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["kicad-cli", "pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th",
                    "--drill-origin", "plot", "--generate-map", "--map-format", "gerberx2", "-o", gdir + "/", src],
                   check=True, stdout=subprocess.DEVNULL)
    shutil.rmtree(tmp)
    z = os.path.join(FAB, NAME + "-gerbers.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
        for n in sorted(os.listdir(gdir)):
            f.write(os.path.join(gdir, n), n)

    b = pcbnew.LoadBoard(PCB)
    edge = b.GetBoardEdgesBoundingBox()
    ox, oy = ToMM(edge.GetLeft()), ToMM(edge.GetBottom())
    groups = {}
    rows = []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith(("H", "#")) or fp.IsDNP():
            continue
        lcsc = fp.GetFieldText("LCSC") if fp.HasFieldByName("LCSC") else ""
        if not lcsc:
            print("no LCSC number:", ref, file=sys.stderr)
            continue
        key = (fp.GetValue(), fp.GetFPIDAsString().split(":")[1], lcsc)
        groups.setdefault(key, []).append(ref)
        pos = fp.GetPosition()
        rows.append([ref, "%.3f" % (ToMM(pos.x) - ox), "%.3f" % (oy - ToMM(pos.y)),
                     "Bottom" if fp.IsFlipped() else "Top", "%.1f" % (fp.GetOrientationDegrees() % 360)])
    def write(suffix, omit=()):
        g = {k: [r for r in refs if r not in omit] for k, refs in groups.items()}
        g = {k: refs for k, refs in g.items() if refs}
        with open(os.path.join(FAB, NAME + suffix + "-bom.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
            for (val, fpn, lcsc), refs in sorted(g.items(), key=lambda kv: kv[1][0]):
                w.writerow([val, ",".join(sorted(refs, key=lambda r: (r.rstrip("0123456789"), int("0" + r.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))))), fpn, lcsc])
        with open(os.path.join(FAB, NAME + suffix + "-cpl.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
            w.writerows(sorted(r for r in rows if r[0] not in omit))
        print("%s%s: %d BOM lines, %d placements" % (NAME, suffix, len(g), sum(1 for r in rows if r[0] not in omit)))
    print(z)
    write("")
    # assembly variants (board.py VARIANTS: name -> the parts left for soldering by hand): the same
    # Gerbers, a BOM and CPL each without those parts
    for name, omit in getattr(board, "VARIANTS", {}).items():
        missing = set(omit) - {r[0] for r in rows}
        if missing:
            raise SystemExit("variant %s: no such parts %s" % (name, sorted(missing)))
        write("-" + name, set(omit))

if __name__ == "__main__":
    main()
