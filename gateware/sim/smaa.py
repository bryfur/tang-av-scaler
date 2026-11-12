#!/usr/bin/env python3
"""smaa.py: the anti-aliasing: SMAA 1x's three steps (Jimenez et al., "SMAA: Enhanced Subpixel
Morphological Antialiasing"; the orthogonal patterns only, no diagonals or corners: its LOW/MEDIUM
presets), in whole numbers as the hardware does them (rtl/smaa.v), on the 720 x 480 picture before
it is scaled.

1. Edges, by luma (y): a pixel has a left edge if |y - y(left)| >= T, a top edge if
   |y - y(top)| >= T; and each only if it is at least half the greatest luma step round the pixel
   (to its left, top, right, bottom neighbours, and from the left one to its left, the top one to
   its top): a strong edge beside hides a weak one.
2. For a pixel with a top edge: how far the edge runs to the left and to the right (to N pixels: it
   ends where the next pixel has no top edge, or where an edge crosses it), and which way the edge
   turns at each end (up, down).  The stair this is a step of is taken for a straight line through
   the steps' middles: the part of the pixel (or of the one above) the line cuts off is the weight
   with which it takes its neighbour's colour (area()).  The same for a left edge, up and down.
3. Each pixel is mixed with the neighbour (left, right, top, bottom) whose weight is greatest.

    smaa.py picture IN.png OUT.png [edges]    # a picture through it (edges: the edges found, as a picture)
    smaa.py table OUT.hex                     # the areas for $readmemh: {pattern 4, left 4, right 4} ->
                                              # {above 8, below 8}
"""
import math
import sys

N = 15              # the search's reach, each way
T = 20              # the luma step that is an edge (of 255)


def edges(y, w, h, thr=T):
    """[row][col] -> (left edge, top edge)"""
    Y = lambda x, r: y[min(max(r, 0), h - 1)][min(max(x, 0), w - 1)]
    out = []
    for r in range(h):
        line = []
        for x in range(w):
            c = Y(x, r)
            dl, dt = abs(c - Y(x - 1, r)), abs(c - Y(x, r - 1))
            el, et = dl >= thr and x > 0, dt >= thr and r > 0
            if el or et:
                mx = max(dl, dt, abs(c - Y(x + 1, r)), abs(c - Y(x, r + 1)),
                         abs(Y(x - 1, r) - Y(x - 2, r)), abs(Y(x, r - 1) - Y(x, r - 2)))
                el = el and 2 * dl >= mx
                et = et and 2 * dt >= mx
            line.append((int(el), int(et)))
        out.append(line)
    return out


def area(o1, o2, d, left):
    """a line from height o1 at the edge's left end to o2 at its right end (d pixels on); the
    pixel `left` pixels from the left end: (the part of the pixel above the edge it cuts off, the
    part of the one below), each 0 to 0.5"""
    y1 = o1 + (o2 - o1) * left / d
    y2 = o1 + (o2 - o1) * (left + 1) / d
    if (y1 >= 0) == (y2 >= 0) or abs(y1) < 1e-9 or abs(y2) < 1e-9:
        a = (y1 + y2) / 2
        return (a, 0.0) if a > 0 else (0.0, -a)
    xz = -y1 / (y2 - y1)                            # where it crosses the edge, within the pixel
    a1, a2 = abs(y1) * xz / 2, abs(y2) * (1 - xz) / 2
    return (a1, a2) if y1 > 0 else (a2, a1)


def pattern_area(pat, left, right):
    """pat: bits 0 the left end turns up, 1 down, 2 the right end up, 3 down.  -> (above, below)
    in 255ths: the weights of the pixel above the edge and of the one below"""
    d = left + right + 1
    ol = {1: 0.5, 2: -0.5}.get(pat & 3, 0.0)        # (both ways at an end: as none)
    orr = {1: 0.5, 2: -0.5}.get(pat >> 2 & 3, 0.0)
    if ol and orr:
        if ol != orr:                               # a Z: one line end to end
            a = area(ol, orr, d, left)
        else:                                       # a U: two half lines to the middle
            a1 = area(ol, 0.0, d / 2, left) if left < d / 2 else (0.0, 0.0)
            a2 = area(0.0, orr, d / 2, left - d / 2) if left + 1 > d / 2 else (0.0, 0.0)
            if d % 2 and left == d // 2:            # (the middle pixel of an odd run: half of each)
                a1 = area(ol, 0.0, d / 2, left)
                a1 = (a1[0] / 2, a1[1] / 2)
                a2 = area(0.0, orr, d / 2, 0)
                a2 = (a2[0] / 2, a2[1] / 2)
            a = (a1[0] + a2[0], a1[1] + a2[1])
    elif ol:                                        # an L: a half line from the left end
        a = area(ol, 0.0, d / 2, left) if 2 * left + 1 <= d else (0.0, 0.0)
    elif orr:
        a = area(0.0, orr, d / 2, left - d / 2) if 2 * left + 1 >= d else (0.0, 0.0)
    else:
        a = (0.0, 0.0)
    return min(255, round(a[0] * 255)), min(255, round(a[1] * 255))


_tab = {}


def lookup(pat, left, right):
    k = (pat, left, right)
    if k not in _tab:
        _tab[k] = pattern_area(pat, left, right)
    return _tab[k]


