// Gowin's DQS block (the GW5A's, DQS_MODE "X4"), a behavioural model for
// the PHY's simulation: ours.  The GW5A's own model is encrypted; this one
// follows UG306's port table, the structure of Gowin's plain model of the
// same block in the GW2A (the install's simlib) and what the board showed
// (2026-11-11, the GW5AST-138C under tools/console/ddr3lab.py):
//
//   writes   DQSW0: FCLK (stopped by HOLD for whole groups of four) WSTEP
//            taps late; DQSW270: the inverse of FCLK late by the write
//            delay (DLLSTEP + WSTEP as WLOADN is low, a tap a WMOVE pulse)
//   reads    READ's four bits (a slot each, bit 0 first) open the gate on
//            DQSIN: from when both halves of a slot are seen until the
//            first falling strobe edge after they are gone, RCLKSEL
//            quarter clocks later (the board: 0 to 7 in order, the gate's
//            good window four of them wide; the GW2A's model orders them
//            otherwise).  DQSR90: the gated strobe late by the read delay
//            (DLLSTEP as RLOADN is low, a tap a RMOVE pulse): the
//            deserializers' clock.
//   the FIFO WPOINT counts the gated strobe, RPOINT the fast clock, four
//            at a time from a pclk boundary once WPOINT is ahead: RVALID
//   RBURST   a burst gated whole: an even count of strobe edges and the
//            gate's request ended between the last two falling ones
//
// Not modelled: the delay of the pins' buffers (the board's gate window is
// some two ns later than a simulation with the wires' flight alone), the
// read data's eye against DQSR90 (on the board the DLL's code is at its
// late edge).

