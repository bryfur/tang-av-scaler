#!/usr/bin/env python3
"""A PNG of a board (top view), for looking at a placement or a routing.

    python3 snap.py board.kicad_pcb out.png [--layers F.Cu,B.Cu,...] [--clip x0,y0,x1,y1]

Default layers F.Cu,B.Cu,F.Fab,B.Fab,Edge.Cuts; --clip zooms to a window in board mm (the whole
board otherwise). Uses kicad-cli for the PDF and PyMuPDF (~/tools/eda-venv) for the raster.
"""
import os
import subprocess
import sys
import tempfile

import gen_pcb

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
    layers = opt.get("--layers", "F.Cu,B.Cu,F.Fab,B.Fab,Edge.Cuts")
    clip = opt.get("--clip", "%s,%s,%s,%s" % (gen_pcb.X0, gen_pcb.Y0, gen_pcb.X1, gen_pcb.Y1))
    with tempfile.TemporaryDirectory() as tmp:
        pdf, edge = os.path.join(tmp, "b.pdf"), os.path.join(tmp, "e.pdf")
        for out_, layers_ in ((pdf, layers), (edge, "Edge.Cuts")):
            subprocess.run(["kicad-cli", "pcb", "export", "pdf", "--layers", layers_, "--exclude-value",
                            "--black-and-white", "--drill-shape-opt", "1", "-o", out_, src],
                           check=True, stdout=subprocess.DEVNULL)
        subprocess.run([PY, "-c", """
import sys, pymupdf
d = pymupdf.open(sys.argv[1]); p = d[0]
X0, Y0, X1, Y1, x0, y0, x1, y1 = [float(v) for v in sys.argv[3].split(",")]
# the board outline (plotted alone, on the same page) maps board mm to page points
r = None
for dr in pymupdf.open(sys.argv[4])[0].get_drawings():
    r = dr["rect"] if r is None else r | dr["rect"]
k = r.width / (X1 - X0)
c = pymupdf.Rect(r.x0 + (x0 - X0) * k, r.y0 + (y0 - Y0) * k, r.x0 + (x1 - X0) * k, r.y0 + (y1 - Y0) * k)
zoom = 2400 / c.width
p.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=c).save(sys.argv[2])
""", pdf, out, "%s,%s,%s,%s,%s" % (gen_pcb.X0, gen_pcb.Y0, gen_pcb.X1, gen_pcb.Y1, clip), edge], check=True)
    print(out)


if __name__ == "__main__":
    main()
