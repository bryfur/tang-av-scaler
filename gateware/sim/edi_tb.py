#!/usr/bin/env python3
"""edi_tb.py [synth]: rtl/deint_edi.v against sim/model.py's edge_line(): lines of noise, of smooth
ground with hard-edged shapes at low angles, and of both, through the module a word a clock; every
word made must be the model's.  synth: the same with what GowinSynthesis makes of the module (its
netlist with the vendor's cell models; on fpga: the Gowin tools in the container) in the source's
place: a simulation of the source is not what the FPGA gets (see edi_synth_tb.py's history).
Icarus Verilog."""
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model

WORK = os.path.join(HERE, "build", "edi")
IV = os.path.expanduser("~/tools/oss-cad-suite/bin")
GW = os.path.expanduser("~/tools/gowin-standard-1.9.12.04/IDE")
FPGARUN = os.environ.get("FPGARUN", os.path.expanduser("~/devel/git/fpc/tools/fpga-container/fpgarun"))
NW, LAT, GAP = 360, 30, 40

TB = r'''`timescale 1ns/1ps
module tb;
reg clk = 0; always #5 clk = !clk;
%(gsr)s
reg [127:0] mem [0:%(last)d];
reg v = 0; reg [9:0] q = 0; reg [31:0] a2 = 0, a = 0, b = 0, b2 = 0;
wire [31:0] bob;
deint_edi dut (.clk(clk), .en(1'b1), .nw(10'd%(nw)d), .v_i(v), .q_i(q), .a2_i(a2), .a_i(a), .b_i(b), .b2_i(b2), .bob(bob));
integer n, k, f;
// (a word is in the module the clock after it is given: its word made LAT clocks after that)
reg [%(lat)d:0] vd = 0;
always @(posedge clk) begin
    vd <= {vd[%(lat)d - 1:0], v};
    if (vd[%(lat)d]) $fwrite(f, "%%h\n", bob);
end
initial begin
    $readmemh("%(work)s/in.hex", mem);
    f = $fopen("%(work)s/out.hex", "w");
    repeat (4) @(negedge clk);
    for (n = 0; n < %(lines)d; n = n + 1) begin
        for (k = 0; k < %(nw)d; k = k + 1) begin
            {a2, a, b, b2} = mem[n * %(nw)d + k]; v = 1; q = k;
            @(negedge clk);
        end
        v = 0; a2 = $random; a = $random; b = $random; b2 = $random;
        repeat (%(gap)d) @(negedge clk);
    end
    repeat (40) @(negedge clk);
    $fclose(f);
    $finish;
end
endmodule
'''
TCL = '''set here [file dirname [file normalize [info script]]]
file mkdir $here/out
cd $here/out
create_project -name t -dir $here/out -pn GW5AST-LV138PG484AC1/I0 -device_version C -force
cd $here/out/t
add_file -type verilog %s
set_option -synthesis_tool gowinsynthesis
set_option -top_module deint_edi
set_option -verilog_std v2001
set_option -output_base_name t
run syn
'''