`timescale 1ns / 1ps

module DQS #(
    parameter      FIFO_MODE_SEL = 1'b0,
    parameter      RD_PNTR = 3'b000,
    parameter      DQS_MODE = "X4",
    parameter      HWL = "false",
    parameter      GSREN = "false",
    parameter real TAP = 0.0125
) (
    input  wire       DQSIN,
    input  wire       PCLK,
    input  wire       FCLK,
    input  wire       RESET,
    input  wire [3:0] READ,
    input  wire [2:0] RCLKSEL,
    input  wire [7:0] DLLSTEP,
    input  wire [7:0] WSTEP,
    input  wire       RLOADN,
    input  wire       RMOVE,
    input  wire       RDIR,
    input  wire       WLOADN,
    input  wire       WMOVE,
    input  wire       WDIR,
    input  wire       HOLD,
    output wire       DQSR90,
    output wire       DQSW0,
    output wire       DQSW270,
    output wire [2:0] RPOINT,
    output reg  [2:0] WPOINT,
    output wire       RVALID,
    output wire       RBURST,
    output wire       RFLAG,
    output wire       WFLAG
);

initial if (DQS_MODE != "X4" || FIFO_MODE_SEL != 1'b0) begin
    $display("ERROR %m: only the X4 memory mode is modelled");
    $finish;
end

// ---- the write clocks ----
reg [2:0] hold_s = 3'b000;
reg [1:0] hold_n = 2'b00;
always @(negedge FCLK or posedge RESET)
    if (RESET) begin
        hold_s <= 3'b000;
        hold_n <= 2'b00;
    end else begin
        hold_s <= {hold_s[1:0], HOLD};
        if (hold_s[2] || hold_n != 0)
            hold_n <= hold_n + 1'b1;
    end
wire fclk_w = FCLK & !(hold_s[2] || hold_n != 0);

reg [7:0] wstep = 8'd0, rstep = 8'd0;
wire [8:0] wsum = DLLSTEP + WSTEP;
wire [7:0] wload = wsum > 255 ? 8'd255 : wsum[7:0];
assign WFLAG = (wstep == 8'hff && !WDIR) || (wstep == 8'h00 && WDIR);
assign RFLAG = (rstep == 8'hff && !RDIR) || (rstep == 8'h00 && RDIR);
always @(wload or WLOADN)
    if (!WLOADN) wstep = wload;
always @(negedge WMOVE)
    if (WLOADN) begin
        if (!WDIR && wstep != 8'hff) wstep = wstep + 1'b1;
        else if (WDIR && wstep != 8'h00) wstep = wstep - 1'b1;
    end
always @(DLLSTEP or RLOADN)
    if (!RLOADN) rstep = DLLSTEP;
always @(negedge RMOVE)
    if (RLOADN) begin
        if (!RDIR && rstep != 8'hff) rstep = rstep + 1'b1;
        else if (RDIR && rstep != 8'h00) rstep = rstep - 1'b1;
    end

reg w0 = 1'b0, w90 = 1'b0;
always @(fclk_w) begin
    w0  <= #(WSTEP * TAP) fclk_w;
    w90 <= #(wstep * TAP) fclk_w;
end
assign DQSW0 = w0;
assign DQSW270 = !w90;

// ---- the gate's request: READ, a slot a bit, on the write clock, then
// RCLKSEL quarter clocks ----
wire clk_rd = w0;
wire clk_rd_s = !clk_rd;
real tck = 2.5, t_f = 0.0;
always @(posedge FCLK) begin
    if (t_f > 0.0 && $realtime - t_f > 0.5 && $realtime - t_f < 20.0)
        tck = $realtime - t_f;
    t_f = $realtime;
end

reg       f_run = 1'b0, r_run = 1'b0;
reg [1:0] f_cnt = 2'b00, r_cnt = 2'b00;
reg       upd0 = 1'b0, upd1 = 1'b0;
reg [3:0] rd0 = 4'd0, rd1 = 4'd0;
reg       q3 = 1'b0, d23 = 1'b0, d123 = 1'b0, rdq = 1'b0, rdqq = 1'b0;
reg       rd_post = 1'b0, rd_pre = 1'b0;

always @(posedge FCLK or posedge RESET)
    if (RESET)
        f_run <= 1'b0;
    else
        f_run <= 1'b1;
always @(posedge FCLK or negedge f_run)
    if (!f_run) begin
        f_cnt <= 2'b00;
        upd0 <= 1'b0;
    end else begin
        f_cnt <= f_cnt + 1'b1;
        upd0 <= f_cnt == 2'b01;
    end
always @(posedge clk_rd or posedge RESET)
    if (RESET)
        r_run <= 1'b0;
    else
        r_run <= 1'b1;
always @(posedge clk_rd or negedge r_run)
    if (!r_run) begin
        r_cnt <= 2'b00;
        upd1 <= 1'b0;
    end else begin
        r_cnt <= r_cnt + 1'b1;
        upd1 <= HWL == "false" ? r_cnt == 2'b00 : r_cnt == 2'b01;
    end
always @(posedge PCLK or posedge RESET)
    if (RESET)
        rd0 <= 4'd0;
    else
        rd0 <= READ;
always @(posedge FCLK or posedge RESET)
    if (RESET)
        rd1 <= 4'd0;
    else if (upd0)
        rd1 <= rd0;
always @(posedge clk_rd or posedge RESET)
    if (RESET) begin
        q3 <= 1'b0; d23 <= 1'b0; d123 <= 1'b0; rdq <= 1'b0; rdqq <= 1'b0;
    end else begin
        rdqq <= rdq;
        if (upd1) begin
            q3 <= rd1[3]; d23 <= rd1[2]; d123 <= rd1[1]; rdq <= rd1[0];
        end else begin
            d23 <= q3; d123 <= d23; rdq <= d123;
        end
    end
// (the request a little after its clock's edge: an edge at the same time
// takes the old one)
wire #0.2 rd_reg = rdq;
always @(posedge clk_rd_s or posedge RESET)
    if (RESET) rd_post <= 1'b0; else rd_post <= rd_reg;
always @(negedge clk_rd_s or posedge RESET)
    if (RESET) rd_pre <= 1'b0; else rd_pre <= rd_post;
wire rd_en0 = rd_post & rd_pre;
reg  rd_en = 1'b0;
always @(rd_en0) rd_en <= #(RCLKSEL * tck / 4.0) rd_en0;

// ---- the gate ----
reg  dqs_en = 1'b0;
wire dqs_c = DQSIN & dqs_en;
wire dqs_set = rd_en & !RESET;
always @(negedge dqs_c or posedge RESET or posedge dqs_set)
    if (RESET)
        dqs_en <= 1'b0;
    else if (dqs_set)
        dqs_en <= 1'b1;
    else
        dqs_en <= rd_en;

reg r90 = 1'b0;
always @(dqs_c) r90 <= #(rstep * TAP) dqs_c;
assign DQSR90 = r90;

// ---- the burst seen whole ----
wire #0.2 dqs_en_n = !dqs_en;
wire det_rstn = !(dqs_en & dqs_en_n) & !RESET;     // (a pulse as the gate opens)
reg  e1 = 1'b0, e1q = 1'b0, e0 = 1'b0, e0q = 1'b0, n0 = 1'b0, n0q = 1'b0;
always @(posedge dqs_c or negedge det_rstn)
    if (!det_rstn) begin
        e1 <= 1'b0; e1q <= 1'b0;
    end else if (dqs_en) begin
        e1 <= !e1; e1q <= e1;
    end
always @(negedge dqs_c or negedge det_rstn)
    if (!det_rstn) begin
        e0 <= 1'b0; e0q <= 1'b0;
    end else begin
        e0 <= !e0; e0q <= e0;
    end
always @(negedge r90 or negedge det_rstn)
    if (!det_rstn) begin
        n0 <= 1'b0; n0q <= 1'b0;
    end else if (rd_en) begin
        n0 <= !n0; n0q <= n0;
    end
assign RBURST = (!e1 & e1q & !dqs_en) & !(!(!e0 & e0q) | !(n0 & !n0q));

// ---- the FIFO's pointers ----
function [2:0] nxt(input [2:0] q);
    nxt = {(q[1] & !q[0]) | (q[2] & q[0]), (!q[2] & q[0]) | (q[1] & !q[0]), q[1] ~^ q[2]};
endfunction

wire      rst_f = RESET | HOLD;
reg [2:0] wq = 3'b000, rq = 3'b000;
always @(posedge r90 or posedge rst_f)
    if (rst_f) wq <= 3'b000; else wq <= nxt(wq);
always @(negedge r90 or posedge rst_f)
    if (rst_f) WPOINT <= 3'b000; else WPOINT <= wq;

reg       p_run = 1'b0, u_run = 1'b0;
reg [1:0] u_cnt = 2'b00;
reg       upd_a = 1'b0, upd_p = 1'b0;
reg       sh0 = 1'b0, sh1 = 1'b0, sh_q = 1'b0, sign = 1'b0, rd_q = 1'b0, rd_q1 = 1'b0, rd_up = 1'b0;
reg       rvalid = 1'b0;
always @(posedge FCLK or posedge rst_f)
    if (rst_f) p_run <= 1'b0; else p_run <= 1'b1;
always @(posedge FCLK or posedge RESET)
    if (RESET) u_run <= 1'b0; else u_run <= 1'b1;
always @(posedge FCLK or negedge u_run)
    if (!u_run) begin
        u_cnt <= 2'b00;
        upd_a <= 1'b0;
    end else begin
        u_cnt <= u_cnt + 1'b1;
        upd_a <= u_cnt == 2'b01;
    end
always @(posedge FCLK or posedge rst_f)
    if (rst_f) upd_p <= 1'b0; else upd_p <= upd_a;

wire shift = sign ? wq != nxt(rq) : wq != rq;
always @(FCLK or p_run or shift)
    if (!p_run) begin
        sh0 <= 1'b0;
        sh1 <= 1'b0;
    end else if (!FCLK)
        sh0 <= shift;
    else
        sh1 <= shift;
always @(negedge FCLK or negedge p_run)
    if (!p_run) sh_q <= 1'b0; else sh_q <= sh0 & !sign;
always @(posedge FCLK or negedge p_run)
    if (!p_run) begin
        sign <= 1'b0; rd_q <= 1'b0; rd_q1 <= 1'b0; rd_up <= 1'b0;
        rq <= RD_PNTR;
    end else begin
        sign <= sh1 & (sh_q | sign);
        if (upd_a) rd_q <= sh1 & (sh_q | sign); else rd_q1 <= rd_q;
        if (upd_p) rd_up <= rd_q1;
        if (rd_q) rq <= nxt(rq);
    end
always @(posedge PCLK or negedge p_run)
    if (!p_run) rvalid <= 1'b0; else rvalid <= rd_up;
assign RPOINT = rq;
assign RVALID = rvalid;

endmodule
