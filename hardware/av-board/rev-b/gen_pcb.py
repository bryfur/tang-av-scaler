#!/usr/bin/env python3
"""Rev B's PCB: the ADV7181D (64-lead LFCSP) board, four layers. The generator is kit/pcbkit.py;
this is rev B's outline, hand placement and the ADV7181D's own rules: its rotation (analog side
up, towards the jacks; pixel side down, towards J10), its decoupling round its supply pins, its
exposed pad (thermal vias, a paste grid).

    python3 rev-b/gen_pcb.py [--route]       (see kit/pcbkit.py)
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "kit"))
import board  # noqa: E402
import pcbkit  # noqa: E402
import pcbnew  # noqa: E402
from pcbkit import courtyard, fit_adv7511, fit_esd, pad_pos, seg_dist  # noqa: E402
from pcbnew import VECTOR2I, FromMM, ToMM  # noqa: E402

AV_RAILS = {"AV_DVDD", "AV_PVDD", "AV_AVDD", "AV_DVDDIO"}
# the ADV7181D's pins tied off through a resistor (no signal): an escape via each, like a supply pin
STATIC_NETS = {"ALSB", "PWRDWN", "PD_FB", "PD_HS_IN_CS_IN", "PD_VS_IN"}


def ToMM2(p):
    return ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)


def layers(*ids):
    s = pcbnew.LSET()
    for i in ids:
        s.AddLayer(i)
    return s


def fit_u1(fp, x, y):
    """Analog side (AIN6-AIN10, pins 33-49) up, towards the jacks' row; pins 1-16 (most of the
    pixel port) down, towards J10: AIN10 (pin 49) at the top left."""
    p49, p8 = pad_pos(fp, "49"), pad_pos(fp, "8")
    return p49[0] < x - 3 and p49[1] < y - 3 and p8[1] > y + 3


class RevB(pcbkit.Layout):
    # F.Cu signal / In1 GND / In2 GND / B.Cu signal (JLC04161H-7628): each signal layer 0.21 mm over
    # its own solid plane, so tracks on either side have the same controlled impedance and return
    # path [HWG 7.2: a solid reference under the pixel clock; 6.3.2: 100 R TMDS pairs]
    LAYERS = 4
    INNER_GND = True
    # the TMDS pairs at the ADV7511's own 0.5 mm pin pitch: 0.25 mm lines, 0.25 mm gap, 103 R
    # differential over 0.21 mm of 7628 (IPC-2141; confirm in JLCPCB's calculator)
    TMDS_W, TMDS_PAIR = 0.25, (0.25, 0.25)
    # (0.4/0.2 mm vias at the ESD arrays' GND pads, between the pairs; JLCPCB's four-layer minimum
    # is 0.3/0.15)
    MIN_VIA = (0.4, 0.2)
    POWER_NETS = {"+5V", "3V6", "3V3", "1V8A", "1V8B", "5VA", "HDMI_5V", "SW_3V6", "TX_DVDD", "TX_AVDD", "TX_PLVDD"} | AV_RAILS
    CLOCK_NETS = {"OUT_CLK", "AV_LLC", "IN_LLC"}
    TMDS_NETS = {"TMDS_D2_P", "TMDS_D2_N", "TMDS_D1_P", "TMDS_D1_N", "TMDS_D0_P", "TMDS_D0_N", "TMDS_CK_P", "TMDS_CK_N"}
    # Rev A's outline: the Console's, plus 15 mm past its left edge for the jacks
    X0, Y0, X1, Y1 = 74.2, 20.6, 168.8, 90.0
    # Hand placement: ref -> (x, y, angle, side).  angle in degrees (KiCad: counter-clockwise).
    HAND = {
        "J9": (129.0, 30.0, 180, "B"),
        "J10": (129.0, 79.0, 0, "B"),
        # RCA jacks on the left edge, facing left, as on rev A: audio at the top, video below
        "J4": (85.2, 29.3, 90, "F"), "J5": (85.2, 42.3, 90, "F"),
        "J1": (85.2, 55.3, 90, "F"), "J2": (85.2, 68.3, 90, "F"), "J3": (85.2, 81.3, 90, "F"),
        # ADV7181D above J10's data end: its left side's lines (control, Y7-Y4, DE, VS) go to J10
        # pins 1-10 below its left, its bottom side's (INT, HS, Y3-Y0, C7-C5) to pins 13-19 under
        # it, its right side's (C4-C0, LLC) to pins 20-26 below its right; the analog inputs leave
        # its top towards the video jacks
        "U1": (116.0, 63.0, None, "F"),
        "U3": (95.0, 37.5, 0, "F"),          # PCM1808 beside the audio jacks
        # ADV7511 below J9's data end, data side up, TMDS side down towards the HDMI connector; the
        # band between it and J9 is its bus's (see board.J9_NET)
        "U2": (148.0, 47.0, None, "F"),
        # the supplies in a row below the TMDS corridor, above J10: 1V8A nearest the ADV7181D,
        # 1V8B under the ADV7511, 3V3, and the buck furthest right, away from the analog side and
        # the TMDS lines
        "U6": (137.0, 68.5, 0, "F"), "U7": (143.5, 68.5, 0, "F"),
        "U5": (150.0, 68.5, 0, "F"), "U4": (156.5, 70.0, 0, "F"),
        "J6": (163.6, 62.0, 90, "F"),
        # TMDS ESD, in line before the HDMI pads (pins 1-12 at x 160.2, y 57.5-63)
        "U9": (156.3, 58.75, None, "F"), "U10": (156.3, 61.75, None, "F"),
        # the scaler's buttons, bottom right (near J10 pins 31/32)
        "SW1": (164.0, 76.0, 0, "F"), "SW2": (164.0, 86.0, 0, "F"),
    }
    # room kept free of small parts for routing, both sides: the J10 bus's fan-out, from under the
    # ADV7181D's series resistors to J10's pins 1-26
    # and the TMDS corridor, from under the ADV7511's TMDS pins to the HDMI connector (the pairs are
    # laid there before routing, see tmds())
    RESERVED = [(103.8, 72.4, 136.6, 76.9), (144.55, 55.4, 158.9, 63.6)]
    KEEP = {"U1": 0.5}
    BOTH_SIDES = {"U1", "U2"}       # (under U1: its exposed pad's vias)
    # the loop filter, the ADC references' caps, the bias resistor and the regulators' feedback
    # dividers, placed before the decoupling takes their room: short traces [DS Fig. 8, Fig. 9;
    # HWG 7.6; TI TPS7A70, TLV62569 layout]
    BIAS_NETS = {"ELPF", "ELPF_RC", "CAPY1", "CAPY2", "CAPC2", "REFOUT", "CML", "R_EXT",
                 "FB_3V3", "FB_3V6", "FB_1V8A", "FB_1V8B"}
    BUSES = [("J10", "U1"), ("J9", "U2")]
    SILK_LABELS = [("J1", "Y"), ("J2", "Pb"), ("J3", "Pr"), ("J4", "L"), ("J5", "R")]
    SILK_NEAR = [("J6", "HDMI")]
    # The exposed pad: paste in a 3 x 3 grid of 1.6 mm squares (about half the pad: a full 7.1 mm
    # aperture floats the part), 12 ground vias in the lanes between them
    EP_PASTE = [(dx, dy) for dx in (-2.3, 0.0, 2.3) for dy in (-2.3, 0.0, 2.3)]
    EP_VIAS = [(dx, dy) for dx in (-1.15, 1.15) for dy in (-2.3, 0.0, 2.3)] + \
              [(dx, dy) for dx in (-2.3, 0.0, 2.3) for dy in (-1.15, 1.15)]

    def __init__(self):
        super().__init__(board, HERE)
        self.FIT = {"U1": fit_u1, "U2": fit_adv7511, "U9": fit_esd, "U10": fit_esd}
        self.rr = {}                # decoupling round robin over a rail's pins
        self.series = {[n for n in p.pins.values() if n.startswith("AV_")][0]: p.ref
                       for p in board.PARTS if p.ref.startswith("R") and not p.ref.startswith("RN") and p.value == "33"}
        self.escape = {}
        self.array_nets = {n for p in board.PARTS if p.ref.startswith("RN") for n in p.pins.values() if n.startswith("AV_")}

    # --- hooks

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
        for p in board.PARTS:
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

    def after_hand(self, ref, fp, fps, occ):
        if ref != "U1":
            return
        # each supply pin's and tied-off pin's escape: out from its side to a via past its
        # neighbours' tips, short of the series rows (1.1 mm from the pin's centre), in front of
        # itself or of a neighbour with no line out of its own (a GND pin, which joins the pad
        # inwards, or an unused one), else further out: of the spots clear of the vias before it,
        # the one that leaves the series resistors most room. Kept free on both sides. A rail's
        # decoupling sits on the bottom by its via
        cx, cy = ToMM(fp.GetPosition().x), ToMM(fp.GetPosition().y)
        pads = {p.GetNumber(): p for p in fp.Pads() if p.GetNumber()}
        self.rail_vias, self.escape, self.rail_spots = [], {}, {}
        # (the supply pins first, with their wider tracks; then the tied-off pins)
        for p in sorted(fp.Pads(), key=lambda p: (p.GetNetname() not in AV_RAILS, int(p.GetNumber() or 0))):
            if p.GetNetname() not in AV_RAILS | STATIC_NETS:
                continue
            x, y = ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)
            ux, uy = (0, 1 if y > cy else -1) if abs(y - cy) > abs(x - cx) else (1 if x > cx else -1, 0)
            n = int(p.GetNumber())
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
            # of the free spots, the one that leaves the series-resistor runs most room
            best = None
            for v in spots:
                # (clear of the hand-placed parts, and 0.65 mm from the other escape vias' centres:
                # 0.5 mm vias with the 0.127 mm clearance between them)
                box = (v[0] - 0.3, v[1] - 0.3, v[0] + 0.3, v[1] + 0.3)
                if not (occ.free("F", box) and occ.free("B", box)) or \
                        any(math.hypot(v[0] - w[0], v[1] - w[1]) < 0.65 for k, w in self.escape.items() if k != p.GetNumber()):
                    continue
                # (its track clear of the vias before it, theirs clear of its via: 0.15 mm)
                w_ = 0.25 if p.GetNetname() in AV_RAILS else self.TRACK
                knee_ = (x + ux * 0.75, y + uy * 0.75)
                if any(min(seg_dist(o[0], o[1], x, y, *knee_), seg_dist(o[0], o[1], *knee_, *v)) < 0.25 + w_ / 2 + 0.15
                       for _, _, o in self.rail_vias) or \
                        any(min(seg_dist(v[0], v[1], *ToMM2(q), *k_), seg_dist(v[0], v[1], *k_, *o)) <
                            0.25 + (0.25 if q.GetNetname() in AV_RAILS else self.TRACK) / 2 + 0.15
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
            if p.GetNetname() in AV_RAILS:
                self.rail_spots.setdefault(p.GetNetname(), []).append(v)
            for side in ("F", "B"):
                occ.take(side, box)
        self.place_series(fps, fp, occ)
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

    def anchor_special(self, p, ic_pads, fps):
        if p.ref == "D1":                   # (the 1V8A-to-3V3 clamp: at the 1V8A LDO's output)
            return [(x, y) for x, y, r in ic_pads["1V8A"] if r == "U6"][0], "F"
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
            spots = self.rail_spots[rail]
            k = self.rr.get(rail, 0)
            self.rr[rail] = k + 1
            return spots[(k // 2) % len(spots)], "F"
        # the rail's ferrite and its 10 uF: at the chip too, after its pins' decoupling
        return self.rail_spots[rail][0], "F"

    def rank_special(self, p, ic_pads):
        if p.ref == "D1":
            return 0
        nets_ = set(p.pins.values()) - {"GND"}
        if nets_ and nets_ <= AV_RAILS and p.ref.startswith("C") and p.value == "100n":
            return -1               # (each supply pin's 100 nF before everything, nearest its via)
        if nets_ and nets_ <= AV_RAILS and p.ref.startswith("C") and p.value == "10n":
            return 1
        if nets_ & AV_RAILS and (p.ref.startswith("FB") or (p.ref.startswith("C") and p.value == "10u")) \
                and not nets_ & self.BIAS_NETS:
            return 3
        return None

    def checks(self, fps):
        # the jacks open to the left edge, U2's data side faces J9 (above it), HDMI at the right
        for ref in ("J1", "J2", "J3", "J4", "J5"):
            bx = courtyard(fps[ref], 0)
            assert bx[0] < self.X0 + 1.5, (ref, bx)
        assert fit_adv7511(fps["U2"], ToMM(fps["U2"].GetPosition().x), ToMM(fps["U2"].GetPosition().y)), "U2 rotation"
        assert courtyard(fps["J6"], 0)[2] > self.X1 - 1.5, "HDMI not at the right edge"

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
            w = 0.25 if p.GetNetname() in AV_RAILS else self.TRACK
            self.track(b, (x, y), knee, w, pcbnew.F_Cu, p.GetNet())
            if abs(knee[0] - vx) + abs(knee[1] - vy) > 1e-6:
                self.track(b, knee, (vx, vy), w, pcbnew.F_Cu, p.GetNet())
            self.via(b, vx, vy, p.GetNet())
        print("U1 fanout: %d exposed-pad vias, %d pin escape vias" % (len(self.EP_VIAS), len(self.rail_vias)))

    # The TMDS pairs: pair, the ADV7511's P and N pins, the ESD array and its P and N pads in and
    # out (flow-through), the connector's P and N pins
    TMDS = [("D2", "43", "42", "U9", "1", "10", "2", "9", "1", "3"),
            ("D1", "40", "39", "U9", "4", "7", "5", "6", "4", "6"),
            ("D0", "36", "35", "U10", "1", "10", "2", "9", "7", "9"),
            ("CK", "33", "32", "U10", "4", "7", "5", "6", "10", "12")]
    # the ADV7511 pins between the pairs: out inwards, under the package, to a via each
    # (pin: via's distance in from the pad's centre); the ESD arrays' GND pads (between the
    # pairs): a small via beside each
    U2_INWARD = {"34": 1.7, "37": 1.7, "38": 2.4, "41": 1.7}
    SMALL_VIA = (0.4, 0.2)

    def tmds(self, b, fps):
        """The TMDS pairs, locked, on F.Cu (over In1), at the class's 0.25 mm: straight out of the
        ADV7511's pads, a 45-degree corner, straight on to the ESD array, across its flow-through
        pads, then to the connector. The lines nest (the pair nearest the array turns first);
        each corner is cut so that the spacing to the line inside it stays what it is on the
        straight parts, so a pair stays coupled through the bend."""
        def pos(ref, num):
            return pad_pos(fps[ref], num)
        lines = []
        for pr, up, un, u, pi, po, ni, no, jp, jn in self.TMDS:
            for s_, upin, ein, eout, jpin in (("P", up, pi, po, jp), ("N", un, ni, no, jn)):
                lines.append(("TMDS_%s_%s" % (pr, s_), pos("U2", upin), pos(u, ein), pos(u, eout), pos("J6", jpin)))
        lines.sort(key=lambda ln: -ln[1][0])            # the innermost (rightmost on the ADV7511) first
        c_prev, prev = None, None
        w = self.TMDS_W
        for name, (x0, y0), (xi, yi), (xo, yo), (xj, yj) in lines:
            if prev is None:
                d = 0.6
                c = x0 - yi + d
            else:
                sp = ((prev[0] - x0) + (yi - prev[1])) / 2      # its spacing to the line inside it
                c = c_prev - math.sqrt(2) * sp
                d = c - x0 + yi
            assert 0 < d < min(yi - y0, xi - x0), (name, d)
            net = b.FindNet(name)
            pts = [(x0, y0), (x0, yi - d), (x0 + d, yi), (xi, yi), (xo, yo)]
            # to the connector: straight on, then 45 degrees onto its pin's line
            dy = yj - yo
            xk = xj - 1.4 - abs(dy)
            pts += [(xk, yo), (xk + abs(dy), yj), (xj, yj)]
            for a_, z_ in zip(pts, pts[1:]):
                if abs(a_[0] - z_[0]) + abs(a_[1] - z_[1]) > 1e-6:
                    self.track(b, a_, z_, w, pcbnew.F_Cu, net)
            c_prev, prev = c, (x0, yi)
        print("TMDS: %d lines laid" % len(lines))

    def fanout(self, b, fps):
        self.fanout_u1(b, fps)
        u2 = fps["U2"]
        cy2 = ToMM(u2.GetPosition().y)
        for num, dist in self.U2_INWARD.items():
            p = [q for q in u2.Pads() if q.GetNumber() == num][0]
            x, y = ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)
            v = (x, y - dist if y > cy2 else y + dist)
            self.track(b, (x, y), v, 0.25 if p.GetNetname() != "OUT_PD" else self.TRACK, pcbnew.F_Cu, p.GetNet())
            self.via(b, v[0], v[1], p.GetNet())
        for u in ("U9", "U10"):
            fp = fps[u]
            cx_ = ToMM(fp.GetPosition().x)
            for num in ("3", "8"):
                p = [q for q in fp.Pads() if q.GetNumber() == num][0]
                x, y = ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)
                v = (x + (0.55 if x > cx_ else -0.55), y)
                self.track(b, (x, y), v, 0.25, pcbnew.F_Cu, p.GetNet())
                self.via(b, v[0], v[1], p.GetNet(), *self.SMALL_VIA)
        self.tmds(b, fps)

    def fanout_skip(self):
        return {"U1", "U2.37", "U9.3", "U9.8", "U10.3", "U10.8"}


LAYOUT = RevB()

if __name__ == "__main__":
    LAYOUT.cli(sys.argv)
