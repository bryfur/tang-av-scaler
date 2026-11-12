// Our DDR3 PHY for the GW5AST-138 (the Tang Console's two x16 chips: 32
// bits, four byte lanes), 1:4: the memory clock `mclk` (the PLL's, 400 MHz
// for DDR3-800), the user clock `pclk` a quarter of it (CLKDIV), every pin
// through the I/O logic's 8:1 serializers.
//
// Time is counted in slots: one memory clock each, four a pclk cycle
// (slot 0 first).  CK rises in the middle of a slot, so a command given
// for a slot is sampled by the chips at its centre.
//
//   commands   c_* : one command a slot ({cs_n, ras_n, cas_n, we_n}, the
//              bank, the address); cke, odt and reset_n for the cycle
//   writes     w_data: the cycle's eight beats (beat b's 32 bits at
//              [b * 32 +: 32]: beats 2s and 2s + 1 are slot s's: the first
//              on the strobe's rising edge at the slot's centre), w_mask
//              (beat b's lane l at [b * 4 + l]: 1 = not written), w_dq_oe
//              (the slots the data pins drive), w_dqs_oe (the slots the
//              strobes drive) and w_dqs_tog (the slots they toggle in: low
//              in the others: the preamble and postamble)
//   reads      r_gate: a lane's READ into Gowin's DQS block, the slots
//              its strobe gate opens for (through its own pipeline: the
//              calibration finds where), r_sel its RCLKSEL (the gate's
//              quarter-clock steps); r_data the deserializers' eight beats
//              each cycle, r_valid and r_burst the DQS blocks' flags
//              (r_burst is a level from the strobe's side: synchronize it)
//   a lane's delays: l_rmove/l_rdir/l_rloadn (the read strobe's 90
//              degrees: DQSR90), l_wmove/l_wdir/l_wloadn and l_wstep (the
//              write clocks), l_slip (a pulse: the deserializers shift one
//              bit), l_hold
//
// The clocks' start (the 50 MHz side, `clk`): the DLL locks on the running
// memory clock; then with the memory clock stopped (mclk_en low: the PLL's
// output enable) the divider and every serializer are reset and released,
// so they all count from the same edge when it runs again; the DLL's code
// is then taken, and loaded into every lane's delays, with the DQS blocks
// held (HOLD: their write clocks stopped).  `ready` (pclk) after that.
//
// Found on the board (2026-11-11, the GW5AST-138C):
//   - a write delay loaded or moved a long way while its clock runs can
//     cost a lane's data serializers a clock: the lane's write data a slot
//     off from then on.  Load and move the write delays under HOLD.
//   - the data pins drive two slots after w_dq_oe says so (and stop at
//     once): w_dq_oe from two slots before the first beat.  The strobe
//     drives in the slot it is told to; it needs the slot after its last
//     edge as well (the postamble).  Gowin's simulation model of
//     OSER8_MEM has neither (sim/ddr3/oser8_mem.v adds them).
//   - RCLKSEL counts quarter clocks, 0 to 7 (the GW2A's model orders them
//     otherwise).
//   - the read strobe's 90 degrees (the DLL's code) is at the late edge of
//     the data's eye: calibrate it down (l_rmove with l_rdir high).

module ddr3_phy #(
    parameter LANES = 4
) (
    input  wire        clk,               // 50 MHz
    input  wire        rst,               // (the PLL not locked)
    input  wire        mclk,
    output reg         mclk_en = 1'b1,
    output wire        pclk,
    output wire        ready,

    input  wire [3:0]  c_cs_n,
    input  wire [3:0]  c_ras_n,
    input  wire [3:0]  c_cas_n,
    input  wire [3:0]  c_we_n,
    input  wire [11:0] c_ba,
    input  wire [59:0] c_a,
    input  wire        c_cke,
    input  wire        c_odt,
    input  wire        c_reset_n,

    input  wire [8*8*LANES-1:0] w_data,
    input  wire [8*LANES-1:0]   w_mask,
    input  wire [3:0]  w_dq_oe,
    input  wire [3:0]  w_dqs_oe,
    input  wire [3:0]  w_dqs_tog,

    input  wire [4*LANES-1:0]   r_gate,
    input  wire [3*LANES-1:0]   r_sel,
    output wire [8*8*LANES-1:0] r_data,
    output wire [LANES-1:0]     r_valid,
    output wire [LANES-1:0]     r_burst,

    input  wire [LANES-1:0]     l_rloadn,
    input  wire [LANES-1:0]     l_rmove,
    input  wire [LANES-1:0]     l_rdir,
    input  wire [LANES-1:0]     l_wloadn,
    input  wire [LANES-1:0]     l_wmove,
    input  wire [LANES-1:0]     l_wdir,
    input  wire [8*LANES-1:0]   l_wstep,
    input  wire [LANES-1:0]     l_slip,
    input  wire [LANES-1:0]     l_hold,
    output wire [LANES-1:0]     l_rflag,
    output wire [LANES-1:0]     l_wflag,
    output wire [7:0]  dll_step,
    output wire        dll_lock,

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

// ---- the clocks' start (clk) ----
reg        io_rst = 1'b1;                 // the divider's and the serializers'
reg        dll_stop = 1'b0;
reg        dll_upd = 1'b0;                // (the DLL's code follows while high)
reg        hold_all = 1'b0;
reg        load_all = 1'b1;               // (the lanes' delays take the DLL's code)
reg        up = 1'b0;
reg [1:0]  lock_s = 2'b00;
reg [7:0]  seq = 8'd0;
wire       fclk = mclk;

