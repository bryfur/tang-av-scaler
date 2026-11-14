"""Check the case (out/*-fitted.stl, from case.py) against the board as built: every part's 3D
model from KiCad's GLB export, plus stand-ins for what KiCad does not model or places wrongly.

    ~/tools/cad-venv/bin/python hardware/case/check.py [--glb FILE]

Prints, per case part, how many points of the board's parts lie inside it (must be 0) and the
smallest gaps, each with the nearest footprint, so a tight spot can be found on the board.
Needs kicad-cli (fpga) for the export, trimesh + rtree + scipy (in ~/tools/cad-venv).
"""
import argparse
import glob
import json
import os
import re
import subprocess
import tempfile

import numpy as np
import trimesh
from scipy.spatial import cKDTree

import logging
logging.getLogger("trimesh").setLevel(logging.ERROR)

import case as C

STANDINS = {
    # the HDMI receptacle and the USB-C: KiCad's models sit off their footprints (courtyards here)
    "J6 HDMI shell": (183.5, 198.5, 47.9, 59.0, C.HDMI_Z0, C.HDMI_Z1),
    "J15 USB-C": (143.03, 151.97, 49.41, 56.76, C.TOP, C.TOP + 3.26),
    "J6 HDMI mouth": (184.3, 197.7, 47.85, 49.0, C.HDMI_Z0 + 0.8, C.HDMI_Z1 - 0.8),       # (render only)
    "J15 USB-C mouth": (143.6, 151.4, 49.36, 50.0, C.TOP + 0.4, C.TOP + 2.86),
    # the SOM on its 3 mm receptacles, its parts, and a heatsink (an estimate: about 28 x 28 mm,
    # its top ~17 mm above the board; measure yours)
    "SOM board": C.som_box() + (C.TOP + 3.0, C.TOP + 4.6),
    "SOM parts": tuple(np.add(C.som_box(), (1, -1, 1, -1))) + (C.TOP + 4.6, C.TOP + 6.6),
    "heatsink (est.)": (C.floor.SOM_AT[0] - 14, C.floor.SOM_AT[0] + 14, C.floor.SOM_AT[1] - 14,
                        C.floor.SOM_AT[1] + 14, C.TOP + 6.6, C.TOP + 17.0),
    # the XIAO on its sockets: module, can, USB-C (2 mm past the module's end, an estimate)
    "XIAO": (103.1, 120.9, 128.5, 149.5, 12.6, 16.0),
    "XIAO USB-C": (107.5, 116.5, 143.0, 151.4, 13.8, 17.0),
    # Dupont housings on the headers (14 mm on the 2.5 mm header body)
    "Dupont J17": (122.2, 127.3, 112.7, 133.1, C.TOP, C.TOP + 16.5),
    "Dupont J8": (103.2, 108.3, 80.9, 101.3, C.TOP, C.TOP + 16.5),
    "Dupont J16": (125.5, 140.5, 144.75, 147.25, C.TOP, C.TOP + 16.5),
    "Dupont J13": (177.7, 180.3, 69.2, 81.9, C.TOP, C.TOP + 16.5),
}


def export_glb(path):
    s = open(C.PCB).read()
    refs = [r for r in re.findall(r'\(property "Reference" "([^"]+)"', s) if r not in ("J6", "J15")]
    av = os.path.abspath(C.AV)
    subprocess.run(["kicad-cli", "pcb", "export", "glb", "-f", "--subst-models", "--component-filter", ",".join(refs),
                    "-o", path, os.path.relpath(C.PCB, av)], cwd=av, check=True, capture_output=True)


