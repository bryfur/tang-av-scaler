"""The ADV7181D's (U1, LFCSP-64) placement and fanout, for any revision that has it (rev B, rev C):
a mixin for pcbkit.Layout. Everything is relative to U1: its rotation (analog side up, towards the
jacks), the escape vias of its supply and tied-off pins, its 33 R series rows and arrays, the
crystal block, the band above its analog pins (the ADC references' ladder, the inputs' fans), the
PLL block (the loop filter, PVDD's decoupling), its rails' decoupling, its exposed pad. The design
behind each is in rev-b/design.md and rev-b/review.md.

A revision's Layout calls, from its hooks:

    after_hand:      self.u1_after_hand(fp, fps, occ)        (for ref "U1": also places the band
                                                               and PLL blocks and the crystal)
    anchor_special:  self.u1_anchor(p, ic_pads)               (None: not one of U1's parts)
    where_for:       self.u1_where(p, fps)
    rank_special:    self.u1_rank(p)
    fanout:          self.fanout_u1(b, fps); self.crystal_lines(b, fps)
    fanout_skip:     self.u1_fanout_skip() | ...             (U1, and the blocks' GND pads)

and sets FIT["U1"] = fit_u1, KEEP["U1"], BOTH_SIDES with "U1", and U1_PRE_ROUTE in PRE_ROUTE.
"""

import math

import pcbnew
from pcbnew import VECTOR2I, FromMM, ToMM

from pcbkit import courtyard, pad_pos, seg_dist

AV_RAILS = {"AV_DVDD", "AV_PVDD", "AV_AVDD", "AV_DVDDIO"}
# the ADV7181D's pins tied off through a resistor (no signal): an escape via each, like a supply pin
STATIC_NETS = {"ALSB", "PWRDWN", "PD_FB"}
# the video and audio inputs: 0.25 mm from any other copper (what the ADV7181D's 0.5 mm pin pitch
# allows at its pins)
ANALOG_NETS = {"RCA_Y", "RCA_PB", "RCA_PR", "AIN_Y", "AIN_PB", "AIN_PR", "SYNC_Y", "RCA_SYNC", "SYNC_G",
               "RCA_L", "RCA_R", "AUD_DIV_L", "AUD_DIV_R", "AUD_VINL", "AUD_VINR",
               "VGA_R", "VGA_G", "VGA_B", "AIN_VR", "AIN_VG", "AIN_VB"}
# the ADC references (their network laid as a block above their pins, ADV7181D.band)
REF_NETS = {"CAPY1", "CAPY2", "CAPC2", "REFOUT", "CML"}
# the crystal's lines: 0.25 mm from any other copper, twice the default (the router keeps the pixel
# lines off them; at the chip the pins' own 0.5 mm pitch leaves 0.275 mm to LLC's pad)
U1_CLASSES = [("XTAL", 0.15, 0.25, {"XTAL", "XTAL1"}),
              ("AREF", 0.2, 0.15, REF_NETS),
              ("ANALOG", 0.127, 0.25, ANALOG_NETS)]
# the loop filter's parts: placed before the decoupling takes their room [DS Fig. 8]
U1_BIAS_NETS = {"ELPF", "ELPF_RC"}
# before routing (pcbkit pre_route), laid first, short, direct and locked: the inputs on the left
# side's top pins (the top side's are laid with the band, the loop filter with the PLL block)
U1_PRE_ROUTE = [(("AIN_Y", "SYNC_Y"), None, "F.Cu,B.Cu", "B.Cu:3")]
# the control lines whose pull resistors sit at the FPGA's end (u1_anchor)
CONTROL_NETS = ("IN_SDA", "IN_SCL", "IN_RESET_N")


def ToMM2(p):
    return ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)


def layers(*ids):
    s = pcbnew.LSET()
    for i in ids:
        s.AddLayer(i)
    return s


def fit_u1(fp, x, y):
    """Analog side (AIN6-AIN10, pins 33-49) up, towards the jacks' row; pins 1-16 (most of the
    pixel port) down: AIN10 (pin 49) at the top left."""
    p49, p8 = pad_pos(fp, "49"), pad_pos(fp, "8")
    return p49[0] < x - 3 and p49[1] < y - 3 and p8[1] > y + 3


