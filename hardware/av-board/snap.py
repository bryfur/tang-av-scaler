#!/usr/bin/env python3
"""A PNG of a board (top view, the board area only), for looking at a placement or a routing.

    python3 snap.py board.kicad_pcb out.png [layers]   (default F.Cu,B.Cu,F.Fab,B.Fab,Edge.Cuts)

Uses kicad-cli for the PDF and PyMuPDF (~/tools/eda-venv) for the raster.
"""
import os
import subprocess
import sys
import tempfile

PY = os.path.expanduser("~/tools/eda-venv/bin/python")


def main():
    src, out = sys.argv[1], sys.argv[2]
    layers = sys.argv[3] if len(sys.argv) > 3 else "F.Cu,B.Cu,F.Fab,B.Fab,Edge.Cuts"
    with tempfile.TemporaryDirectory() as tmp:
        pdf = os.path.join(tmp, "b.pdf")
        subprocess.run(["kicad-cli", "pcb", "export", "pdf", "--layers", layers, "--exclude-value",
                        "--black-and-white", "--drill-shape-opt", "1", "-o", pdf, src],
                       check=True, stdout=subprocess.DEVNULL)
        subprocess.run([PY, "-c", """
import sys, pymupdf
d = pymupdf.open(sys.argv[1]); p = d[0]
# crop to what is drawn (the board), with a margin
r = None
for dr in p.get_drawings():
    r = dr["rect"] if r is None else r | dr["rect"]
r = pymupdf.Rect(r.x0 - 4, r.y0 - 4, r.x1 + 4, r.y1 + 4)
zoom = 2400 / r.width
p.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=r).save(sys.argv[2])
""", pdf, out], check=True)
    print(out)


if __name__ == "__main__":
    main()