def lines():
    """sets of four lines (A2, A, B, B2) of words"""
    rng = random.Random(5)
    out = []
    w = 2 * NW

    def words(ys, cs):
        return [(cs[2 * k], ys[2 * k], cs[2 * k + 1], ys[2 * k + 1]) for k in range(NW)]
    # shapes with hard edges at low angles on smooth ground, a little noise: four lines of a field
    for n in range(40):
        slope = rng.choice([0.5, 1, 2, 3, 4, 6, 8, 10]) * rng.choice([-1, 1])
        x0 = rng.randrange(80, w - 80)
        lo, hi = rng.randrange(20, 90), rng.randrange(140, 235)
        thick = rng.choice([400, 400, 30, 6])
        noise = rng.choice([0, 0, 1, 3])
        rows = []
        for r in (-3, -1, 1, 3):                    # the field's lines: two of the frame's apart
            ys = []
            for x in range(w):
                edge = x0 + slope * r
                v = hi if edge <= x < edge + thick else lo
                ys.append(min(255, max(0, v + rng.randrange(-noise, noise + 1))))
            cs = [(100 + (x // 2 + r * 3) % 60 + (40 if x0 + slope * r <= x else 0)) & 255 for x in range(w)]
            rows.append(words(ys, cs))
        out.append(rows)
    # noise; and steps everywhere
    for n in range(12):
        rows = [words([rng.randrange(256) for _ in range(w)], [rng.randrange(256) for _ in range(w)]) for _ in range(4)]
        out.append(rows)
    for n in range(12):
        base = [rng.choice([30, 200]) for _ in range(w // 6 + 2)]
        rows = []
        for r in range(4):
            sh = rng.randrange(0, 6)
            rows.append(words([min(255, base[(x + sh + 2 * r) // 6] + rng.randrange(0, 4)) for x in range(w)], [rng.randrange(256) for _ in range(w)]))
        out.append(rows)
    return out


def main():
    synth = "synth" in sys.argv[1:]
    os.makedirs(WORK, exist_ok=True)
    sets = lines()
    hexw = lambda wd: "%02x%02x%02x%02x" % wd
    open(os.path.join(WORK, "in.hex"), "w").write("\n".join(hexw(a2[k]) + hexw(a[k]) + hexw(b[k]) + hexw(b2[k]) for a2, a, b, b2 in sets for k in range(NW)) + "\n")
    src = os.path.join(HERE, "../rtl/deint_edi.v")
    files = [src]
    if synth:
        open(os.path.join(WORK, "t.tcl"), "w").write(TCL % src)
        subprocess.call(["rm", "-rf", os.path.join(WORK, "out")])
        log = open(os.path.join(WORK, "syn.log"), "w")
        subprocess.check_call([FPGARUN, "env", "QT_QPA_PLATFORM=minimal", "LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libfreetype.so.6",
                               os.path.join(GW, "bin/gw_sh"), os.path.join(WORK, "t.tcl")], stdout=log, stderr=log)
        files = [os.path.join(WORK, "out/t/impl/gwsynthesis/t.vg"), os.path.join(GW, "simlib/gw5a/prim_sim.v")]
    tb = os.path.join(WORK, "tb.v")
    open(tb, "w").write(TB % dict(last=len(sets) * NW - 1, nw=NW, lat=LAT, work=WORK, lines=len(sets), gap=GAP,
                                  gsr="GSR GSR (.GSRI(1'b1));" if synth else ""))
    exe = os.path.join(WORK, "tb.vvp")
    subprocess.check_call([os.path.join(IV, "iverilog"), "-g2012", "-o", exe, "-s", "tb", tb] + files, stderr=subprocess.DEVNULL)
    subprocess.check_call([os.path.join(IV, "vvp"), "-n", exe], stdout=subprocess.DEVNULL)
    got = [int(t, 16) if "x" not in t else -1 for t in open(os.path.join(WORK, "out.hex")).read().split()]
    bad = moved = 0
    for n, (a2, a, b, b2) in enumerate(sets):
        want = model.edge_line(a, b, a2, b2)
        mean = [tuple(model.mean(p, q) for p, q in zip(wa, wb)) for wa, wb in zip(a, b)]
        for k in range(NW):
            g = got[n * NW + k] if n * NW + k < len(got) else -1
            wv = want[k][0] << 24 | want[k][1] << 16 | want[k][2] << 8 | want[k][3]
            moved += want[k] != mean[k]
            if g != wv:
                bad += 1
                if bad <= 6:
                    print("  line set %d word %d: got %08x want %08x" % (n, k, g & 0xFFFFFFFF, wv))
    print("%d words made (%d not straight down), %d wrong%s" % (len(sets) * NW, moved, bad, " (the netlist)" if synth else ""))
    print("PASS" if not bad and len(got) == len(sets) * NW else "FAIL")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
