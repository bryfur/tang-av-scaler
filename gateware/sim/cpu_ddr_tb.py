#!/usr/bin/env python3
"""cpu_ddr_tb.py: rtl/cpu_ddr.v between an AHB master as the core is (transfers of 1 to 8 bytes,
one after another with the next address given during the data, or with nothing between) and a
memory that answers as ddr_arb.v's user port does, on another clock: every read must give the
bytes last written, and the memory must end up holding them.  Icarus Verilog."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build")
IV = os.path.expanduser("~/tools/oss-cad-suite/bin")

TB = r'''`timescale 1ns / 1ps
module tb;
reg clk = 0, pclk = 0, rstn = 0;
integer errs = 0;
always #10 clk = !clk;
always #4.87 pclk = !pclk;
reg  [31:0] haddr = 0;
reg  [1:0]  htrans = 0;
reg         hwrite = 0;
reg  [2:0]  hsize = 0;
reg  [63:0] hwdata = 0;
wire [63:0] hrdata;
wire        hready, d_valid, d_wr;
wire [24:0] d_line;
wire [255:0] d_data;
wire [31:0] d_mask;
reg         d_ack = 0, d_rvalid = 0;
reg  [255:0] d_rdata = 0;
wire [23:0] n_rd, n_wr;
cpu_ddr dut (.clk(clk), .rstn(rstn), .haddr(haddr), .htrans(htrans), .hwrite(hwrite), .hsize(hsize), .hwdata(hwdata),
             .hrdata(hrdata), .hready(hready), .ok(1'b1), .pclk(pclk), .d_valid(d_valid), .d_wr(d_wr), .d_line(d_line),
             .d_data(d_data), .d_mask(d_mask), .d_ack(d_ack), .d_rvalid(d_rvalid), .d_rdata(d_rdata),
             .n_rd(n_rd), .n_wr(n_wr), .dead(), .first_line());

// (a memory that never answers: the bus must not wait for ever)
reg  [31:0] haddr2 = 0;
reg  [1:0]  htrans2 = 0;
reg         hwrite2 = 0;
wire [63:0] hrdata2;
wire        hready2, dead2;
cpu_ddr #(.TMO_LOG2(6)) dut2 (.clk(clk), .rstn(rstn), .haddr(haddr2), .htrans(htrans2), .hwrite(hwrite2), .hsize(3'd2),
             .hwdata(64'h1122334455667788), .hrdata(hrdata2), .hready(hready2), .ok(1'b1), .pclk(pclk), .d_valid(), .d_wr(),
             .d_line(), .d_data(), .d_mask(), .d_ack(1'b0), .d_rvalid(1'b0), .d_rdata(256'd0), .n_rd(), .n_wr(), .dead(dead2), .first_line());
integer t2;
task one2(input wr, input [31:0] a);
    begin
        htrans2 <= 2'b10; haddr2 <= a; hwrite2 <= wr;
        @(posedge clk); while (!hready2) @(posedge clk);
        htrans2 <= 2'b00;
        t2 = 0;
        @(posedge clk); while (!hready2) begin t2 = t2 + 1; @(posedge clk); end
    end
endtask
initial begin
    repeat (12) @(posedge clk);
    one2(1'b0, 32'h100);
    if (!dead2 || hrdata2 !== 64'd0 || t2 > 200) begin errs = errs + 1; $display("ERROR: no answer: the read took %0d clocks, dead %b", t2, dead2); end
    one2(1'b1, 32'h2000);
    one2(1'b0, 32'h2000);
    if (t2 > 4 || hrdata2 !== 64'd0) begin errs = errs + 1; $display("ERROR: a dead port's read: %0d clocks, %h", t2, hrdata2); end
    $display("a memory that never answers: the port gives up (dead %b)", dead2);
end

// ---- the memory: 16 lines somewhere in the 1 GB; ddr_arb.v's way of answering ----
reg [24:0]  where [0:15];
reg [255:0] mem [0:15];
reg [7:0]   want [0:511];                // what the bus side should see: the 16 lines' bytes
integer i, j;
function integer slot(input [24:0] l);
    begin
        slot = -1;
        for (i = 0; i < 16; i = i + 1) if (where[i] == l) slot = i;
    end
endfunction
reg [63:0] rnd = 64'h2545f4914f6cdd1d;
task step; begin rnd = rnd ^ (rnd << 13); rnd = rnd ^ (rnd >> 7); rnd = rnd ^ (rnd << 17); end endtask

// (a request taken after a while, its ack a clock; a read's line some clocks later, in order)
reg         taken = 0;
reg [3:0]   wait_a = 0;
reg [255:0] rq [0:7];
reg [5:0]   rq_t [0:7];
reg [2:0]   rq_w = 0, rq_r = 0;
integer     sl, k;
always @(posedge pclk) begin
    d_ack <= 1'b0;
    d_rvalid <= 1'b0;
    for (k = 0; k < 8; k = k + 1) if (rq_t[k] != 0) rq_t[k] <= rq_t[k] - 1;
    if (rq_w != rq_r && rq_t[rq_r] == 0) begin
        d_rvalid <= 1'b1;
        d_rdata <= rq[rq_r];
        rq_r <= rq_r + 1;
    end
    if (d_valid && !d_ack && !taken) begin
        if (wait_a != 0)
            wait_a <= wait_a - 1;
        else begin
            sl = slot(d_line);
            if (sl < 0) begin
                errs = errs + 1;
                $display("ERROR: a line never asked for: %h", d_line);
            end else if (d_wr) begin
                for (k = 0; k < 32; k = k + 1)
                    if (!d_mask[k]) mem[sl][k * 8 +: 8] = d_data[k * 8 +: 8];
            end else begin
                rq[rq_w] <= mem[sl];
                rq_t[rq_w] <= 6 + rnd[2:0];
                rq_w <= rq_w + 1;
            end
            d_ack <= 1'b1;
            taken <= 1'b1;
            step;
            wait_a <= rnd[11:8] < 4 ? rnd[3:0] : 0;
        end
    end
    if (taken && !d_valid)
        taken <= 1'b0;
    // (a request still up in ack's clock is not taken twice: as ddr_arb.v)
    if (d_ack)
        taken <= d_valid;
end

// ---- the bus: n transfers one after another, the next's address during the one's data ----
reg         t_wr [0:7];
reg [29:0]  t_a [0:7];
reg [2:0]   t_size [0:7];
reg [63:0]  t_wd [0:7];
integer     n_x = 0, n_checked = 0;
task check(input integer q);
    integer b, nb, base;
    reg [63:0] got;
    begin
        got = hrdata;
        nb = 1 << t_size[q];
        base = slot(t_a[q][29:5]) * 32 + t_a[q][4:0];
        if (!t_wr[q]) begin
            for (b = 0; b < nb; b = b + 1)
                if (got[(t_a[q][2:0] + b) * 8 +: 8] !== want[base + b]) begin
                    errs = errs + 1;
                    if (errs < 8)
                        $display("ERROR: read at %h (%0d bytes): byte %0d is %h, should be %h (%0.0f ns)",
                                 t_a[q], nb, b, got[(t_a[q][2:0] + b) * 8 +: 8], want[base + b], $realtime);
                end
            n_checked = n_checked + 1;
        end
    end
endtask
task run(input integer n);
    integer q, b, nb, base;
    begin
        for (q = 0; q < n; q = q + 1) begin
            htrans <= 2'b10;
            haddr <= {2'b00, t_a[q]};
            hwrite <= t_wr[q];
            hsize <= t_size[q];
            @(posedge clk);
            while (!hready) @(posedge clk);
            // (the address taken; the transfer before is over: its data)
            if (q > 0) check(q - 1);
            hwdata <= t_wd[q];
            if (t_wr[q]) begin
                nb = 1 << t_size[q];
                base = slot(t_a[q][29:5]) * 32 + t_a[q][4:0];
                for (b = 0; b < nb; b = b + 1)
                    want[base + b] = t_wd[q][(t_a[q][2:0] + b) * 8 +: 8];
            end
            n_x = n_x + 1;
        end
        htrans <= 2'b00;
        @(posedge clk);
        while (!hready) @(posedge clk);
        check(n - 1);
    end
endtask

integer it, n, q, line_i;
initial begin
    for (i = 0; i < 16; i = i + 1) begin
        step; where[i] = rnd[24:0];
        step; mem[i][63:0] = rnd; step; mem[i][127:64] = rnd; step; mem[i][191:128] = rnd; step; mem[i][255:192] = rnd;
        for (j = 0; j < 32; j = j + 1) want[i * 32 + j] = mem[i][j * 8 +: 8];
    end
    for (i = 0; i < 8; i = i + 1) rq_t[i] = 0;
    repeat (5) @(posedge clk);
    rstn <= 1'b1;
    repeat (3) @(posedge clk);
    line_i = 0;
    for (it = 0; it < 6000; it = it + 1) begin
        step;
        n = rnd[1:0] == 0 ? 1 : rnd[4:2] + 1;
        for (q = 0; q < n; q = q + 1) begin
            step;
            // (mostly on in the same line or the next, as a program is; now and then anywhere)
            if (rnd[7:4] == 0) line_i = rnd[11:8];
            else if (rnd[7:4] < 3) line_i = (line_i + 1) % 16;
            t_wr[q] = rnd[13] && rnd[12];
            t_size[q] = rnd[15:14];
            t_a[q] = {where[line_i], rnd[20:16]} & ~((30'd1 << t_size[q]) - 30'd1);
            step;
            t_wd[q] = rnd;
        end
        run(n);
        step;
        if (rnd[3:0] == 0) repeat (rnd[9:4]) @(posedge clk);
    end
    // the gather written out, then the memory against what the bus saw
    repeat (200) @(posedge clk);
    for (i = 0; i < 16; i = i + 1)
        for (j = 0; j < 32; j = j + 1)
            if (mem[i][j * 8 +: 8] !== want[i * 32 + j]) begin
                errs = errs + 1;
                if (errs < 8) $display("ERROR: the memory's line %0d byte %0d is %h, should be %h", i, j, mem[i][j * 8 +: 8], want[i * 32 + j]);
            end
    $display("%0d transfers, %0d reads checked; the memory's lines read %0d, written %0d; wrong %0d", n_x, n_checked, n_rd, n_wr, errs);
    $display("%0s", errs == 0 ? "PASS" : "FAIL");
    $finish;
end
initial #200000000 begin $display("TIMEOUT"); $display("FAIL"); $finish; end
endmodule
'''


def main():
    os.makedirs(WORK, exist_ok=True)
    tb = os.path.join(WORK, "cpu_ddr_tb.v")
    open(tb, "w").write(TB)
    exe = os.path.join(WORK, "cpu_ddr_tb")
    subprocess.check_call([os.path.join(IV, "iverilog"), "-g2012", "-o", exe, "-s", "tb", tb, os.path.join(HERE, "../rtl/cpu_ddr.v")])
    out = subprocess.run([os.path.join(IV, "vvp"), "-n", exe], stdout=subprocess.PIPE, text=True).stdout
    lines = [ln for ln in out.splitlines() if "$finish" not in ln]
    print("\n".join(lines[-14:]))
    sys.exit(0 if lines and lines[-1] == "PASS" else 1)


if __name__ == "__main__":
    main()
