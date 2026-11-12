// The DDR3 data path on ddr3_phy.v: what a write's and a read's command
// set going on the data pins, cycles later.
//
//   a write   wr_go with its command (in the cycle's slot WSLOT: its data
//             then starts a cycle, WCYC = 2 cycles later), wr_data and
//             wr_mask with it.  The data pins drive from two slots before
//             the first beat (the board: they take two slots to drive) to
//             the slot after the last, and hold the first beat's value
//             until it starts; the strobe is low for two slots before (the
//             preamble) and two after (the postamble); ODT from the
//             command's cycle to the postamble's.  Writes a cycle apart
//             run on without a gap; with a cycle between them the strobe
//             stays driven.
//             (The board, with a one-slot preamble and the data pins
//             driving the last write's beats again before the first beat:
//             the first write after a gap of a cycle stored its first beat
//             wrong now and then, one bit: the strobe pair, not driven for
//             two slots with the chips' termination on and the data pins
//             switching beside it, gave them an edge.)
//   a read    rd_go with its command, in slot 0.  Where a burst falls in
//             the deserializers' words depends on the command's slot and
//             on the lane (the board: with reads in slot 1 three lanes
//             had it one way and the fourth the other: a boundary there;
//             the cycle it comes in changes between slots 2 and 3): slot
//             0 has a slot each side, and the calibration slips each
//             lane's words until its burst fills one.  Each lane's gate
//             opens g_cyc cycles and g_rot slots after the command's
//             cycle for four slots, g_sel quarter clocks later.  Each
//             lane's bursts come with its RVALID: rd_valid and the line in
//             rd_data when every lane has its next one (eight cycles
//             after rd_go on the board: seven to the deserializers'
//             words, one for a register beside them), reads in order.
//   dqs_pulse a strobe edge of our own: a gate left open by a wrong
//             setting closes on it (the calibration's).

module ddr3_dp #(
    parameter CL  = 6,
    parameter CWL = 5,
    parameter LANES = 4
) (
    input  wire        clk,               // 50 MHz (the PHY's start)
    input  wire        rst,
    input  wire        mclk,
    output wire        mclk_en,
    output wire        pclk,
    output wire        ready,

    input  wire [3:0]  c_cs_n,
    input  wire [3:0]  c_ras_n,
    input  wire [3:0]  c_cas_n,
    input  wire [3:0]  c_we_n,
    input  wire [11:0] c_ba,
    input  wire [59:0] c_a,
    input  wire        c_cke,
    input  wire        c_reset_n,

    input  wire        wr_go,
    input  wire [8*8*LANES-1:0] wr_data,
    input  wire [8*LANES-1:0]   wr_mask,
    input  wire        rd_go,
    output wire        rd_valid,
    output wire [8*8*LANES-1:0] rd_data,
    input  wire        rd_raw,            // (the calibration: no lines, r_data and r_valid as they come)
    output wire [8*8*LANES-1:0] r_data,
    output reg         rd_stray = 1'b0,   // a burst no read asked for, or one too many kept (it stays)

    input  wire [2*LANES-1:0]   g_cyc,
    input  wire [2*LANES-1:0]   g_rot,
    input  wire [3*LANES-1:0]   g_sel,
    input  wire        dqs_pulse,
    input  wire [LANES-1:0]     l_hold,
    input  wire [LANES-1:0]     l_rmove,
    input  wire [LANES-1:0]     l_rdir,
    input  wire [LANES-1:0]     l_slip,
    output wire [LANES-1:0]     r_valid,
    output wire [7:0]  dll_step,

    output wire [14:0] ddr_addr,
    output wire [2:0]  ddr_bank,
    output wire        ddr_cs,
    output wire        ddr_ras,
    output wire        ddr_cas,
    output wire        ddr_we,
    output wire        ddr_ck,
    output wire        ddr_ck_n,
    output wire        ddr_cke,
    output wire        ddr_odt,
    output wire        ddr_reset_n,
    output wire [LANES-1:0]     ddr_dm,
    inout  wire [8*LANES-1:0]   ddr_dq,
    inout  wire [LANES-1:0]     ddr_dqs,
    inout  wire [LANES-1:0]     ddr_dqs_n
);

// ---- a write: three cycles after its command's ----
reg [3:1] wr_sr = 3'b000;
reg [8*8*LANES-1:0] wd1 = 0, wd2 = 0;
reg [8*LANES-1:0]   wm1 = 0, wm2 = 0;
reg       pulse_q = 1'b0;
always @(posedge pclk) begin
    wr_sr <= {wr_sr[2:1], wr_go};
    wd1 <= wr_data;
    wd2 <= wd1;
    wm1 <= wr_mask;
    wm2 <= wm1;
    pulse_q <= dqs_pulse;
    if (!ready) begin
        wr_sr <= 3'b000;
        pulse_q <= 1'b0;
    end
end
wire [3:0] w_dq_oe   = {wr_sr[1] | wr_sr[2], wr_sr[1] | wr_sr[2], wr_sr[2], wr_sr[2] | wr_sr[3]};
wire [3:0] w_dqs_oe  = {wr_sr[1] | wr_sr[2], wr_sr[1] | wr_sr[2], wr_sr[2] | wr_sr[3] | pulse_q,
                        wr_sr[2] | wr_sr[3] | pulse_q};
// (outside a write's own cycle the data pins hold the coming line's first
// beat: they drive early, and must drive still)
wire [8*8*LANES-1:0] w_data = wr_sr[2] ? wd2 : {8{wd1[8*LANES-1:0]}};
wire [8*LANES-1:0]   w_mask = wr_sr[2] ? wm2 : {8{wm1[LANES-1:0]}};
wire [3:0] w_dqs_tog = {wr_sr[2], wr_sr[2], wr_sr[2], wr_sr[2] | pulse_q};
wire       c_odt = wr_go | wr_sr[1] | wr_sr[2] | wr_sr[3];