def board_points(glb):
    sc = trimesh.load(glb)
    pts = []
    for name in sc.graph.nodes_geometry:
        T, g = sc.graph[name]
        m = sc.geometry[g].copy()
        m.apply_transform(T)
        if len(m.faces) == 0:
            continue
        pts.append(m.vertices)
        pts.append(trimesh.sample.sample_surface_even(m, max(50, int(m.area * 1e6 / 0.5)))[0])
    p = np.concatenate(pts) * 1000.0            # gltf metres, y up: (x, height, board y)
    xyz = np.column_stack([p[:, 0], p[:, 2], p[:, 1]])
    # the board's own body (z 0..1.6) is not a collision: the panels sit beside it, the pillars on it
    body = (xyz[:, 2] > -0.01) & (xyz[:, 2] < C.TOP + 0.01) & (xyz[:, 0] >= C.BX0 - 0.01) & (xyz[:, 0] <= C.BX1 + 0.01) \
        & (xyz[:, 1] >= C.BY0 - 0.01) & (xyz[:, 1] <= C.BY1 + 0.01)
    return xyz[~body]


def box_points(b, step=0.4):
    x0, x1, y0, y1, z0, z1 = b
    m = trimesh.creation.box(extents=(x1 - x0, y1 - y0, z1 - z0))
    m.apply_translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    return np.concatenate([m.vertices, trimesh.sample.sample_surface_even(m, int(m.area / step ** 2))[0]])


def to_case(xyz):
    return np.column_stack([xyz[:, 0] - C.CX, C.CY - xyz[:, 1], xyz[:, 2]])


def nearest_fp(x, y):
    return min(C.FP, key=lambda r: (C.FP[r][0] - x) ** 2 + (C.FP[r][1] - y) ** 2)


def write_standins():
    """The stand-ins as boxes in case coordinates, for render.py."""
    with open(os.path.join(C.HERE, "out", "standins.json"), "w") as f:
        json.dump({k: [b[0] - C.CX, b[1] - C.CX, C.CY - b[3], C.CY - b[2], b[4], b[5]] for k, b in STANDINS.items()
                   if not k.startswith("Dupont")}, f, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glb", help="a board export without J6/J15 (made with kicad-cli if missing)")
    a = ap.parse_args()
    glb = a.glb or os.path.join(tempfile.gettempdir(), "av-board-cb-case.glb")
    if not os.path.exists(glb):
        export_glb(glb)
    write_standins()
    sets = {"board parts": board_points(glb)}
    for k, b in STANDINS.items():
        sets[k] = box_points(b)
    bad = 0
    for f in sorted(glob.glob(os.path.join(C.HERE, "out", "*-fitted.stl"))):
        part = os.path.basename(f)[:-len("-fitted.stl")]
        m = trimesh.load(f)
        assert m.is_watertight, part
        lo, hi = m.bounds[0] - 3, m.bounds[1] + 3
        tree = cKDTree(np.concatenate([m.vertices, trimesh.sample.sample_surface_even(m, int(m.area / 0.09))[0]]))
        rows = []
        for k, xyz in sets.items():
            q = to_case(xyz)
            q = q[np.all((q > lo) & (q < hi), axis=1)]
            # every point inside a part is within 4 mm of its surface (no wall is 8 mm thick):
            # the exact signed distance only for those
            q = q[tree.query(q, distance_upper_bound=4.0)[0] < 4.0]
            if not len(q):
                continue
            # the gap: to the nearest of the part's surface samples (0.3 mm apart: within 0.15 mm);
            # inside or not by ray test (trimesh's exact signed distance needs ~30 GB on the lid)
            dist = tree.query(q)[0]
            ins = np.concatenate([m.contains(q[i:i + 2000]) for i in range(0, len(q), 2000)])
            d = np.where(ins, dist, -dist)                     # > 0 inside
            inside = int((d > 0.01).sum())
            i = int(np.argmax(d))
            rows.append((-d[i], k, inside, q[i]))
        rows.sort(key=lambda r: r[0])
        print(part)
        for gap, k, inside, q in rows[:4]:
            x, y = q[0] + C.CX, C.CY - q[1]
            near = nearest_fp(x, y) if k == "board parts" else ""
            flag = "  COLLIDES" if inside else ""
            bad += inside
            print("   %-16s gap %6.2f mm at board (%6.1f, %6.1f, z %5.1f) %-5s%s%s" %
                  (k, gap, x, y, q[2], near, ("  %d points inside" % inside) if inside else "", flag))
    print("collisions: %d points" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
