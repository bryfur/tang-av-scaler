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


def luma(line):
    return [v for w in line for v in (w[1], w[3])]


def mean(a, b):
    return (a + b + 1) >> 1


def blend(w, b, a):
    return (w * (16 - a) + b * a + 8) >> 4


def deinterlace(fields, pars, mode=0, thr=6, top_f=0):
    """the last four of the fields (each LINES lines of words; pars their F) -> 2 LINES lines"""
    c, p1 = fields[-1], fields[-2]
    hist = (len(fields) >= 4 and pars[-2] != pars[-1] and pars[-3] == pars[-1] and pars[-4] != pars[-1])
    p2 = fields[-3] if len(fields) >= 3 else c
    p3 = fields[-4] if len(fields) >= 4 else p1
    pc = int(pars[-1] != top_f)
    nl = len(c)
    out = [None] * (2 * nl)
    dcp = [[abs(a - b) for a, b in zip(luma(c[n]), luma(p2[n]))] for n in range(nl)]
    for k in range(nl + (0 if pc else 1)):
        if not pc and k == 0:
            continue
        new, old = (k if k < nl else None), (k - 1 if k >= 1 else None)
        if new is None:
            new = old
        if old is None:
            old = new
        w = k if pc else k - 1
        line_i, line_d = (2 * k, 2 * k + 1) if pc else (2 * (k - 1) + 1, 2 * (k - 1))
        out[line_d] = c[new] if pc else c[old]
        dw = [abs(a - b) for a, b in zip(luma(p1[w]), luma(p3[w]))]
        m = [max(a, b, d) for a, b, d in zip(dcp[new], dcp[old], dw)]
        al = []
        for i in range(2 * PAIRS):
            left = (m[i - 1] if i % 16 else (m[i - 1] if i else 0))
            right = m[i] if i % 16 == 15 else m[i + 1]
            md = max(left, m[i], right)
            if mode == 1 or (not hist and mode != 2):
                al.append(16)
            elif mode == 2:
                al.append(0)
            else:
                al.append(min(16, max(0, md - thr)))
        line = []
        for q in range(PAIRS):
            o, n_, ww = c[old][q], c[new][q], p1[w][q]
            a0, a1 = al[2 * q], al[2 * q + 1]
            ac = max(a0, a1)
            line.append((blend(ww[0], mean(o[0], n_[0]), ac), blend(ww[1], mean(o[1], n_[1]), a0),
                         blend(ww[2], mean(o[2], n_[2]), ac), blend(ww[3], mean(o[3], n_[3]), a1)))
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


def frame_480(fields, pars, mode=0, thr=6, smaa_thr=None, smaa_dbg=False, smaa_diag=False, smaa_corner=False):
    """deint.v, smaa.v (smaa_thr: its edge threshold; None: no SMAA), the 4:4:4 lines"""
    lines = deinterlace(fields, pars, mode, thr)
    if smaa_thr is not None:
        import smaa
        lines = smaa.smaa_words(lines, smaa_thr, dbg=smaa_dbg, diag=smaa_diag, corner=smaa_corner)
    return [upsample(line) for line in lines]


def frame_1080(fields, pars, mode=0, thr=6, smaa_thr=None, sharp=0, smaa_dbg=False, smaa_diag=False, smaa_corner=False,
               crop=()):
    """deint.v, smaa.v, lstream.v, easu.v, rcas.v: 1080 rows of 1920 (r, g, b); crop: the part shown (x0, cw, y0, ch)"""
    import fsr
    pix = frame_480(fields, pars, mode, thr, smaa_thr, smaa_dbg, smaa_diag, smaa_corner)
    w, h = len(pix[0]), len(pix)
    out = fsr.rcas(fsr.scale_hw(pix, fsr.analysis([[p[0] for p in row] for row in pix], w, h), w, h, fsr.table(), fsr.geom(*crop)), sharp)
    side = (1920 - len(out[0])) // 2
    return [[(0, 0, 0)] * side + [rgb(*p) for p in row] + [(0, 0, 0)] * side for row in out]
