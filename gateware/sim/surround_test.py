#!/usr/bin/env python3
"""surround_test.py: sw/surround.c on a PC: five channels mixed down to two the way a game's
Pro Logic II setting does it (the published matrix; the surrounds a quarter turn late), decoded,
and what comes out of each channel measured: a sound in one channel must come out of that one, a
sound between two neighbours out of those two as it went in, and two channels with nothing in
common as the plain matrix gives them."""
import math
import os
import random
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build")
FS = 48000
N = FS // 2
NAMES = ["L", "R", "C", "LFE", "Ls", "Rs"]
MAIN = r"""
#include <stdio.h>
#include <stdint.h>
#include "surround.h"
int main(void)
{
    int32_t in[2], out[6];
    surround_reset();
    while (fread(in, 4, 2, stdin) == 2) {
        surround(in[0], in[1], out);
        fwrite(out, 4, 6, stdout);
    }
    return 0;
}
"""


class Sound:
    """a sound as its tones (frequency, phase): it and its copy a quarter turn late are both
    known exactly"""

    def __init__(self, seed, amp=0.1, tones=16):
        rng = random.Random(seed)
        self.tones = [(math.exp(rng.uniform(math.log(100), math.log(8000))), rng.uniform(0, 2 * math.pi))
                      for _ in range(tones)]
        self.amp = amp * 0x7FFFFF * math.sqrt(2.0 / tones)

    def samples(self, late=False):
        out = [0.0] * N
        for hz, ph in self.tones:
            w = 2 * math.pi * hz / FS
            ph -= math.pi / 2 if late else 0
            for k in range(N):
                out[k] += math.sin(w * k + ph)
        return [v * self.amp for v in out]


def mix(l=(), r=(), c=(), ls=(), rs=()):
    """the five into the two; each a list of (sound, gain, gate): gate a list of 0/1 a sample or None"""
    lt, rt = [0.0] * N, [0.0] * N

    def add(parts, to, late):
        for part, k_lt, k_rt in to:
            for snd, g, gate in part:
                x = snd.samples(late)
                for k in range(N):
                    v = x[k] * g * (gate[k] if gate else 1)
                    lt[k] += v * k_lt
                    rt[k] += v * k_rt
    add(None, [(l, 1, 0), (r, 0, 1), (c, 0.7071, 0.7071)], False)
    add(None, [(ls, -0.8165, 0.5774), (rs, -0.5774, 0.8165)], True)
    return lt, rt


def decode(lt, rt):
    clip = lambda v: max(-0x800000, min(0x7FFFFF, int(round(v))))
    raw = struct.pack("<%di" % (2 * N), *[clip(v) for pair in zip(lt, rt) for v in pair])
    out = subprocess.run([os.path.join(WORK, "surround")], input=raw, stdout=subprocess.PIPE, check=True).stdout
    v = struct.unpack("<%di" % (6 * N), out)
    return [v[k::6] for k in range(6)]


