#!/usr/bin/env python3
"""cnn_tb.py [synth] [MODEL.json] [DIR]: rtl/cnn.v against the trainer's test vectors (docs/cnn-upscaler.md): each
DIR/<name>-in.png is the source's lines, every pass run, and what the network writes must be
DIR/<name>-out.png, pixel for pixel.  Default: cnn/t8s.json, cnn/vec/t8s.  Also a part of the first
picture as lines 10 to 40 of a taller one (first, last: the picture's edges are where it is told),
against cnn_ref.py.  synth: the netlist GowinSynthesis makes of it in the source's place (the IDE's simlib; the
pictures 96 wide, the design's own model; some twelve minutes): made by
    GW_SRCS="sim/cnn_top.v rtl/cnn.v rtl/easu.v" GW_CST=sim/cnn_top.cst GW_MODE=1080p60 \
        GW_OUT=$PWD/gowin/build/cnnsyn gowin/build.sh  Icarus Verilog; PIL."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cnn_ref
import model

WORK = os.path.join(HERE, "build")
IV = os.path.expanduser("~/tools/oss-cad-suite/bin")

TB = r'''`timescale 1ns/1ps
module tb;
    localparam W = %(w)d, H = %(h)d, FIRST = %(first)d, LAST = %(last)d;
    reg clk = 0; always #3 clk = ~clk;
    reg [7:0] src [0:W * H - 1];
    reg go = 0; reg signed [10:0] n = 0; wire quiet = n < FIRST;
    wire busy, rdy; wire [9:0] s_col; wire [49:0] s_line; reg [269:0] s_q; reg [55:0] s_r;
    wire o_we; wire [10:0] o_line, o_col; wire [7:0] o_d;
    wire c_we; wire [9:0] c_line, c_col; wire [15:0] c_d;
    wire l_ack;
    %(gsr)s
    %(inst)s u (.clk(clk), .go(go), .n(n), .quiet(quiet), .first(FIRST[9:0]), .last(LAST[9:0]), .busy(busy), .rdy(rdy), .s_col(s_col), .s_line(s_line),
                    .s_r(s_r), .o_we(o_we), .o_line(o_line), .o_col(o_col), .o_d(o_d), .c_we(c_we), .c_line(c_line),
                    .c_col(c_col), .c_d(c_d)%(load)s);
    // the ring: the column's words three clocks after it (its address register, the RAM's two), the five
    // chosen a clock after that (easu.v's n_rows); a
    // word's luma at 25:18, its chroma {the line, the column} (to see the right one written on)
    reg [9:0] c1; reg [269:0] q1; integer i, f, nw = 0, bad = 0;
    always @(posedge clk) begin
        c1 <= s_col;
        for (i = 0; i < 5; i = i + 1)
            q1[54 * i +: 54] <= {28'd0, src[s_line[10 * i +: 10] * W + c1], s_line[10 * i +: 8], c1[7:0], 2'd0};
        s_q <= q1;
        s_r <= {s_q[54 + 2 +: 16], s_q[54 * 4 + 18 +: 8], s_q[54 * 3 + 18 +: 8], s_q[54 * 2 + 18 +: 8], s_q[54 + 18 +: 8], s_q[18 +: 8]};
        if (o_we) begin $fwrite(f, "%%0d %%0d %%0d\n", o_line, o_col, o_d); nw = nw + 1; end
        if (c_we && c_d !== {c_line[7:0], c_col[7:0]}) bad = bad + 1;
        if (c_we && c_line !== n[9:0]) bad = bad + 1;
    end
    integer k;
    initial begin
        $readmemh("%(work)s/cnn_tb%(tag)s_src.hex", src);
        f = $fopen("%(work)s/cnn_tb%(tag)s_out.txt", "w");
        repeat (10) @(posedge clk);
        for (k = FIRST - 1; k <= LAST; k = k + 1) begin
            @(negedge clk); n = k; go = 1;
            @(negedge clk); go = 0;
            wait (!busy);
            repeat (3) @(posedge clk);
        end
        repeat (10) @(posedge clk);
        $fclose(f);
        $display("%%0d pixels written, %%0d chroma words wrong", nw, bad);
        $finish;
    end
endmodule
'''


SYNTH = False
NETLIST = os.path.join(HERE, "../gowin/build/cnnsyn/avb/impl/gwsynthesis/avb.vg")
PRIM = os.path.expanduser("~/tools/gowin-standard-1.9.12.04/IDE/simlib/gw5a/prim_sim.v")


def run(net, rows, first, last, want, name):
    """rows: the whole source (H lines); the network's picture is the lines first to last; want: 2 (last - first + 1) rows"""
    h, w = len(rows), len(rows[0])
    tag = "_syn" if SYNTH else ""
    open(os.path.join(WORK, "cnn_tb%s_src.hex" % tag), "w").write("".join("%02x\n" % v for r in rows for v in r))
    tb = os.path.join(WORK, "cnn_tb%s.v" % tag)
    open(tb, "w").write(TB % dict(w=w, h=h, first=first, last=last, work=WORK, tag=tag, gsr="GSR GSR (.GSRI(1'b1));" if SYNTH else "",
                                  inst="top" if SYNTH else "cnn #(.W(W))",
                                  load="" if SYNTH else ", .l_req(1'b0), .l_a(12'd0), .l_d(22'd0), .l_ack(l_ack)"))
    exe = os.path.join(WORK, "cnn_tb" + tag)
    files = [NETLIST, PRIM] if SYNTH else [os.path.join(HERE, "../rtl/cnn.v"), os.path.join(HERE, "../rtl/easu.v")]
    subprocess.check_call([os.path.join(IV, "iverilog"), "-g2012", "-o", exe, "-s", "tb", "-I", os.path.join(WORK, "cnn_tb_inc"), tb] + files)
    log = subprocess.run([os.path.join(IV, "vvp"), "-n", exe], stdout=subprocess.PIPE, text=True).stdout.strip().splitlines()
    got = {}
    for t in open(os.path.join(WORK, "cnn_tb%s_out.txt" % tag)):
        ln, col, d = (int(v) for v in t.split())
        got[ln, col] = got.get((ln, col), []) + [d]
    bad = twice = 0
    for y, row in enumerate(want):
        for x, v in enumerate(row):
            g = got.get((2 * first + y, x), [])
            twice += len(g) > 1
            bad += g[-1:] != [v]
    extra = sum(1 for (ln, col) in got if not (2 * first <= ln <= 2 * last + 1 and col < 2 * w))
    said = next((t for t in log if "pixels written" in t), "nothing said")
    ok = not bad and not twice and not extra and said.endswith(" 0 chroma words wrong")
    print("%s: %d x %d: %d pixels wrong, %d written twice, %d outside; %s" % (name, 2 * w, len(want), bad, twice, extra, said))
    return ok


