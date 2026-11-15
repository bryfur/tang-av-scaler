#!/usr/bin/env python3
"""cnn_ref_hist.py: the multi-frame ("history") network's arithmetic in whole numbers, pure Python: the reference
the RTL is checked against (no numpy, no torch).  A model is the .json cnn_hwr.py writes; the network part is
sim/cnn_ref.py's (its layer(), skip16()).

    run(model, pictures, vectors, real=None) -> [the x 2 output after each picture]
        pictures  [rows of 0..255] (640 x 448: a frame, or a field with the lines between filled by the mean of
                  the lines above and below)
        vectors   for each picture after the first: the blocks' motion, [56 rows][80 blocks] of (vy, vx) in
                  EIGHTHS of an output pixel (what was at output pixel (y, x) of the picture before is now at
                  (y, x) moved by -(vy, vx) / 8: the history is sampled at (y + vy / 8, x + vx / 8)); None: still
        real      (a model with 7 inputs) for each picture: the parity of its real lines (0: even rows)

THE ARITHMETIC, for each picture p (source H x W; output 2H x 2W):
    the history h: the output before (8 bits); for the first picture: (skip16(p) + 8) >> 4
    each output pixel's vector (spread "bilinear"): from the four nearest blocks' (block b's middle at output
        16 b + 7.5): rows b0 = (2 y - 15) >> 5 and b0 + 1 (clamped to the blocks there are), ty = 2 y - 15 - 32 b0
        (1..31, 32nds), the same across; v = ((32 - ty)((32 - tx) a + tx b) + ty((32 - tx) c + tx d) + 512) >> 10;
        ("block": its own block's)
    hm (the moved history), each output pixel: Y = 8 y + vy, X = 8 x + vx; iy = Y >> 3, fy = Y & 7 (same for x;
        the pixels outside the picture: the edge's): ((8 - fy)((8 - fx) a + fx b) + fy((8 - fx) c + fx d) + 32) >> 6
    d (agreement), each source pixel: |p - ((the sum of hm's 2 x 2) + 2) >> 2|; the first picture: 255
    the network's inputs: p, [real lines: 255 on the picture's real rows, else 0], hm's 2 x 2 of each source
        pixel (top left, top right, bottom left, bottom right), d
    the output: sim/cnn_ref.py's arithmetic (layers, then (skip16(p) + r + 8) >> 4, 0..255)
    (>> floors: Python's >> on negative numbers does)"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "git", "tang-av-scaler", "gateware", "sim"))
import cnn_ref


def spread(vectors, H2, W2, how):
    nby, nbx = len(vectors), len(vectors[0])
    cl = lambda v, hi: min(max(v, 0), hi)
    def axis(i, nb):
        b0 = (2 * i - 15) // 32
        return cl(b0, nb - 1), cl(b0 + 1, nb - 1), 2 * i - 15 - 32 * b0
    out = []
    for y in range(H2):
        if how == "block":
            out.append([vectors[min(y // 16, nby - 1)][min(x // 16, nbx - 1)] for x in range(W2)])
            continue
        b0, b1, ty = axis(y, nby)
        row = []
        for x in range(W2):
            c0, c1, tx = axis(x, nbx)
            row.append(tuple(((32 - ty) * ((32 - tx) * vectors[b0][c0][i] + tx * vectors[b0][c1][i])
                              + ty * ((32 - tx) * vectors[b1][c0][i] + tx * vectors[b1][c1][i]) + 512) >> 10 for i in range(2)))
        out.append(row)
    return out


def warp(h, vec):
    H2, W2 = len(h), len(h[0])
    cl = lambda v, hi: min(max(v, 0), hi)
    out = []
    for y in range(H2):
        row = []
        for x in range(W2):
            vy, vx = vec[y][x]
            Y, X = 8 * y + vy, 8 * x + vx
            iy, fy, ix, fx = Y >> 3, Y & 7, X >> 3, X & 7
            y0, y1, x0, x1 = cl(iy, H2 - 1), cl(iy + 1, H2 - 1), cl(ix, W2 - 1), cl(ix + 1, W2 - 1)
            a, b, c, d = h[y0][x0], h[y0][x1], h[y1][x0], h[y1][x1]
            row.append(((8 - fy) * ((8 - fx) * a + fx * b) + fy * ((8 - fx) * c + fx * d) + 32) >> 6)
        out.append(row)
    return out


def step(model, p, hm, first, par=None):
    """one picture: -> the output (2H x 2W)"""
    H, W = len(p), len(p[0])
    if first:
        d = [[255] * W for _ in range(H)]
    else:
        d = [[abs(p[y][x] - ((hm[2 * y][2 * x] + hm[2 * y][2 * x + 1] + hm[2 * y + 1][2 * x] + hm[2 * y + 1][2 * x + 1] + 2) >> 2))
              for x in range(W)] for y in range(H)]
    a = [[list(r) for r in p]]
    if model["in"] == 7:
        a.append([[255 if (y - par) % 2 == 0 else 0] * W for y in range(H)])
    for j in range(2):
        for i in range(2):
            a.append([hm[2 * y + j][i::2] for y in range(H)])
    a.append(d)
    L = len(model["layers"])
    for n, l in enumerate(model["layers"]):
        a = cnn_ref.layer(l, a, n == L - 1)
    sk = cnn_ref.skip16(p)
    out = [[0] * (2 * W) for _ in range(2 * H)]
    for y in range(H):
        for j in range(2):
            o, s = out[2 * y + j], sk[2 * y + j]
            for i in range(2):
                r = a[2 * j + i][y]
                o[i::2] = [min(255, max(0, (s[2 * x + i] + r[x] + 8) >> 4)) for x in range(W)]
    return out


def run(model, pictures, vectors, real=None):
    outs, h = [], None
    for n, p in enumerate(pictures):
        H, W = len(p), len(p[0])
        if h is None:
            hm = [[min(255, max(0, (v + 8) >> 4)) for v in r] for r in cnn_ref.skip16(p)]
            first = True
        else:
            v = vectors[n]
            hm = h if v is None else warp(h, spread(v, 2 * H, 2 * W, model.get("spread", "bilinear")))
            first = False
        h = step(model, p, hm, first, real[n] if real else None)
        outs.append(h)
    return outs


def main():
    """cnn_ref_hist.py MODEL.json check DIR: DIR/seq.json ({"vectors": [...], "real": [...] or null}) and
    DIR/<n>-in.png, DIR/<n>-out.png: every output must be equal"""
    from PIL import Image
    model = json.load(open(sys.argv[1]))
    d = sys.argv[3]
    meta = json.load(open(os.path.join(d, "seq.json")))
    rows = lambda im: [list(im.crop((0, y, im.size[0], y + 1)).getdata()) for y in range(im.size[1])]
    n = len(meta["vectors"])
    pics = [rows(Image.open(os.path.join(d, "%02d-in.png" % k)).convert("L")) for k in range(n)]
    outs = run(model, pics, meta["vectors"], meta.get("real"))
    bad = 0
    for k, o in enumerate(outs):
        want = rows(Image.open(os.path.join(d, "%02d-out.png" % k)).convert("L"))
        diff = sum(1 for a, b in zip(o, want) for u, v in zip(a, b) if u != v)
        print("picture %d: %s" % (k, "equal" if not diff else "%d pixels differ" % diff), flush=True)
        bad += diff
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
