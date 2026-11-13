#!/usr/bin/env python3
"""grab_tb.py: rtl/grab.v with frames of a small picture whose pixels say where they are: rows asked
for (a first row, a step) must be in its RAM as they went by, done after them, for two rows a frame
(the design's) and for eight; rows past the picture's end left out.  Icarus Verilog."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build")
IV = os.path.expanduser("~/tools/oss-cad-suite/bin")

TB = r'''`timescale 1ns/1ps
module tb;
reg clk = 0, rclk = 0;
always #3 clk = !clk;
always #10 rclk = !rclk;
// a picture of 64 x 40 in a frame of 80 x 48; a pixel is {row, column}
localparam W = 64, H = 40, HT = 80, VT = 48;
integer hx = 0, vy = 0;
wire de = hx < W && vy < H;
wire vs = vy >= H + 2 && vy < H + 4;
wire [23:0] rgb = {vy[11:0], hx[11:0]};
always @(posedge clk) begin
    hx <= hx == HT - 1 ? 0 : hx + 1;
    if (hx == HT - 1) vy <= vy == VT - 1 ? 0 : vy + 1;
end
reg [10:0] row = 0; reg [3:0] step = 1; reg arm = 0;
reg [13:0] ra = 0;
wire done2, done8; wire [23:0] rd2, rd8;
grab #(.LR(1)) u2 (.clk(clk), .ce(1'b1), .de(de), .vs(vs), .rgb(rgb), .row(row), .step(step), .arm(arm), .done(done2), .rclk(rclk), .ra(ra), .rd(rd2));
grab #(.LR(3)) u8 (.clk(clk), .ce(1'b1), .de(de), .vs(vs), .rgb(rgb), .row(row), .step(step), .arm(arm), .done(done8), .rclk(rclk), .ra(ra), .rd(rd8));
integer errs = 0, k, x, n = 0;
reg [23:0] want;
task take(input [10:0] r, input [3:0] s);
    begin
        row = r; step = s; arm = !arm;
        repeat (4) @(posedge clk);
        if (done2 || done8) begin errs = errs + 1; $display("ERROR: done at once"); end
        wait (done2 && done8);
        for (k = 0; k < 8; k = k + 1)
            for (x = 0; x < W; x = x + 7) begin
                ra = {k[2:0], x[10:0]};
                @(posedge rclk); @(posedge rclk); #1;
                want = ((r + k * s) << 12) | x;
                if (r + k * s < H) begin
                    if (rd8 !== want) begin errs = errs + 1; if (errs < 6) $display("ERROR: eight: row %0d + %0d x %0d column %0d: %h", r, k, s, x, rd8); end
                    if (k < 2 && rd2 !== want) begin errs = errs + 1; if (errs < 6) $display("ERROR: two: row %0d + %0d x %0d column %0d: %h", r, k, s, x, rd2); end
                    n = n + 1;
                end
            end
    end
endtask
initial begin
    repeat (200) @(posedge clk);
    take(0, 1);
    take(5, 1);
    take(6, 2);
    take(10, 4);
    take(38, 1);        // (the last two rows)
    take(36, 2);        // (the second of eight asked for is past the end)
    $display("%0d pixels looked at, %0d wrong", n, errs);
    $display("%0s", errs == 0 ? "PASS" : "FAIL");
    $finish;
end
initial #40000000 begin $display("TIMEOUT (done never came)"); $display("FAIL"); $finish; end
endmodule
'''


def main():
    os.makedirs(WORK, exist_ok=True)
    tb = os.path.join(WORK, "grab_tb.v")
    open(tb, "w").write(TB)
    exe = os.path.join(WORK, "grab_tb")
    subprocess.check_call([os.path.join(IV, "iverilog"), "-g2012", "-o", exe, "-s", "tb", tb, os.path.join(HERE, "../rtl/grab.v")])
    out = subprocess.run([os.path.join(IV, "vvp"), "-n", exe], stdout=subprocess.PIPE, text=True).stdout
    lines = [ln for ln in out.splitlines() if "$finish" not in ln]
    print("\n".join(lines[-8:]))
    sys.exit(0 if lines and lines[-1] == "PASS" else 1)


if __name__ == "__main__":
    main()
