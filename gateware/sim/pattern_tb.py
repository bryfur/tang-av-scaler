#!/usr/bin/env python3
"""pattern_tb.py [PPC ...]: rtl/pattern.v's timing over two frames (iverilog), 3840x2160 at PPC
pixels a clock (default 1, 2, 4; 1 = the 1080p defaults): line and frame lengths, the picture's
size, the syncs' widths and places, the preamble, guard band and unscrambled characters."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(ppc):
    work = os.path.join(HERE, "build")
    os.makedirs(work, exist_ok=True)
    big = ppc > 1
    ht, vt, ha, va, hf, hs_w, vf, vs_w = (4400, 2250, 3840, 2160, 176, 88, 8, 10) if big else (2200, 1125, 1920, 1080, 88, 44, 4, 5)
    params = "#(.PPC(%d), .HA(3840), .HF(176), .HS(88), .HT(4400), .VA(2160), .VF(8), .VS(10), .VT(2250))" % ppc if big else ""
    tb = '''`timescale 1ns/1ps
module tb;
    localparam P = %d;
    reg clk = 0; always #1 clk = ~clk;
    wire [P - 1:0] de, hs, vs, pre, gb, ucc;
    wire [8 * P - 1:0] r, g, b;
    pattern %s dut (.clk(clk), .de(de), .hs(hs), .vs(vs), .pre(pre), .gb(gb), .ucc(ucc), .r(r), .g(g), .b(b));
    integer f, i, k;
    initial begin
        f = $fopen("%s/pat.bin", "wb");
        repeat (4) @(posedge clk);
        for (i = 0; i < %d; i = i + 1) begin
            @(posedge clk); #0.1;
            for (k = 0; k < P; k = k + 1)
                $fwrite(f, "%%c", 8'd32 + {2'b0, ucc[k], gb[k], pre[k], vs[k], hs[k], de[k]});
        end
        $fclose(f);
        $finish;
    end
endmodule
''' % (ppc, params, work, 2 * ht * vt // ppc + ht // ppc)
    open(os.path.join(work, "pat_tb.v"), "w").write(tb)
    subprocess.check_call(["iverilog", "-g2005", "-o", os.path.join(work, "pat.vvp"), os.path.join(work, "pat_tb.v"),
                           os.path.join(HERE, "../rtl/pattern.v")])
    subprocess.check_call(["vvp", "-n", os.path.join(work, "pat.vvp")], stdout=subprocess.DEVNULL)
    s = bytes(c - 32 for c in open(os.path.join(work, "pat.bin"), "rb").read())
    de = [c & 1 for c in s]
    hs = [c >> 1 & 1 for c in s]
    vs = [c >> 2 & 1 for c in s]
    rises = lambda v: [k for k in range(1, len(v)) if v[k] and not v[k - 1]]
    falls = lambda v: [k for k in range(1, len(v)) if not v[k] and v[k - 1]]
    hr, hfl, vr, vfl, dr, dfl = rises(hs), falls(hs), rises(vs), falls(vs), rises(de), falls(de)
    ok = True

    def check(name, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        print("  %-46s %s%s" % (name, got, "" if good else "   <-- want %s" % (want,)))

    print("PPC %d:" % ppc)
    check("HSYNC period (every one)", sorted(set(b - a for a, b in zip(hr, hr[1:]))), [ht])
    check("HSYNC width", sorted(set(b - a for a, b in zip(hr, [x for x in hfl if x > hr[0]]))), [hs_w])
    check("frame (VSYNC to VSYNC), in lines", [(b - a) / ht for a, b in zip(vr, vr[1:])], [float(vt)])
    check("VSYNC width, in lines", sorted(set((b - a) / ht for a, b in zip(vr, [x for x in vfl if x > vr[0]]))), [float(vs_w)])
    check("VSYNC rises with HSYNC", all(v in hr for v in vr), True)
    v0 = vr[0]
    frame_de_r = [x for x in dr if v0 < x < v0 + ht * vt]
    frame_de_f = [x for x in dfl if v0 < x < v0 + ht * vt + ht]
    check("lines of picture in a frame", len(frame_de_r), va)
    check("picture width", sorted(set(b - a for a, b in zip(frame_de_r, frame_de_f))), [ha])
    check("HSYNC's start after a line of picture ends", sorted(set(min(h for h in hr if h > x) - x for x in frame_de_f[:50])), [hf])
    check("picture's start after HSYNC's start", sorted(set(x - max(h for h in hr if h < x) for x in frame_de_r[:50])), [ht - ha - hf])
    last_end = frame_de_f[-1] if frame_de_f[-1] < v0 + ht * vt else frame_de_f[-2]
    first = frame_de_r[0]
    check("VSYNC's start to the first line of picture, lines", (first - (ht - ha - hf) - v0) / ht, float(vt - va - vf))
    gb = [k for k in range(len(s)) if s[k] >> 4 & 1]
    pre = [k for k in range(len(s)) if s[k] >> 3 & 1]
    ucc = [k for k in range(len(s)) if s[k] >> 5 & 1]
    check("guard band: the 2 characters before each line", all(de[k + 2 - (k - frame_de_r[0]) % 1] or True for k in gb[:1]) and
          all(s[x - 1] >> 4 & 1 and s[x - 2] >> 4 & 1 and not s[x - 3] >> 4 & 1 for x in frame_de_r), True)
    check("preamble: the 8 before the guard band", all(all(s[x - 3 - j] >> 3 & 1 for j in range(8)) and not s[x - 11] >> 3 & 1
                                                      for x in frame_de_r), True)
    check("guard band and preamble only before picture", len([k for k in gb if v0 < k < v0 + ht * vt]) == 2 * va and
          len([k for k in pre if v0 < k < v0 + ht * vt]) == 8 * va, True)
    check("unscrambled characters: 8 from VSYNC's rise", [k - v0 for k in ucc if v0 <= k < v0 + ht], list(range(8)))
    return ok


if __name__ == "__main__":
    ppcs = [int(a) for a in sys.argv[1:]] or [1, 2, 4]
    sys.exit(0 if all([run(p) for p in ppcs]) else 1)
