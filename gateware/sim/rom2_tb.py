#!/usr/bin/env python3
"""rom2_tb.py: rtl/smaa.v's smaa_rom2 as the build has it (the block RAMs named, what they hold from
sim/smaa.py dpb) against the tables themselves, with Gowin's own model of the block RAM: every
word at both ports, for the plain table and the diagonals'."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build")
IV = os.path.expanduser("~/tools/oss-cad-suite/bin")
PRIM = os.path.expanduser("~/tools/gowin-standard-1.9.12.04/IDE/simlib/gw5a/prim_sim.v")

TB = r"""`timescale 1ns/1ps
module tb;
    reg clk = 0; always #5 clk = ~clk;
    GSR GSR (.GSRI(1'b1));
    reg [11:0] a = 0, b = 0;
    wire [15:0] qa, qb, da, db;
    reg [15:0] mo [0:4095], md [0:4095];
    smaa_rom2 #(.DIAG(0)) uo (.clk(clk), .a(a), .b(b), .qa(qa), .qb(qb));
    smaa_rom2 #(.DIAG(1)) ud (.clk(clk), .a(a), .b(b), .qa(da), .qb(db));
    integer i, bad = 0;
    reg [11:0] a1, a2, b1, b2;
    always @(posedge clk) begin a1 <= a; a2 <= a1; b1 <= b; b2 <= b1; end
    initial begin
        $readmemh("%(o)s", mo); $readmemh("%(d)s", md);
        repeat (4) @(negedge clk);
        for (i = 0; i < 4096 + 4; i = i + 1) begin
            a = i; b = 4095 - i[11:0] ^ 12'h5A5;
            @(negedge clk);
            if (i >= 3 && (qa !== mo[a2] || qb !== mo[b2] || da !== md[a2] || db !== md[b2])) begin
                bad = bad + 1;
                if (bad < 5) $display("WRONG at %%0d: %%h %%h %%h %%h, wanted %%h %%h %%h %%h", a2, qa, qb, da, db, mo[a2], mo[b2], md[a2], md[b2]);
            end
        end
        $display("%%0d wrong", bad);
        if (bad) $display("FAIL"); else $display("PASS");
        $finish;
    end
endmodule
"""


def main():
    os.makedirs(WORK, exist_ok=True)
    o, d = os.path.join(WORK, "smaa.hex"), os.path.join(WORK, "smaad.hex")
    subprocess.check_call([sys.executable, os.path.join(HERE, "smaa.py"), "table", o, d, os.path.join(WORK, "smaah.hex")])
    subprocess.check_call([sys.executable, os.path.join(HERE, "smaa.py"), "dpb", o, os.path.join(WORK, "smaa_dpb.vh")])
    subprocess.check_call([sys.executable, os.path.join(HERE, "smaa.py"), "dpb", d, os.path.join(WORK, "smaad_dpb.vh")])
    tb = os.path.join(WORK, "rom2_tb.v")
    open(tb, "w").write(TB % dict(o=o, d=d))
    out = os.path.join(WORK, "rom2_tb")
    subprocess.check_call([IV + "/iverilog", "-g2012", "-DAVB_GOWIN", "-I", WORK, "-o", out, "-s", "tb", tb,
                           os.path.join(HERE, "../rtl/smaa.v"), PRIM])
    log = subprocess.run([IV + "/vvp", "-n", out], stdout=subprocess.PIPE, text=True).stdout
    print(log.strip()[-1500:])
    sys.exit(0 if "PASS" in log else 1)


if __name__ == "__main__":
    main()