def main():
    import warnings
    warnings.simplefilter("ignore")
    from PIL import Image
    os.makedirs(WORK, exist_ok=True)
    global SYNTH
    a = sys.argv[1:]
    if a[:1] == ["synth"]:
        SYNTH, a = True, a[1:]
    mf = a[0] if a else os.path.join(HERE, "cnn/t8s.json")
    d = a[1] if len(a) > 1 else os.path.join(HERE, "cnn/vec/t8s")
    net = json.load(open(mf))
    os.makedirs(os.path.join(WORK, "cnn_tb_inc"), exist_ok=True)
    model.net_init(net, os.path.join(WORK, "cnn_tb_inc", "cnn_init.vh"))
    rows = lambda im: [list(im.crop((0, y, im.size[0], y + 1)).getdata()) for y in range(im.size[1])]
    ok, first = True, None
    for f in sorted(os.listdir(d)):
        if f.endswith("-in.png"):
            src = rows(Image.open(os.path.join(d, f)).convert("L"))
            want = rows(Image.open(os.path.join(d, f[:-7] + "-out.png")).convert("L"))
            if SYNTH and len(src[0]) != 96:
                continue
            ok &= run(net, src, 0, len(src) - 1, want, f[:-7])
            first = first or src
    # a picture whose edges are not the lines' store's: lines 10 to 40
    ok &= run(net, first, 10, 40, cnn_ref.upscale(net, first[10:41]), "lines 10 to 40")
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
