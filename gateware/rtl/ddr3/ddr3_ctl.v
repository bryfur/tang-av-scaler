// The DDR3 controller (the first: a request at a time, rows left open).
// The user's port is Gowin's DDR3 Memory Interface's, as the console uses
// it: cmd (0 a write, 1 a read), cmd_en, addr ({rank, bank 3, row 15,
// column 10}: a line is 8 columns), a write's 256 bits and its mask (1: a
// byte not written) with the command; a command is given the clock after
// cmd_ready was seen; reads come back in order (ddr3_dp.v's rd_valid).
//
// A request waits in `rq` (one more behind it in `sk`: the command a
// ready already promised).  Each clock, one command for it:
//
//   its bank open at its row    the read or the write, when the timers allow
//   its bank open elsewhere     PRE
//   its bank closed             ACT
//
// Reads go in slot 0 of a cycle (ddr3_dp.v: why), writes in the slot that
// starts their data with a cycle, ACT in slot 2 (a read two cycles later
// is tRCD after it at DDR3-800), PRE and REF in slot 0: the timers below
// count cycles between those slots.  They are common to the
// eight banks here (a bank waits out another's).
//
// Refresh: one owed every 7.8 us; given when no request waits, or at once
// when six are owed (JEDEC lets eight wait): all banks closed, REF.

module ddr3_ctl #(
    parameter CL       = 6,
    parameter CWL      = 5,
    parameter TCK_PS   = 2500,
    parameter PCLK_KHZ = 100000,
    // (JEDEC's DDR3-800E; ps)
    parameter T_RCD = 15000,
    parameter T_RP  = 15000,
    parameter T_RAS = 37500,
    parameter T_WR  = 15000,
    parameter T_WTR = 7500,
    parameter T_RTP = 7500,
    parameter T_RFC = 260000
) (
    input  wire        clk,
    input  wire        rst,               // (until the calibration is done)

    output wire        cmd_ready,
    input  wire        cmd_en,
    input  wire        cmd_wr,
    input  wire [28:0] addr,
    input  wire [255:0] wr_data,
    input  wire [31:0] wr_mask,

    output reg  [3:0]  o_cmd = 4'hf,
    output reg  [1:0]  o_slot = 2'd0,
    output reg  [2:0]  o_ba = 3'd0,
    output reg  [14:0] o_a = 15'd0,
    output reg         wr_go = 1'b0,
    output reg  [255:0] o_wdata = 256'd0,
    output reg  [31:0] o_wmask = 32'd0,
    output reg         rd_go = 1'b0
);

localparam REF = 4'b0001, PRE = 4'b0010, ACT = 4'b0011, WRC = 4'b0100, RDC = 4'b0101, DES = 4'b1111;
localparam RSLOT = 0, WSLOT = (4 - CWL % 4) % 4, ASLOT = 2, PSLOT = 0;

// a time in slots (at least `least` clocks), and the cycles from a command
// in slot s1 to one in slot s2 that far apart
function integer slots(input integer ps, input integer least);
    begin
        slots = (ps + TCK_PS - 1) / TCK_PS;
        if (slots < least) slots = least;
    end
endfunction
function integer cyc(input integer n, input integer s1, input integer s2);
    begin
        cyc = (n - (s2 - s1) + 3) / 4;
        if (cyc < 1) cyc = 1;
    end
endfunction
localparam C_ACT_RD  = cyc(slots(T_RCD, 0), ASLOT, RSLOT);
localparam C_ACT_WR  = cyc(slots(T_RCD, 0), ASLOT, WSLOT);
localparam C_ACT_PRE = cyc(slots(T_RAS, 0), ASLOT, PSLOT);
localparam C_PRE_ACT = cyc(slots(T_RP, 0), PSLOT, ASLOT);
localparam C_PRE_REF = cyc(slots(T_RP, 0), PSLOT, PSLOT);
localparam C_RD_PRE  = cyc(slots(T_RTP, 4), RSLOT, PSLOT);
localparam C_WR_PRE  = cyc(CWL + 4 + slots(T_WR, 0), WSLOT, PSLOT);
localparam C_WR_RD   = cyc(CWL + 4 + slots(T_WTR, 4), WSLOT, RSLOT);
// (a write after a read: JEDEC's RL + tCCD + 2 - WL, and two slots more:
// the data pins drive from two slots before the write's first beat)
localparam C_RD_WR   = cyc(CL + 4 + 2 - CWL + 2, RSLOT, WSLOT);
localparam C_REF     = cyc(slots(T_RFC, 0), PSLOT, ASLOT);
localparam [15:0] T_REFI = PCLK_KHZ * 78 / 10000;      // 7.8 us

// ---- the request and the one behind it ----
reg         rq_v = 1'b0, sk_v = 1'b0;
reg         rq_wr = 1'b0, sk_wr = 1'b0;
reg [28:0]  rq_a = 29'd0, sk_a = 29'd0;
reg [255:0] rq_d = 256'd0, sk_d = 256'd0;
reg [31:0]  rq_m = 32'd0, sk_m = 32'd0;
wire [2:0]  rq_bank = rq_a[27:25];
wire [14:0] rq_row = rq_a[24:10];

// ---- the banks ----
// (rq_hit: the request's row is its bank's open one: found as the request
// comes into rq, kept right as banks open and close)
reg [7:0]   open = 8'd0;
reg [14:0]  row [0:7];
reg         rq_hit = 1'b0;
wire [28:0] in_a = sk_v ? sk_a : addr;
wire        in_hit = open[in_a[27:25]] && row[in_a[27:25]] == in_a[24:10];
wire        hit = rq_hit;