class ADV7181D:
    # the analog lines and ADC references kept 0.5 mm from digital ones by the router (the classes'
    # own 0.25 mm, which the chip's 0.5 mm pins need, let it run the VGA syncs 0.25 mm beside the
    # Y and sync inputs for 10-12 mm on rev B)
    CLASS_CLASS = [("ANALOG", "kicad_default", 0.5), ("ANALOG", "CLOCK", 0.5),
                   ("AREF", "kicad_default", 0.5), ("AREF", "CLOCK", 0.5)]
    # The exposed pad: paste in a 3 x 3 grid of 1.6 mm squares (about half the pad: a full 7.1 mm
    # aperture floats the part), 12 ground vias in the lanes between them
    EP_PASTE = [(dx, dy) for dx in (-2.3, 0.0, 2.3) for dy in (-2.3, 0.0, 2.3)]
    EP_VIAS = [(dx, dy) for dx in (-1.15, 1.15) for dy in (-2.3, 0.0, 2.3)] + \
              [(dx, dy) for dx in (-2.3, 0.0, 2.3) for dy in (-1.15, 1.15)]
    ANALOG_NETS = ANALOG_NETS
    # the band above the ADV7181D's analog pins (33-48, the top side): laid out by band(); its sides
    # take the inputs' coupling and sync caps; every other part keeps out
    BAND_NETS = {"AIN_Y", "SYNC_Y"}
    # other pins that take an escape via: slow lines among the analog pins and the tied-off ones,
    # which the router otherwise finds boxed in, or takes through the analog band: RESET (between
    # SOY and ALSB), the I2C pair beside it, the VGA syncs; and REFOUT and CML, whose capacitors sit
    # at the band's sides (band()). They and AVDD take the small vias (MIN_VIA), staggered 1.1 and
    # 1.8 mm out: AVDD's 0.2 A is far inside a 0.2 mm drill's rating
    U1_ESCAPE_EXTRA = {"IN_RESET_N", "IN_SDA", "IN_SCL", "VGA_HSIN", "VGA_VSIN", "REFOUT", "CML"}
    SMALL_ESCAPE = {"REFOUT", "CML", "AV_AVDD"}

    def u1_init(self):
        board = self.board
        self.rr = {}                # decoupling round robin over a rail's pins
        self.series = {[n for n in p.pins.values() if n.startswith("AV_")][0]: p.ref
                       for p in board.PARTS if p.ref.startswith("R") and not p.ref.startswith("RN") and p.value == "33"
                       and any(n.startswith("AV_") for n in p.pins.values())}
        self.escape = {}
        self.array_nets = {n for p in board.PARTS if p.ref.startswith("RN") for n in p.pins.values() if n.startswith("AV_")}

    def side_pins(self, u1):
        """side -> [(position along the side, net)] of the ADV7181D's pins that have a line out
        (GND pins join the pad inwards; unused pins have none); a pin with an escape via at the
        via's position."""
        cx, cy = ToMM(u1.GetPosition().x), ToMM(u1.GetPosition().y)
        sides = {}
        for p in u1.Pads():
            n = p.GetNetname()
            if not p.GetNumber() or p.GetNumber() == "65" or not n or n == "GND":
                continue
            px, py = ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)
            dx, dy = px - cx, py - cy
            side = ("B" if dy > 0 else "T") if abs(dy) > abs(dx) else ("R" if dx > 0 else "L")
            if p.GetNumber() in self.escape:        # (an escape via blocks where it is)
                px, py = self.escape[p.GetNumber()]
            sides.setdefault(side, []).append((px if side in "TB" else py, n))
        for pins in sides.values():
            pins.sort()
        return sides

    def runs(self, pins, pitch=1.1, tight=0.95):
        """The runs of series-resistor pins along one side, each with the room it may use (lo,
        hi: half a pitch inside the next pins with lines of their own), its step and its slack."""
        out, k = [], 0
        while k < len(pins):
            if pins[k][1] not in self.series:
                k += 1
                continue
            run = [k]
            while run[-1] + 1 < len(pins) and pins[run[-1] + 1][1] in self.series:
                run.append(run[-1] + 1)
            k = run[-1] + 1

            # (an array's pads reach 0.15 mm past its line and a single's 0.32: 0.8 mm off one)
            def margin(i):
                return 0.8 if pins[i][1] in self.array_nets else 0.5
            lo = pins[run[0] - 1][0] + margin(run[0] - 1) if run[0] > 0 else -1e9
            hi = pins[run[-1] + 1][0] - margin(run[-1] + 1) if run[-1] + 1 < len(pins) else 1e9
            n = len(run)
            room = min(hi, 1e8) - max(lo, -1e8)
            step = pitch if n < 2 or room >= pitch * (n - 1) else max(tight, room / (n - 1))
            out.append((run, lo, hi, step, room - tight * (n - 1)))
        return out

    def place_arrays(self, fps, u1, occ, off=6.7):
        """The 33 R arrays: each centred on its four pins, at their 0.5 mm pitch, pads 1-4 towards
        the chip, pad 1 on its first pin's line: four straight lines. Its inner pads just outside
        the escape vias beside it (off: the array's centre from the chip's)."""
        cx, cy = ToMM(u1.GetPosition().x), ToMM(u1.GetPosition().y)
        pins = {p.GetNetname(): (ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)) for p in u1.Pads()}
        for p in self.board.PARTS:
            if not (p.ref.startswith("RN") and p.value == "33"):
                continue
            pts = [pins[p.pins[str(k)]] for k in (1, 2, 3, 4)]
            mx, my = sum(x for x, _ in pts) / 4, sum(y for _, y in pts) / 4
            dx, dy = mx - cx, my - cy
            ox, oy = (0, 1 if dy > 0 else -1) if abs(dy) > abs(dx) else (1 if dx > 0 else -1, 0)
            fp = fps[p.ref]
            x, y = (mx, cy + oy * off) if oy else (cx + ox * off, my)
            fp.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
            for a in (0, 90, 180, 270):
                fp.SetOrientationDegrees(a)
                p1, p8 = pad_pos(fp, "1"), pad_pos(fp, "8")
                inward = (p1[0] - p8[0]) * ox + (p1[1] - p8[1]) * oy < 0
                lined = abs((p1[0] - pts[0][0]) * oy) + abs((p1[1] - pts[0][1]) * ox) < 0.05
                if inward and lined:
                    break
            else:
                raise SystemExit("%s: no rotation lines up with its pins" % p.ref)
            occ.take("F", courtyard(fp))
            self.HAND[p.ref] = None
            # its lines' band, chip to array, kept free
            a_ = [(x_ if oy else y_) for x_, y_ in pts]
            lo, hi, near_, far_ = min(a_) - 0.3, max(a_) + 0.3, 4.95, off - 0.7
            occ.take("F", (lo, cy + near_, hi, cy + far_) if oy > 0 else (lo, cy - far_, hi, cy - near_) if oy else
                     (cx + near_, lo, cx + far_, hi) if ox > 0 else (cx - far_, lo, cx - near_, hi))

    def place_series(self, fps, u1, occ, off=7.6):
        """The 33 R series resistors in a row along each side of the ADV7181D, each across the row,
        its chip end inwards, as near in line with its pin as the pitch allows. A resistor stays
        between the pins on either side of its own that have lines of their own going out (the
        crystal, control lines, escape vias): its line would cross theirs. A run of resistors with
        such pins at both ends packs tighter; one open towards a corner spills that way."""
        cx, cy = ToMM(u1.GetPosition().x), ToMM(u1.GetPosition().y)
        self.place_arrays(fps, u1, occ)
        sides = self.side_pins(u1)
        for side, pins in sides.items():
            for run, lo, hi, step, _ in self.runs(pins):
                t_pins = [pins[r][0] for r in run]
                n = len(run)
                # centred on its pins, then moved inside (lo, hi)
                c = (t_pins[0] + t_pins[-1]) / 2
                ts = [c + (r - (n - 1) / 2) * step for r in range(n)]
                ts = [t + max(0.0, lo - ts[0]) + min(0.0, hi - ts[-1]) for t in ts]
                for (_, net), t in zip([pins[r] for r in run], ts):
                    ref = self.series[net]
                    fp = fps[ref]
                    x, y = {"B": (t, cy + off), "T": (t, cy - off), "L": (cx - off, t), "R": (cx + off, t)}[side]
                    fp.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
                    for a in (0, 90, 180, 270):
                        fp.SetOrientationDegrees(a)
                        inner = [q for q in fp.Pads() if q.GetNetname() == net][0]
                        ix, iy = ToMM(inner.GetPosition().x), ToMM(inner.GetPosition().y)
                        if (ix - x) * (cx - x) + (iy - y) * (cy - y) > 0 and \
                                (abs(ix - x) > 0.1 if side in "LR" else abs(iy - y) > 0.1):
                            break
                    occ.take("F", courtyard(fp))
                    self.HAND[ref] = None
                # the band between the chip and the run, over the run's pins and resistors, is its
                # lines': kept free of other top-side parts
                a_, b_ = min(t_pins + ts) - 0.3, max(t_pins + ts) + 0.3
                near_, far_ = 4.95, off - 1.2
                occ.take("F", {"B": (a_, cy + near_, b_, cy + far_), "T": (a_, cy - far_, b_, cy - near_),
                               "L": (cx - far_, a_, cx - near_, b_), "R": (cx + near_, a_, cx + far_, b_)}[side])

    def u1_after_hand(self, fp, fps, occ):
        # each supply pin's and tied-off pin's escape: out from its side to a via past its
        # neighbours' tips, short of the series rows (1.1 mm from the pin's centre), in front of
        # itself or of a neighbour with no line out of its own (a GND pin, which joins the pad
        # inwards, or an unused one), else further out: of the spots clear of the vias before it,
        # the one that leaves the series resistors most room. Kept free on both sides. A rail's
        # decoupling sits on the bottom by its via
        cx, cy = ToMM(fp.GetPosition().x), ToMM(fp.GetPosition().y)
        self.u1c = cx, cy
        self.band_gnd = set()                    # GND pads the band and PLL blocks give vias of their own
        self.pll_reserve(occ)
        pads = {p.GetNumber(): p for p in fp.Pads() if p.GetNumber()}
        self.rail_vias, self.escape, self.rail_spots = [], {}, {}
        vr = self.escape_via_r
        # (the supply pins first, with their wider tracks; then the others)
        for p in sorted(fp.Pads(), key=lambda p: (p.GetNetname() not in AV_RAILS, int(p.GetNumber() or 0))):
            if p.GetNetname() not in (AV_RAILS - {"AV_PVDD"}) | STATIC_NETS | self.U1_ESCAPE_EXTRA:
                continue
            x, y = ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)
            ux, uy = (0, 1 if y > cy else -1) if abs(y - cy) > abs(x - cx) else (1 if x > cx else -1, 0)
            # in front of itself, or of a neighbour on its side with no line out of its own (a GND
            # pin, which joins the pad inwards, or an unused one), or of none (past the corner);
            # never in front of a neighbour with a line: it would block that line
            spots = []
            for d in (1.1, 1.8):
                spots.append((x + ux * d, y + uy * d))
                for s_ in (0.5, -0.5):
                    v = (x + ux * d - uy * s_, y + uy * d + ux * s_)
                    front = [q for q in pads.values() if q.GetNumber() != "65" and
                             abs(ToMM(q.GetPosition().x) + ux * d - v[0]) < 0.1 and
                             abs(ToMM(q.GetPosition().y) + uy * d - v[1]) < 0.1]
                    if all(q.GetNetname() in ("", "GND") for q in front):
                        spots.append(v)
            # (not beside the crystal pins' lines: they run straight out, see crystal())
            xt = [ToMM2(q) for q in pads.values() if q.GetNetname() in ("XTAL", "XTAL1")]
            spots = [v for v in spots if all(abs((v[0] - qx) * uy) + abs((v[1] - qy) * ux) > 0.6 or
                                            abs((qx - x) * ux + (qy - y) * uy) > 0.1 for qx, qy in xt)]
            # of the free spots, the one that leaves the series-resistor runs most room
            best = None
            for v in spots:
                # (clear of the hand-placed parts, and 0.15 mm from the other escape vias)
                r_ = vr(p.GetNetname())
                box = (v[0] - r_ - 0.05, v[1] - r_ - 0.05, v[0] + r_ + 0.05, v[1] + r_ + 0.05)
                if not (occ.free("F", box) and occ.free("B", box)) or \
                        any(math.hypot(v[0] - o[0], v[1] - o[1]) < r_ + vr(q.GetNetname()) + 0.15
                            for q, _, o in self.rail_vias):
                    continue
                # (its track clear of the vias before it, theirs clear of its via: 0.15 mm)
                w_ = self.escape_w(p.GetNetname())
                knee_ = (x + ux * 0.75, y + uy * 0.75)
                if any(min(seg_dist(o[0], o[1], x, y, *knee_), seg_dist(o[0], o[1], *knee_, *v)) <
                       vr(q.GetNetname()) + w_ / 2 + 0.15 for q, _, o in self.rail_vias) or \
                        any(min(seg_dist(v[0], v[1], *ToMM2(q), *k_), seg_dist(v[0], v[1], *k_, *o)) <
                            r_ + self.escape_w(q.GetNetname()) / 2 + 0.15
                            for q, k_, o in self.rail_vias):
                    continue
                self.escape[p.GetNumber()] = v
                slack = min([r[4] for pins_ in self.side_pins(fp).values() for r in self.runs(pins_)] or [0])
                if best is None or slack > best[0] + 1e-6:
                    best = (slack, v, box)
            self.escape.pop(p.GetNumber(), None)
            if best is None:
                raise SystemExit("U1 pin %s: no escape via spot" % p.GetNumber())
            _, v, box = best
            # (straight out past the neighbours' tips first, then to the via)
            knee = (x + ux * 0.75, y + uy * 0.75)
            self.rail_vias.append((p, knee, v))
            self.escape[p.GetNumber()] = v
            if p.GetNetname() in AV_RAILS | REF_NETS:
                self.rail_spots.setdefault(p.GetNetname(), []).append(v)
            for side in ("F", "B"):
                occ.take(side, box)
        self.band(fps, fp, occ)
        self.pll(fps, occ)
        self.place_series(fps, fp, occ)
        self.crystal(fps, fp, occ)
        ep = pads["65"]
        ep.SetLayerSet(layers(pcbnew.F_Cu, pcbnew.F_Mask))
        ex, ey = ToMM(ep.GetPosition().x), ToMM(ep.GetPosition().y)
        for dx, dy in self.EP_PASTE:
            q = pcbnew.PAD(fp)
            q.SetShape(pcbnew.PAD_SHAPE_RECT)
            q.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            q.SetLayerSet(layers(pcbnew.F_Paste))
            q.SetSize(VECTOR2I(FromMM(1.6), FromMM(1.6)))
            q.SetNumber("")
            fp.Add(q)
            q.SetPosition(VECTOR2I(FromMM(ex + dx), FromMM(ey + dy)))

    def crystal(self, fps, u1, occ):
        """The crystal block, in the lane straight out from XTAL/XTAL1 (pins 22/21) between the
        series rows: the 1 M across the lines just past the rows, the crystal (pads one above the
        other) beyond it, each 33 pF beside its crystal pad, its GND end outwards. The lines are
        laid in fanout() (crystal_lines); the block is kept free of other parts."""
        refs = {}
        for p in self.board.PARTS:
            nets_ = set(p.pins.values())
            if p.ref.startswith("Y") and nets_ & {"XTAL", "XTAL1"}:
                refs["Y"] = p.ref
            elif nets_ == {"XTAL", "XTAL1"}:
                refs["R"] = p.ref
            elif nets_ == {"XTAL", "GND"}:
                refs["CA"] = p.ref
            elif nets_ == {"XTAL1", "GND"}:
                refs["CB"] = p.ref
        pa = [q for q in u1.Pads() if q.GetNetname() == "XTAL"][0]
        pb = [q for q in u1.Pads() if q.GetNetname() == "XTAL1"][0]
        for q in [pa, pb] + [q for q in u1.Pads() if q.GetNetname() in self.ANALOG_NETS]:
            q.SetLocalClearance(FromMM(0.15))           # (its neighbours on the chip are 0.2 mm off)
        (xa, ya), (xb, yb) = ToMM2(pa), ToMM2(pb)
        cx = ToMM(u1.GetPosition().x)
        assert abs(xa - xb) < 0.01 and xa > cx, "the crystal block expects XTAL/XTAL1 on the chip's right side"
        la, lb = ya, yb
        xr = cx + 9.1                                   # the 1 M, past the rows
        xy = xr + 2.35                                  # the crystal's centre (its body clear of the 1 M)
        ym = (la + lb) / 2

        def put(ref, x, y, test):
            f = fps[ref]
            f.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
            for a in (0, 90, 180, 270):
                f.SetOrientationDegrees(a)
                if test(f):
                    break
            else:
                raise SystemExit("%s: no rotation fits" % ref)
            occ.take("F", courtyard(f, 0.1))
            self.HAND[ref] = None
        # the 1 M: pad on XTAL's net above (y smaller), XTAL1's below
        put(refs["R"], xr, ym, lambda f: [ToMM2(q)[1] for q in f.Pads() if q.GetNetname() == "XTAL"][0] <
            [ToMM2(q)[1] for q in f.Pads() if q.GetNetname() == "XTAL1"][0] - 0.5)
        put(refs["Y"], xy, ym, lambda f: [ToMM2(q)[1] for q in f.Pads() if q.GetNetname() == "XTAL"][0] <
            [ToMM2(q)[1] for q in f.Pads() if q.GetNetname() == "XTAL1"][0] - 3)
        ycA = [ToMM2(q)[1] for q in fps[refs["Y"]].Pads() if q.GetNetname() == "XTAL"][0]
        ycB = [ToMM2(q)[1] for q in fps[refs["Y"]].Pads() if q.GetNetname() == "XTAL1"][0]
        for ref, yc, net in ((refs["CA"], ycA, "XTAL"), (refs["CB"], ycB, "XTAL1")):
            put(ref, xy + 2.6, yc, lambda f, net=net: [ToMM2(q)[0] for q in f.Pads() if q.GetNetname() == net][0] <
                [ToMM2(q)[0] for q in f.Pads() if q.GetNetname() == "GND"][0])
        self.xtal = dict(refs=refs, pins=((xa, ya, la, "XTAL"), (xb, yb, lb, "XTAL1")), xr=xr)
        # the block, kept free (the pixel lines from the rows go round it)
        occ.take("F", (xr - 0.6, min(ycA, ycB) - 1.4, xy + 3.7, max(ycA, ycB) + 1.4))

    def crystal_lines(self, b, fps):
        """XTAL and XTAL1, locked: straight out of the pins to the 1 M's pads, on to the crystal's
        pads (the 33 pF caps sit against them, the GND end taking a via)."""
        x_ = self.xtal
        r, y_ = fps[x_["refs"]["R"]], fps[x_["refs"]["Y"]]
        for xp, yp, ly, net in x_["pins"]:
            n = b.FindNet(net)
            rp = ToMM2([q for q in r.Pads() if q.GetNetname() == net][0])
            yc = ToMM2([q for q in y_.Pads() if q.GetNetname() == net][0])
            cap = fps[x_["refs"]["CA" if net == "XTAL" else "CB"]]
            cp = ToMM2([q for q in cap.Pads() if q.GetNetname() == net][0])
            gp = ToMM2([q for q in cap.Pads() if q.GetNetname() == "GND"][0])
            pts = [(xp, yp), (rp[0] - 0.5, ly), rp]
            dy = yc[1] - rp[1]
            pts += [(rp[0] + abs(dy), yc[1]), yc, cp]
            for a_, z_ in zip(pts, pts[1:]):
                if abs(a_[0] - z_[0]) + abs(a_[1] - z_[1]) > 1e-6:
                    self.track(b, a_, z_, 0.15, pcbnew.F_Cu, n)
            g = b.FindNet("GND")
            self.track(b, gp, (gp[0] + 0.7, gp[1]), 0.25, pcbnew.F_Cu, g)
            self.via(b, gp[0] + 0.7, gp[1], g)

    # --- the band above the analog pins ------------------------------------------------------
    #
    # Coordinates (u, v) from the top side's pad ends: u along the side (right +), v away from the
    # chip. The pins: 33 SOG (u +3.75), 34-38 AIN1-AIN5, 39 CAPY1 (+0.75), 40 CAPY2, 41 AVDD, 42
    # REFOUT, 43 CML, 44 CAPC2 (-1.75), 45-48 AIN6-AIN9 (-3.75), 0.5 mm apart. Of the network [DS Fig.
    # 9] only CAPY2 is shared: 10 uF + 0.1 uF + 10 nF to CAPY1, the same to CAPC2, 2 x 0.1 uF to GND.
    # So: REFOUT and CML leave through their escape vias (bottom layer) to their capacitors on the
    # band's left, AVDD to its pin decoupling on the right, and the top layer above the pins is a
    # ladder: CAPC2, CAPY2 and CAPY1 run straight up as three lanes, the CAPC2-CAPY2 caps between the
    # first two, the CAPY1-CAPY2 caps between the last two (10 nF nearest the pins, then 0.1 uF, then
    # 10 uF), CAPY2's two to GND above. The inputs' lines fan out sideways below the band to their
    # coupling caps at its sides: 45-48 to the left (the outermost lowest, nested), 33-38 to the right.
    LADDER = (2.1, 3.1, 4.1)                    # the ladder's rows (v): 10 nF, 0.1 uF, 10 uF
    LANE = {"CAPC2": -1.75, "CAPY2": 0.25, "CAPY1": 2.35}
    LADDER_U = {"CAPC2": -0.75, "CAPY1": 1.3}   # each side's caps' centre
    CAPY1_TURN = 1.35                            # CAPY1 runs right to its lane at this v (over the right inputs)
    GND_ROW = 5.1                                # CAPY2's two caps to GND
    GND_U = (-0.75, 1.3)                         # their centres: GND left, then GND right
    LEFT_ROWS = (2.4, 3.4, 4.4, 5.4)             # REFOUT and CML caps (u -3.5): their node left, GND right
    RIGHT_ROWS = (2.0, 3.0)                      # AVDD's 10 nF and 0.1 uF (u +3.6)
    INPUT_V = 2.4                                # the inputs' coupling caps (upright; the pin's side down)
    FAN_V = (0.4, 0.85, 1.3, 1.75)               # the inputs' turns, outermost pin lowest
    FAN_W = 0.15
    AVDD_VIA = (3.12, 1.4)
    LEFT_INPUT_U = (-5.5, -6.5, -7.5, -8.5)      # pins 45..48's, the innermost pin's nearest
    RIGHT_INPUT_U = (5.6, 6.6, 7.6)              # pins 38..33's used ones, likewise

    def uv(self, u, v):
        return self.u1c[0] + u, self.u1c[1] - 4.9 - v

    def band_parts(self):
        """The band's parts by role: {role: ref}."""
        out = {}
        for p in self.board.PARTS:
            ns = frozenset(p.pins.values())
            for role, nets_ in (("Y1", {"CAPY1", "CAPY2"}), ("C2", {"CAPC2", "CAPY2"}), ("G", {"CAPY2", "GND"}),
                                ("REFOUT", {"REFOUT", "GND"}), ("CML", {"CML", "GND"})):
                if ns == nets_:
                    out.setdefault(role, {}).setdefault(p.value, []).append(p.ref)
            if ns == {"AV_AVDD", "GND"} and p.value in ("100n", "10n"):
                out.setdefault("AVDD", {}).setdefault(p.value, []).append(p.ref)
        return out

    def input_caps(self, u1):
        """The top side's inputs: [(pin, AIN net, cap ref)] left (45-48) and right (33-38) of the
        references, each list from the references outwards."""
        cap = {}
        for p in self.board.PARTS:
            ns = set(p.pins.values())
            if len(ns) == 2 and p.ref.startswith("C") and ns & (self.ANALOG_NETS - {"RCA_L", "RCA_R"}):
                for n in ns:
                    if n.startswith(("AIN_", "SYNC_")):
                        cap[n] = p.ref
        pins = {q.GetNumber(): q.GetNetname() for q in u1.Pads()}
        left = [(n, pins[str(n)], cap[pins[str(n)]]) for n in range(45, 49) if pins.get(str(n)) in cap]
        right = [(n, pins[str(n)], cap[pins[str(n)]]) for n in range(38, 32, -1) if pins.get(str(n)) in cap]
        return left, right

    def band(self, fps, u1, occ):
        """Place the band's parts (see above) and keep the band free of anything else."""
        assert abs(pad_pos(u1, "40")[1] - (self.u1c[1] - 4.5)) < 0.01 and pad_pos(u1, "33")[0] > self.u1c[0], \
            "the band expects the analog side up, pin 33 at the right"
        parts = self.band_parts()

        def put(ref, u, v, axis, low_net):
            """A two-pin part at (u, v): axis "h" with low_net's pad left, "v" with it nearer the chip."""
            f = fps[ref]
            x, y = self.uv(u, v)
            f.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
            for a in ((0, 180) if axis == "h" else (90, 270)):
                f.SetOrientationDegrees(a)
                lo = [ToMM2(q) for q in f.Pads() if q.GetNetname() == low_net][0]
                hi = [ToMM2(q) for q in f.Pads() if q.GetNetname() != low_net][0]
                if (lo[0] < hi[0]) if axis == "h" else (lo[1] > hi[1]):
                    break
            occ.take("F", courtyard(f, 0.05))
            self.HAND[ref] = None
            for q in f.Pads():
                if q.GetNetname() == "GND":
                    self.band_gnd.add("%s.%s" % (ref, q.GetNumber()))
        for side, u, left_net in (("C2", self.LADDER_U["CAPC2"], "CAPC2"), ("Y1", self.LADDER_U["CAPY1"], "CAPY2")):
            for v, val in zip(self.LADDER, ("10n", "100n", "10u")):
                put(parts[side][val][0], u, v, "h", left_net)
        g = parts["G"]["100n"]
        put(g[0], self.GND_U[0], self.GND_ROW, "h", "GND")
        put(g[1], self.GND_U[1], self.GND_ROW, "h", "CAPY2")
        for v, (role, val) in zip(self.LEFT_ROWS, (("REFOUT", "100n"), ("CML", "100n"), ("REFOUT", "10u"), ("CML", "10u"))):
            put(parts[role][val][0], -3.5, v, "h", role)
        for v, val in zip(self.RIGHT_ROWS, ("10n", "100n")):
            put(parts["AVDD"][val][0], 3.6, v, "h", "AV_AVDD")
        left, right = self.input_caps(u1)
        for (pin, net, ref), u in zip(sorted(left), self.LEFT_INPUT_U):
            put(ref, u, self.INPUT_V, "v", net)
        for (pin, net, ref), u in zip(sorted(right, reverse=True), self.RIGHT_INPUT_U):
            put(ref, u, self.INPUT_V, "v", net)
        self.band_inputs = left + right
        # AVDD's rail (its ferrite and 10 uF) by its pin decoupling, the band's right
        self.rail_spots["AV_AVDD"] = [self.uv(3.6, 4.5)]
        # the band, kept free (its lanes, vias, the inputs' fans and caps; their outer pads' lines
        # leave upwards)
        for (ua, va), (ub, vb) in (((-4.9, 6.2), (5.0, 0.0)), ((-9.3, 3.5), (-4.9, -0.1)), ((5.0, 3.5), (8.3, -0.1))):
            x0, y0 = self.uv(ua, va)
            x1, y1 = self.uv(ub, vb)
            occ.take("F", (x0, y0, x1, y1))

    def band_lines(self, b):
        """The band's copper, locked: the ladder's lanes and stubs, the vias and stubs of the
        capacitors at its sides (their nets reach them from the escape vias on the bottom layer, by
        the pre-route)."""
        def net(n):
            return b.FindNet(n)

        def line(n, pts, w=0.25):
            pts = [self.uv(u, v) for u, v in pts]
            for a_, z_ in zip(pts, pts[1:]):
                if abs(a_[0] - z_[0]) + abs(a_[1] - z_[1]) > 1e-6:
                    self.track(b, a_, z_, w, pcbnew.F_Cu, net(n))

        def via(n, u, v):
            x, y = self.uv(u, v)
            self.via(b, x, y, net(n), *self.MIN_VIA)
        top = self.LADDER[-1]
        line("CAPC2", [(self.LANE["CAPC2"], -0.4), (self.LANE["CAPC2"], top)])
        line("CAPY2", [(self.LANE["CAPY2"], -0.4), (self.LANE["CAPY2"], self.GND_ROW)])
        line("CAPY1", [(0.75, -0.4), (0.75, self.CAPY1_TURN), (self.LANE["CAPY1"], self.CAPY1_TURN),
                       (self.LANE["CAPY1"], top)])
        for v in self.LADDER:
            line("CAPC2", [(self.LANE["CAPC2"], v), (self.LADDER_U["CAPC2"] - 0.48, v)])
            line("CAPY2", [(self.LANE["CAPY2"], v), (self.LADDER_U["CAPC2"] + 0.48, v)])
            line("CAPY2", [(self.LANE["CAPY2"], v), (self.LADDER_U["CAPY1"] - 0.48, v)])
            line("CAPY1", [(self.LANE["CAPY1"], v), (self.LADDER_U["CAPY1"] + 0.48, v)])
        line("CAPY2", [(self.LANE["CAPY2"], self.GND_ROW), (self.GND_U[0] + 0.48, self.GND_ROW)])
        line("CAPY2", [(self.LANE["CAPY2"], self.GND_ROW), (self.GND_U[1] - 0.48, self.GND_ROW)])
        for u in (self.GND_U[0] - 0.48, self.GND_U[1] + 0.48):
            line("GND", [(u, self.GND_ROW), (u, self.GND_ROW + 0.75)])
            via("GND", u, self.GND_ROW + 0.75)
        nodes = ("REFOUT", "CML", "REFOUT", "CML")
        for v, n in zip(self.LEFT_ROWS, nodes):
            line(n, [(-3.98, v), (-4.65, v)])
            via(n, -4.65, v)
            line("GND", [(-3.02, v), (-2.35, v)])
            via("GND", -2.35, v)
        line("AV_AVDD", [self.AVDD_VIA, (3.12, self.RIGHT_ROWS[-1])])
        via("AV_AVDD", *self.AVDD_VIA)
        for v in self.RIGHT_ROWS:
            line("GND", [(4.08, v), (4.75, v)])
            via("GND", 4.75, v)

        # REFOUT, CML and AVDD on the bottom layer, from their escape vias to the vias at their caps:
        # REFOUT over the top (v 1.9) to a trunk at u -3.5 between the caps' two via columns, CML under
        # it (v 1.15) to a trunk at u -5.2 outside them, AVDD right (v 0.7)
        def esc(net_):
            (q, _, (x, y)), = [e for e in self.rail_vias if e[0].GetNetname() == net_]
            return x - self.u1c[0], self.u1c[1] - 4.9 - y

        def bline(n, pts):
            pts = [self.uv(u, v) for u, v in pts]
            for a_, z_ in zip(pts, pts[1:]):
                if abs(a_[0] - z_[0]) + abs(a_[1] - z_[1]) > 1e-6:
                    self.track(b, a_, z_, 0.25, pcbnew.B_Cu, net(n))
        ur, vr = esc("REFOUT")
        rows = dict(zip(self.LEFT_ROWS, nodes))
        top_r = max(v for v, n in rows.items() if n == "REFOUT")
        bline("REFOUT", [(ur, vr), (ur, 1.9), (-3.5, 1.9), (-3.5, top_r)])
        for v, n in rows.items():
            if n == "REFOUT":
                bline("REFOUT", [(-3.5, v), (-4.65, v)])
        uc, vc = esc("CML")
        top_c = max(v for v, n in rows.items() if n == "CML")
        bline("CML", [(uc, vc), (uc, 1.15), (-5.2, 1.15), (-5.2, top_c)])
        for v, n in rows.items():
            if n == "CML":
                bline("CML", [(-5.2, v), (-4.65, v)])
        ua, va = esc("AV_AVDD")
        bline("AV_AVDD", [(ua, va), (ua, 0.7), (self.AVDD_VIA[0] - 0.7, 0.7), self.AVDD_VIA])

        # the top side's inputs: up from the pin, sideways at their turn (the outermost lowest), up
        # into their caps' pin-side pads
        left = sorted(self.band_inputs[:len([i for i in self.band_inputs if i[0] >= 45])], reverse=True)
        right = sorted([i for i in self.band_inputs if i[0] < 45])
        for pins_, cols in ((left, self.LEFT_INPUT_U), (right, self.RIGHT_INPUT_U)):
            # (outermost pin first: the lowest turn)
            for (pin, n, ref), v_t, u_c in zip(pins_, self.FAN_V, cols[:len(pins_)][::-1]):
                u_p = 3.75 - (pin - 33) * 0.5
                line(n, [(u_p, -0.4), (u_p, v_t), (u_c, v_t), (u_c, self.INPUT_V - 0.48)], self.FAN_W)

    # --- the PLL block, beside ELPF (30) and PVDD (31) -----------------------------------------
    #
    # The loop filter [DS Fig. 8: 1.69 k + 82 nF in series and 10 nF across, from ELPF to PVDD; "as
    # close to the pin as possible"] and PVDD's decoupling (0.1 uF + 10 nF), laid out beside the pins
    # (w out from the right side's pad ends, z along it as v): the 10 nF straight across the two
    # pins, then the 1.69 k and the 82 nF upright (ELPF_RC between them in a lane), then PVDD's two
    # caps on their sides (PVDD towards the filter, GND out), clear of the crystal block below; a
    # PVDD line over the filter, under the inputs' fan. PVDD takes no escape via (the line is its way
    # to the rest of its rail)
    PLL_W = {"10n": 1.6, "R": 2.8, "82n": 4.0}
    PLL_Z = (-2.38, -1.42)                       # the upright parts' two pads (the pins are at -2.15, -1.65)
    PLL_RAIL = -0.75                             # the PVDD line
    PLL_DECAP = {"P100n": (5.5, -1.3), "P10n": (5.5, -2.3)}

    def pll_reserve(self, occ):
        """The strip in front of ELPF and PVDD, taken before the escape vias are chosen: PD_FB's then
        goes past the corner, not in front of its pin beside PVDD's line. (Only the strip: on the
        placer's 0.25 mm grid a wider box would also take PWRDWN's spot, in front of the unused pin
        28, and PD_FB's past the corner.)"""
        x0, y0 = self.wz(0.0, -1.25)
        x1, y1 = self.wz(1.9, -2.4)
        occ.take("F", (x0, y0, x1, y1))

    def wz(self, w, z):
        return self.uv(4.9 + w, z)

    def pll(self, fps, occ):
        """Place the PLL block (see above)."""
        parts = {}
        for p in self.board.PARTS:
            ns = frozenset(p.pins.values())
            if ns == {"ELPF", "AV_PVDD"}:
                parts["10n"] = p.ref
            elif ns == {"ELPF", "ELPF_RC"}:
                parts["R"] = p.ref
            elif ns == {"ELPF_RC", "AV_PVDD"}:
                parts["82n"] = p.ref
            elif ns == {"AV_PVDD", "GND"} and p.value in ("100n", "10n"):
                parts["P" + p.value] = p.ref
        low = {"10n": "ELPF", "R": "ELPF", "82n": "ELPF_RC"}
        spots = {role: (w, sum(self.PLL_Z) / 2, "v") for role, w in self.PLL_W.items()}
        spots.update({role: (w, z, "h") for role, (w, z) in self.PLL_DECAP.items()})
        for role, (w, z, axis) in spots.items():
            f = fps[parts[role]]
            x, y = self.wz(w, z)
            f.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
            for a in ((90, 270) if axis == "v" else (0, 180)):
                f.SetOrientationDegrees(a)
                if axis == "v":                 # (its low pad nearer the chip's middle: larger y)
                    ok = [ToMM2(q) for q in f.Pads() if q.GetNetname() == low[role]][0][1] > y
                else:                           # (PVDD's pad towards the filter, nearer the chip)
                    ok = [ToMM2(q) for q in f.Pads() if q.GetNetname() == "AV_PVDD"][0][0] < x
                if ok:
                    break
            occ.take("F", courtyard(f, 0.05))
            self.HAND[parts[role]] = None
            for q in f.Pads():
                if q.GetNetname() == "GND":
                    self.band_gnd.add("%s.%s" % (parts[role], q.GetNumber()))
        x0, y0 = self.wz(0.3, self.PLL_RAIL + 0.3)
        x1, y1 = self.wz(7.0, self.PLL_Z[0] - 0.34)
        occ.take("F", (x0, y0, x1, y1))
        # PVDD's rail (ferrite, 10 uF) by the block's far end
        self.rail_spots["AV_PVDD"] = [self.wz(7.5, -1.9)]

    def pll_lines(self, b):
        """The PLL block's copper, locked."""
        def line(n, pts, w=0.2):
            pts = [self.wz(*q) for q in pts]
            for a_, z_ in zip(pts, pts[1:]):
                if abs(a_[0] - z_[0]) + abs(a_[1] - z_[1]) > 1e-6:
                    self.track(b, a_, z_, w, pcbnew.F_Cu, b.FindNet(n))
        lo, hi = self.PLL_Z
        W = self.PLL_W
        line("ELPF", [(-0.4, -2.15), (W["10n"], -2.15), (W["10n"], lo), (W["R"], lo)])
        line("AV_PVDD", [(-0.4, -1.65), (W["10n"] - 0.5, -1.65), (W["10n"], hi)], 0.25)
        line("ELPF_RC", [(W["R"], hi), ((W["R"] + W["82n"]) / 2, hi), ((W["R"] + W["82n"]) / 2, lo), (W["82n"], lo)])
        d = self.PLL_DECAP
        wp = d["P100n"][0] - 0.48                # the decaps' PVDD pads
        line("AV_PVDD", [(W["10n"], hi), (W["10n"], self.PLL_RAIL), (wp, self.PLL_RAIL), (wp, d["P10n"][1])], 0.25)
        line("AV_PVDD", [(W["82n"], self.PLL_RAIL), (W["82n"], hi)], 0.25)
        g = b.FindNet("GND")
        for w, z in d.values():
            line("GND", [(w + 0.48, z), (w + 1.1, z)], 0.25)
            x, y = self.wz(w + 1.1, z)
            self.via(b, x, y, g, *self.MIN_VIA)

    def u1_fanout_skip(self):
        """U1 and the band's GND pads (band_lines gives them their vias)."""
        return {"U1"} | getattr(self, "band_gnd", set())

    def escape_via_r(self, net):
        """An escape via's radius (SMALL_ESCAPE's: the smallest via the rules allow)."""
        return self.MIN_VIA[0] / 2 if net in self.SMALL_ESCAPE else self.VIA_D / 2

    def escape_w(self, net):
        """An escape track's width: the supplies' and references' 0.25 mm, the rest the default."""
        return 0.25 if net in AV_RAILS | REF_NETS else self.TRACK

    def esd_clearance(self, fps):
        """The video inputs' ESD parts' pads (0.2-0.24 mm apart, inside the ANALOG class's 0.25 mm)
        at a local 0.15 mm."""
        for p in self.board.PARTS:
            if self.esd(p) and set(p.pins.values()) & self.ANALOG_NETS:
                for q in fps[p.ref].Pads():
                    q.SetLocalClearance(FromMM(0.15))

    def u1_anchor(self, p, ic_pads):
        """Where the ADV7181D's rail, reference and control-line parts go (None: p is not one of
        them)."""
        # the control lines' pull resistors (I2C, reset) at the lines' far end, the FPGA's: by the chip
        # they sat in the ADC references' corner, and the lines, walled in there, did not route (rev
        # B), or ran among the references (rev C)
        ctl = [n for n in p.pins.values() if n in CONTROL_NETS]
        if ctl and p.ref.startswith("R"):
            return [(x, y) for x, y, r in ic_pads[ctl[0]] if r in self.FPGA_HEADERS][0], "F"
        nets_ = [n for n in p.pins.values() if n != "GND"]
        if not nets_ or not all(n in AV_RAILS for n in nets_) and not (
                p.ref.startswith("FB") and nets_[-1] in AV_RAILS):
            return None
        rail = [n for n in nets_ if n in AV_RAILS][0]
        if p.ref.startswith("C") and p.value in ("100n", "10n"):
            # per-pin decoupling, round robin over the rail's pins (the 100 nF of a pair first), on
            # the top by the pin's escape via: all SMT parts on one side, one assembly pass. The
            # band between the chip and its series rows is the pixel lines' (kept free), so they
            # sit at the chip's corners, its analog side or past the rows
            spots = self.rail_spots.get(rail) or [(x, y) for x, y, r in ic_pads[rail] if r == "U1"]
            k = self.rr.get(rail, 0)
            self.rr[rail] = k + 1
            return spots[(k // 2) % len(spots)], "F"
        # the rail's ferrite and its 10 uF: at the chip too, after its pins' decoupling
        return (self.rail_spots.get(rail) or [(x, y) for x, y, r in ic_pads[rail] if r == "U1"])[0], "F"

    def u1_where(self, p, fps):
        nets_ = set(p.pins.values()) - {"GND"}
        if nets_ & self.BAND_NETS or (nets_ == {"AV_AVDD"} and p.value in ("100n", "10n")):
            return None
        u1 = fps["U1"]
        cx, cy = ToMM(u1.GetPosition().x), ToMM(u1.GetPosition().y)
        band = (cx - 4.9, cy - 11.0, cx + 5.0, cy - 4.95)

        def where(box):
            return not (box[2] > band[0] and box[0] < band[2] and box[3] > band[1] and box[1] < band[3])
        return where

    def u1_rank(self, p):
        nets_ = set(p.pins.values()) - {"GND"}
        if nets_ and nets_ <= AV_RAILS and p.ref.startswith("C") and p.value == "100n":
            return -1               # (each supply pin's 100 nF before everything, nearest its via)
        if nets_ and nets_ <= AV_RAILS and p.ref.startswith("C") and p.value == "10n":
            return 1
        if nets_ & AV_RAILS and (p.ref.startswith("FB") or (p.ref.startswith("C") and p.value == "10u")) \
                and not nets_ & self.BIAS_NETS:
            return 3
        return None

    def fanout_u1(self, b, fps):
        """The exposed pad's ground vias, and the four GND pins joined to the pad on F.Cu."""
        u1 = fps["U1"]
        ep = [p for p in u1.Pads() if p.GetNumber() == "65"][0]
        cx, cy = ToMM(ep.GetPosition().x), ToMM(ep.GetPosition().y)
        for dx, dy in self.EP_VIAS:
            self.via(b, cx + dx, cy + dy, ep.GetNet())
        for p in u1.Pads():
            if p.GetNetname() == "GND" and p.GetNumber() != "65" and p.GetNumber():
                x, y = ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)
                # straight in from the pin's side (along the pin, clear of its neighbours) to 0.5 mm
                # inside the pad's edge
                ux, uy = (0, 1 if cy > y else -1) if abs(cy - y) > abs(cx - x) else (1 if cx > x else -1, 0)
                self.track(b, (x, y), (x + ux * 1.4, y + uy * 1.4), 0.2, pcbnew.F_Cu, p.GetNet())
        for p, knee, (vx, vy) in self.rail_vias:
            x, y = ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)
            w = self.escape_w(p.GetNetname())
            self.track(b, (x, y), knee, w, pcbnew.F_Cu, p.GetNet())
            if abs(knee[0] - vx) + abs(knee[1] - vy) > 1e-6:
                self.track(b, knee, (vx, vy), w, pcbnew.F_Cu, p.GetNet())
            if p.GetNetname() in self.SMALL_ESCAPE:
                self.via(b, vx, vy, p.GetNet(), *self.MIN_VIA)
            else:
                self.via(b, vx, vy, p.GetNet())
        self.band_lines(b)
        self.pll_lines(b)
        print("U1 fanout: %d exposed-pad vias, %d pin escape vias" % (len(self.EP_VIAS), len(self.rail_vias)))
