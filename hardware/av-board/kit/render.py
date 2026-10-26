#!/usr/bin/env python3
"""3D renders of a revision's board for its README: rev-x/img/<name>-3d.png (a perspective view from
the front left) and rev-x/img/<name>-top.png (straight down). KiCad's raytracer (kicad-cli pcb
render), the LCSC parts' models (kit/fetch_lib.sh) and KiCad's own (kit/fetch_3d.py).

    python3 kit/render.py rev-b
"""
import os
import subprocess
import sys

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
from rev import args, board, rev_dir  # noqa: E402

VIEWS = {"3d": ["--perspective", "--rotate", "-35,0,-20", "--zoom", "0.9"],
         "top": ["--zoom", "1.3"]}


def main():
    arg, _ = args(__doc__)
    d = rev_dir(arg)
    name = board(arg).NAME
    os.makedirs(os.path.join(d, "img"), exist_ok=True)
    for view, opts in VIEWS.items():
        out = os.path.join(d, "img", "%s-%s.png" % (name, view))
        subprocess.run(["kicad-cli", "pcb", "render", "-o", out, "--width", "1600", "--height", "1100",
                        "--quality", "high", "-D", "KICAD9_3DMODEL_DIR=" + os.path.join(os.path.dirname(KIT), "lib", "kicad.3dshapes")]
                       + opts + [os.path.join(d, name + ".kicad_pcb")], check=True, stdout=subprocess.DEVNULL)
        print(out)


if __name__ == "__main__":
    main()