// ---- the timers: cycles until a command may go ----
reg [5:0] t_rd = 0, t_wr = 0, t_pre = 0, t_act = 0, t_ref = 0;
function [5:0] atleast(input [5:0] t, input integer nn);
    atleast = t > nn ? t : nn[5:0];
endfunction

// ---- refresh ----
reg [15:0] ref_t = 16'd0;
reg [3:0]  ref_owed = 4'd0;
reg        ref_run = 1'b0;                // (closing the banks for one)
wire       ref_force = ref_owed >= 4'd6;
wire       ref_now = ref_owed != 0 && ((!rq_v && !cmd_en) || ref_force);

wire cas_ok = rq_wr ? t_wr == 0 : t_rd == 0;
wire take = rq_v && !ref_run && !ref_force && hit && cas_ok;
wire pre_all = (ref_run || ref_now) && open != 0 && t_pre == 0;
assign cmd_ready = !sk_v && (!rq_v || take) && !ref_run && !rst;

integer k;
always @(posedge clk) begin
    o_cmd <= DES;
    wr_go <= 1'b0;
    rd_go <= 1'b0;
    if (t_rd != 0) t_rd <= t_rd - 1'b1;
    if (t_wr != 0) t_wr <= t_wr - 1'b1;
    if (t_pre != 0) t_pre <= t_pre - 1'b1;
    if (t_act != 0) t_act <= t_act - 1'b1;
    if (t_ref != 0) t_ref <= t_ref - 1'b1;

    ref_t <= ref_t + 1'b1;
    if (ref_t == T_REFI - 1) begin
        ref_t <= 16'd0;
        if (ref_owed != 4'd15) ref_owed <= ref_owed + 1'b1;
    end

    // ---- one command ----
    if (ref_run || ref_now) begin
        ref_run <= 1'b1;
        if (open != 0) begin
            if (t_pre == 0) begin
                o_cmd <= PRE;
                o_slot <= PSLOT;
                o_a <= 15'h0400;          // (all banks)
                open <= 8'd0;
                t_act <= atleast(t_act, C_PRE_ACT - 1);
                t_ref <= C_PRE_REF - 1;
            end
        end else if (t_ref == 0 && t_act == 0) begin
            o_cmd <= REF;
            o_slot <= PSLOT;
            t_act <= C_REF - 1;
            // (owed less one: this clock's tick counted too)
            ref_owed <= ref_owed - 1'b1 + (ref_t == T_REFI - 1 ? 1'b1 : 1'b0);
            ref_run <= 1'b0;
        end
    end else if (rq_v) begin
        if (hit) begin
            if (cas_ok) begin
                o_cmd <= rq_wr ? WRC : RDC;
                o_slot <= rq_wr ? WSLOT : RSLOT;
                o_ba <= rq_bank;
                o_a <= {5'd0, rq_a[9:0]};
                wr_go <= rq_wr;
                rd_go <= !rq_wr;
                o_wdata <= rq_d;
                o_wmask <= rq_m;
                if (rq_wr) begin
                    t_rd <= atleast(t_rd, C_WR_RD - 1);
                    t_pre <= atleast(t_pre, C_WR_PRE - 1);
                end else begin
                    t_wr <= atleast(t_wr, C_RD_WR - 1);
                    t_pre <= atleast(t_pre, C_RD_PRE - 1);
                end
            end
        end else if (open[rq_bank]) begin
            if (t_pre == 0) begin
                o_cmd <= PRE;
                o_slot <= PSLOT;
                o_ba <= rq_bank;
                o_a <= 15'd0;
                open[rq_bank] <= 1'b0;
                t_act <= atleast(t_act, C_PRE_ACT - 1);
                t_ref <= C_PRE_REF - 1;
            end
        end else if (t_act == 0) begin
            o_cmd <= ACT;
            o_slot <= ASLOT;
            o_ba <= rq_bank;
            o_a <= rq_row;
            open[rq_bank] <= 1'b1;
            row[rq_bank] <= rq_row;
            rq_hit <= 1'b1;
            t_rd <= atleast(t_rd, C_ACT_RD - 1);
            t_wr <= atleast(t_wr, C_ACT_WR - 1);
            t_pre <= atleast(t_pre, C_ACT_PRE - 1);
        end
    end

    // ---- the requests ----
    if (take || !rq_v) begin
        rq_hit <= in_hit;
        if (sk_v) begin
            rq_v <= 1'b1; rq_wr <= sk_wr; rq_a <= sk_a; rq_d <= sk_d; rq_m <= sk_m;
            sk_v <= 1'b0;
        end else begin
            rq_v <= cmd_en;
            rq_wr <= cmd_wr; rq_a <= addr; rq_d <= wr_data; rq_m <= wr_mask;
        end
    end else if (cmd_en) begin
        sk_v <= 1'b1; sk_wr <= cmd_wr; sk_a <= addr; sk_d <= wr_data; sk_m <= wr_mask;
    end
    if (pre_all)
        rq_hit <= 1'b0;

    if (rst) begin
        rq_v <= 1'b0;
        sk_v <= 1'b0;
        open <= 8'd0;
        ref_run <= 1'b0;
        ref_owed <= 4'd0;
        ref_t <= 16'd0;
        t_rd <= 0; t_wr <= 0; t_pre <= 0; t_act <= 0; t_ref <= 0;
    end
end

endmodule
