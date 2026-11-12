#!/usr/bin/env python3
"""cpu_tb.py: the register bus's three masters at once (iverilog): rtl/cpu.v's turns (a stand-in for
the SoC: an AHB master that reads and writes registers as the core would), the monitor's host on the
UART, and the link on rtl/spis.v's SPI port, each on registers of its own: every word read is the one
last written.  And the link's messages: requests of every length to the stand-in, which answers each
with its bytes turned over and a few more."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build")

TB = r'''`timescale 1ns/1ps
// the SoC's stand-in: its extended AHB slave port driven by tasks
module RiscV_AE350_SOC_Top (
    input [31:0] ROM_HRDATA, input ROM_HREADY, input ROM_HRESP, output [31:0] ROM_HADDR, output [1:0] ROM_HTRANS,
    output ROM_HWRITE, output ROM_HCLK, output ROM_HRSTN,
    input [63:0] DDR_HRDATA, input DDR_HREADY, input DDR_HRESP, output [31:0] DDR_HADDR, output [2:0] DDR_HBURST,
    output [3:0] DDR_HPROT, output [2:0] DDR_HSIZE, output [1:0] DDR_HTRANS, output [63:0] DDR_HWDATA, output DDR_HWRITE,
    output DDR_HCLK, output DDR_HRSTN,
    input TCK_IN, input TMS_IN, input TRST_IN, input TDI_IN, output TDO_OUT, output TDO_OE, input [15:0] EXT_INT,
    input [31:0] EXTS_HRDATA, input EXTS_HREADYIN, input EXTS_HRESP, output reg [31:0] EXTS_HADDR, output [2:0] EXTS_HBURST,
    output [3:0] EXTS_HPROT, output reg EXTS_HSEL, output [2:0] EXTS_HSIZE, output reg [1:0] EXTS_HTRANS,
    output reg [31:0] EXTS_HWDATA, output reg EXTS_HWRITE, output EXTS_HCLK, output EXTS_HRSTN,
    output UART2_TXD, output UART2_RTSN, input UART2_RXD, input UART2_CTSN, input UART2_DCDN, input UART2_DSRN,
    input UART2_RIN, output UART2_DTRN, output UART2_OUT1N, output UART2_OUT2N,
    input [31:0] GPIO_IN, output [31:0] GPIO_OE, output [31:0] GPIO_OUT, output CORE0_WFI_MODE, output RTC_WAKEUP,
    input CORE_CLK, input DDR_CLK, input AHB_CLK, input APB_CLK, input RTC_CLK, input POR_RSTN, input HW_RSTN
);
    // (the clock back a little late, as from the chip's core)
    assign #0.7 EXTS_HCLK = AHB_CLK;
    assign ROM_HCLK = AHB_CLK;
    assign ROM_HTRANS = 2'b00;
    initial begin EXTS_HSEL = 0; EXTS_HTRANS = 0; EXTS_HWRITE = 0; EXTS_HADDR = 0; EXTS_HWDATA = 0; end
    task xfer(input wr, input [7:0] r, input [31:0] d, output [31:0] q);
        begin
            @(posedge EXTS_HCLK); #0.2;
            EXTS_HSEL = 1; EXTS_HTRANS = 2'b10; EXTS_HWRITE = wr; EXTS_HADDR = 32'hE8000000 + 4 * r;
            @(posedge EXTS_HCLK); while (!EXTS_HREADYIN) @(posedge EXTS_HCLK);
            #0.2; EXTS_HSEL = 0; EXTS_HTRANS = 2'b00; EXTS_HWDATA = d;
            @(posedge EXTS_HCLK); while (!EXTS_HREADYIN) @(posedge EXTS_HCLK);
            q = EXTS_HRDATA;
        end
    endtask
endmodule

module tb;
    reg clk = 0; always #10 clk = ~clk;
    reg rx = 1; wire tx;
    reg [31:0] rdata; reg [31:0] r [0:7];
    wire [7:0] m_addr, c_addr, s_addr; wire [31:0] m_wdata, c_wdata, s_wdata; wire m_we, c_we, c_own, s_we, s_own, c_stall, s_stall, busy;
    wire stall = c_stall || s_stall;
    wire [7:0] addr = c_own ? c_addr : s_own ? s_addr : m_addr; wire [31:0] wdata = c_own ? c_wdata : s_own ? s_wdata : m_wdata;
    wire we = c_own ? c_we : s_own ? s_we : m_we;
    reg cs_n = 1, sck = 0, mosi = 0; wire miso, irq_n; wire [31:0] q_stat, q_rx, q_pins;
    spis u_spi (.clk(clk), .cs_n(cs_n), .sck(sck), .mosi(mosi), .miso(miso), .irq_n(irq_n), .stall(s_stall), .mon_busy(busy),
                .other(c_stall), .s_own(s_own), .s_we(s_we), .s_addr(s_addr), .s_wdata(s_wdata), .rdata(rdata), .we(we), .addr(addr),
                .wdata(wdata), .q_stat(q_stat), .q_rx(q_rx), .q_pins(q_pins));
    mon #(.DIV(4)) u_mon (.clk(clk), .rx(rx), .tx(tx), .addr(m_addr), .wdata(m_wdata), .we(m_we), .rdata(rdata), .hold(1'b0),
                          .stall(stall), .busy(busy));
    cpu #(.HEX("%(work)s/cpu_tb_rom.hex"), .WORDS(16)) dut (.clk(clk), .core_clk(1'b0), .rst_n(1'b1), .pm_we(1'b0), .pm_wa(13'd0),
        .pm_wd(32'd0), .stall(c_stall), .mon_busy(busy), .other(s_own), .c_own(c_own), .c_we(c_we), .c_addr(c_addr), .c_wdata(c_wdata),
        .rdata(rdata), .txd(), .rxd(1'b1), .wfi());
    integer k;
    initial for (k = 0; k < 8; k = k + 1) r[k] = 0;
    always @(posedge clk) begin
        if (we && addr[7:3] == 5'b01100) r[addr[2:0]] <= wdata;
        rdata <= addr[7:3] == 5'b01100 ? r[addr[2:0]] : addr == 8'h70 ? q_stat : addr == 8'h71 ? q_rx : addr == 8'h74 ? q_pins : 32'hBAD0BAD0;
    end
    // the host: bytes onto the monitor's UART (4 clocks a bit), its answers taken off
    task send(input [7:0] b); integer i; begin
        rx = 0; repeat (4) @(posedge clk);
        for (i = 0; i < 8; i = i + 1) begin rx = b[i]; repeat (4) @(posedge clk); end
        rx = 1; repeat (4) @(posedge clk);
    end endtask
    reg [7:0] got [0:3]; integer gn = 0; integer gi;
    reg [7:0] sh;
    always begin
        @(negedge tx); repeat (6) @(posedge clk);
        for (gi = 0; gi < 8; gi = gi + 1) begin sh[gi] = tx; repeat (4) @(posedge clk); end
        got[gn & 3] = sh; gn = gn + 1;
    end
    integer bad = 0, hi, ci, mreads = 0, creads = 0, sreads = 0, msgs = 0, ml, mi, mj, mk;
    reg [7:0] mb [0:255]; reg [31:0] mw;
    // the link: SPI mode 0, 5 MHz, not in step with clk
    reg [7:0] sq;
    task spi_byte(input [7:0] b); integer i; begin
        for (i = 7; i >= 0; i = i - 1) begin
            mosi = b[i]; #101; sck = 1; sq[i] = miso; #101; sck = 0;
        end
    end endtask
    integer si, sl, sj, sn; reg [31:0] sv, sr; reg [7:0] sm [0:255]; reg [7:0] st; reg [15:0] rl; reg sdone = 0;
    initial begin
        #5003;
        for (si = 0; si < 40; si = si + 1) begin
            // a register written (two words to two registers by turns) and read back
            sv = {$random};
            cs_n = 0; #150; spi_byte(8'h01); spi_byte(8'h62 + (si & 1));
            spi_byte(sv[7:0]); spi_byte(sv[15:8]); spi_byte(sv[23:16]); spi_byte(sv[31:24]); #150; cs_n = 1; #400;
            cs_n = 0; #150; spi_byte(8'h02); spi_byte(8'h62 + (si & 1)); spi_byte(8'h00);
            spi_byte(0); sr[7:0] = sq; spi_byte(0); sr[15:8] = sq; spi_byte(0); sr[23:16] = sq; spi_byte(0); sr[31:24] = sq;
            #150; cs_n = 1; #400;
            sreads = sreads + 1;
            if (sr !== sv) begin bad = bad + 1; $display("spi: wrote %%h read %%h", sv, sr); end
            // a message of some length, and its answer
            sl = si == 0 ? 1 : si == 1 ? 252 : si == 2 ? 4 : 1 + {$random} %% 252;
            cs_n = 0; #150; spi_byte(8'h03);
            for (sj = 0; sj < sl; sj = sj + 1) begin sm[sj] = {$random}; spi_byte(sm[sj]); end
            #150; cs_n = 1; #400;
            sn = 0; st = 0;
            while (!st[0] && sn < 4000) begin
                if (irq_n) begin #20000; sn = sn + 1; end
                else begin
                    cs_n = 0; #150; spi_byte(8'h04); spi_byte(0); st = sq;
                    if (st[0]) begin
                        spi_byte(0); rl[7:0] = sq; spi_byte(0); rl[15:8] = sq;
                        if (rl !== sl + 3) begin bad = bad + 1; $display("spi: a message of %%0d, an answer of %%0d", sl, rl); end
                        for (sj = 0; sj < rl; sj = sj + 1) begin
                            spi_byte(0);
                            if (sq !== (sj < sl ? sm[sl - 1 - sj] : 8'hA0 + (sj - sl))) begin
                                bad = bad + 1;
                                if (bad < 12) $display("spi: message %%0d of %%0d bytes: byte %%0d is %%h", si, sl, sj, sq);
                            end
                        end
                    end
                    #150; cs_n = 1; #400;
                end
            end
            if (!st[0]) begin bad = bad + 1; $display("spi: no answer to message %%0d", si); end
            else msgs = msgs + 1;
        end
        sdone = 1;
    end
    reg [31:0] hv, hq, cv, cq, cq2, exp_m [0:1], exp_c [0:1];
    reg hdone = 0;
    // the host on registers 0x60, 0x61 (and reads the CPU's 0x62 now and then: whatever it is, a word the CPU wrote)
    initial begin
        exp_m[0] = 0; exp_m[1] = 0;
        repeat (200) @(posedge clk);
        for (hi = 0; hi < 60; hi = hi + 1) begin
            hv = {$random};
            send("W"); send(8'h60 + (hi & 1)); send(hv[7:0]); send(hv[15:8]); send(hv[23:16]); send(hv[31:24]);
            exp_m[hi & 1] = hv;
            gn = 0;
            send("R"); send(8'h60 + (hi & 1));
            wait (gn == 4); repeat (8) @(posedge clk);
            hq = {got[3], got[2], got[1], got[0]};
            mreads = mreads + 1;
            if (hq !== hv) begin bad = bad + 1; $display("host: wrote %%h read %%h", hv, hq); end
        end
        hdone = 1;
    end
    // the CPU on 0x64, 0x65, and reading the host's
    initial begin
        exp_c[0] = 0; exp_c[1] = 0;
        repeat (100) @(posedge clk);
        ci = 0;
        while (!hdone || !sdone) begin
            cv = {$random};
            dut.u_soc.xfer(1, 8'h64 + (ci & 1), cv, cq);
            dut.u_soc.xfer(0, 8'h64 + (ci & 1), 0, cq);
            creads = creads + 1;
            if (cq !== cv) begin bad = bad + 1; $display("cpu: wrote %%h read %%h", cv, cq); end
            dut.u_soc.xfer(0, 8'h60 + (ci & 1), 0, cq);
            dut.u_soc.xfer(0, 8'h60 + (ci & 1), 0, cq2);
            if (cq !== exp_m[ci & 1] && cq2 !== exp_m[ci & 1] && cq !== cq2) begin bad = bad + 1; $display("cpu: the host's %%h read %%h %%h", exp_m[ci & 1], cq, cq2); end
            ci = ci + 1;
            // a request from the link: its bytes turned over, and three more, back
            dut.u_soc.xfer(0, 8'h70, 0, cq);
            if (cq[0]) begin
                ml = cq[15:8];
                for (mi = 0; mi < (ml + 3) / 4; mi = mi + 1) begin
                    dut.u_soc.xfer(1, 8'h71, mi, cq2);
                    dut.u_soc.xfer(0, 8'h71, 0, cq2);
                    {mb[4 * mi + 3], mb[4 * mi + 2], mb[4 * mi + 1], mb[4 * mi]} = cq2;
                end
                dut.u_soc.xfer(1, 8'h72, 0, cq2);
                for (mi = 0; mi < (ml + 3 + 3) / 4; mi = mi + 1) begin
                    for (mj = 0; mj < 4; mj = mj + 1) begin
                        mk = 4 * mi + mj;
                        mw[8 * mj +: 8] = mk < ml ? mb[ml - 1 - mk] : 8'hA0 + (mk - ml);
                    end
                    dut.u_soc.xfer(1, 8'h73, mw, cq2);
                end
                dut.u_soc.xfer(1, 8'h70, 32'd3 | (ml + 3) << 16, cq2);
            end
            repeat ({$random} %% 7) @(posedge clk);
        end
        $display("done: %%0d host reads, %%0d cpu reads, %%0d link reads, %%0d messages, %%0d wrong", mreads, creads, sreads, msgs, bad);
        $finish;
    end
    initial begin #2000000000; $display("done: TIMEOUT %%0d host reads, %%0d cpu reads", mreads, creads); $finish; end
endmodule
'''


def main():
    os.makedirs(WORK, exist_ok=True)
    open(os.path.join(WORK, "cpu_tb.v"), "w").write(TB % dict(work=WORK))
    open(os.path.join(WORK, "cpu_tb_rom.hex"), "w").write("00000013\n" * 16)
    rtl = [os.path.join(HERE, "../rtl", f) for f in ("cpu.v", "mon.v", "uart.v", "spis.v")]
    subprocess.check_call(["iverilog", "-g2005", "-o", os.path.join(WORK, "cpu_tb.vvp"), os.path.join(WORK, "cpu_tb.v")] + rtl)
    out = subprocess.check_output(["vvp", os.path.join(WORK, "cpu_tb.vvp")]).decode()
    print("\n".join(out.strip().splitlines()[-8:]))
    return 0 if " 0 wrong" in out and "TIMEOUT" not in out else 1


if __name__ == "__main__":
    sys.exit(main())
