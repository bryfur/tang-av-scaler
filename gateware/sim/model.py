"""model.py: what the picture's path computes, in Python, for the testbenches to hold the RTL to:
deint.v's motion adaptive deinterlacer, lineview.v's scaling and colour conversion; and a test
picture with a part that moves."""

LINES, PAIRS = 240, 360


def field(t):
    """field t (its parity t & 1) of a 720 x 480 picture: LINES lines of PAIRS words (cb, y0, cr, y1);
    a box moves across a still ground"""
    out = []
    for n in range(LINES):
        yf = 2 * n + (t & 1)
        line = []
        for q in range(PAIRS):
            ys = []
            for x in (2 * q, 2 * q + 1):
                if 100 + 24 * t <= x < 260 + 24 * t and 120 <= yf < 300:
                    ys.append(40 + (x * 7 + yf * 3 + t * 31) % 180)
                else:
                    ys.append(16 + (x * 3 + yf * 5) % 200)
            if 50 + 12 * t <= q < 130 + 12 * t and 120 <= yf < 300:
                cb, cr = 200 - (q + t * 9) % 50, 90 + (q * 2 + yf + t * 5) % 90
            else:
                cb, cr = 60 + (q * 5 + yf * 2) % 120, 70 + (q * 3 + yf * 7) % 110
            line.append((cb, ys[0], cr, ys[1]))
        out.append(line)
    return out


def frame(t):
    """frame t of the same picture, progressive: 2 LINES lines (480p: every line each time)"""
    out = []
    for n in range(2 * LINES):
        line = []
        for q in range(PAIRS):
            ys = []
            for x in (2 * q, 2 * q + 1):
                if 100 + 24 * t <= x < 260 + 24 * t and 120 <= n < 300:
                    ys.append(40 + (x * 7 + n * 3 + t * 31) % 180)
                else:
                    ys.append(16 + (x * 3 + n * 5) % 200)
            if 50 + 12 * t <= q < 130 + 12 * t and 120 <= n < 300:
                cb, cr = 200 - (q + t * 9) % 50, 90 + (q * 2 + n + t * 5) % 90
            else:
                cb, cr = 60 + (q * 5 + n * 2) % 120, 70 + (q * 3 + n * 7) % 110
            line.append((cb, ys[0], cr, ys[1]))
        out.append(line)
    return out