// ---- a read: each lane's gate, then the line ----
reg [14:1] rd_sr = 14'd0;
always @(posedge pclk) begin
    rd_sr <= {rd_sr[13:1], rd_go};
    if (!ready)
        rd_sr <= 14'd0;
end
wire [14:0] rd_at = {rd_sr, rd_go};      // (bit k: a read k cycles ago)
wire [4*LANES-1:0] r_gate;
genvar l;
generate for (l = 0; l < LANES; l = l + 1) begin : g_gate
    wire [1:0] cyc = g_cyc[l * 2 +: 2];
    wire [3:0] first = 4'hf << g_rot[l * 2 +: 2];
    assign r_gate[l * 4 +: 4] = (rd_at[cyc] ? first : 4'h0) | (rd_at[cyc + 3'd1] ? ~first : 4'h0);
end endgenerate

// ---- the lines: each lane's bursts in order, a line when every lane has
// its next one ----
// (Gowin's DQS block hands a lane's burst over with RVALID, a cycle sooner
// or later by the lane's flight and by whether its FIFO was already
// running: a lane's k-th burst is the k-th read's.  A lane ahead keeps up
// to two bursts; nothing is taken while no read is owed.)
// (RVALID and the words registered once first: they come a long way from
// the pins' blocks)
reg  [LANES-1:0] rv_q = 0;
reg  [8*8*LANES-1:0] rdat_q = 0;
always @(posedge pclk) begin
    rv_q <= r_valid;
    rdat_q <= r_data;
end
reg  [4:0] owed = 5'd0;                   // reads whose line is still to come
wire [LANES-1:0] have;
wire       line = &have && owed != 0;
assign rd_valid = line && !rd_raw;
generate for (l = 0; l < LANES; l = l + 1) begin : g_line
    reg [1:0]  cnt = 2'd0;
    reg [63:0] b0 = 64'd0, b1 = 64'd0;
    wire [63:0] in;
    genvar bt;
    for (bt = 0; bt < 8; bt = bt + 1) begin : g_b
        assign in[bt * 8 +: 8] = rdat_q[bt * 8 * LANES + l * 8 +: 8];
        assign rd_data[bt * 8 * LANES + l * 8 +: 8] = cnt != 0 ? b0[bt * 8 +: 8] : in[bt * 8 +: 8];
    end
    wire arrive = rv_q[l] && owed != 0 && !rd_raw;
    assign have[l] = cnt != 0 || rv_q[l];
    always @(posedge pclk) begin
        if (line && cnt != 0) begin       // (its oldest goes; one more may come)
            b0 <= cnt == 2'd2 ? b1 : in;
            b1 <= in;
            cnt <= cnt - 1'b1 + arrive;
        end else if (!line && arrive) begin
            if (cnt == 2'd0) b0 <= in;
            if (cnt == 2'd1) b1 <= in;
            if (cnt != 2'd2) cnt <= cnt + 1'b1;
        end
        if (!ready || rd_raw || (owed == 0 && !rd_go))
            cnt <= 2'd0;
    end
end endgenerate
always @(posedge pclk) begin
    owed <= owed + (rd_go ? 1'b1 : 1'b0) - (rd_valid ? 1'b1 : 1'b0);
    if (!rd_raw && owed == 0 && |rv_q)
        rd_stray <= 1'b1;
    if (!ready || rd_raw) begin
        owed <= 5'd0;
        if (!ready) rd_stray <= 1'b0;
    end
end

ddr3_phy #(.LANES(LANES)) u_phy (
    .clk(clk), .rst(rst), .mclk(mclk), .mclk_en(mclk_en), .pclk(pclk), .ready(ready),
    .c_cs_n(c_cs_n), .c_ras_n(c_ras_n), .c_cas_n(c_cas_n), .c_we_n(c_we_n), .c_ba(c_ba), .c_a(c_a),
    .c_cke(c_cke), .c_odt(c_odt), .c_reset_n(c_reset_n),
    .w_data(w_data), .w_mask(w_mask), .w_dq_oe(w_dq_oe), .w_dqs_oe(w_dqs_oe), .w_dqs_tog(w_dqs_tog),
    .r_gate(r_gate), .r_sel(g_sel), .r_data(r_data), .r_valid(r_valid), .r_burst(),
    .l_rloadn({LANES{1'b1}}), .l_rmove(l_rmove), .l_rdir(l_rdir),
    .l_wloadn({LANES{1'b1}}), .l_wmove({LANES{1'b0}}), .l_wdir({LANES{1'b0}}),
    .l_wstep({8*LANES{1'b0}}), .l_slip(l_slip), .l_hold(l_hold), .l_rflag(), .l_wflag(),
    .dll_step(dll_step), .dll_lock(),
    .ddr_addr(ddr_addr), .ddr_bank(ddr_bank), .ddr_cs(ddr_cs), .ddr_ras(ddr_ras), .ddr_cas(ddr_cas),
    .ddr_we(ddr_we), .ddr_ck(ddr_ck), .ddr_ck_n(ddr_ck_n), .ddr_cke(ddr_cke), .ddr_odt(ddr_odt),
    .ddr_reset_n(ddr_reset_n), .ddr_dm(ddr_dm), .ddr_dq(ddr_dq), .ddr_dqs(ddr_dqs),
    .ddr_dqs_n(ddr_dqs_n)
);

endmodule
