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
self.tmds_fanout(b, fps) from fanout().
"""

import math

import pcbnew
from pcbnew import ToMM

from pcbkit import pad_pos


def _rot(x, y, a):
    r = math.radians(a)
    return x * math.cos(r) + y * math.sin(r), -x * math.sin(r) + y * math.cos(r)


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
