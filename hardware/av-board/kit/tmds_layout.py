"""TMDS pairs laid by the generator, before routing (rev B's, rev-b/design.md): from a transmitter's
pins (the ADV7511's, or an SN65DP159's outputs), straight out, one 45-degree corner, straight to a
flow-through ESD array, across it, on to the HDMI receptacle; nested so each pair stays coupled
through the bend. A mixin for pcbkit.Layout.

The geometry is worked out in a frame where the lines leave the chip downwards (+y) and run on to
the right (+x), as on rev B; TMDS_ANGLE turns that frame on the board (KiCad's angle: 90 = the
lines leave the chip to the right and run on upwards). Rev B's 0 leaves every point exactly as
it was.

A revision sets TMDS_CHIP, TMDS_CONN, TMDS (the pairs: name, chip P and N pins, ESD array, its P
in/out and N in/out pads, the receptacle's P and N pins), TMDS_INWARD (the chip's pins between
the pairs: {pin: via's distance in from the pad}), TMDS_ESD (the ESD arrays) and calls
self.tmds_fanout(b, fps) from fanout(); the keep-outs along the pairs (tmds_keepouts) come with
the generator's keepouts() hook.
"""

import math

import pcbnew
from pcbnew import ToMM

from pcbkit import pad_pos


def _rot(x, y, a):
    r = math.radians(a)
    return x * math.cos(r) + y * math.sin(r), -x * math.sin(r) + y * math.cos(r)


def _dirs(pts):
    out = []
    for (ax, ay), (zx, zy) in zip(pts, pts[1:]):
        m = math.hypot(zx - ax, zy - ay)
        out.append(((zx - ax) / m, (zy - ay) / m))
    return out


def _meet(a, d, c, e):
    """Where the line through a along d meets the line through c along e."""
    s = ((c[0] - a[0]) * e[1] - (c[1] - a[1]) * e[0]) / (d[0] * e[1] - d[1] * e[0])
    return a[0] + s * d[0], a[1] + s * d[1]


def _offset(pts, r):
    """A polyline moved r to its left (-ty, tx): towards the outer lines, the frame's lines turning
    left from down to right; r < 0 the other way), its corners mitred. A segment its offset turns
    back on (inside a corner tighter than r) is dropped, its neighbours meeting directly."""
    pts = list(pts)
    while True:
        t = _dirs(pts)
        moved = [((a[0] - r * d[1], a[1] + r * d[0]), d) for a, d in zip(pts, t)]
        out = [moved[0][0]] + [_meet(p, d, q, e) for (p, d), (q, e) in zip(moved, moved[1:])]
        out.append((pts[-1][0] - r * t[-1][1], pts[-1][1] + r * t[-1][0]))
        back = [k for k in range(1, len(t) - 1)
                if (out[k + 1][0] - out[k][0]) * t[k][0] + (out[k + 1][1] - out[k][1]) * t[k][1] <= 0]
        if not back:
            return out
        k = back[0]
        pts[k:k + 2] = [_meet(pts[k - 1], t[k - 1], pts[k + 1], t[k + 1])]


