#!/usr/bin/env python3
"""edi_synth_tb.py: what GowinSynthesis makes of the deinterlacer's edge search (rtl/deint.v, from
"the edges' way" to the output's pass: taken out into a module of its own), against the source:
both simulated side by side (Icarus Verilog; the netlist with the vendor's models of its cells) on
noise and on smooth pictures with an edge; the word made and probes at each stage must be the same
every clock.

Why: with the "least of nine" tree's registers written as arrays of two, the netlist did not do
what the source does (found 2026-11-13: the board's picture in the edge mode was not the model's,
the simulation was).  Needs the Gowin tools (the fpga-tools container: fpc's fpgarun): on fpga."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build", "edi_synth")
IV = os.path.expanduser("~/tools/oss-cad-suite/bin")
GW = os.path.expanduser("~/tools/gowin-standard-1.9.12.04/IDE")
FPGARUN = os.environ.get("FPGARUN", os.path.expanduser("~/devel/git/fpc/tools/fpga-container/fpgarun"))

HEAD = '''module edi_unit (
    input              clk,
    input              edi,
    input      [111:0] wa_i,
    input      [111:0] wb_i,
    input      [79:0]  ca_i,
    input      [79:0]  cn_i,
    input              side_i,
    output     [31:0]  bob,
    output     [159:0] dbg
);
    function [7:0] absd(input [7:0] a, input [7:0] b);
        absd = a > b ? a - b : b - a;
    endfunction
    function [7:0] mean(input [7:0] a, input [7:0] b);
        reg [8:0] t;
        begin
            t = {1'b0, a} + {1'b0, b} + 9'd1;
            mean = t[8:1];
        end
    endfunction
    reg [31:0] s1_bob;
    integer    wi;
'''
TAIL = '''
    always @(posedge clk) begin
        wa <= wa_i;
        wb <= wb_i;
        ca <= ca_i;
        cn <= cn_i;
        s0_side <= side_i;
    end
    assign bob = s1_bob;
    // probes: each stage folded to 32 bits: the differences, the sums, the least after stage 4, after 6, the offsets
    reg [31:0] f_ad, f_sm, f_m2, f_m4;
    integer pi;
    always @(*) begin
        f_ad = 0; f_sm = 0; f_m2 = 0; f_m4 = 0;
        for (pi = 0; pi < 432; pi = pi + 1) f_ad[pi % 32] = f_ad[pi % 32] ^ ad[pi];
        for (pi = 0; pi < 198; pi = pi + 1) f_sm[pi % 32] = f_sm[pi % 32] ^ sm[pi];
        for (pi = 0; pi < 138; pi = pi + 1) f_m2[pi % 32] = f_m2[pi % 32] ^ m2[pi];
        for (pi = 0; pi < 46; pi = pi + 1) f_m4[pi % 32] = f_m4[pi % 32] ^ m4[pi];
    end
    assign dbg = {f_ad, f_sm, f_m2, f_m4, 24'd0, ed[1], ed[0]};
endmodule
'''
TB = r'''`timescale 1ns/1ps
module tb;
reg clk = 0; always #5 clk = !clk;
GSR GSR (.GSRI(1'b1));
reg edi = 1; reg [111:0] wa, wb; reg [79:0] ca, cn; reg side = 0;
wire [31:0] b_rtl, b_net; wire [159:0] g_rtl, g_net;
edi_unit u_rtl (.clk(clk), .edi(edi), .wa_i(wa), .wb_i(wb), .ca_i(ca), .cn_i(cn), .side_i(side), .bob(b_rtl), .dbg(g_rtl));
edi_net u_net (.clk(clk), .edi(edi), .wa_i(wa), .wb_i(wb), .ca_i(ca), .cn_i(cn), .side_i(side), .bob(b_net), .dbg(g_net));
integer i, k, l, errs = 0, n = 0, ge [0:4];
reg [7:0] base;
initial begin
    for (l = 0; l < 5; l = l + 1) ge[l] = 0;
    for (i = 0; i < 6000; i = i + 1) begin
        @(negedge clk);
        if (i > 20) begin
            n = n + 1;
            for (l = 0; l < 5; l = l + 1) if (g_rtl[32 * l +: 32] !== g_net[32 * l +: 32]) ge[l] = ge[l] + 1;
            if (b_rtl !== b_net) errs = errs + 1;
        end
        // pictures of two kinds: noise, and smooth with an edge (near values: the comparisons' ties)
        base = $random;
        for (k = 0; k < 14; k = k + 1) begin
            wa[8 * k +: 8] = i[0] ? $random : base + (k > (i >> 1) % 14 ? 60 : 0) + ($random & 3);
            wb[8 * k +: 8] = i[0] ? $random : base + (k > (i >> 5) % 14 ? 60 : 0) + ($random & 3);
        end
        ca = {$random, $random, $random}; cn = {$random, $random, $random};
        side = ($random & 15) == 0;
        edi = ($random & 63) != 0;
    end
    $display("%0d clocks; wrong: the word made %0d; the differences %0d, the sums %0d, the least (stage 4) %0d, (stage 6) %0d, the offsets %0d",
             n, errs, ge[4], ge[3], ge[2], ge[1], ge[0]);
    $display("%0s", errs + ge[0] + ge[1] + ge[2] + ge[3] + ge[4] == 0 ? "PASS" : "FAIL");
    $finish;
end
endmodule
'''
TCL = '''set here [file dirname [file normalize [info script]]]
file mkdir $here/out
cd $here/out
create_project -name t -dir $here/out -pn GW5AST-LV138PG484AC1/I0 -device_version C -force
cd $here/out/t
add_file -type verilog $here/edi_unit.v
set_option -synthesis_tool gowinsynthesis
set_option -top_module edi_unit
set_option -verilog_std v2001
set_option -output_base_name t
run syn
'''


def main():
    os.makedirs(WORK, exist_ok=True)
    s = open(os.path.join(HERE, "../rtl/deint.v")).read()
    body = s[s.index("    // ---- the edges' way (edi) ----"):s.index("    // the output's pass: its stages (not held by the state")]
    open(os.path.join(WORK, "edi_unit.v"), "w").write(HEAD + body + TAIL)
    open(os.path.join(WORK, "tb.v"), "w").write(TB)
    open(os.path.join(WORK, "t.tcl"), "w").write(TCL)
    subprocess.call(["rm", "-rf", os.path.join(WORK, "out")])
    log = open(os.path.join(WORK, "syn.log"), "w")
    subprocess.check_call([FPGARUN, "env", "QT_QPA_PLATFORM=minimal", "LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libfreetype.so.6",
                           os.path.join(GW, "bin/gw_sh"), os.path.join(WORK, "t.tcl")], stdout=log, stderr=log)
    net = open(os.path.join(WORK, "out/t/impl/gwsynthesis/t.vg")).read().replace("module edi_unit", "module edi_net", 1)
    open(os.path.join(WORK, "edi_net.vg"), "w").write(net)
    exe = os.path.join(WORK, "tb.vvp")
    subprocess.check_call([os.path.join(IV, "iverilog"), "-g2012", "-o", exe, "-s", "tb", os.path.join(WORK, "tb.v"),
                           os.path.join(WORK, "edi_unit.v"), os.path.join(WORK, "edi_net.vg"), os.path.join(GW, "simlib/gw5a/prim_sim.v")],
                          stderr=subprocess.DEVNULL)
    out = subprocess.run([os.path.join(IV, "vvp"), "-n", exe], stdout=subprocess.PIPE, text=True).stdout
    lines = [ln for ln in out.splitlines() if "$finish" not in ln]
    print("\n".join(lines[-3:]))
    sys.exit(0 if lines and lines[-1] == "PASS" else 1)


if __name__ == "__main__":
    main()
