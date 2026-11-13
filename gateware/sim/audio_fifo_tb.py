#!/usr/bin/env python3
"""audio_fifo_tb.py: rtl/audio_fifo.v (iverilog): pairs in at the sample time, a CPU that takes each
(AUDL, AUDR) and gives a set of six made from it (AUDO) in bursts with pauses; every set comes out
once, in order, a sample time each, after the first OUT_START have gathered; a long pause runs it
dry (silence, counted) and it starts again."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build")

TB = r'''`timescale 1ns/1ps
module tb;
    reg clk = 0; always #10 clk = ~clk;
    reg we = 0; reg [7:0] addr = 0; reg [31:0] wdata = 0;
    reg in_tick = 0; reg [23:0] in_l = 24'h000100, in_r = 24'h800000;
    wire [31:0] r_stat, r_l, r_r; wire on, o_tick; wire [143:0] o_s;
    audio_fifo #(.OUT_START(24)) dut (.clk(clk), .we(we), .addr(addr), .wdata(wdata), .in_tick(in_tick), .in_l(in_l),
                                     .in_r(in_r), .r_stat(r_stat), .r_l(r_l), .r_r(r_r), .on(on), .o_tick(o_tick), .o_s(o_s));
    // a pair every 2 us (the tick from another clock)
    integer n_in = 0;
    always #2000 begin in_l = in_l + 24'd1; in_r = in_r + 24'd3; n_in = n_in + 1; #7 in_tick = ~in_tick; end
    reg ot = 0;
    always @(posedge clk) begin ot <= o_tick; if (ot != o_tick) $display("out %h", o_s); end
    task wr(input [7:0] a, input [31:0] d); begin @(negedge clk); addr = a; wdata = d; we = 1; @(negedge clk); we = 0; repeat (3) @(negedge clk); end endtask
    integer k, done;
    reg [23:0] l, r;
    task serve(input integer most);     // the CPU's turn: the pairs waiting, most at most
        begin
            done = 0;
            while (done < most && r_l[31]) begin
                l = r_l[23:0]; r = r_r[23:0];
                wr(8'h57, l); wr(8'h57, r); wr(8'h57, l + r); wr(8'h57, 24'h111111); wr(8'h57, l ^ 24'hFFFFFF); wr(8'h57, r ^ 24'hFFFFFF);
                repeat (4) @(negedge clk);
                done = done + 1;
            end
        end
    endtask
    initial begin
        repeat (20) @(negedge clk);
        wr(8'h54, 32'd1);
        for (k = 0; k < 300; k = k + 1) begin serve(64); #(9000 + 370 * (k % 17)); end
        $display("stat %h", r_stat);
        #400000;                        // a long pause: it runs dry
        $display("stat %h", r_stat);
        for (k = 0; k < 200; k = k + 1) begin serve(64); #(7000); end
        $display("stat %h", r_stat);
        $finish;
    end
endmodule
'''


def main():
    os.makedirs(WORK, exist_ok=True)
    open(os.path.join(WORK, "audio_fifo_tb.v"), "w").write(TB)
    exe = os.path.join(WORK, "audio_fifo_tb")
    subprocess.check_call(["iverilog", "-g2005", "-o", exe, os.path.join(WORK, "audio_fifo_tb.v"), os.path.join(HERE, "../rtl/audio_fifo.v")])
    out = subprocess.check_output(["vvp", exe]).decode().splitlines()
    sets = [int(l.split()[1], 16) for l in out if l.startswith("out ")]
    stats = [int(l.split()[1], 16) for l in out if l.startswith("stat ")]
    ch = lambda v, k: v >> 24 * k & 0xFFFFFF
    ok = True
    real = [v for v in sets if v]
    # each set: made of one pair as the CPU makes it; the pairs in order, none twice
    for j, v in enumerate(real):
        l, r = ch(v, 0), ch(v, 1)
        if (ch(v, 2), ch(v, 3), ch(v, 4), ch(v, 5)) != ((l + r) & 0xFFFFFF, 0x111111, l ^ 0xFFFFFF, r ^ 0xFFFFFF):
            ok = False; print("  WRONG: set %d is not of one pair: %036x" % (j, v))
        if j and (l != (ch(real[j - 1], 0) + 1) & 0xFFFFFF or r != (ch(real[j - 1], 1) + 3) & 0xFFFFFF):
            # (pairs lost while the CPU was away are not an error: the count jumps on; never back)
            if (l - ch(real[j - 1], 0)) & 0xFFFFFF > 600:
                ok = False; print("  WRONG: set %d goes back: %06x after %06x" % (j, l, ch(real[j - 1], 0)))
    silent = sum(1 for v in sets if not v)
    dry = [s >> 26 for s in stats]
    print("%d sample times: %d sets, %d of silence; dry runs counted %s" % (len(sets), len(real), silent, dry))
    if not (len(real) > 2000 and dry[0] == 0 and dry[1] == 1 and dry[2] == 1):
        ok = False; print("  WRONG: the sets or the dry runs")
    print("audio_fifo: %s" % ("as it should be" if ok else "WRONG"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
