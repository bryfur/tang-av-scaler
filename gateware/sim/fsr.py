#!/usr/bin/env python3
"""fsr.py: the scaler: AMD's FSR 1 edge adaptive spatial upsampling (EASU: ffx_fsr1.h FsrEasuF, MIT
licence), a part of the 720 x 480 picture (all of it, or less: geom()) to 1440 x 1080, as the hardware
does it, and as the shader does for comparison (the whole picture only).

The shader, per output pixel: the 12 source pixels round it; from their luma an edge direction and
an "edge-ness" (len), interpolated between the four nearest pixels' own; a Lanczos-like kernel
rotated along the edge and stretched by len weighs the 12; the result held between the least and
greatest of the four nearest.

The hardware (rtl/easu.v, rtl/easu_ana.v):
- each source pixel's own part of the direction and len is worked out once, as the pixels stream by
  (analysis(): dx, dy the luma differences across it, ls = lenX^2 + lenY^2 in 64ths);
- an output pixel's place in the source is counted up in 65536ths (geom(): a start and a step each
  way); between source pixels it is taken as one of 8 x 8 places (across: k/8, the nearest; down:
  (2k + 1)/16); the four pixels' parts are weighed by whole numbers (128ths);
- the direction is put in one of 32 bins over the half turn, len in one of 8, and the 12 weights
  for (place, direction, len) come from a table (table(): the weights in 256ths, their sum 256: the
  division by the weights' sum is in the table).  The table has the upper four places down only
  (8192 entries): a lower one is its mirror image's (the rows and the direction turned over).

    fsr.py table OUT                # the table for $readmemh: OUT0.hex to OUT3.hex, three weights
                                    # of 10 bits a line each
    fsr.py picture IN.png OUT.png [float|nearest|hw|sharpN] [X0,CW,Y0,CH]  # a 720 x 480 picture scaled, as the
                                                      # hardware (default), the shader, by the nearest
                                                      # pixel, or the hardware's with RCAS at N/16
"""
import math
import sys

