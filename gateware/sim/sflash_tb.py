#!/usr/bin/env python3
"""sflash_tb.py: rtl/sflash.v against a model of the flash (sflash_model.v), in iverilog: the
identity and the status read; a read; a sector erased, pages programmed and read back; a program
and an erase below 0x800000 or without the key refused (nothing reaches the flash); a read left
open when another command comes; then 20000 register writes of anything at all, after which the
flash must have seen no command but the six and no program or erase below 0x800000."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build")
IV = os.path.expanduser("~/tools/oss-cad-suite/bin")

TB = r'''`timescale 1ns/1ps
module tb;
    reg clk = 0; always #10 clk = ~clk;
    reg we = 0; reg [7:0] addr = 0; reg [31:0] wdata = 0;
    wire [31:0] q_d, q_s; wire cs_n, sck, mosi, miso, wp_n, hold_n;
    sflash u (.clk(clk), .we(we), .addr(addr), .wdata(wdata), .q_d(q_d), .q_s(q_s), .f_cs_n(cs_n), .f_sck(sck),
              .f_mosi(mosi), .f_miso(miso), .f_wp_n(wp_n), .f_hold_n(hold_n));
    sflash_model m (.cs_n(cs_n), .sck(sck), .mosi(mosi), .miso(miso));
    integer bad = 0, i, j, seed = 7;
    task bus(input [7:0] a, input [31:0] d);
        begin @(negedge clk); we = 1; addr = a; wdata = d; @(negedge clk); we = 0; end
    endtask
    task cmd(input [3:0] op, input [3:0] key, input [23:0] a);
        begin bus(8'h68, {op, key, a}); @(negedge clk); while (q_s[0]) @(negedge clk); end
    endtask
    task want(input [31:0] got, input [31:0] exp, input [255:0] what);
        if (got !== exp) begin bad = bad + 1; $display("WRONG %0s: %h, wanted %h", what, got, exp); end
    endtask
    task idle;      // the flash's own write over
        begin cmd(6, 0, 0); while (q_d[0]) cmd(6, 0, 0); end
    endtask
    reg [31:0] r;
    initial begin
        for (i = 0; i < 256; i = i + 1) m.mem[i] = i ^ 8'h5A;
        repeat (10) @(negedge clk);
        cmd(7, 0, 0); want(q_d, 32'h00EF4018, "identity");
        cmd(6, 0, 0); want(q_d, 32'h0, "status");
        // a read, three words on
        cmd(1, 0, 24'h000010);
        for (i = 0; i < 3; i = i + 1) begin
            want(q_d, {m.mem[19 + 4 * i], m.mem[18 + 4 * i], m.mem[17 + 4 * i], m.mem[16 + 4 * i]}, "read");
            cmd(2, 0, 0);
        end
        want(q_s, 32'h4, "a read open");
        // (another command with the read open: ended first)
        cmd(7, 0, 0); want(q_d, 32'h00EF4018, "identity after an open read"); want(q_s, 32'h0, "nothing open");
        // refused: below 0x800000, or no key
        cmd(4, 4'hA, 24'h000000); want(q_s, 32'h2, "program at 0 refused");
        cmd(5, 4'hA, 24'h7FF000); want(q_s, 32'h2, "erase below refused");
        cmd(4, 4'h0, 24'h900000); want(q_s, 32'h2, "program without the key refused");
        cmd(5, 4'h5, 24'h900000); want(q_s, 32'h2, "erase without the key refused");
        want(m.n_prog + m.n_erase, 0, "nothing written yet");
        // erase, program two pages, read back
        cmd(5, 4'hA, 24'h901000); want(q_s, 32'h0, "erase taken"); idle;
        for (j = 0; j < 2; j = j + 1) begin
            cmd(4, 4'hA, 24'h901000 + 256 * j); want(q_s, 32'hC, "a program open");
            for (i = 0; i < 64; i = i + 1) begin
                bus(8'h69, 32'hC0DE0000 + 64 * j + i); cmd(2, 0, 0);
            end
            cmd(3, 0, 0); idle;
        end
        cmd(1, 0, 24'h901000);
        for (i = 0; i < 128; i = i + 1) begin
            want(q_d, 32'hC0DE0000 + i, "read back");
            cmd(2, 0, 0);
        end
        want(q_d, 32'hFFFFFFFF, "after them: erased");
        cmd(3, 0, 0);
        want(m.n_prog, 2, "programs"); want(m.n_erase, 1, "erases");
        // a program over what is there: bits only go down
        cmd(4, 4'hA, 24'h901000); bus(8'h69, 32'h0000FFFF); cmd(2, 0, 0); cmd(3, 0, 0); idle;
        cmd(1, 0, 24'h901000); want(q_d, 32'h00000000, "programmed over"); cmd(3, 0, 0);
        // anything at all written to the registers
        for (i = 0; i < 20000; i = i + 1) begin
            @(negedge clk); we = 1; addr = 8'h68 + ($random(seed) & 3); wdata = $random(seed);
            if (($random(seed) & 7) == 0) wdata[27:20] = 8'hA8 | ($random(seed) & 8'h07);
            @(negedge clk); we = 0;
            repeat ($random(seed) & 63) @(negedge clk);
            if (($random(seed) & 31) == 0) begin while (q_s[0]) @(negedge clk); end
        end
        while (q_s[0]) @(negedge clk);
        want(m.bad_cmd, 0, "commands the flash should not see");
        want(m.low_write, 0, "programs or erases below 0x800000");
        $display("the flash saw %0d reads, %0d programs, %0d erases; %0d wrong", m.n_read, m.n_prog, m.n_erase, bad);
        if (bad) $display("FAIL"); else $display("PASS");
        $finish;
    end
endmodule
'''


def main():
    os.makedirs(WORK, exist_ok=True)
    tb = os.path.join(WORK, "sflash_tb.v")
    open(tb, "w").write(TB)
    out = os.path.join(WORK, "sflash_tb")
    subprocess.check_call([IV + "/iverilog", "-g2012", "-o", out, "-s", "tb", tb, os.path.join(HERE, "sflash_model.v"),
                           os.path.join(HERE, "../rtl/sflash.v")])
    log = subprocess.run([IV + "/vvp", "-n", out], stdout=subprocess.PIPE, text=True).stdout
    print(log.strip()[-3000:])
    sys.exit(0 if log.strip().endswith("PASS") else 1)


if __name__ == "__main__":
    main()
