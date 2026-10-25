#!/usr/bin/env python3
"""Rev B's PCB: the ADV7181D (64-lead LFCSP) board, four layers. The generator is kit/pcbkit.py;
this is rev B's outline, hand placement and the ADV7181D's own rules: its rotation (analog side
up, towards the jacks; pixel side down, towards J10), its decoupling round its supply pins, its
exposed pad (thermal vias, a paste grid).

    python3 rev-b/gen_pcb.py [--route]       (see kit/pcbkit.py)
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "kit"))
import board  # noqa: E402
import pcbkit  # noqa: E402
import pcbnew  # noqa: E402
from pcbkit import courtyard, fit_adv7511, fit_esd, pad_pos  # noqa: E402
from pcbnew import VECTOR2I, FromMM, ToMM  # noqa: E402

AV_RAILS = {"AV_DVDD", "AV_PVDD", "AV_AVDD", "AV_DVDDIO"}


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
    LAYERS = 4
    POWER_NETS = {"+5V", "3V3", "2V5", "1V8A", "1V8B", "5VA", "HDMI_5V", "SW_2V5", "TX_DVDD", "TX_AVDD", "TX_PLVDD"} | AV_RAILS
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
        # the supplies under it, clear of both buses and of the TMDS lines (rev A's places)
        "U7": (142.5, 63.0, 0, "F"), "U6": (142.5, 71.0, 0, "F"),
        "U5": (149.0, 65.0, 0, "F"), "U4": (148.5, 74.0, 0, "F"),
        "J6": (163.6, 62.0, 90, "F"),
        # TMDS ESD, in line before the HDMI pads (pins 1-12 at x 160.2, y 57.5-63)
        "U9": (156.3, 58.75, None, "F"), "U10": (156.3, 61.75, None, "F"),
        # the scaler's buttons, bottom right (near J10 pins 31/32)
        "SW1": (164.0, 76.0, 0, "F"), "SW2": (164.0, 86.0, 0, "F"),
    }
    # room kept free of small parts for routing, both sides: the J10 bus's fan-out, from under the
    # ADV7181D's series resistors to J10's pins 1-26
    RESERVED = [(103.8, 72.4, 136.6, 76.9)]
    KEEP = {"U1": 0.5}
    BOTH_SIDES = {"U1", "U2"}       # (under U1: its exposed pad's vias)
    # the loop filter, the ADC references' caps, the bias resistor and the regulators' feedback
    # dividers, placed before the decoupling takes their room: short traces [DS Fig. 8, Fig. 9;
    # HWG 7.6; TI TPS7A70, TLV62569 layout]
    BIAS_NETS = {"ELPF", "ELPF_RC", "CAPY1", "CAPY2", "CAPC2", "REFOUT", "CML", "R_EXT",
                 "FB_3V3", "FB_2V5", "FB_1V8A", "FB_1V8B"}
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

    # --- hooks

    def place_series(self, fps, u1, occ, off=6.6, pitch=1.1):
        """The 33 R series resistors in a row along each side of the ADV7181D, each in line with
        its pin (spread to pitch where pins are closer), across the row, its chip end inwards."""
        cx, cy = ToMM(u1.GetPosition().x), ToMM(u1.GetPosition().y)
        pins = {p.GetNetname(): (ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)) for p in u1.Pads()}
        rows = {}
        for p in board.PARTS:
            if p.ref.startswith("R") and p.value == "33":
                near = [n for n in p.pins.values() if n in pins][0]
                px, py = pins[near]
                dx, dy = px - cx, py - cy
                side = ("B" if dy > 0 else "T") if abs(dy) > abs(dx) else ("R" if dx > 0 else "L")
                rows.setdefault(side, []).append((px if side in "TB" else py, p.ref, near))
        for side, row in rows.items():
            row.sort()
            ts = [t for t, _, _ in row]
            for _ in range(50):                 # at least pitch apart, in order
                for k in range(1, len(ts)):
                    if ts[k] - ts[k - 1] < pitch:
                        d = (pitch - (ts[k] - ts[k - 1])) / 2
                        ts[k - 1] -= d
                        ts[k] += d
            for (_, ref, near), t in zip(row, ts):
                fp = fps[ref]
                x, y = {"B": (t, cy + off), "T": (t, cy - off), "L": (cx - off, t), "R": (cx + off, t)}[side]
                fp.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
                for a in (0, 90, 180, 270):
                    fp.SetOrientationDegrees(a)
                    inner = [q for q in fp.Pads() if q.GetNetname() == near][0]
                    ix, iy = ToMM(inner.GetPosition().x), ToMM(inner.GetPosition().y)
                    if (ix - x) * (cx - x) + (iy - y) * (cy - y) > 0 and \
                            (abs(ix - x) > 0.1 if side in "LR" else abs(iy - y) > 0.1):
                        break
                occ.take("F", courtyard(fp))
                self.HAND[ref] = None

    def after_hand(self, ref, fp, fps, occ):
        if ref != "U1":
            return
        self.place_series(fps, fp, occ)
        ep = [p for p in fp.Pads() if p.GetNumber() == "65"][0]
        ep.SetLayerSet(layers(pcbnew.F_Cu, pcbnew.F_Mask))
        cx, cy = ToMM(ep.GetPosition().x), ToMM(ep.GetPosition().y)
        for dx, dy in self.EP_PASTE:
            p = pcbnew.PAD(fp)
            p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetLayerSet(layers(pcbnew.F_Paste))
            p.SetSize(VECTOR2I(FromMM(1.6), FromMM(1.6)))
            p.SetNumber("")
            fp.Add(p)
            p.SetPosition(VECTOR2I(FromMM(cx + dx), FromMM(cy + dy)))

    def anchor_special(self, p, ic_pads, fps):
        nets_ = [n for n in p.pins.values() if n != "GND"]
        if not nets_ or not all(n in AV_RAILS for n in nets_) and not (
                p.ref.startswith("FB") and nets_[-1] in AV_RAILS):
            return None
        rail = [n for n in nets_ if n in AV_RAILS][0]
        pins = [(x, y) for x, y, r in ic_pads.get(rail, []) if r == "U1"]
        if p.ref.startswith("C") and p.value in ("100n", "10n"):
            # per-pin decoupling, round robin over the rail's pins (the 100 nF of a pair first), on
            # the bottom right under its pin: the top round the chip is the pixel lines' (a via
            # beside the pin takes it down)
            k = self.rr.get(rail, 0)
            self.rr[rail] = k + 1
            return pins[(k // 2) % len(pins)], "B"
        # the rail's ferrite and its 10 uF: at the chip too, after its pins' decoupling
        return pins[0], "F"

    def rank_special(self, p, ic_pads):
        nets_ = set(p.pins.values()) - {"GND"}
        if nets_ and nets_ <= AV_RAILS and p.ref.startswith("C") and p.value in ("100n", "10n"):
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

    def fanout(self, b, fps):
        """The exposed pad's ground vias, and the four GND pins joined to the pad on F.Cu."""
        u1 = fps["U1"]
        ep = [p for p in u1.Pads() if p.GetNumber() == "65"][0]
        cx, cy = ToMM(ep.GetPosition().x), ToMM(ep.GetPosition().y)
        for dx, dy in self.EP_VIAS:
            self.via(b, cx + dx, cy + dy, ep.GetNet())
        for p in u1.Pads():
            if p.GetNetname() == "GND" and p.GetNumber() != "65" and p.GetNumber():
                x, y = ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)
                # inwards, to 0.5 mm inside the pad's edge
                ux, uy = cx - x, cy - y
                d = (ux * ux + uy * uy) ** 0.5
                self.track(b, (x, y), (x + ux / d * 1.4, y + uy / d * 1.4), 0.2, pcbnew.F_Cu, p.GetNet())
        print("U1 fanout: %d exposed-pad vias" % len(self.EP_VIAS))

    def fanout_skip(self):
        return {"U1"}


LAYOUT = RevB()

if __name__ == "__main__":
    LAYOUT.cli(sys.argv)
