#!/usr/bin/env python3
"""bram_tb.py: rtl/bram.v's bram32 as the FPGA has it (the DPB primitive, the vendor's model of it:
the Gowin IDE's simlib) beside the plain Verilog the other tests use: writes and reads at random
(never both in a clock), both latencies; what comes out must be the same every clock once a word
has been read.  Icarus Verilog."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build")
IV = os.path.expanduser("~/tools/oss-cad-suite/bin")
PRIM = os.path.expanduser("~/tools/gowin-standard-1.9.12.04/IDE/simlib/gw5a/prim_sim.v")

TB = r'''`timescale 1ns/1ps
module tb;
reg clk = 0; always #5 clk = !clk;
GSR GSR (.GSRI(1'b1));
reg we = 0; reg [8:0] wa = 0, ra = 0; reg [31:0] wd = 0;
wire [31:0] qa2, qb2, qa1, qb1;
prim_bram32 #(.LAT(2)) a2 (.clk(clk), .we(we), .wa(wa), .wd(wd), .ra(ra), .q(qa2));
plain_bram32 #(.LAT(2)) b2 (.clk(clk), .we(we), .wa(wa), .wd(wd), .ra(ra), .q(qb2));
prim_bram32 #(.LAT(1)) a1 (.clk(clk), .we(we), .wa(wa), .wd(wd), .ra(ra), .q(qa1));
plain_bram32 #(.LAT(1)) b1 (.clk(clk), .we(we), .wa(wa), .wd(wd), .ra(ra), .q(qb1));
integer i, errs = 0, n = 0, seen = 0;
initial begin
    // every word written first (what was never written is not the same in the two)
    for (i = 0; i < 512; i = i + 1) begin
        @(negedge clk); we = 1; wa = i; wd = $random;
    end
    @(negedge clk); we = 0; ra = 0;
    repeat (4) @(negedge clk);
    for (i = 0; i < 200000; i = i + 1) begin
        @(negedge clk);
        if (qa2 !== qb2 || qa1 !== qb1) begin
            errs = errs + 1;
            if (errs < 6) $display("ERROR at %0d: %h %h, %h %h", i, qa2, qb2, qa1, qb1);
        end
        n = n + 1;
        we = ($random & 3) == 0;
        wa = $random; wd = $random; ra = $random;
    end
    $display("%0d clocks, %0d wrong", n, errs);
    $display("%0s", errs == 0 ? "PASS" : "FAIL");
    $finish;
end
endmodule
'''


def main():
    os.makedirs(WORK, exist_ok=True)
    src = open(os.path.join(HERE, "../rtl/bram.v")).read()
    # the module twice: as the FPGA has it, and plain
    prim = os.path.join(WORK, "bram_prim.v")
    plain = os.path.join(WORK, "bram_plain.v")
    open(prim, "w").write("`define AVB_GOWIN\n" + src.replace("module bram32", "module prim_bram32") + "\n`undef AVB_GOWIN\n")
    open(plain, "w").write(src.replace("module bram32", "module plain_bram32"))
    tb = os.path.join(WORK, "bram_tb.v")
    open(tb, "w").write(TB)
    exe = os.path.join(WORK, "bram_tb")
    subprocess.check_call([os.path.join(IV, "iverilog"), "-g2012", "-o", exe, "-s", "tb", tb, plain, prim, PRIM],
                          stderr=subprocess.DEVNULL)
    out = subprocess.run([os.path.join(IV, "vvp"), "-n", exe], stdout=subprocess.PIPE, text=True).stdout
    lines = [ln for ln in out.splitlines() if "$finish" not in ln]
    print("\n".join(lines[-8:]))
    sys.exit(0 if lines and lines[-1] == "PASS" else 1)


if __name__ == "__main__":
    main()