TAPS = [(0, -1), (1, -1), (-1, 0), (0, 0), (1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (2, 1), (0, 2), (1, 2)]
NANG, NLEN = 32, 8
NPX, NPY = 8, 8                                     # places between source pixels: k/8 across, (2k + 1)/16 down
OW, OH, OX0 = 1440, 1080, 240                       # the output picture, its first column in the raster
MIRROR = [10, 11, 6, 7, 8, 9, 2, 3, 4, 5, 0, 1]     # TAPS with the rows turned over (ty -> 1 - ty)
TAN = [round(1024 * math.tan((2 * k - 1) * math.pi / 64)) for k in range(1, 9)]    # the bins' edges, to 45 degrees
LEN_TH = [-(-(2 * j - 1) * 16384 // 14) for j in range(1, 8)]                     # len's levels' edges
RECIP = [0] + [4096 // v for v in range(1, 256)]


def geom(x0=0, cw=720, y0=0, ch=480):
    """the part of the source the output shows, cw x ch pixels from (x0, y0): (XR, DX, YS, DY) as the
    hardware has them: a raster column x's place is XR + x DX, a row y's YS + y DY, in 65536ths of a
    source pixel (pixel n's middle at n); the place across with a sixteenth more (to the nearest
    eighth, when the rest is cut off)"""
    dx = (cw * 65536 + OW // 2) // OW
    dy = (ch * 65536 + OH // 2) // OH
    return (x0 * 65536 + dx // 2 - 32768 + 4096 - OX0 * dx, dx, y0 * 65536 + dy // 2 - 32768, dy)


def kernel(ppx, ppy, dx, dy, ln):
    """the 12 weights, as the shader after its direction (dx, dy: a unit vector) and len (0-1) are
    known"""
    ln = ln * ln
    stretch = (dx * dx + dy * dy) / max(abs(dx), abs(dy))
    len2x, len2y = 1 + (stretch - 1) * ln, 1 - 0.5 * ln
    lob = 0.5 + ((1 / 4 - 0.04) - 0.5) * ln
    clp = 1 / lob
    ws = []
    for tx, ty in TAPS:
        ox, oy = tx - ppx, ty - ppy
        vx, vy = (ox * dx + oy * dy) * len2x, (ox * -dy + oy * dx) * len2y
        d2 = min(vx * vx + vy * vy, clp)
        wb, wa = 2 / 5 * d2 - 1, lob * d2 - 1
        ws.append((25 / 16 * wb * wb - (25 / 16 - 1)) * wa * wa)
    return ws


def table():
    """[ky 0-3][kx 0-7][ang][len]: 12 weights in 256ths, their sum 256; the place below the row
    above is (2 ky + 1)/16, right of the column to the left kx/8"""
    out = {}
    for py in range(NPY // 2):
        for px in range(NPX):
            for ang in range(NANG):
                th = ang * math.pi / NANG
                for li in range(NLEN):
                    ws = kernel(px / NPX, (2 * py + 1) / (2 * NPY), math.cos(th), math.sin(th), li / (NLEN - 1))
                    tot = sum(ws)
                    q = [round(w / tot * 256) for w in ws]
                    q[max(range(12), key=lambda k: q[k])] += 256 - sum(q)
                    out[py, px, ang, li] = q
    return out


def analysis(luma, w, h):
    """each source pixel's (dx, dy, ls): rtl/easu_ana.v.  luma: h rows of w"""
    def part(lo, mid, hi):
        d = hi - lo
        mx = max(abs(hi - mid), abs(mid - lo))
        t = min(64, (abs(d) * RECIP[mx]) >> 6)
        return d, (t * t) >> 6
    out = []
    for y in range(h):
        up, dn = luma[max(y - 1, 0)], luma[min(y + 1, h - 1)]
        row = luma[y]
        line = []
        for x in range(w):
            dx, sx = part(row[max(x - 1, 0)], row[x], row[min(x + 1, w - 1)])
            dy, sy = part(up[x], row[x], dn[x])
            line.append((dx, dy, sx + sy))
        out.append(line)
    return out


def angle_bin(ax, ay):
    """the direction's bin, 0-31 over the half turn, by comparisons (the direction and its opposite
    are one)"""
    if ax == 0 and ay == 0:
        return 0
    m, n = (abs(ax), abs(ay)) if abs(ax) >= abs(ay) else (abs(ay), abs(ax))
    t = sum(1 for k in TAN if n * 1024 >= m * k)
    if abs(ay) > abs(ax):
        t = 16 - t
    if (ax < 0) != (ay < 0) and ax != 0 and ay != 0:
        t = (32 - t) % 32
    return t % 32


def scale_hw(pix, ana, w, h, tab, g=None):
    """rtl/easu.v: pix h rows of w (y, cb, cr) -> 1080 rows of 1440; g: geom()'s"""
    xr, dx, ys, dy = g or geom()
    out = []
    cx = lambda x: min(max(x, 0), w - 1)
    cy = lambda y: min(max(y, 0), h - 1)
    for oy in range(OH):
        yp = ys + oy * dy
        fy, ky = yp >> 16, yp >> 13 & 7
        wy = (15 - 2 * ky, 2 * ky + 1)
        mirror = ky >= NPY // 2
        rows = [pix[cy(fy + d)] for d in (-1, 0, 1, 2)]
        arow = [ana[cy(fy)], ana[cy(fy + 1)]]
        line = []
        for ox in range(OW):
            xp = xr + (ox + OX0) * dx
            fx, px = xp >> 16, xp >> 13 & 7
            wx = (8 - px, px)
            ax = ay = al = 0
            for j in range(2):
                for i in range(2):
                    a = arow[j][cx(fx + i)]
                    wgt = wx[i] * wy[j]
                    ax += wgt * a[0]
                    ay += wgt * a[1]
                    al += wgt * a[2]
            ang = angle_bin(ax, ay)
            li = sum(1 for t in LEN_TH if al >= t)
            taps = [rows[ty + 1][cx(fx + tx)] for tx, ty in TAPS]
            if mirror:
                wts = tab[NPY - 1 - ky, px, (NANG - ang) % NANG, li]
                taps = [taps[m] for m in MIRROR]
            else:
                wts = tab[ky, px, ang, li]
            near = [taps[3], taps[4], taps[7], taps[8]]
            p = []
            for c in range(3):
                v = (sum(wt * t[c] for wt, t in zip(wts, taps)) + 128) >> 8
                p.append(min(max(n[c] for n in near), max(min(n[c] for n in near), v)))
            line.append(tuple(p))
        out.append(line)
    return out


def scale_float(pix, w, h):
    """the shader, on the same pixels (luma = y)"""
    out = []
    cx = lambda x: min(max(x, 0), w - 1)
    cy = lambda y: min(max(y, 0), h - 1)
    L = lambda x, y: pix[cy(y)][cx(x)][0] / 255.0
    for oy in range(h * 9 // 4):
        sy = (oy + 0.5) * 4 / 9 - 0.5
        fy = math.floor(sy)
        ppy = sy - fy
        line = []
        for ox in range(w * 2):
            sx = (ox + 0.5) / 2 - 0.5
            fx = math.floor(sx)
            ppx = sx - fx
            dx = dy = ln = 0.0
            for (i, j, wgt) in ((0, 0, (1 - ppx) * (1 - ppy)), (1, 0, ppx * (1 - ppy)), (0, 1, (1 - ppx) * ppy), (1, 1, ppx * ppy)):
                x, y = fx + i, fy + j
                a, b, c, d, e = L(x, y - 1), L(x - 1, y), L(x, y), L(x + 1, y), L(x, y + 1)
                m = max(abs(d - c), abs(c - b))
                dirx = d - b
                dx += dirx * wgt
                lx = min(1.0, abs(dirx) / m) if m else 0.0
                ln += lx * lx * wgt
                m = max(abs(e - c), abs(c - a))
                diry = e - a
                dy += diry * wgt
                ly = min(1.0, abs(diry) / m) if m else 0.0
                ln += ly * ly * wgt
            r = dx * dx + dy * dy
            if r < 1 / 32768:
                dx, dy = 1.0, 0.0
            else:
                r = 1 / math.sqrt(r)
                dx, dy = dx * r, dy * r
            ws = kernel(ppx, ppy, dx, dy, ln * 0.5)
            taps = [pix[cy(fy + ty)][cx(fx + tx)] for tx, ty in TAPS]
            near = [taps[3], taps[4], taps[7], taps[8]]
            tot = sum(ws)
            p = []
            for c in range(3):
                v = sum(wt * t[c] for wt, t in zip(ws, taps)) / tot
                p.append(int(min(max(n[c] for n in near), max(min(n[c] for n in near), round(v)))))
            line.append(tuple(p))
        out.append(line)
    return out


RCAS_P = 219                                        # luma's range above black (16-235)
RCAS_RD = [(65536 + 128 - 2 * k) // (256 - 4 * k) for k in range(49)]


def rcas(pix, sharp):
    """rtl/rcas.v: FSR 1's robust contrast adaptive sharpening (RCAS), on luma: each pixel less a
    part L of its four neighbours, L as great as leaves the result between black and white and not
    past the neighbours' range (at most 3/16), times sharp/16.  pix: rows of (y, cb, cr)"""
    h, w = len(pix), len(pix[0])
    v = [[min(max(p[0] - 16, 0), RCAS_P) for p in row] for row in pix]
    out = []
    for r in range(h):
        up, dn, row = v[max(r - 1, 0)], v[min(r + 1, h - 1)], v[r]
        line = []
        for x in range(w):
            e, b, hh, d, f = row[x], up[x], dn[x], row[max(x - 1, 0)], row[min(x + 1, w - 1)]
            mn4, mx4 = min(b, d, f, hh), max(b, d, f, hh)
            t1 = (min(mn4, e) * RECIP[mx4]) >> 6
            t2 = ((RCAS_P - max(mx4, e)) * RECIP[RCAS_P - mn4]) >> 6
            ls = (min(t1, t2, 48) * sharp) >> 4
            num = max(e * 256 - ls * (b + d + f + hh), 0)
            y = min((num * RCAS_RD[ls] + 32768) >> 16, RCAS_P) + 16
            line.append((y, pix[r][x][1], pix[r][x][2]))
        out.append(line)
    return out


def scale_nearest(pix, w, h):
    return [[pix[(4 * oy + 2) // 9][ox >> 1] for ox in range(2 * w)] for oy in range(h * 9 // 4)]


def to_ycc(rgb):
    r, g, b = rgb
    return (max(0, min(255, (66 * r + 129 * g + 25 * b + 128 >> 8) + 16)),
            max(0, min(255, (-38 * r - 74 * g + 112 * b + 128 >> 8) + 128)),
            max(0, min(255, (112 * r - 94 * g - 18 * b + 128 >> 8) + 128)))


def to_rgb(p):
    clamp = lambda v: 0 if v < 0 else 255 if v > 0xFFFF else v >> 8
    y, cb, cr = p
    yy = 298 * max(y - 16, 0)
    return (clamp(yy + 409 * (cr - 128) + 128), clamp(yy - 100 * (cb - 128) - 208 * (cr - 128) + 128),
            clamp(yy + 516 * (cb - 128) + 128))


def main():
    a = sys.argv[1:]
    if a[0] == "table":
        tab = table()
        # four files, three weights each (rtl/easu.v's four ROMs): OUT0.hex ... OUT3.hex
        fs = [open("%s%d.hex" % (a[1][:-4] if a[1].endswith(".hex") else a[1], k), "w") for k in range(4)]
        for py in range(NPY // 2):
            for px in range(NPX):
                for ang in range(NANG):
                    for li in range(NLEN):
                        q = tab.get((py, px, ang, li), [0] * 12)
                        for k in range(4):
                            fs[k].write("%08x\n" % sum((v & 0x3FF) << 10 * j for j, v in enumerate(q[3 * k:3 * k + 3])))
        for f in fs:
            f.close()
        lo = min(min(q) for q in tab.values())
        hi = max(max(q) for q in tab.values())
        print("table: %d entries, weights %d..%d" % (len(tab), lo, hi))
    elif a[0] == "picture":
        from PIL import Image
        im = Image.open(a[1]).convert("RGB")
        w, h = im.size
        pix = [[to_ycc(im.getpixel((x, y))) for x in range(w)] for y in range(h)]
        how = a[3] if len(a) > 3 else "hw"
        if how == "float":
            out = scale_float(pix, w, h)
        elif how == "nearest":
            out = scale_nearest(pix, w, h)
        else:
            crop = [int(v) for v in a[4].split(",")] if len(a) > 4 else []
            out = scale_hw(pix, analysis([[p[0] for p in row] for row in pix], w, h), w, h, table(), geom(*crop))
            if how.startswith("sharp"):
                out = rcas(out, int(how[5:] or 16))
        res = Image.new("RGB", (len(out[0]), len(out)))
        res.putdata([to_rgb(p) for row in out for p in row])
        res.save(a[2])


if __name__ == "__main__":
    main()