def weights(e, w, h, n=N):
    """[row][col] -> (top, up_of_top, left, left_of_left): with a top edge, top: how much the pixel
    takes of the one above, up_of_top: how much the one above takes of it; the same for a left
    edge"""
    E = lambda x, r: e[r][x] if 0 <= x < w and 0 <= r < h else (0, 0)
    out = []
    for r in range(h):
        line = []
        for x in range(w):
            el, et = e[r][x]
            wt = wu = wl = wo = 0
            if et:
                # leftwards: the boundary on the left of pixel x - i
                i = 0
                while i < n and not (E(x - i, r)[0] or E(x - i, r - 1)[0]) and E(x - i - 1, r)[1]:
                    i += 1
                d1 = i
                pl = E(x - i, r - 1)[0] | E(x - i, r)[0] << 1
                i = 0
                while i < n and not (E(x + i + 1, r)[0] or E(x + i + 1, r - 1)[0]) and E(x + i + 1, r)[1]:
                    i += 1
                d2 = i
                pr = E(x + i + 1, r - 1)[0] | E(x + i + 1, r)[0] << 1
                above, below = lookup(pl | pr << 2, d1, d2)
                wt, wu = below, above
            if el:
                i = 0
                while i < n and not (E(x, r - i)[1] or E(x - 1, r - i)[1]) and E(x, r - i - 1)[0]:
                    i += 1
                d1 = i
                pu = E(x - 1, r - i)[1] | E(x, r - i)[1] << 1
                i = 0
                while i < n and not (E(x, r + i + 1)[1] or E(x - 1, r + i + 1)[1]) and E(x, r + i + 1)[0]:
                    i += 1
                d2 = i
                pd = E(x - 1, r + i + 1)[1] | E(x, r + i + 1)[1] << 1
                other, own = lookup(pu | pd << 2, d1, d2)
                wl, wo = own, other
            line.append((wt, wu, wl, wo))
        out.append(line)
    return out


def blend(pix, wts, w, h):
    W = lambda x, r: wts[r][x] if 0 <= x < w and 0 <= r < h else (0, 0, 0, 0)
    out = []
    for r in range(h):
        line = []
        for x in range(w):
            a_top, a_left = W(x, r)[0], W(x, r)[2]
            a_bot, a_right = W(x, r + 1)[1], W(x + 1, r)[3]
            best = max(a_top, a_left, a_bot, a_right)
            if not best:
                line.append(pix[r][x])
                continue
            if best == a_top:
                nb = pix[r - 1][x]
            elif best == a_bot:
                nb = pix[r + 1][x]
            elif best == a_left:
                nb = pix[r][x - 1]
            else:
                nb = pix[r][x + 1]
            c = pix[r][x]
            line.append(tuple(c[k] + (((nb[k] - c[k]) * best + 128) >> 8) for k in range(3)))
        out.append(line)
    return out


def smaa_words(lines, thr=T, n=N):
    """rtl/smaa.v: the picture as lines of 4:2:2 words (cb, y0, cr, y1) -> the same: luma mixed as
    blend() does; a chroma sample mixed only with the one above or below it (a pixel carries one:
    Cb the even pixels, Cr the odd)"""
    h, w = len(lines), 2 * len(lines[0])
    y = [[v for wd in line for v in (wd[1], wd[3])] for line in lines]
    c = [[v for wd in line for v in (wd[0], wd[2])] for line in lines]
    wts = weights(edges(y, w, h, thr), w, h, n)
    W = lambda x, r: wts[r][x] if 0 <= x < w and 0 <= r < h else (0, 0, 0, 0)
    mix = lambda a, b, k: a + (((b - a) * k + 128) >> 8)
    out = []
    for r in range(h):
        ny, nc = [], []
        for x in range(w):
            a_top, a_left = W(x, r)[0], W(x, r)[2]
            a_bot, a_right = W(x, r + 1)[1], W(x + 1, r)[3]
            best = max(a_top, a_left, a_bot, a_right)
            yy, cc = y[r][x], c[r][x]
            if best:
                if best == a_top:
                    yy, cc = mix(yy, y[r - 1][x], best), mix(cc, c[r - 1][x], best)
                elif best == a_bot:
                    yy, cc = mix(yy, y[r + 1][x], best), mix(cc, c[r + 1][x], best)
                elif best == a_left:
                    yy = mix(yy, y[r][x - 1], best)
                else:
                    yy = mix(yy, y[r][x + 1], best)
            ny.append(yy)
            nc.append(cc)
        out.append([(nc[2 * q], ny[2 * q], nc[2 * q + 1], ny[2 * q + 1]) for q in range(w // 2)])
    return out


def smaa(pix, w, h, thr=T, n=N):
    e = edges([[p[0] for p in row] for row in pix], w, h, thr)
    return blend(pix, weights(e, w, h, n), w, h), e


def main():
    a = sys.argv[1:]
    if a[0] == "picture":
        from PIL import Image
        import fsr
        im = Image.open(a[1]).convert("RGB")
        w, h = im.size
        pix = [[fsr.to_ycc(im.getpixel((x, y))) for x in range(w)] for y in range(h)]
        out, e = smaa(pix, w, h)
        res = Image.new("RGB", (w, h))
        if len(a) > 3 and a[3] == "edges":
            res.putdata([(255 * el, 255 * et, 0) for row in e for el, et in row])
        else:
            res.putdata([fsr.to_rgb(p) for row in out for p in row])
        res.save(a[2])
        print("edges: %d left, %d top of %d pixels" % (sum(el for row in e for el, _ in row), sum(et for row in e for _, et in row), w * h))
    elif a[0] == "table":
        with open(a[1], "w") as f:
            for pat in range(16):
                for left in range(16):
                    for right in range(16):
                        ab, be = lookup(pat, left, right)
                        f.write("%04x\n" % (ab << 8 | be))


if __name__ == "__main__":
    main()
