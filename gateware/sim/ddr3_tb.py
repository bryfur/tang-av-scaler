#!/usr/bin/env python3
"""ddr3_tb.py [+vcd] [ops=N]: the DDR3 controller (rtl/ddr3) on two x16 chips of a model that checks
what it is given (sim/ddr3/ddr3_chip.v: the protocol, the chips' timing, the strobes), with
Gowin's own models of the I/O logic from the install and ours of the DQS block (sim/ddr3: the
GW5A's is encrypted).  Icarus Verilog.

The power-up and the calibration; 256 lines written (eight banks, rows that change), read back in
a stream; then lines written and read at random, with gaps; a read alone after a wait.  Every line
read must be the one last written there, and the chips must have nothing to say."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build", "ddr3")
R = os.path.join(HERE, "../rtl/ddr3")
IV = os.path.expanduser("~/tools/oss-cad-suite/bin")
GW = os.path.expanduser("~/tools/gowin-standard-1.9.12.04/IDE/simlib/gw5a/prim_sim.v")

TB = r'''`timescale 1ns / 1ps
module tb;
GSR GSR (.GSRI(1'b1));
reg clk50 = 1'b0;
always #10 clk50 = !clk50;

// (the PLL: the memory clock, stopped while its enable is low)
reg raw = 1'b0, en_q = 1'b1, lock = 1'b0;
wire pll_stop;
always #1.25 raw = !raw;
always @(negedge raw) en_q <= pll_stop;
wire memory_clk = raw & en_q;
always @(posedge clk50) lock <= 1'b1;

wire [14:0] ddr_addr;
wire [2:0]  ddr_bank;
wire        ddr_cs, ddr_ras, ddr_cas, ddr_we, ddr_ck, ddr_ck_n, ddr_cke, ddr_odt, ddr_reset_n;
wire [3:0]  ddr_dm, ddr_dqs, ddr_dqs_n;
wire [31:0] ddr_dq;
wire        pclk, calib, cmd_ready, rd_valid, cal_fail, rd_stray;
wire [7:0]  cal_info;
wire [127:0] cal_dbg;
wire [255:0] rd_data;
reg  [2:0]  cmd = 3'd0;
reg         cmd_en = 1'b0;
reg  [28:0] addr = 29'd0;
reg  [255:0] wr_data = 256'd0;

ddr3_top #(.CL(6), .CWL(5), .TCK_PS(2500), .PCLK_KHZ(100000), .FAST(1)) dut (
    .memory_clk(memory_clk), .pll_stop(pll_stop), .clk(clk50), .rst_n(1'b1), .pll_lock(lock),
    .clk_out(pclk), .init_calib_complete(calib),
    .cmd_ready(cmd_ready), .cmd(cmd), .cmd_en(cmd_en), .addr(addr), .wr_data_rdy(),
    .wr_data(wr_data), .wr_data_en(cmd_en), .wr_data_end(cmd_en), .wr_data_mask(32'd0),
    .rd_data(rd_data), .rd_data_valid(rd_valid), .rd_data_end(),
    .cal_fail(cal_fail), .cal_info(cal_info), .cal_dbg(cal_dbg), .cal_map(), .cal_snap(), .rd_stray(rd_stray),
    .cal_opt(16'h0020), .dll_step(),
    .O_ddr_addr(ddr_addr), .O_ddr_ba(ddr_bank), .O_ddr_cs_n(ddr_cs), .O_ddr_ras_n(ddr_ras),
    .O_ddr_cas_n(ddr_cas), .O_ddr_we_n(ddr_we), .O_ddr_clk(ddr_ck), .O_ddr_clk_n(ddr_ck_n),
    .O_ddr_cke(ddr_cke), .O_ddr_odt(ddr_odt), .O_ddr_reset_n(ddr_reset_n), .O_ddr_dqm(ddr_dm),
    .IO_ddr_dq(ddr_dq), .IO_ddr_dqs(ddr_dqs), .IO_ddr_dqs_n(ddr_dqs_n));

// (the strobes rest low when nothing drives them)
assign (weak0, weak1) ddr_dqs = 4'b0000;
assign (weak0, weak1) ddr_dqs_n = 4'b1111;

ddr3_chip #(.LANES(2), .CKDLY(0.30), .DQDLY(0.25), .TDQSCK(0.10), .T_RESET(2000.0), .T_CKE(5000.0)) u0 (
    .ck(ddr_ck), .ck_n(ddr_ck_n), .cke(ddr_cke), .cs_n(ddr_cs), .ras_n(ddr_ras), .cas_n(ddr_cas),
    .we_n(ddr_we), .ba(ddr_bank), .a(ddr_addr), .odt(ddr_odt), .reset_n(ddr_reset_n),
    .dm(ddr_dm[1:0]), .dq(ddr_dq[15:0]), .dqs(ddr_dqs[1:0]), .dqs_n(ddr_dqs_n[1:0]));
ddr3_chip #(.LANES(2), .CKDLY(0.45), .DQDLY(0.30), .TDQSCK(0.25), .T_RESET(2000.0), .T_CKE(5000.0)) u1 (
    .ck(ddr_ck), .ck_n(ddr_ck_n), .cke(ddr_cke), .cs_n(ddr_cs), .ras_n(ddr_ras), .cas_n(ddr_cas),
    .we_n(ddr_we), .ba(ddr_bank), .a(ddr_addr), .odt(ddr_odt), .reset_n(ddr_reset_n),
    .dm(ddr_dm[3:2]), .dq(ddr_dq[31:16]), .dqs(ddr_dqs[3:2]), .dqs_n(ddr_dqs_n[3:2]));

// ---- the lines: 256 places (a bank, one of 32 rows, a column), what each holds ----
reg  [255:0] mem [0:255];
reg  [255:0] held [0:255];              // (written: bit 0 of wrote)
reg  [255:0] wrote = 256'd0;
function [28:0] place(input [7:0] s);
    place = {1'b0, s[2:0], 2'd0, s[7:6], 8'd0, s[5:3], s[1:0], 4'd0, s[7:4] ^ s[3:0], 3'd0};
endfunction
reg  [63:0] rnd = 64'h9e3779b97f4a7c15;
task step; begin rnd = rnd ^ (rnd << 13); rnd = rnd ^ (rnd >> 7); rnd = rnd ^ (rnd << 17); end endtask

// the reads asked for, in order: what each must give
reg  [255:0] expq [0:1023];
reg  [9:0]   exp_w = 10'd0, exp_r = 10'd0;
integer errs = 0, n_rd = 0, n_wr = 0, lone = 0, t_ask = 0, t = 0;
always @(posedge pclk) begin
    t <= t + 1;
    if (rd_valid) begin
        if (exp_w == exp_r) begin
            errs = errs + 1;
            $display("ERROR: a line nobody asked for at %0.1f us", $realtime / 1000.0);
        end else begin
            if (rd_data !== expq[exp_r]) begin
                errs = errs + 1;
                if (errs < 6)
                    $display("ERROR: read %0d wrong at %0.1f us:\n  got  %h\n  want %h", n_rd, $realtime / 1000.0, rd_data, expq[exp_r]);
            end
            exp_r <= exp_r + 10'd1;
            n_rd = n_rd + 1;
            lone = t - t_ask;
        end
    end
end

// a request: given the clock after cmd_ready was seen
task ask(input wr, input [7:0] s, input [255:0] d);
    begin
        while (!cmd_ready) @(posedge pclk);
        cmd_en <= 1'b1;
        cmd <= wr ? 3'd0 : 3'd1;
        addr <= place(s);
        wr_data <= d;
        if (wr) begin
            held[s] = d;
            wrote[s] = 1'b1;
            n_wr = n_wr + 1;
        end else begin
            expq[exp_w] = held[s];
            exp_w = exp_w + 10'd1;
            t_ask = t;
        end
        @(posedge pclk);
        cmd_en <= 1'b0;
    end
endtask

integer k, ops, gap;
reg [7:0] s;
reg [255:0] d;
initial begin
    if ($test$plusargs("vcd")) begin
        $dumpfile("%WORK%/tb.vcd");
        $dumpvars(0, tb);
    end
    if (!$value$plusargs("ops=%d", ops)) ops = 3000;
    wait (calib);
    $display("calibrated at %0.1f us: lanes %h %h %h %h", $realtime / 1000.0,
        cal_dbg[31:0], cal_dbg[63:32], cal_dbg[95:64], cal_dbg[127:96]);
    repeat (8) @(posedge pclk);
    // every place written, then read in a stream
    for (k = 0; k < 256; k = k + 1) begin
        step; d[63:0] = rnd; step; d[127:64] = rnd; step; d[191:128] = rnd; step; d[255:192] = rnd;
        ask(1'b1, k[7:0], d);
    end
    for (k = 0; k < 256; k = k + 1)
        ask(1'b0, k[7:0], 256'd0);
    repeat (40) @(posedge pclk);
    $display("256 lines written and read in a stream at %0.1f us: %0d wrong", $realtime / 1000.0, errs);
    // at random: writes and reads, runs in one row and jumps, gaps
    for (k = 0; k < ops; k = k + 1) begin
        step;
        s = rnd[20] ? s + 8'd8 : rnd[15:8];     // (the next place in the bank and row, or anywhere)
        gap = rnd[31:28] == 4'd0 ? rnd[27:24] : rnd[31:28] < 4'd4 ? 1 : 0;
        repeat (gap) @(posedge pclk);
        while (exp_w - exp_r > 10'd900) @(posedge pclk);
        if (rnd[40] && rnd[41]) begin
            step; d[63:0] = rnd; step; d[127:64] = rnd; step; d[191:128] = rnd; step; d[255:192] = rnd;
            ask(1'b1, s, d);
        end else
            ask(1'b0, s, 256'd0);
    end
    repeat (40) @(posedge pclk);
    $display("%0d more at random at %0.1f us: %0d wrong so far", ops, $realtime / 1000.0, errs);
    // a read alone, after a wait: how long it takes
    repeat (300) @(posedge pclk);
    ask(1'b0, 8'd77, 256'd0);
    repeat (40) @(posedge pclk);
    $display("a read alone: its line %0d clocks after it was asked for", lone);
    // a long stream of reads (refreshes come due in it), then a read alone at once
    for (k = 0; k < 2000; k = k + 1) begin
        while (exp_w - exp_r > 10'd900) @(posedge pclk);
        ask(1'b0, k[7:0], 256'd0);
    end
    repeat (60) @(posedge pclk);
    ask(1'b0, 8'd5, 256'd0);
    repeat (80) @(posedge pclk);
    $display("a read alone after a stream of 2000: %0d clocks", lone);
    if (exp_w != exp_r) begin
        errs = errs + 1;
        $display("ERROR: %0d reads never came", exp_w - exp_r);
    end
    $display("reads %0d, writes %0d; wrong %0d; the chips' errors %0d %0d (reads %0d writes %0d refreshes %0d); stray %b",
        n_rd, n_wr, errs, u0.errors, u1.errors, u0.n_rd, u0.n_wr, u0.n_ref, rd_stray);
    $display("%0s", errs == 0 && u0.errors == 0 && u1.errors == 0 && !rd_stray ? "PASS" : "FAIL");
    $finish;
end
always @(posedge cal_fail) begin
    $display("calibration FAILED at %0.1f us: info %h", $realtime / 1000.0, cal_info);
    #1000 $display("FAIL");
    $finish;
end
initial #60000000 begin $display("TIMEOUT"); $display("FAIL"); $finish; end
endmodule
'''


def main():
    os.makedirs(WORK, exist_ok=True)
    # (Gowin's models, OSER8_MEM under another name: sim/ddr3/oser8_mem.v stands on it)
    prim = os.path.join(WORK, "prim_sim.v")
    open(prim, "w").write(open(GW, errors="replace").read().replace("module OSER8_MEM ", "module OSER8_MEM_gowin "))
    tb = os.path.join(WORK, "tb.v")
    open(tb, "w").write(TB.replace("%WORK%", WORK))
    src = [tb, os.path.join(HERE, "ddr3/ddr3_chip.v"), os.path.join(HERE, "ddr3/oser8_mem.v"),
           os.path.join(HERE, "ddr3/dqs_model.v"), prim] + [os.path.join(R, "ddr3_%s.v" % n) for n in ("top", "ctl", "cal", "dp", "phy")]
    subprocess.check_call([os.path.join(IV, "iverilog"), "-g2012", "-o", os.path.join(WORK, "tb"), "-s", "tb"] + src)
    args = ["+" + a.lstrip("+") for a in sys.argv[1:]]
    out = subprocess.run([os.path.join(IV, "vvp"), "-n", os.path.join(WORK, "tb")] + args, stdout=subprocess.PIPE, text=True).stdout
    lines = [ln for ln in out.splitlines() if "$finish" not in ln]
    for ln in lines[:40] + (["..."] if len(lines) > 80 else []) + lines[-40:] if len(lines) > 80 else lines:
        print(ln)
    sys.exit(0 if lines and lines[-1] == "PASS" else 1)


if __name__ == "__main__":
    main()
