#!/usr/bin/env python3
"""cnn_ref.py: the upscaling network's arithmetic in whole numbers, pure Python: the reference the RTL is
checked against (no numpy, no torch).  A model is the .json cnn_hw.py writes.

    upscale(model, src, hist=None) -> the picture at x 2 as rows of 0..255
        src   rows of source luma, 0..255
        hist  (a model with "in": 5) the previous OUTPUT picture (x 2 rows), already moved to lie on this
              frame; None: the frame's own two-tap stretch (what the first frame uses)

    cnn_ref.py MODEL.json IN.png OUT.png          one picture (luma)
    cnn_ref.py MODEL.json check DIR               every DIR/<name>-in.png against DIR/<name>-out.png
                                                  (written by the trainer's integer path): must be equal

THE ARITHMETIC (s = 2; source pixels p = 0..255; edges: the edge pixels repeated, for every layer's input):

    a0 = p                 (in = 5: channels 1..4 = the history's 2 x 2 pixels of each source pixel: top
                            left, top right, bottom left, bottom right)
    layer l = 1 .. L-1:    acc = sum over the kernel and input channels of W * a_(l-1), + B
                           a_l = clamp((acc + 2^(shift-1)) >> shift, 0, 255)
    layer L (4 channels):  r = (acc + 2^(shift-1)) >> shift      (signed, an arithmetic shift; shift 0: r = acc)
    out[2y + j][2x + i] = clamp((skip16 + r[2j + i] + 8) >> 4, 0, 255)
        skip16 = 9 a + 3 b + 3 c + d: a the source pixel itself, b the next one up (j = 0) or down (j = 1),
        c the next one left (i = 0) or right (i = 1), d the diagonal one

    W: -127..127 (8 bits signed), a: 0..255, B: a whole number in acc's units, >> floors (negative too).
    model["layers"][l] = {"kh", "kw", "cin", "cout", "shift", "w": [cout][cin][kh][kw], "b": [cout]}"""
import json
import os
import sys


def skip16(src):
    h, w = len(src), len(src[0])
    out = [[0] * (2 * w) for _ in range(2 * h)]
    for y in range(h):
        r, up, dn = src[y], src[max(y - 1, 0)], src[min(y + 1, h - 1)]
        o0, o1 = out[2 * y], out[2 * y + 1]
        for x in range(w):
            xl, xr = max(x - 1, 0), min(x + 1, w - 1)
            a9 = 9 * r[x]
            o0[2 * x] = a9 + 3 * up[x] + 3 * r[xl] + up[xl]
            o0[2 * x + 1] = a9 + 3 * up[x] + 3 * r[xr] + up[xr]
            o1[2 * x] = a9 + 3 * dn[x] + 3 * r[xl] + dn[xl]
            o1[2 * x + 1] = a9 + 3 * dn[x] + 3 * r[xr] + dn[xr]
    return out


def layer(l, a, last):
    """a: [cin][h][w] -> [cout][h][w]"""
    h, w = len(a[0]), len(a[0][0])
    kh, kw, sh = l["kh"], l["kw"], l["shift"]
    half = (1 << (sh - 1)) if sh else 0
    # each input plane padded by its edge pixels
    pad = []
    for pl in a:
        rows = [[r[0]] * (kw // 2) + r + [r[-1]] * (kw // 2) for r in pl]
        pad.append([rows[0]] * (kh // 2) + rows + [rows[-1]] * (kh // 2))
    out = []
    for co in range(l["cout"]):
        taps = [(ci, dy, dx, l["w"][co][ci][dy][dx]) for ci in range(l["cin"]) for dy in range(kh) for dx in range(kw)
                if l["w"][co][ci][dy][dx]]
        b = l["b"][co]
        plane = []
        for y in range(h):
            acc = [b] * w
            for ci, dy, dx, wt in taps:
                row = pad[ci][y + dy]
                acc = [s + wt * v for s, v in zip(acc, row[dx:dx + w])]
            if last:
                plane.append([(s + half) >> sh for s in acc])
            else:
                plane.append([min(255, max(0, (s + half) >> sh)) for s in acc])
        out.append(plane)
    return out


def upscale(model, src, hist=None):
    h, w = len(src), len(src[0])
    sk = skip16(src)
    a = [[list(r) for r in src]]
    if model["in"] == 5:
        if hist is None:
            hist = [[min(255, max(0, (v + 8) >> 4)) for v in r] for r in sk]
        for j in range(2):
            for i in range(2):
                a.append([hist[2 * y + j][i::2] for y in range(h)])
    L = len(model["layers"])
    for n, l in enumerate(model["layers"]):
        a = layer(l, a, n == L - 1)
    out = [[0] * (2 * w) for _ in range(2 * h)]
    for y in range(h):
        for j in range(2):
            o, s = out[2 * y + j], sk[2 * y + j]
            for i in range(2):
                r = a[2 * j + i][y]
                o[i::2] = [min(255, max(0, (s[2 * x + i] + r[x] + 8) >> 4)) for x in range(w)]
    return out


def main():
    from PIL import Image
    model = json.load(open(sys.argv[1]))
    rows = lambda im: [list(im.crop((0, y, im.size[0], y + 1)).getdata()) for y in range(im.size[1])]
    if sys.argv[2] == "check":
        d, bad = sys.argv[3], 0
        for f in sorted(os.listdir(d)):
            if not f.endswith("-in.png"):
                continue
            n = f[:-7]
            hist = os.path.join(d, n + "-hist.png")
            got = upscale(model, rows(Image.open(os.path.join(d, f)).convert("L")),
                          rows(Image.open(hist).convert("L")) if model["in"] == 5 and os.path.exists(hist) else None)
            want = rows(Image.open(os.path.join(d, n + "-out.png")).convert("L"))
            diff = sum(1 for a, b in zip(got, want) for u, v in zip(a, b) if u != v)
            print("%s: %s" % (n, "equal" if not diff else "%d pixels differ" % diff), flush=True)
            bad += diff
        sys.exit(1 if bad else 0)
    out = upscale(model, rows(Image.open(sys.argv[2]).convert("L")))
    im = Image.new("L", (len(out[0]), len(out)))
    im.putdata([v for r in out for v in r])
    im.save(sys.argv[3])


if __name__ == "__main__":
    main()