DDRDLL #(
    .DLL_FORCE("FALSE"), .DIV_SEL(1'b1), .CODESCAL("000"), .SCAL_EN("FALSE")
) u_dll (
    .CLKIN(fclk), .STOP(dll_stop), .RESET(rst), .UPDNCNTL(!dll_upd),
    .STEP(dll_step), .LOCK(dll_lock)
);

CLKDIV #(
    .DIV_MODE("4")
) u_div (
    .HCLKIN(fclk), .RESETN(!io_rst), .CALIB(1'b0), .CLKOUT(pclk)
);

always @(posedge clk or posedge rst)
    if (rst) begin
        io_rst <= 1'b1;
        mclk_en <= 1'b1;
        dll_stop <= 1'b0;
        dll_upd <= 1'b0;
        hold_all <= 1'b0;
        load_all <= 1'b1;
        up <= 1'b0;
        lock_s <= 2'b00;
        seq <= 8'd0;
    end else begin
        lock_s <= {lock_s[0], dll_lock};
        if (!lock_s[1])
            seq <= 8'd0;
        else if (!seq[7])
            seq <= seq + 1'b1;
        // (eight clk cycles a step: the memory clock's enable takes a few
        // of its own cycles each way)
        case (seq)
        8'd8:   dll_stop <= 1'b1;
        8'd16:  mclk_en <= 1'b0;
        8'd24:  io_rst <= 1'b1;
        8'd40:  io_rst <= 1'b0;
        8'd48:  mclk_en <= 1'b1;
        8'd56:  dll_stop <= 1'b0;
        8'd64:  hold_all <= 1'b1;
        8'd72:  dll_upd <= 1'b1;
        8'd80:  dll_upd <= 1'b0;
        8'd84:  load_all <= 1'b0;
        8'd88:  hold_all <= 1'b0;
        8'd120: up <= 1'b1;
        default: ;
        endcase
    end

reg [2:0] up_s = 3'b000;
always @(posedge pclk or negedge up)
    if (!up)
        up_s <= 3'b000;
    else
        up_s <= {up_s[1:0], 1'b1};
assign ready = up_s[2];

// ---- the clock and the commands: OSER8, a slot two bits ----
wire ck_o;
OSER8 #(
    .TXCLK_POL(1'b0), .HWL("false")
) u_ck (
    .D0(1'b0), .D1(1'b1), .D2(1'b0), .D3(1'b1), .D4(1'b0), .D5(1'b1), .D6(1'b0), .D7(1'b1),
    .TX0(1'b0), .TX1(1'b0), .TX2(1'b0), .TX3(1'b0),
    .PCLK(pclk), .FCLK(fclk), .RESET(io_rst), .Q0(ck_o), .Q1()
);
ELVDS_OBUF u_ck_buf (.I(ck_o), .O(ddr_ck), .OB(ddr_ck_n));

wire [24:0] cmd_s [0:3];
wire [24:0] cmd_pin;
genvar s, i, l;
generate for (s = 0; s < 4; s = s + 1) begin : g_slot
    assign cmd_s[s] = {c_reset_n, c_cke, c_odt, c_cs_n[s], c_ras_n[s], c_cas_n[s], c_we_n[s],
                       c_ba[s * 3 +: 3], c_a[s * 15 +: 15]};
end endgenerate
generate for (i = 0; i < 25; i = i + 1) begin : g_cmd
    OSER8 #(
        .TXCLK_POL(1'b0), .HWL("false")
    ) u (
        .D0(cmd_s[0][i]), .D1(cmd_s[0][i]), .D2(cmd_s[1][i]), .D3(cmd_s[1][i]),
        .D4(cmd_s[2][i]), .D5(cmd_s[2][i]), .D6(cmd_s[3][i]), .D7(cmd_s[3][i]),
        .TX0(1'b0), .TX1(1'b0), .TX2(1'b0), .TX3(1'b0),
        .PCLK(pclk), .FCLK(fclk), .RESET(io_rst), .Q0(cmd_pin[i]), .Q1()
    );
end endgenerate
assign {ddr_reset_n, ddr_cke, ddr_odt, ddr_cs, ddr_ras, ddr_cas, ddr_we, ddr_bank, ddr_addr} = cmd_pin;

// ---- a lane: its DQS block, the strobe, the mask, eight data pins ----
generate for (l = 0; l < LANES; l = l + 1) begin : g_lane
    wire       dqs_i, dqs_o, dqs_oen;
    wire       dqsr90, dqsw0, dqsw270;
    wire [2:0] rpoint, wpoint;

    DQS #(
        .DQS_MODE("X4"), .FIFO_MODE_SEL(1'b0), .RD_PNTR(3'b000), .HWL("false")
    ) u_dqs (
        .DQSIN(dqs_i), .PCLK(pclk), .FCLK(fclk), .RESET(io_rst),
        .READ(r_gate[l * 4 +: 4]), .RCLKSEL(r_sel[l * 3 +: 3]),
        .DLLSTEP(dll_step), .WSTEP(l_wstep[l * 8 +: 8]),
        .RLOADN(l_rloadn[l] & !load_all), .RMOVE(l_rmove[l]), .RDIR(l_rdir[l]),
        .WLOADN(l_wloadn[l] & !load_all), .WMOVE(l_wmove[l]), .WDIR(l_wdir[l]),
        .HOLD(hold_all | l_hold[l]),
        .DQSR90(dqsr90), .DQSW0(dqsw0), .DQSW270(dqsw270),
        .RPOINT(rpoint), .WPOINT(wpoint),
        .RVALID(r_valid[l]), .RBURST(r_burst[l]), .RFLAG(l_rflag[l]), .WFLAG(l_wflag[l])
    );

    // (the strobe: low then high in a slot it toggles in, low in the others)
    OSER8_MEM #(
        .TCLK_SOURCE("DQSW"), .TXCLK_POL(1'b0), .HWL("false")
    ) u_dqs_o (
        .D0(1'b0), .D1(w_dqs_tog[0]), .D2(1'b0), .D3(w_dqs_tog[1]),
        .D4(1'b0), .D5(w_dqs_tog[2]), .D6(1'b0), .D7(w_dqs_tog[3]),
        .TX0(!w_dqs_oe[0]), .TX1(!w_dqs_oe[1]), .TX2(!w_dqs_oe[2]), .TX3(!w_dqs_oe[3]),
        .PCLK(pclk), .FCLK(fclk), .TCLK(dqsw0), .RESET(io_rst), .Q0(dqs_o), .Q1(dqs_oen)
    );
    ELVDS_IOBUF u_dqs_buf (
        .I(dqs_o), .OEN(dqs_oen), .O(dqs_i), .IO(ddr_dqs[l]), .IOB(ddr_dqs_n[l])
    );

    OSER8_MEM #(
        .TCLK_SOURCE("DQSW270"), .TXCLK_POL(1'b0), .HWL("false")
    ) u_dm (
        .D0(w_mask[0 * LANES + l]), .D1(w_mask[1 * LANES + l]), .D2(w_mask[2 * LANES + l]),
        .D3(w_mask[3 * LANES + l]), .D4(w_mask[4 * LANES + l]), .D5(w_mask[5 * LANES + l]),
        .D6(w_mask[6 * LANES + l]), .D7(w_mask[7 * LANES + l]),
        .TX0(1'b0), .TX1(1'b0), .TX2(1'b0), .TX3(1'b0),
        .PCLK(pclk), .FCLK(fclk), .TCLK(dqsw270), .RESET(io_rst), .Q0(ddr_dm[l]), .Q1()
    );

    for (i = 0; i < 8; i = i + 1) begin : g_dq
        localparam B = l * 8 + i;
        wire dq_o, dq_oen, dq_i;
        OSER8_MEM #(
            .TCLK_SOURCE("DQSW270"), .TXCLK_POL(1'b0), .HWL("false")
        ) u_o (
            .D0(w_data[0 * 8 * LANES + B]), .D1(w_data[1 * 8 * LANES + B]),
            .D2(w_data[2 * 8 * LANES + B]), .D3(w_data[3 * 8 * LANES + B]),
            .D4(w_data[4 * 8 * LANES + B]), .D5(w_data[5 * 8 * LANES + B]),
            .D6(w_data[6 * 8 * LANES + B]), .D7(w_data[7 * 8 * LANES + B]),
            .TX0(!w_dq_oe[0]), .TX1(!w_dq_oe[1]), .TX2(!w_dq_oe[2]), .TX3(!w_dq_oe[3]),
            .PCLK(pclk), .FCLK(fclk), .TCLK(dqsw270), .RESET(io_rst), .Q0(dq_o), .Q1(dq_oen)
        );
        IOBUF u_buf (.I(dq_o), .OEN(dq_oen), .O(dq_i), .IO(ddr_dq[B]));
        IDES8_MEM u_i (
            .D(dq_i), .ICLK(dqsr90), .FCLK(fclk), .PCLK(pclk),
            .WADDR(wpoint), .RADDR(rpoint), .CALIB(l_slip[l]), .RESET(io_rst),
            .Q0(r_data[0 * 8 * LANES + B]), .Q1(r_data[1 * 8 * LANES + B]),
            .Q2(r_data[2 * 8 * LANES + B]), .Q3(r_data[3 * 8 * LANES + B]),
            .Q4(r_data[4 * 8 * LANES + B]), .Q5(r_data[5 * 8 * LANES + B]),
            .Q6(r_data[6 * 8 * LANES + B]), .Q7(r_data[7 * 8 * LANES + B])
        );
    end
end endgenerate

endmodule