def pan_field(t, dx, dyr):
    """field t of a picture that pans: what is at (x, row) in a field is at (x + dx, row + dyr) in the
    field two before (dx pixels, dyr rows of the field: dyr of the picture's lines a field); a box
    in it stands still"""
    out = []
    for n in range(LINES):
        yf = 2 * n + (t & 1)
        line = []
        for q in range(PAIRS):
            ys = []
            for x in (2 * q, 2 * q + 1):
                if 300 <= x < 420 and 200 <= yf < 280:
                    ys.append(30 + (x * 5 + yf * 9) % 190)
                else:
                    u, v = 2 * x + dx * t, yf + dyr * t         # (half pixels across: dx / 2 a field)
                    ys.append(20 + ((u * u // 16 + v * 7 + (u // 2) * (v // 3)) % 200))
            if 150 <= q < 210 and 200 <= yf < 280:
                cb, cr = 90 + (q * 3) % 60, 100 + (yf * 2) % 70
            else:
                u, v = 4 * q + dx * t, yf + dyr * t
                cb, cr = 60 + (u // 4 * 5 + v * 2) % 120, 70 + (u // 4 * 3 + v * 7) % 110
            line.append((cb, ys[0], cr, ys[1]))
        out.append(line)
    return out


def poly_field(t):
    """field t of a picture of hard-edged bars at low angles on a plain ground (a console's polygons:
    no anti-aliasing), each moving across: what the edge search is for"""
    bars = [(40, 60, 8, 200, 3), (120, 300, -6, 30, -2), (200, 100, 3, 220, 4), (260, 420, -12, 180, 1), (330, 250, 2, 25, -3),
            (380, 500, 16, 210, 2), (60, 480, -4, 190, -4), (430, 80, 5, 40, 3)]
    out = []
    for n in range(LINES):
        yf = 2 * n + (t & 1)
        ys = []
        for x in range(2 * PAIRS):
            v = 90 + (x // 64 + yf // 48) % 2 * 12
            for y0, x0, run, lum, speed in bars:        # a bar: 14 lines thick, a line down every |run| pixels across
                xs = x - x0 - speed * t
                top = y0 + (xs // run if run > 0 else -(xs // -run))
                if 0 <= xs < 420 and top <= yf < top + 14:
                    v = lum
            ys.append(v)
        out.append([(110 + (q // 9) % 30, ys[2 * q], 120 + (yf // 7) % 40, ys[2 * q + 1]) for q in range(PAIRS)])
    return out


def noisy(fields, amp):
    """the fields with noise of +-amp added to every sample (the same each run), within 16 to 235"""
    import random
    r = random.Random(1)
    lim = lambda v: min(235, max(16, v))
    return [[[tuple(lim(v + r.randint(-amp, amp)) for v in w) for w in line] for line in f] for f in fields]


def picture_fields(path, n):
    """n fields (as field()'s) of a still 720 x 480 picture from a file"""
    from PIL import Image
    im = Image.open(path).convert("YCbCr").resize((2 * PAIRS, 2 * LINES))
    px = im.load()
    c = lambda v: min(240, max(16, v))
    out = []
    for t in range(n):
        f = []
        for k in range(LINES):
            yf = 2 * k + (t & 1)
            f.append([(c((px[2 * q, yf][1] + px[2 * q + 1, yf][1] + 1) >> 1), min(235, max(16, px[2 * q, yf][0])),
                       c((px[2 * q, yf][2] + px[2 * q + 1, yf][2] + 1) >> 1), min(235, max(16, px[2 * q + 1, yf][0])))
                      for q in range(PAIRS)])
        out.append(f)
    return out


def border(fields, thr=40):
    """border.v: (first pair, last pair, first line, last line) with picture over the fields, None if none"""
    b = None
    for f in fields:
        for n, line in enumerate(f):
            run = 0
            for q, (cb, y0, cr, y1) in enumerate(line):
                lit = y0 > thr and y1 > thr
                was, run = run, (0 if not lit else 1 if q == 0 else min(run + 1, 4))
                if lit and q != 0 and was >= 3:
                    b = (q - 3, q, n, n) if b is None else (min(b[0], q - 3), max(b[1], q), min(b[2], n), max(b[3], n))
    return b


def focus(f):
    """focus.v: a field's sum of the squares (in sixteenths) of the luma steps between neighbours"""
    s = 0
    for line in f:
        y = luma(line)
        s += sum((a - b) ** 2 >> 4 for a, b in zip(y, y[1:]))
    return min(s, 0xFFFFFFF)


def luma(line):
    return [v for w in line for v in (w[1], w[3])]


def mean(a, b):
    return (a + b + 1) >> 1


def blend(w, b, a):
    return (w * (16 - a) + b * a + 8) >> 4


def tnr(cur, oth, nr):
    """a sample and the same one two fields before (the same line, a frame earlier), where the picture
    is still: their mean while they differ by T = 1 << nr or less, less and less of the older one
    from there, none from 2 T on (something moved)"""
    if not nr:
        return cur
    t = 1 << nr
    d = oth - cur
    a = abs(d)
    if a >= 2 * t:
        return cur
    c = (a * min(t, 2 * t - a) + t) >> (nr + 1)
    return cur + c if d > 0 else cur - c


EDI_D, EDI_T1, EDI_E, EDI_SIDE = 8, 24, 60, 26
EDI_ORDER = [d for k in range(1, EDI_D + 1) for d in (-k, k)]      # the offsets, as they are tried


def edge_dirs(A, B, A2, B2):
    """each made pixel's direction (rtl/deint_edi.v): d of -8 to 8: the line above (A) at x + d and
    the line below (B) at x - d are the two ends of an edge through the pixel.  A direction is one
    only where
      - there is a step to bridge: |A[x] - B[x]| >= EDI_T1
      - its two ends are alike over five columns: c = the sum over k of -2 to 2 of
        |A[x + k + d] - B[x + k - d]| is under a third of straight down's (the same sum at d = 0)
      - the edge goes on through the field's next lines out (A2 above A, B2 below B):
        e = the sum over the five columns of |A2[x + k + 3 d] - A[x + k + d]| +
        |B2[x + k - 3 d] - B[x + k - d]| is under EDI_E
      - its own two pixels differ by a quarter of the step at most
    The least 2 c + e + 2 |d| wins (the first of equals, in the order -1, 1, -2, 2, ...); none: 0.
    Then the pixels beside must agree: a direction more than 1 from the median of the five about it
    is dropped.  The EDI_SIDE pixels at each side: 0 (the search reaches that far)."""
    w = len(A)
    ds = [0] * w
    for x in range(EDI_SIDE, w - EDI_SIDE):
        v = abs(A[x] - B[x])
        if v < EDI_T1:
            continue
        c0 = sum(abs(A[x + k] - B[x + k]) for k in range(-2, 3))
        best = None
        for d in EDI_ORDER:
            if 4 * abs(A[x + d] - B[x - d]) > v:
                continue
            c = sum(abs(A[x + k + d] - B[x + k - d]) for k in range(-2, 3))
            if 3 * c >= c0:
                continue
            e = sum(abs(A2[x + k + 3 * d] - A[x + k + d]) + abs(B2[x + k - 3 * d] - B[x + k - d]) for k in range(-2, 3))
            if e >= EDI_E:
                continue
            sc = 2 * c + e + 2 * abs(d)
            if best is None or sc < best[0]:
                best = (sc, d)
        if best:
            ds[x] = best[1]
    out = []
    for x in range(w):
        med = sorted(ds[min(max(x + j, 0), w - 1)] for j in (-2, -1, 0, 1, 2))[2]
        out.append(ds[x] if abs(ds[x] - med) <= 1 else 0)
    return out


def edge_line(o, n, o2=None, n2=None):
    """the line between o (above) and n (below) made along the picture's edges (rtl/deint.v edi;
    o2, n2: the field's next lines out, above o and below n: without one, the nearer line itself):
    each pixel the mean of the line above at x + d and the line below at x - d (edge_dirs()), held
    between the pixels straight above and below.  The chroma goes the way of its pair's first
    pixel, half as far (towards straight down).  -> the line's words"""
    A, B = luma(o), luma(n)
    ds = edge_dirs(A, B, luma(o2 if o2 is not None else o), luma(n2 if n2 is not None else n))
    hold = lambda v, a, b: min(max(v, min(a, b)), max(a, b))
    out = []
    for q in range(len(A) // 2):
        d0, d1 = ds[2 * q], ds[2 * q + 1]
        dq = int(d0 / 2)                    # (towards 0)
        y0 = hold(mean(A[2 * q + d0], B[2 * q - d0]), A[2 * q], B[2 * q])
        y1 = hold(mean(A[2 * q + 1 + d1], B[2 * q + 1 - d1]), A[2 * q + 1], B[2 * q + 1])
        cb = hold(mean(o[q + dq][0], n[q - dq][0]), o[q][0], n[q][0])
        cr = hold(mean(o[q + dq][2], n[q - dq][2]), o[q][2], n[q][2])
        out.append((cb, y0, cr, y1))
    return out


MC_HOLD = 12
ME_UPS = [(1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0), (3, 0), (-3, 0), (1, 1), (-1, -1), (4, 0), (-4, 0), (0, 2), (0, -2),
          (1, -1), (-1, 1)]
ME_PEN = [0, 2, 2, 6, 4, 4]
ME_RX, ME_RY, ME_OUT = 31, 4, 512


def me_candidates(k, b, prev, pan, nb):
    """the six vectors block b tries at step k (None: none there): its own of the line above; a
    neighbour's of the line above (left and right in turn); no move, or the frame's pan (in turn, if
    one is known); one of all the vectors there are (a different one each line and block); its own
    nudged, twice (the nudges in turn)"""
    side = b - 1 if (k + b) & 1 == 0 else b + 1
    h = (37 * k + 101 * b) & 511
    c = [prev[b], prev[side] if 0 <= side < nb else None, pan if pan is not None and (k + b) & 3 >= 2 else (0, 0),
         ((h & 63) - 32, 2 * ((h >> 6) % 5) - 4)]
    for u in range(2):
        up = ME_UPS[(3 * k + 5 * b + 7 * u) & 15]
        c.append((prev[b][0] + up[0], prev[b][1] + up[1]))
    return c


def me_line(k, cl, p2l, prev, pan):
    """the vectors of step k's blocks of eight pixels (rtl/deint.v's estimator): for each block the
    candidate (dx, dy) with the least sum of |C - P2 moved| over the block's eight pixels in C's four
    rows about the line made (k - 2 to k + 1; past the field's ends: the nearest; a row of P2 past
    them: ME_OUT), and the candidate's penalty; the first of the least.  A candidate is left out
    if it is past +-ME_RX, +-ME_RY or takes the block outside the picture; none left: no move.
    cl, p2l: the fields' luma rows; prev: the line above's vectors"""
    nl, W = len(cl), len(cl[0])
    nb = W // 8
    out = []
    for b in range(nb):
        x0 = 8 * b
        best = None
        for ci, v in enumerate(me_candidates(k, b, prev, pan, nb)):
            if v is None:
                continue
            dx, dy = v
            if abs(dx) > ME_RX or abs(dy) > ME_RY or x0 + dx < 0 or x0 + 7 + dx > W - 1:
                continue
            sm = ME_PEN[ci]
            for r in (k - 2, k - 1, k, k + 1):
                if 0 <= r + dy < nl:
                    ra, rb = cl[min(max(r, 0), nl - 1)], p2l[r + dy]
                    sm += sum(abs(ra[x0 + j] - rb[x0 + dx + j]) for j in range(8))
                else:
                    sm += ME_OUT
            if best is None or sm < best[0]:
                best = (sm, v)
        out.append(best[1] if best else (0, 0))
    return out


def deinterlace(fields, pars, mode=0, thr=6, top_f=0, nr=0, edi=False, mv=None, mc=False, first=0, vecs=None):
    """the last four of the fields (each LINES lines of words; pars their F) -> 2 LINES lines; nr: the
    temporal noise reduction (0 none, 1 to 3: tnr()), with four fields of alternating parity; mc:
    motion compensation (rtl/deint.v mc): each block of eight pixels of each line made has a
    vector (dx, dyr) (me_line(): what is at (x, row) in a field is at (x + dx, row + dyr) in the
    field two before), and where the picture is that (and dyr is even: the field before has a line
    there), the line made is the field before's, moved by half of it; mv: the frame's pan as the
    CPU found it, a candidate for the blocks and what they begin with; first: no vectors for the
    lines made before this one (a part of the picture shown: they are not seen); vecs: a list
    that is given each step's (k, vectors)"""
    c, p1 = fields[-1], fields[-2]
    hist = (len(fields) >= 4 and pars[-2] != pars[-1] and pars[-3] == pars[-1] and pars[-4] != pars[-1])
    p2 = fields[-3] if len(fields) >= 3 else c
    p3 = fields[-4] if len(fields) >= 4 else p1
    raw_c, raw_p1 = c, p1               # (what moves is seen in the fields as they are)
    if hist and nr:
        c = [[tuple(tnr(a, b, nr) for a, b in zip(wa, wb)) for wa, wb in zip(la, lb)] for la, lb in zip(c, p2)]
        p1 = [[tuple(tnr(a, b, nr) for a, b in zip(wa, wb)) for wa, wb in zip(la, lb)] for la, lb in zip(p1, p3)]
    pc = int(pars[-1] != top_f)
    nl = len(c)
    out = [None] * (2 * nl)
    dcp = [[abs(a - b) for a, b in zip(luma(raw_c[n]), luma(p2[n]))] for n in range(nl)]
    mc = mc and hist and mode == 0
    W = 2 * PAIRS
    if mc:
        cl, p2l, p1l, p3l = ([luma(r) for r in f] for f in (raw_c, p2, raw_p1, p3))
        vec = [mv if mv is not None else (0, 0)] * (W // 8)
    for k in range(nl + (0 if pc else 1)):
        if not pc and k == 0:
            continue
        new, old = (k if k < nl else None), (k - 1 if k >= 1 else None)
        edge = new is None or old is None
        if new is None:
            new = old
        if old is None:
            old = new
        w = k if pc else k - 1
        line_i, line_d = (2 * k, 2 * k + 1) if pc else (2 * (k - 1) + 1, 2 * (k - 1))
        out[line_d] = c[new] if pc else c[old]
        dw = [abs(a - b) for a, b in zip(luma(raw_p1[w]), luma(p3[w]))]
        m = [max(a, b, d) for a, b, d in zip(dcp[new], dcp[old], dw)]
        al = []
        for i in range(2 * PAIRS):
            left = m[i - 1] if i else 0
            right = m[i + 1] if i < 2 * PAIRS - 1 else 0
            md = max(left, m[i], right)
            if mode == 1 or (not hist and mode != 2):
                al.append(16)
            elif mode == 2:
                al.append(0)
            else:
                al.append(min(16, max(0, md - thr)))
        line = []
        bob = edge_line(c[old], c[new], c[old - 1] if old >= 1 else None, c[new + 1] if new + 1 < nl else None) if edi else None
        # the vectors' way: how far the picture is from itself two fields ago moved by the block's
        # (dx, dyr) (on old, on new, and the field before against the one three before, at the line
        # itself moved by half of it): as m; 255 (no use of it) where a line or a pixel of it is
        # outside the field, at the picture's first and last lines, where dyr is odd, and where the
        # block does not move
        av, wv = [16] * W, [None] * PAIRS
        if mc and not edge and line_i >= first:
            vec = me_line(k, cl, p2l, vec, mv)
            if vecs is not None:
                vecs.append((k, list(vec)))
            mm, wy = [255] * W, [None] * W
            for x in range(W):
                dx, dyr = vec[x // 8]
                if dyr % 2 or (dx == 0 and dyr == 0):
                    continue
                s1, half = dx >> 1, dx & 1
                s3 = dx + s1
                r1 = w + dyr // 2
                r3 = r1 + dyr

                def disp(f, row, xx, hf):
                    if not 0 <= row < nl or xx < 0 or xx + hf > W - 1:
                        return None
                    return mean(f[row][xx], f[row][xx + 1]) if hf else f[row][xx]
                pn, po = disp(p2l, new + dyr, x + dx, 0), disp(p2l, old + dyr, x + dx, 0)
                e, f = disp(p1l, r1, x + s1, half), disp(p3l, r3, x + s3, half)
                part = lambda a_, b_: 255 if a_ is None or b_ is None else abs(a_ - b_)
                mm[x] = max(part(cl[old][x], po), part(cl[new][x], pn), part(e, f))
                wy[x] = e
            # (a pair with a pixel of the field before's outside the picture: no use for either)
            for q in range(PAIRS):
                if wy[2 * q] is None or wy[2 * q + 1] is None:
                    mm[2 * q] = mm[2 * q + 1] = 255
            lo_, ln_ = luma(c[old]), luma(c[new])
            for i in range(W):
                left = mm[i - 1] if i else 0
                right = mm[i + 1] if i < W - 1 else 0
                a_ = min(16, max(0, max(left, mm[i], right) - thr))
                # (and the pixel it would put there must lie near the lines above and below)
                if wy[i] is None or not (min(lo_[i], ln_[i]) - MC_HOLD <= wy[i] <= max(lo_[i], ln_[i]) + MC_HOLD):
                    a_ = 16
                av[i] = a_
            for q in range(PAIRS):
                if wy[2 * q] is not None and wy[2 * q + 1] is not None:
                    dx, dyr = vec[q // 4]
                    qc = (2 * q + (dx >> 1)) >> 1
                    r1 = w + dyr // 2
                    wv[q] = (raw_p1[r1][qc][0], wy[2 * q], raw_p1[r1][qc][2], wy[2 * q + 1])
        for q in range(PAIRS):
            o, n_, ww = c[old][q], c[new][q], p1[w][q]
            a0, a1 = al[2 * q], al[2 * q + 1]
            ac = max(a0, a1)
            b = bob[q] if edi else (mean(o[0], n_[0]), mean(o[1], n_[1]), mean(o[2], n_[2]), mean(o[3], n_[3]))
            v0, v1 = av[2 * q], av[2 * q + 1]
            vc = max(v0, v1)
            if wv[q] is not None:
                b = (blend(wv[q][0], b[0], vc), blend(wv[q][1], b[1], v0), blend(wv[q][2], b[2], vc), blend(wv[q][3], b[3], v1))
            line.append((blend(ww[0], b[0], ac), blend(ww[1], b[1], a0), blend(ww[2], b[2], ac), blend(ww[3], b[3], a1)))
        out[line_i] = line
    return out


def clamp(v):
    return 0 if v < 0 else 255 if v > 0xFFFF else v >> 8


def rgb(y, cb, cr):
    yy = 298 * max(y - 16, 0)
    return (clamp(yy + 409 * (cr - 128) + 128), clamp(yy - 100 * (cb - 128) - 208 * (cr - 128) + 128),
            clamp(yy + 516 * (cb - 128) + 128))


def scale_nearest(prog):
    """lineview.v: 2 LINES progressive lines -> 1080 rows of 1920 (r, g, b)"""
    rows = []
    cache = {}
    for row in range(1080):
        sy = (4 * row + 2) // 9
        if sy not in cache:
            line = prog[sy]
            cache = {sy: [(0, 0, 0)] * 240 + [rgb(line[(col - 240) >> 2][3 if (col - 240) >> 1 & 1 else 1],
                                                 line[(col - 240) >> 2][0], line[(col - 240) >> 2][2])
                                             for col in range(240, 1680)] + [(0, 0, 0)] * 240}
        rows.append(cache[sy])
    return rows


def upsample(line):
    """lstream.v: a line of words (cb, y0, cr, y1) -> pixels (y, cb, cr); a word's second pixel
    has the mean of its chroma and the next word's"""
    out = []
    for q, (cb, y0, cr, y1) in enumerate(line):
        out.append((y0, cb, cr))
        nb, nr = (line[q + 1][0], line[q + 1][2]) if q + 1 < len(line) else (cb, cr)
        out.append((y1, mean(cb, nb), mean(cr, nr)))
    return out


def frame_480(fields, pars, mode=0, thr=6, smaa_thr=None, smaa_dbg=False, smaa_diag=False, smaa_corner=False, nr=0,
              prog=False, edi=False, mv=None, mc=False, first=0, skip=0):
    """deint.v, smaa.v (smaa_thr: its edge threshold; None: no SMAA), the 4:4:4 lines; prog: what came
    in is progressive (each of fields a whole frame): the newest as it is"""
    lines = fields[-1] if prog else deinterlace(fields, pars, mode, thr, nr=nr, edi=edi, mv=mv, mc=mc, first=first)
    # (skip: the lines before it are not made: what follows takes the rest as the whole picture;
    # here they are black)
    lines = lines[skip:]
    if smaa_thr is not None:
        import smaa
        lines = smaa.smaa_words(lines, smaa_thr, dbg=smaa_dbg, diag=smaa_diag, corner=smaa_corner)
    return [[(16, 128, 128)] * (2 * len(lines[0]))] * skip + [upsample(line) for line in lines]


def table_words(tab):
    """a table (fsr.table()'s form: {(place below 0-3, place right 0-7, direction 0-31, strength 0-7):
    12 weights in 256ths}) as the scaler's RAM holds it and a .tab file has it: 8192 entries in that
    order, four words each, three weights (10 bits, signed) a word, the first lowest"""
    out = []
    for py in range(4):
        for px in range(8):
            for ang in range(32):
                for li in range(8):
                    q = tab[py, px, ang, li]
                    out += [sum((v & 0x3FF) << 10 * j for j, v in enumerate(q[3 * k:3 * k + 3])) for k in range(4)]
    return out


def table_from_words(words):
    sgn = lambda v: v - 1024 if v & 512 else v
    tab = {}
    for n in range(8192):
        tab[n >> 11, n >> 8 & 7, n >> 3 & 31, n & 7] = [sgn(words[4 * n + k] >> 10 * j & 0x3FF) for k in range(4) for j in range(3)]
    return tab


def table_load(path):
    """a table from a file: PATH.tab (table_words()'s words, 32 bits each, little-endian), PATH.json
    ({"py,px,ang,len": [12 weights]}), or the four files PATH0.hex to PATH3.hex (a quarter of the
    entries' words each: what the block RAMs are given)"""
    import os
    if path.endswith(".json"):
        import json
        return {tuple(map(int, k.split(","))): v for k, v in json.load(open(path)).items()}
    if path.endswith(".tab") or os.path.exists(path + ".tab"):
        d = open(path if path.endswith(".tab") else path + ".tab", "rb").read()
        if len(d) != 131072:
            raise ValueError("%s: %d bytes, not 131072" % (path, len(d)))
        return table_from_words([int.from_bytes(d[4 * k:4 * k + 4], "little") for k in range(32768)])
    qs = [[int(t, 16) for t in open("%s%d.hex" % (path, k)).read().split()] for k in range(4)]
    if any(len(q) != 8192 for q in qs):
        raise ValueError("%s0.hex to %s3.hex: not 8192 words each" % (path, path))
    return table_from_words([qs[k][n] for n in range(8192) for k in range(4)])


def frame_1080(fields, pars, mode=0, thr=6, smaa_thr=None, sharp=0, smaa_dbg=False, smaa_diag=False, smaa_corner=False,
               crop=(), nr=0, dn=False, prog=False, edi=False, mv=None, mc=False, first=0, skip=0, tab=None):
    """deint.v, smaa.v, lstream.v, easu.v, rcas.v: 1080 rows of 1920 (r, g, b); crop: the part shown (x0, cw, y0, ch);
    tab: the scaler's table (fsr.table()'s form: table_load()), else FSR's"""
    import fsr
    pix = frame_480(fields, pars, mode, thr, smaa_thr, smaa_dbg, smaa_diag, smaa_corner, nr, prog, edi, mv, mc, first, skip)
    w, h = len(pix[0]), len(pix)
    ana = [[(0, 0, 0)] * w] * skip + fsr.analysis([[p[0] for p in row] for row in pix[skip:]], w, h - skip)
    out = fsr.rcas(fsr.scale_hw(pix, ana, w, h, tab or fsr.table(), fsr.geom(*crop)), sharp, dn)
    side = (1920 - len(out[0])) // 2
    return [[(0, 0, 0)] * side + [rgb(*p) for p in row] + [(0, 0, 0)] * side for row in out]