def power(x, a=N // 2, b=N):
    return sum(v * v for v in x[a:b]) / (b - a)


def db(p, ref):
    return 10 * math.log10(max(p, 1e-3) / ref)


def main():
    os.makedirs(WORK, exist_ok=True)
    src = os.path.join(WORK, "surround_main.c")
    open(src, "w").write(MAIN)
    subprocess.check_call(["cc", "-O2", "-Wall", "-Wextra", "-I", os.path.join(HERE, "../sw"), "-o",
                           os.path.join(WORK, "surround"), src, os.path.join(HERE, "../sw/surround.c")])
    ok = True
    five = (0, 1, 2, 4, 5)

    def bad(msg):
        nonlocal ok
        ok = False
        print("  WRONG:", msg)

    print("one channel alone (a sound of 16 tones at -20 dB): what comes out of each, dB under what went in")
    x = Sound(1)
    ref = power(x.samples())
    for name in ("l", "r", "c", "ls", "rs"):
        o = decode(*mix(**{name: [(x, 1, None)]}))
        p = [power(o[k]) for k in range(6)]
        own = [n.lower() for n in NAMES].index(name)
        worst = max(db(p[k], ref) for k in five if k != own)
        print("  %-3s -> %s   (the others at most %.1f)" % (NAMES[own], "  ".join("%s %6.1f" % (NAMES[k], db(p[k], ref)) for k in five), worst))
        if abs(db(p[own], ref)) > 0.3 or worst > -40:
            bad("%s alone: its own %.1f dB, another %.1f dB" % (NAMES[own], db(p[own], ref), worst))

    print("the same through the plain matrix (a decoder without steering)")
    d = {"L": (1, 0), "R": (0, 1), "C": (.7071, .7071), "Ls": (-.8165, .5774), "Rs": (-.5774, .8165)}
    for name in ("l", "c", "ls"):
        lt, rt = mix(**{name: [(x, 1, None)]})
        print("  %-3s -> %s" % (name.capitalize(), "  ".join("%s %6.1f" % (k, db(power([a * u + b * v for u, v in zip(lt, rt)]), ref))
                                                            for k, (a, b) in d.items())))

    print("a sound between two neighbours: out of those two as it went in")
    x = Sound(2)
    ref = power(x.samples())
    for label, kw, want in (("L 0.6 + C 0.8", dict(l=0.6, c=0.8), {0: 0.6, 2: 0.8}),
                            ("C 0.8 + R 0.6", dict(c=0.8, r=0.6), {2: 0.8, 1: 0.6}),
                            ("Ls 1 + Rs 1 (behind)", dict(ls=1, rs=1), {4: 1, 5: 1}),
                            ("Ls 1 + Rs 0.5", dict(ls=1, rs=0.5), {4: 1, 5: 0.5}),
                            ("L 0.7 + Ls 0.7", dict(l=0.7, ls=0.7), None),
                            ("R 0.7 + Rs 0.7", dict(r=0.7, rs=0.7), None)):
        o = decode(*mix(**{k: [(x, g, None)] for k, g in kw.items()}))
        amp = [math.sqrt(power(o[k]) / ref) for k in range(6)]
        print("  %-22s -> %s" % (label, "  ".join("%s %.3f" % (NAMES[k], amp[k]) for k in five)))
        if want:
            for k in five:
                if abs(amp[k] - want.get(k, 0)) > 0.02:
                    bad("%s: %s %.3f, should be %.3f" % (label, NAMES[k], amp[k], want.get(k, 0)))
    print("  (a front and a surround channel are a quarter turn apart: nothing in common, no one direction)")

    print("nothing in common (two sounds, left and right): the plain matrix")
    a, b = Sound(3), Sound(4)
    ref = power(a.samples())
    o = decode(*mix(l=[(a, 1, None)], r=[(b, 1, None)]))
    p = [power(o[k]) for k in range(6)]
    print("  %s" % "  ".join("%s %6.1f" % (NAMES[k], db(p[k], ref)) for k in five))
    if abs(db(p[0], ref)) > 1 or abs(db(p[2], ref)) > 1.5:
        bad("two channels with nothing in common do not come out as they are")

    print("speech in the centre over other sound, left and right, each 12 dB under it")
    c, a, b = Sound(5), Sound(6, 0.025), Sound(7, 0.025)
    cs = c.samples()
    ref = power(cs)
    o = decode(*mix(l=[(a, 1, None)], r=[(b, 1, None)], c=[(c, 1, None)]))
    for k, lag in ((0, 0), (1, 0), (2, 0), (4, 480), (5, 480)):
        # (how much of the centre's sound is in the channel: by what the two have in common)
        g = sum(o[k][j] * cs[j - lag] for j in range(N // 2, N)) / sum(cs[j - lag] ** 2 for j in range(N // 2, N))
        print("  %-3s %6.1f dB in all, the centre's sound in it %6.1f dB" % (NAMES[k], db(power(o[k]), ref), 20 * math.log10(max(abs(g), 1e-5))))
        if k != 2 and 20 * math.log10(max(abs(g), 1e-5)) > -15:
            bad("the centre's sound in %s" % NAMES[k])

    print("a change of side: left for 100 ms, then right for 100 ms, ...")
    x = Sound(8)
    xs = x.samples()
    gate = [(k // (FS // 10)) % 2 for k in range(N)]
    o = decode(*mix(l=[(x, 1, [1 - g for g in gate])], r=[(x, 1, gate)]))
    at = 3 * (FS // 10)                         # (left to right)
    step = FS // 1000
    row = ["%5.1f" % db(power(o[0], at + k * step, at + (k + 1) * step) + power(o[2], at + k * step, at + (k + 1) * step)
                        + power(o[4], at + 480 + k * step, at + 480 + (k + 1) * step),
                        power(xs, at + k * step, at + (k + 1) * step)) for k in range(0, 12)]
    print("  the right's sound in L + C + Ls, each ms after the change: %s dB" % " ".join(row))

    print("as loud as can be: every channel at once, each at half of full scale")
    o = decode(*mix(**{k: [(Sound(9 + j, 0.2), 1, None)] for j, k in enumerate(("l", "r", "c", "ls", "rs"))}))
    top = max(max(abs(v) for v in ch) for ch in o)
    print("  largest sample out: %d of %d" % (top, 0x7FFFFF))
    print("surround: %s" % ("as it should be" if ok else "WRONG"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
