#!/usr/bin/env python3
"""A PNG of a board (top view), for looking at a placement or a routing.

    python3 kit/snap.py board.kicad_pcb out.png [--layers F.Cu,B.Cu,...] [--clip x0,y0,x1,y1]

Default layers F.Cu,B.Cu,F.Fab,B.Fab,Edge.Cuts; --clip zooms to a window in board mm (the whole
board otherwise). kicad-cli plots an SVG whose page is the board's outline, PyMuPDF
(~/tools/eda-venv) rasterises it.
"""
import os
import subprocess
import sys
import tempfile

import pcbnew

PY = os.path.expanduser("~/tools/eda-venv/bin/python")


def main():
    a = sys.argv[1:]
    opt = {}
    for k in ("--layers", "--clip"):
        if k in a:
            i = a.index(k)
            opt[k] = a[i + 1]
            del a[i:i + 2]
    src, out = a[0], a[1]
    e = pcbnew.LoadBoard(src).GetBoardEdgesBoundingBox()
    X0, Y0, X1, Y1 = (round(pcbnew.ToMM(v), 3) for v in (e.GetLeft(), e.GetTop(), e.GetRight(), e.GetBottom()))
    layers = opt.get("--layers", "F.Cu,B.Cu,F.Fab,B.Fab,Edge.Cuts")
    clip = opt.get("--clip", "%s,%s,%s,%s" % (X0, Y0, X1, Y1))
    with tempfile.TemporaryDirectory() as tmp:
        svg = os.path.join(tmp, "b.svg")
        subprocess.run(["kicad-cli", "pcb", "export", "svg", "--layers", layers, "--black-and-white",
                        "--page-size-mode", "2", "--exclude-drawing-sheet", "--drill-shape-opt", "1",
                        "--mode-single", "-o", svg, src], check=True, stdout=subprocess.DEVNULL)
        subprocess.run([PY, "-c", """
import sys, pymupdf
d = pymupdf.open(sys.argv[1]); p = d[0]
X0, Y0, X1, Y1, x0, y0, x1, y1 = [float(v) for v in sys.argv[3].split(",")]
# the page is the board's outline: board mm -> page points
k = p.rect.width / (X1 - X0)
c = pymupdf.Rect((x0 - X0) * k, (y0 - Y0) * k, (x1 - X0) * k, (y1 - Y0) * k) & p.rect
zoom = 2400 / c.width
p.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=c).save(sys.argv[2])
""", svg, out, "%s,%s,%s,%s,%s" % (X0, Y0, X1, Y1, clip)], check=True)
    print(out)


if __name__ == "__main__":
    main()
