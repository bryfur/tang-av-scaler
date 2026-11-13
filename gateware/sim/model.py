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


EDI_D, EDI_PEN, EDI_SIDE = 4, 2, 6


def edge_line(o, n):
    """the line between o (above) and n (below) made along the picture's edges (rtl/deint.v edi): for
    each pixel the offset d of -4 to 4 for which the pixels above at x + d and below at x - d are
    most alike, by the sum over the five columns x - 2 to x + 2 of |above(x + k + d) - below(x + k - d)|
    and 2 |d| more (the nearer to straight down first among equals); used only where that sum is
    under two thirds of straight down's, and its own two pixels are no less alike than the two
    straight above and below; the six pixels at each side: straight down.  The pixel: the mean of
    the two, held between the pixels straight above and below.  The chroma goes the way of its
    pair's first pixel, half as far (towards straight down).  -> the line's words"""
    A, B = luma(o), luma(n)
    w = len(A)
    ds = []
    for x in range(w):
        d = 0
        if EDI_SIDE <= x <= w - 1 - EDI_SIDE:
            cost = lambda dd: sum(abs(A[x + k + dd] - B[x + k - dd]) for k in range(-2, 3)) + EDI_PEN * abs(dd)
            c0 = best = cost(0)
            for dd in (-1, 1, -2, 2, -3, 3, -4, 4):
                c = cost(dd)
                if c < best:
                    best, d = c, dd
            if not (3 * best < 2 * c0 and abs(A[x + d] - B[x - d]) <= abs(A[x] - B[x])):
                d = 0
        ds.append(d)
    hold = lambda v, a, b: min(max(v, min(a, b)), max(a, b))
    out = []
    for q in range(w // 2):
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
        bob = edge_line(c[old], c[new]) if edi else None
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
              prog=False, edi=False, mv=None, mc=False, first=0):
    """deint.v, smaa.v (smaa_thr: its edge threshold; None: no SMAA), the 4:4:4 lines; prog: what came
    in is progressive (each of fields a whole frame): the newest as it is"""
    lines = fields[-1] if prog else deinterlace(fields, pars, mode, thr, nr=nr, edi=edi, mv=mv, mc=mc, first=first)
    if smaa_thr is not None:
        import smaa
        lines = smaa.smaa_words(lines, smaa_thr, dbg=smaa_dbg, diag=smaa_diag, corner=smaa_corner)
    return [upsample(line) for line in lines]


def frame_1080(fields, pars, mode=0, thr=6, smaa_thr=None, sharp=0, smaa_dbg=False, smaa_diag=False, smaa_corner=False,
               crop=(), nr=0, dn=False, prog=False, edi=False, mv=None, mc=False, first=0):
    """deint.v, smaa.v, lstream.v, easu.v, rcas.v: 1080 rows of 1920 (r, g, b); crop: the part shown (x0, cw, y0, ch)"""
    import fsr
    pix = frame_480(fields, pars, mode, thr, smaa_thr, smaa_dbg, smaa_diag, smaa_corner, nr, prog, edi, mv, mc, first)
    w, h = len(pix[0]), len(pix)
    out = fsr.rcas(fsr.scale_hw(pix, fsr.analysis([[p[0] for p in row] for row in pix], w, h), w, h, fsr.table(), fsr.geom(*crop)), sharp, dn)
    side = (1920 - len(out[0])) // 2
    return [[(0, 0, 0)] * side + [rgb(*p) for p in row] + [(0, 0, 0)] * side for row in out]