class TMDSLayout:
    TMDS_ANGLE = 0
    TMDS_CHIP, TMDS_CONN = "U2", "J6"
    TMDS = []
    TMDS_INWARD = {}
    TMDS_ESD = ("U9", "U10")
    SMALL_VIA = (0.4, 0.2)
    # a line's straight run out of its pin before its corner, at least: the corner then clears the
    # neighbouring pin's pad (rev C-B's receptacle 1 mm further left turned D2+ 0.2 mm out of its
    # pin, its diagonal 0.19 mm from pin 36)
    TMDS_OUT = 0.8
    # more room between the pairs along their run than the ESD arrays' pins give (0.75 mm between
    # pairs, 3 W at 0.25 mm lines): TI SPRAAR7 3.1 asks for 5 W. The pairs spread by this much each
    # (centred on the bundle) after the chip's corner and close up again just before the arrays,
    # within the receptacle's break-out (3.3: within 0.25 in). 0: as the arrays' pins (rev B, C-A)
    TMDS_SPREAD = 0.0
    TMDS_CONVERGE = 0.3     # the straight left before the arrays' pads once the pairs have closed up
    # keep-outs along the pairs (tmds_keepouts): beside and between them, other tracks and vias
    # (and so their antipads in In1 under the lines: 1.5 W from a void, SPRAAR7 3.2) and the ground
    # pour (the pairs reckoned as microstrips, 100 R) kept TMDS_KEEP off, 30 mil (3.1), from the
    # corner on to where the pairs close up before the ESD arrays; unspread, they run straight in,
    # and the keep-outs stop TMDS_KEEP_END before the arrays' pads (the ground vias between the
    # pairs stand 0.55 mm out). TMDS_KEEP_OUT: the first leg too, out of the chip to the corner,
    # past the chip's break-out (3.3: 0.25 in; rev C-A's first leg runs 15 mm). Within the
    # break-outs other nets' pins stand beside the pairs anyway.
    TMDS_KEEP = 0.76
    TMDS_KEEP_END = 1.0
    TMDS_KEEP_OUT = False
    TMDS_BREAKOUT = 6.35
    TMDS_ESD_VOID = 0.6     # In1 and In2 voided under this much of the arrays' TMDS pads (3.14)

    def to_frame(self, p):
        return _rot(p[0], p[1], -self.TMDS_ANGLE)

    def from_frame(self, p):
        return _rot(p[0], p[1], self.TMDS_ANGLE)

    def tmds(self, b, fps):
        """The TMDS pairs, locked, on F.Cu (over In1), at the class's width: straight out of the
        chip's pads, a 45-degree corner, straight on to the ESD array, across its flow-through
        pads, then to the connector. The lines nest (the pair nearest the array turns first);
        each corner is cut so that the spacing to the line inside it stays what it is on the
        straight parts, so a pair stays coupled through the bend."""
        def pos(ref, num):
            return self.to_frame(pad_pos(fps[ref], num))
        lines = []
        for pr, up, un, u, pi, po, ni, no, jp, jn in self.TMDS:
            for s_, upin, ein, eout, jpin in (("P", up, pi, po, jp), ("N", un, ni, no, jn)):
                lines.append(("TMDS_%s_%s" % (pr, s_), pos(self.TMDS_CHIP, upin), pos(u, ein), pos(u, eout),
                              pos(self.TMDS_CONN, jpin)))
        lines.sort(key=lambda ln: -ln[1][0])            # the innermost (rightmost on the chip) first
        # (TMDS_SPREAD) each line's run, yr, off its array pad's line, yi: the pairs spread about the
        # bundle's middle; then where each closes up again (its 45-degree jog's start, a): the line
        # in front (towards which the lines move) first; behind it the next starts as much later as
        # keeps the two the smaller of their spacings apart on the diagonals (within a pair at
        # 0.5 mm: 0.21 mm later; between pairs: together)
        pairs = []
        for ln in lines:
            if ln[0][:-2] not in pairs:
                pairs.append(ln[0][:-2])
        off = {p: (k - (len(pairs) - 1) / 2) * self.TMDS_SPREAD for k, p in enumerate(pairs)}
        # the innermost line keeps its TMDS_OUT out of its pin and a corner of 0.3 mm at least
        # (0.6 as laid unspread): the spread shifted outwards as much as that needs
        name0, (x00, y00), (_, yi0) = lines[0][0], lines[0][1], lines[0][2]
        room = yi0 + off[name0[:-2]] - y00 - self.TMDS_OUT
        d0 = min(0.6, room)
        if d0 < 0.3:
            off = {p: v + 0.3 - d0 for p, v in off.items()}
            d0 = 0.3
        yr = {ln[0]: ln[2][1] + off[ln[0][:-2]] for ln in lines}
        a = {}
        for movers in ([ln for ln in reversed(lines) if off[ln[0][:-2]] < 0], [ln for ln in lines if off[ln[0][:-2]] > 0]):
            for front, back in zip([None] + movers, movers):
                if front is None:
                    a[back[0]] = 0.0
                    continue
                p0, pf = abs(yr[front[0]] - yr[back[0]]), abs(front[2][1] - back[2][1])
                a[back[0]] = a[front[0]] + max(0.0, min(p0, pf) * math.sqrt(2) - p0)
        if a:
            x_end = min(ln[2][0] for ln in lines) - self.TMDS_CONVERGE
            base = x_end - max(a[n] + abs(off[n[:-2]]) for n in a)
        c_prev, prev = None, None
        w = self.TMDS_W
        for name, (x0, y0), (xi, yi), (xo, yo), (xj, yj) in lines:
            yrun = yr[name]
            if prev is None:
                d = d0
                c = x0 - yrun + d
            else:
                sp = ((prev[0] - x0) + (yrun - prev[1])) / 2    # its spacing to the line inside it
                c = c_prev - math.sqrt(2) * sp
                d = c - x0 + yrun
            assert 0 < d < min(yrun - y0, xi - x0) and yrun - d - y0 >= self.TMDS_OUT - 1e-6, (name, d, yrun - d - y0)
            net = b.FindNet(name)
            pts = [(x0, y0), (x0, yrun - d), (x0 + d, yrun)]
            if name in a:                       # (closing up onto the array's pad line)
                assert base + a[name] > x0 + d, (name, "the pairs close up before the chip's corner ends")
                pts += [(base + a[name], yrun), (base + a[name] + abs(yi - yrun), yi)]
            pts += [(xi, yi), (xo, yo)]
            # to the connector: straight on, then 45 degrees onto its pin's line
            dy = yj - yo
            xk = xj - 1.4 - abs(dy)
            pts += [(xk, yo), (xk + abs(dy), yj), (xj, yj)]
            pts = [self.from_frame(p) for p in pts]
            for a_, z_ in zip(pts, pts[1:]):
                if abs(a_[0] - z_[0]) + abs(a_[1] - z_[1]) > 1e-6:
                    self.track(b, a_, z_, w, pcbnew.F_Cu, net)
            c_prev, prev = c, (x0, yrun)
        print("TMDS: %d lines laid%s" % (len(lines), ", spread %.2f mm between pairs on their run" % self.TMDS_SPREAD
                                         if self.TMDS_SPREAD else ""))

    def tmds_fanout(self, b, fps):
        """The chip's pins between the pairs: out inwards, under the package, to a via each; the
        ESD arrays' GND pads (between the pairs): a small via beside each; then the pairs."""
        chip = fps[self.TMDS_CHIP]
        cy2 = self.to_frame((ToMM(chip.GetPosition().x), ToMM(chip.GetPosition().y)))[1]
        for num, dist in self.TMDS_INWARD.items():
            p = [q for q in chip.Pads() if q.GetNumber() == num][0]
            x, y = self.to_frame((ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)))
            v = self.from_frame((x, y - dist if y > cy2 else y + dist))
            self.track(b, self.from_frame((x, y)), v, 0.25 if p.GetNetname() != "OUT_PD" else self.TRACK,
                       pcbnew.F_Cu, p.GetNet())
            self.via(b, v[0], v[1], p.GetNet())
        for u in self.TMDS_ESD:
            fp = fps[u]
            cx_ = self.to_frame((ToMM(fp.GetPosition().x), ToMM(fp.GetPosition().y)))[0]
            for num in ("3", "8"):
                p = [q for q in fp.Pads() if q.GetNumber() == num][0]
                x, y = self.to_frame((ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)))
                v = self.from_frame((x + (0.55 if x > cx_ else -0.55), y))
                self.track(b, self.from_frame((x, y)), v, 0.25, pcbnew.F_Cu, p.GetNet())
                self.via(b, v[0], v[1], p.GetNet(), *self.SMALL_VIA)
        self.tmds(b, fps)

    def keepouts(self, b, fps):
        self.tmds_keepouts(b, fps)

    def tmds_paths(self, b, fps):
        """Each TMDS line as it lies on the board (its locked tracks, from the chip's pad on), in the
        frame: {name: [(x, y), ...]}; the array's input pad's x with it."""
        def near(p, q):
            return abs(p[0] - q[0]) + abs(p[1] - q[1]) < 1e-3

        paths = {}
        for pr, up, un, u, pi, _, ni, _, _, _ in self.TMDS:
            for s_, pin, epad in (("P", up, pi), ("N", un, ni)):
                name = "TMDS_%s_%s" % (pr, s_)
                segs = [(self.to_frame((ToMM(t.GetStart().x), ToMM(t.GetStart().y))),
                         self.to_frame((ToMM(t.GetEnd().x), ToMM(t.GetEnd().y))))
                        for t in b.GetTracks() if t.GetClass() == "PCB_TRACK" and t.IsLocked() and t.GetNetname() == name]
                p = self.to_frame(pad_pos(fps[self.TMDS_CHIP], pin))
                path = [p]
                while True:
                    nxt = [s for s in segs if near(s[0], p) or near(s[1], p)]
                    if not nxt:
                        break
                    segs.remove(nxt[0])
                    p = nxt[0][1] if near(nxt[0][0], p) else nxt[0][0]
                    path.append(p)
                assert len(path) > 3, (name, "no locked line from the chip's pad")
                paths[name] = (path, self.to_frame(pad_pos(fps[u], epad))[0])
        return paths

    def tmds_keepouts(self, b, fps):
        """The keep-outs along the pairs (TMDS_KEEP above): rule areas on F.Cu outside the outermost
        line (round its corner), inside the innermost and between the pairs, each following the
        lines from where they are guarded to where they close up; In1 and In2 voided under the
        arrays' TMDS pads. Worked out from the lines on the board, so the same on a routed board
        (--keepouts) as on a new one."""
        hw = self.TMDS_W / 2
        r_in, r_out = hw + 0.01, hw + self.TMDS_KEEP
        span = {}
        for name, (path, xi) in self.tmds_paths(b, fps).items():
            # the corner: the first diagonal; the run on from it, straight, to where the line jogs to
            # close up (spread) or into the array's pad
            k = [k for k, (a, z) in enumerate(zip(path, path[1:])) if z[0] - a[0] > 1e-3 and z[1] - a[1] > 1e-3][0]
            c0, c1 = path[k], path[k + 1]
            j = k + 1
            while j + 1 < len(path) and abs(path[j + 1][1] - c1[1]) < 1e-4 and path[j][0] < path[j + 1][0] <= xi + 1e-4:
                j += 1
            xe = (path[j][0] if path[j][0] < xi - 1e-3 else xi - self.TMDS_KEEP_END) - 0.1
            first = (c0[0], path[0][1] + self.TMDS_BREAKOUT)
            out = [first] if self.TMDS_KEEP_OUT and first[1] < c0[1] - 1e-3 else []
            span[name] = (out, c0, c1, (xe, c1[1]))
        lines = sorted(span, key=lambda n: span[n][2][1])        # the innermost (its run nearest the chip) first
        polys = []

        def guarded(n):                 # (along the first leg too, or the run alone)
            out, c0, c1, e = span[n]
            return out + [c0, c1, e] if out else [c1, e]
        # outside the outermost line, from its corner on; inside the innermost (unguarded first leg:
        # from 0.4 mm along its run, clear of its own corner)
        o = span[lines[-1]]
        po = o[0] + [o[1], o[2], o[3]]
        polys.append(_offset(po, r_in) + _offset(po, r_out)[::-1])
        pi_ = guarded(lines[0]) if span[lines[0]][0] else [(span[lines[0]][2][0] + 0.4, span[lines[0]][2][1]), span[lines[0]][3]]
        polys.append(_offset(pi_, -r_in) + _offset(pi_, -r_out)[::-1])
        # between the pairs: from the later start of the two to the earlier end
        for a, z in zip(lines, lines[1:]):
            if a[:-2] == z[:-2]:
                continue
            pa, pz = guarded(a), guarded(z)
            if not span[a][0]:
                x0 = max(pa[0][0], pz[0][0])
                pa[0], pz[0] = (x0, pa[0][1]), (x0, pz[0][1])
            x1 = min(pa[-1][0], pz[-1][0])
            pa[-1], pz[-1] = (x1, pa[-1][1]), (x1, pz[-1][1])
            polys.append(_offset(pa, r_in) + _offset(pz, -r_in)[::-1])
        for poly in polys:
            z = self.rule_area(b, [self.from_frame(p) for p in poly], [pcbnew.F_Cu], tracks=True, vias=True,
                               fills=True, name="TMDS keep-out")
            assert not z.Outline().IsSelfIntersecting(), "a TMDS keep-out crosses itself"
        voids = [q for u in self.TMDS_ESD for q in fps[u].Pads() if q.GetNetname().startswith("TMDS_")]
        for q in voids:
            self.pad_void(b, q, self.TMDS_ESD_VOID, "TMDS void")
        print("TMDS keep-outs: %d strips (%s), In1/In2 voided under %d array pads"
              % (len(polys), "first leg, corner and run" if self.TMDS_KEEP_OUT else "run", len(voids)))

    def pad_void(self, b, q, share, name):
        """In1 and In2 voided under a pad: its middle, share of its area (1: all of it)."""
        bb = q.GetBoundingBox()
        cx, cy = ToMM(bb.GetCenter().x), ToMM(bb.GetCenter().y)
        hx, hy = ToMM(bb.GetWidth()) * math.sqrt(share) / 2, ToMM(bb.GetHeight()) * math.sqrt(share) / 2
        self.rule_area(b, [(cx - hx, cy - hy), (cx + hx, cy - hy), (cx + hx, cy + hy), (cx - hx, cy + hy)],
                       [pcbnew.In1_Cu, pcbnew.In2_Cu], fills=True, name=name)
