"""Find walls thinner than a printer takes, in the parts as printed (out/*.stl).

    ~/tools/cad-venv/bin/python hardware/case/walls.py [MIN_MM]

From points spread over each part's surface, a ray goes straight in (against the face's normal);
the distance to where it leaves the part is the wall's thickness there. A wall thinner than MIN_MM
(default 1.0) is printed with where it is, grouped to 2 mm cells. A ray started near an edge can
graze the next face and read thin: each thin reading is taken again 0.3 mm away in four directions
along the face, and kept if at least two of those are thin too.
"""
import glob
import os
import sys

import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))


def thickness(m, pts, normals):
    origins = pts - normals * 1e-3
    loc, idx_ray, _ = m.ray.intersects_location(origins, -normals, multiple_hits=False)
    t = np.full(len(pts), np.inf)
    if len(idx_ray):
        t[idx_ray] = np.linalg.norm(loc - origins[idx_ray], axis=1)
    return t


def main():
    lim = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    worst = 0
    for f in sorted(glob.glob(os.path.join(HERE, "out", "*.stl"))):
        if f.endswith("-fitted.stl"):
            continue
        m = trimesh.load(f)
        pts, fi = trimesh.sample.sample_surface_even(m, int(m.area / 0.04))
        n = m.face_normals[fi]
        t = thickness(m, pts, n)
        thin = np.where(t < lim)[0]
        # a second look 0.3 mm along the face each way: a ray grazing an edge reads thin on one side
        # only; a real thin wall (flat or curved: a tube reads thin along its axis) on at least two
        if len(thin):
            nn = n[thin]
            u = np.cross(nn, np.where(np.abs(nn[:, :1]) < 0.9, [[1.0, 0, 0]], [[0, 1.0, 0]]))
            u /= np.linalg.norm(u, axis=1)[:, None]
            v = np.cross(nn, u)
            still = np.zeros(len(thin), int)
            for d in (u, -u, v, -v):
                still += thickness(m, pts[thin] + 0.3 * d, nn) < lim
            thin = thin[still >= 2]
        name = os.path.basename(f)
        if not len(thin):
            print("%-12s ok (no wall under %.2f mm)" % (name, lim))
            continue
        worst += len(thin)
        cells = {}
        for i in thin:
            k = tuple(np.round(pts[i] / 2.0).astype(int))
            if k not in cells or t[i] < cells[k][0]:
                cells[k] = (t[i], pts[i])
        print("%-12s %d thin spots" % (name, len(cells)))
        for tt, p in sorted(cells.values(), key=lambda c: c[0])[:12]:
            print("   %.2f mm at (%.1f, %.1f, %.1f)" % (tt, *p))
    return 1 if worst else 0


if __name__ == "__main__":
    raise SystemExit(main())
