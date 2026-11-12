// The DDR3 chips' power-up and the PHY's calibration (ddr3_dp.v's
// settings), in hardware: after it `done`, or `fail` with its code.
//
//   1. RESET# low 200 us, 500 us to CKE, the mode registers (MR2: CWL;
//      MR3; MR1: the DLL on, RZQ/7 drive, Rtt 40; MR0: CL, the DLL's
//      reset, write recovery), ZQCL.
//   2. The read strobes' delay halved: the DLL's 90 degrees is at the late
//      edge of the data's eye on this chip.
//   3. A line of a known pattern written (bank 0, row 0, column 0) and
//      its complement's (column 8), read in turn from here on: every bit
//      both ways on every beat (the board, with the one line: the delay of
//      5 found no low edge, and in use a 1 on a burst's first beat read as
//      0 now and then: that beat's eye opens later).  The write path needs
//      no calibration at these speeds (the board: the data's eye +-38 taps
//      around the DLL's code).
//   4. Each lane's read gate: the line read with the gate at every quarter
//      clock of a range (the gate and the FIFOs put right before each: a
//      strobe edge of our own, HOLD); a position is good when the lane's
//      eight beats are right NRD times, RVALID with them, in the same
//      cycle, with a strobe edge of our own between the reads: where the
//      gate opens in time but does not close behind the burst, that edge
//      gets into the lane's FIFO and the next read is out of step (the
//      board, without it: windows of seven positions and more, and in use
//      the first read after a write wrong on those lanes).  The longest
//      run of good positions: two quarters after its first.  Its first is
//      the sharp edge (the preamble's start: earlier, the gate closes a
//      strobe early); the run is the preamble's clock long, four
//      positions, but goes on where the read strobe's delay leaves room
//      (the gate opening just after the first edge still takes the first
//      beat): up to seven positions on the board, their middle on the
//      preamble's end and the lane unsteady.  No run: the lane's
//      deserializers slipped a bit (a burst's place in their words: it
//      depends on the read command's slot and on the lane's flight), and
//      again, up to eight times.
//   5. Each lane's read strobe delay: down from there until the data
//      fails or the delay is none, up until it fails: the middle.
//   6. The line read 16 times more through ddr3_dp.v's lines (every
//      lane's burst by its own RVALID); the bank closed.
//
// A refresh every 6 us through 4 and 5.  map_all, map_first: the gate
// positions that were good for the lane last swept (bit q), all NRD reads
// and the first alone.  The codes of `fail`: 1 no gate
// window (info: the lane), 3 the last reads.
// `dbg`: a lane's 32 bits: [5:0] the gate's position (quarter clocks from
// the read command's cycle), [8:6] its window, [11:9] the slips, [15:12]
// the cycle the line came in, [23:16] the delay's low edge, [31:24] its
// high edge (taps).

module ddr3_cal #(
    parameter CL       = 6,
    parameter CWL      = 5,
    parameter LANES    = 4,
    parameter PCLK_KHZ = 100000,
    parameter FAST     = 0,               // (simulation: the power-up's waits cut short)
    parameter [14:0] MR1 = 15'h0046,
    parameter [2:0]  WR_REC = 3'b010,     // MR0's write recovery: 6 clocks
    parameter NRD      = 4
) (
    input  wire        clk,               // pclk
    input  wire        rst,

    output reg  [3:0]  o_cmd = 4'hf,      // {cs_n, ras_n, cas_n, we_n}
    output reg  [1:0]  o_slot = 2'd0,
    output reg  [2:0]  o_ba = 3'd0,
    output reg  [14:0] o_a = 15'd0,
    output reg         o_cke = 1'b0,
    output reg         o_reset_n = 1'b0,
    output reg         wr_go = 1'b0,
    output wire [255:0] wr_data,
    output reg         rd_go = 1'b0,
    output reg         rd_raw = 1'b1,     // (ddr3_dp.v: no lines until the last reads)
    input  wire [255:0] r_data,
    input  wire [LANES-1:0] r_valid,
    input  wire        rd_valid,
    input  wire [255:0] rd_data,
    input  wire [7:0]  dll_step,

    output reg  [2*LANES-1:0] g_cyc = 0,
    output reg  [2*LANES-1:0] g_rot = 0,
    output reg  [3*LANES-1:0] g_sel = 0,
    output reg         dqs_pulse = 1'b0,
    output reg  [LANES-1:0] l_hold = 0,
    output reg  [LANES-1:0] l_rmove = 0,
    output reg  [LANES-1:0] l_rdir = 0,
    output reg  [LANES-1:0] l_slip = 0,

    output reg         done = 1'b0,
    output reg         fail = 1'b0,
    output reg  [7:0]  info = 8'd0,
    output reg  [32*LANES-1:0] dbg = 0,
    output reg  [63:0] map_all = 64'd0,   // the last lane's gate positions: good
    output reg  [63:0] map_first = 64'd0, // (its first read alone)
    // ([13:12] the read commands' slot; the rest for bring-up: [5:0] the
    // gate position whose first read on lane 0 is kept in snap, [9] the
    // strobe delays left at the DLL's code, [10] no HOLD and [11] no
    // strobe edge before a position's reads; 16'h0020 as a rule: slot 0)
    input  wire [15:0] opt,
    output reg  [135:0] snap = 136'd0     // {RVALID from 5 cycles on, the lane's line 8 cycles on, 7}
);

// (the pattern's line at column 0, its complement's at column 8: every
// bit both ways on every beat: a burst's first beat has its own eye)
localparam [255:0] PAT = 256'h2cd20c2fd22cf0d3c30ea597f068965be14b5b1f96a50fc38787f087b4e1a54b;
reg  inv = 1'b0;                          // the line written or read: the complement's
assign wr_data = PAT ^ {256{inv}};

localparam MRS = 4'b0000, REF = 4'b0001, PRE = 4'b0010, ACT = 4'b0011, WRC = 4'b0100,
           RDC = 4'b0101, ZQC = 4'b0110, DES = 4'b1111;
localparam WSLOT = (4 - CWL % 4) % 4;
localparam [16:0] T_RST  = FAST ? PCLK_KHZ / 450 : PCLK_KHZ / 5;
localparam [16:0] T_CKE  = FAST ? PCLK_KHZ / 190 : PCLK_KHZ / 2;
localparam [16:0] T_XPR  = PCLK_KHZ / 3000;
localparam [16:0] T_RFC  = PCLK_KHZ / 3500 + 1;
localparam [11:0] T_REFI = PCLK_KHZ * 6 / 1000;
localparam [5:0]  QMIN = 6'd16, QMAX = 6'd55;
localparam [3:0]  LMIN = 4'd5, LMAX = 4'd10;

localparam S_RST0 = 0, S_RST1 = 1, S_CKE = 2, S_MRS = 3, S_ZQ = 4, S_SLIP = 5, S_PREC = 6,
           S_ACT = 7, S_WR = 8, S_G0 = 9, S_FL0 = 10, S_FL1 = 11, S_FL2 = 12, S_FL3 = 13,
           S_RD = 14, S_RDE = 15, S_GNEXT = 16, S_GPICK0 = 17, S_GPICK = 18, S_GDONE = 19,
           S_E0 = 20, S_EDOWN = 21, S_EDOWN_T = 22, S_EBACK = 23, S_EUP = 24, S_EUP_T = 25,
           S_ESET = 26, S_EDONE = 27, S_MOVE = 28, S_MOVE1 = 29, S_REF0 = 30, S_REF1 = 31,
           S_REF2 = 32, S_FIN0 = 33, S_VRD = 34, S_VRDE = 35, S_FIN1 = 36, S_DONE = 37,
           S_FAIL = 38, S_TEST = 39, S_FIN2 = 40, S_GSLIP = 41, S_GSLIP1 = 42, S_RDP = 43, S_WR2 = 44;

reg [5:0]  st = S_RST0, fl_ret = S_RD, rd_ret = S_GNEXT, mv_ret = S_ACT, ref_ret = S_FL0;
reg [16:0] wait_n = 17'd0;
reg [1:0]  idx = 2'd0;
reg [2:0]  lane = 3'd0;
reg [5:0]  q = 6'd0;
reg        set_cfg = 1'b0;                // (the flush sets the lane's gate to q)
reg [2:0]  n = 3'd0;
reg        ok = 1'b0;
reg [3:0]  rd_t = 4'd15;                  // cycles since a read's command at the PHY
reg        hit = 1'b0;
reg [3:0]  hit_lat = 4'd0, lat0 = 4'd0;
reg        fix_lat = 1'b0;                // (the eye's tests: the line in the lane's cycle only)
reg [5:0]  run = 6'd0, run_start = 6'd0, best_len = 6'd0, best_start = 6'd0;
reg [3:0]  run_lat = 4'd0, best_lat = 4'd0;
reg [3:0]  lat [0:LANES-1];
reg [7:0]  pos = 8'd0, p0 = 8'd0, lo = 8'd0, hi = 8'd0;
reg [7:0]  mv_n = 8'd0;
reg [LANES-1:0] mv_lanes = 0;
reg        mv_dir = 1'b0;
reg [11:0] ref_cnt = 12'd0;
reg [4:0]  vn = 5'd0;
reg [2:0]  slips = 3'd0;                  // the lane's, so far
reg [LANES-1:0] eq_r = 0, rv_r = 0;
reg        rdv_r = 1'b0, seen = 1'b0;      // (the last reads: a line came)
wire [LANES-1:0] one = {{LANES-1{1'b0}}, 1'b1};
wire [LANES-1:0] this_lane = one << lane;

wire [LANES-1:0] eq;
genvar l, b;
generate for (l = 0; l < LANES; l = l + 1) begin : g_eq
    wire [7:0] e;
    for (b = 0; b < 8; b = b + 1) begin : g_b
        assign e[b] = (rd_raw ? r_data[b * 8 * LANES + l * 8 +: 8] : rd_data[b * 8 * LANES + l * 8 +: 8])
                      == (PAT[b * 8 * LANES + l * 8 +: 8] ^ {8{inv}});
    end
    assign eq[l] = &e;
end endgenerate

wire [7:0] mid = ({1'b0, lo} + {1'b0, hi}) >> 1;

integer k;
always @(posedge clk) begin
    o_cmd <= DES;
    wr_go <= 1'b0;
    rd_go <= 1'b0;
    dqs_pulse <= 1'b0;
    eq_r <= eq;
    rv_r <= r_valid;
    if (!(&ref_cnt))
        ref_cnt <= ref_cnt + 1'b1;
    if (rd_t != 4'd15)
        rd_t <= rd_t + 1'b1;
    // (a read's line: the lane's beats and RVALID, the cycle they came in)
    if (rd_t >= LMIN + 1 && rd_t <= LMAX + 1 && eq_r[lane] && rv_r[lane] && !hit
            && (!fix_lat || rd_t == lat0 + 1)) begin
        hit <= 1'b1;
        hit_lat <= rd_t - 1'b1;
    end

    if (wait_n != 0)
        wait_n <= wait_n - 1'b1;
    else case (st)
    // ---- the chips' power-up ----
    S_RST0: begin
        o_reset_n <= 1'b0;
        o_cke <= 1'b0;
        wait_n <= T_RST;
        st <= S_RST1;
    end
    S_RST1: begin
        o_reset_n <= 1'b1;
        wait_n <= T_CKE;
        st <= S_CKE;
    end
    S_CKE: begin
        o_cke <= 1'b1;
        wait_n <= T_XPR;
        idx <= 2'd0;
        st <= S_MRS;
    end
    S_MRS: begin
        o_cmd <= MRS;
        o_slot <= 2'd0;
        case (idx)
        2'd0: begin o_ba <= 3'd2; o_a <= {9'd0, CWL[2:0] - 3'd5, 3'd0}; end
        2'd1: begin o_ba <= 3'd3; o_a <= 15'd0; end
        2'd2: begin o_ba <= 3'd1; o_a <= MR1; end
        2'd3: begin o_ba <= 3'd0; o_a <= {3'd0, WR_REC, 1'b1, 1'b0, CL[2:0] - 3'd4, 4'b0000}; end
        endcase
        wait_n <= 17'd6;
        idx <= idx + 1'b1;
        if (idx == 2'd3)
            st <= S_ZQ;
    end
    S_ZQ: begin
        o_cmd <= ZQC;
        o_a <= 15'h0400;
        wait_n <= 17'd140;
        n <= 3'd0;
        st <= S_SLIP;
    end
    // ---- the read strobes' delay: half the DLL's code ----
    S_SLIP: begin
        l_slip <= 0;
        p0 <= opt[9] ? dll_step : dll_step - (dll_step >> 1);
        mv_n <= opt[9] ? 8'd0 : dll_step >> 1;
        mv_dir <= 1'b1;
        mv_lanes <= {LANES{1'b1}};
        mv_ret <= S_ACT;
        wait_n <= 17'd6;
        st <= S_MOVE;
    end
    // (mv_n taps on mv_lanes, a pulse each: its falling edge moves)
    S_MOVE: begin
        l_rdir <= {LANES{mv_dir}};
        l_rmove <= 0;
        wait_n <= 17'd3;
        st <= mv_n == 0 ? mv_ret : S_MOVE1;
    end
    S_MOVE1: begin
        l_rmove <= mv_lanes;
        mv_n <= mv_n - 1'b1;
        wait_n <= 17'd3;
        st <= S_MOVE;
    end
    // ---- the pattern's line ----
    S_ACT: begin
        o_cmd <= ACT;
        o_slot <= 2'd3;
        o_ba <= 3'd0;
        o_a <= 15'd0;
        wait_n <= 17'd4;
        ref_cnt <= 12'd0;
        inv <= 1'b0;
        st <= S_WR;
    end
    S_WR: begin
        o_cmd <= WRC;
        o_slot <= WSLOT;
        o_a <= inv ? 15'd8 : 15'd0;
        wr_go <= 1'b1;
        wait_n <= 17'd12;
        lane <= 3'd0;
        slips <= 3'd0;
        st <= inv ? S_G0 : S_WR2;
    end
    S_WR2: begin
        inv <= 1'b1;
        wait_n <= 17'd1;
        st <= S_WR;
    end
    // ---- a lane's gate ----
    S_G0: begin
        q <= QMIN;
        map_all <= 64'd0;
        map_first <= 64'd0;
        run <= 6'd0;
        best_len <= 6'd0;
        set_cfg <= 1'b1;
        fix_lat <= 1'b0;
        fl_ret <= S_RD;
        rd_ret <= S_GNEXT;
        st <= S_FL0;
    end
    // (the gate and the FIFOs put right: a strobe edge of our own closes a
    // gate left open, HOLD starts the pointers again; the lane's gate set
    // while its clocks are held)
    S_FL0: begin
        if (ref_cnt >= T_REFI) begin
            ref_ret <= S_FL0;
            st <= S_REF0;
        end else begin
            dqs_pulse <= !opt[11];
            wait_n <= 17'd8;              // (the edge out of the pins before the hold)
            st <= S_FL1;
        end
    end
    S_FL1: begin
        l_hold <= {LANES{!opt[10]}};
        wait_n <= 17'd4;
        st <= S_FL2;
    end
    S_FL2: begin
        if (set_cfg)
            for (k = 0; k < LANES; k = k + 1)
                if (k == lane) begin
                    g_cyc[k * 2 +: 2] <= q[5:4];
                    g_rot[k * 2 +: 2] <= q[3:2];
                    g_sel[k * 3 +: 3] <= {1'b0, q[1:0]};
                end
        wait_n <= 17'd4;
        st <= S_FL3;
    end
    S_FL3: begin
        l_hold <= 0;
        wait_n <= 17'd8;
        n <= 3'd0;
        ok <= 1'b1;
        st <= fl_ret;
    end
    // (NRD reads of the line: ok if the lane had it each time, in one cycle)
    S_RD: begin
        o_cmd <= RDC;
        o_slot <= opt[13:12];
        o_ba <= 3'd0;
        o_a <= n[0] ? 15'd8 : 15'd0;      // (the pattern's line, its complement's, in turn)
        inv <= n[0];
        rd_go <= 1'b1;
        rd_t <= 4'd0;                     // (0 as the command reaches the PHY)
        hit <= 1'b0;
        wait_n <= 17'd13;
        st <= S_RDE;
    end
    S_RDE: begin
        if (hit && n == 0 && !fix_lat)
            map_first[q] <= 1'b1;
        if (!hit)
            ok <= 1'b0;
        else if (n == 0 && !fix_lat)
            lat0 <= hit_lat;
        else if (hit_lat != lat0)
            ok <= 1'b0;
        n <= n + 1'b1;
        st <= n == NRD - 1 ? rd_ret : S_RDP;
    end
    // (between a position's reads, a strobe edge of our own and no HOLD:
    // a gate that did not close behind the burst takes it into the lane's
    // FIFO and the next read comes out of step, as it would after the
    // write that follows a read in use)
    S_RDP: begin
        dqs_pulse <= 1'b1;
        wait_n <= 17'd8;
        st <= S_RD;
    end
    S_GNEXT: begin
        if (ok)
            map_all[q] <= 1'b1;
        if (ok && run != 0 && lat0 == run_lat)
            run <= run + 1'b1;
        else begin
            if (run > best_len) begin
                best_len <= run;
                best_start <= run_start;
                best_lat <= run_lat;
            end
            run <= ok ? 6'd1 : 6'd0;
            run_start <= q;
            run_lat <= lat0;
        end
        q <= q + 1'b1;
        st <= q == QMAX ? S_GPICK0 : S_FL0;
    end
    S_GPICK0: begin
        if (run > best_len) begin
            best_len <= run;
            best_start <= run_start;
            best_lat <= run_lat;
        end
        st <= S_GPICK;
    end
    S_GPICK: begin
        if (best_len < 3) begin
            // (no window: the lane's words a bit on, the sweep again)
            info <= {4'd1, 1'b0, lane};
            st <= slips == 3'd7 ? S_FAIL : S_GSLIP;
        end else begin
            q <= best_start + (best_len >= 4 ? 6'd2 : 6'd1);
            lat[lane] <= best_lat;
            for (k = 0; k < LANES; k = k + 1)
                if (k == lane) begin
                    dbg[k * 32 +: 6] <= best_start + (best_len >= 4 ? 6'd2 : 6'd1);
                    dbg[k * 32 + 6 +: 3] <= best_len > 7 ? 3'd7 : best_len[2:0];
                    dbg[k * 32 + 9 +: 3] <= slips;
                    dbg[k * 32 + 12 +: 4] <= best_lat;
                end
            fl_ret <= S_GDONE;
            st <= S_FL0;
        end
    end
    S_GSLIP: begin
        l_slip <= this_lane;
        slips <= slips + 1'b1;
        wait_n <= 17'd1;
        st <= S_GSLIP1;
    end
    S_GSLIP1: begin
        l_slip <= 0;
        wait_n <= 17'd8;
        st <= S_G0;
    end
    S_GDONE: begin
        lane <= lane + 1'b1;
        slips <= 3'd0;
        st <= lane == LANES - 1 ? S_E0 : S_G0;
        if (lane == LANES - 1)
            lane <= 3'd0;
    end
    // ---- a lane's read strobe delay ----
    S_E0: begin
        pos <= p0;
        set_cfg <= 1'b0;
        fix_lat <= 1'b1;
        lat0 <= lat[lane];
        mv_lanes <= this_lane;
        st <= S_EDOWN;
    end
    S_EDOWN: begin
        if (pos < 2) begin
            lo <= 8'd0;
            st <= S_EBACK;
        end else begin
            pos <= pos - 8'd2;
            mv_n <= 8'd2;
            mv_dir <= 1'b1;
            mv_ret <= S_TEST;
            rd_ret <= S_EDOWN_T;
            st <= S_MOVE;
        end
    end
    S_TEST: begin
        fl_ret <= S_RD;
        st <= S_FL0;
    end
    S_EDOWN_T: begin
        if (ok)
            st <= S_EDOWN;
        else begin
            lo <= pos;
            st <= S_EBACK;
        end
    end
    S_EBACK: begin                        // (back to where it was known good)
        mv_n <= p0 - pos;
        mv_dir <= 1'b0;
        pos <= p0;
        mv_ret <= S_EUP;
        st <= S_MOVE;
    end
    S_EUP: begin
        if (pos >= 8'd250) begin
            hi <= pos;
            st <= S_ESET;
        end else begin
            pos <= pos + 8'd2;
            mv_n <= 8'd2;
            mv_dir <= 1'b0;
            mv_ret <= S_TEST;
            rd_ret <= S_EUP_T;
            st <= S_MOVE;
        end
    end
    S_EUP_T: begin
        if (ok)
            st <= S_EUP;
        else begin
            hi <= pos;
            st <= S_ESET;
        end
    end
    S_ESET: begin
        mv_n <= pos - mid;
        mv_dir <= 1'b1;
        mv_ret <= S_EDONE;
        for (k = 0; k < LANES; k = k + 1)
            if (k == lane) begin
                dbg[k * 32 + 16 +: 8] <= lo;
                dbg[k * 32 + 24 +: 8] <= pos;
            end
        st <= S_MOVE;
    end
    S_EDONE: begin
        lane <= lane + 1'b1;
        st <= lane == LANES - 1 ? S_FIN0 : S_E0;
        if (lane == LANES - 1)
            lane <= 3'd0;
    end
    // ---- a refresh: the bank closed, opened again ----
    S_REF0: begin
        o_cmd <= PRE;
        o_slot <= 2'd1;
        o_a <= 15'h0400;
        wait_n <= 17'd2;
        st <= S_REF1;
    end
    S_REF1: begin
        o_cmd <= REF;
        o_slot <= 2'd1;
        wait_n <= T_RFC;
        st <= S_REF2;
    end
    S_REF2: begin
        o_cmd <= ACT;
        o_slot <= 2'd3;
        o_ba <= 3'd0;
        o_a <= 15'd0;
        wait_n <= 17'd3;
        ref_cnt <= 12'd0;
        st <= ref_ret;
    end
    // ---- the end: one cycle for all lanes, the line once more ----
    S_FIN0: begin
        fl_ret <= S_FIN2;
        st <= S_FL0;
    end
    S_FIN2: begin
        ok <= 1'b1;
        rd_raw <= 1'b0;
        vn <= 5'd0;
        wait_n <= 17'd4;
        st <= S_VRD;
    end
    S_VRD: begin
        begin
            seen <= 1'b0;
            o_cmd <= RDC;
            o_slot <= opt[13:12];
            o_ba <= 3'd0;
            o_a <= vn[0] ? 15'd8 : 15'd0;
            inv <= vn[0];
            rd_go <= 1'b1;
            rd_t <= 4'd0;
            wait_n <= 17'd13;
            st <= S_VRDE;
        end
    end
    S_VRDE: begin
        vn <= vn + 1'b1;
        if (!ok || !seen) begin
            info <= {4'd3, 4'd0};
            st <= S_FAIL;
        end else begin
            dqs_pulse <= 1'b1;
            wait_n <= 17'd8;
            st <= vn == 5'd15 ? S_FIN1 : S_VRD;
        end
    end
    S_FIN1: begin
        o_cmd <= PRE;
        o_slot <= 2'd1;
        o_a <= 15'h0400;
        wait_n <= 17'd4;
        st <= S_DONE;
    end
    S_DONE: done <= 1'b1;
    S_FAIL: fail <= 1'b1;
    default: st <= S_FAIL;
    endcase

    // (bring-up: what lane 0's first read at the position asked gave)
    if (st == S_RDE && lane == 0 && q == opt[5:0] && n == 0 && !fix_lat && set_cfg) begin
        if (rd_t == 4'd7) snap[63:0] <= {rd_data[231:224], rd_data[199:192], rd_data[167:160], rd_data[135:128],
                                         rd_data[103:96], rd_data[71:64], rd_data[39:32], rd_data[7:0]};
        if (rd_t == 4'd8) snap[127:64] <= {rd_data[231:224], rd_data[199:192], rd_data[167:160], rd_data[135:128],
                                           rd_data[103:96], rd_data[71:64], rd_data[39:32], rd_data[7:0]};
        if (rd_t >= 4'd5 && rd_t <= 4'd12) snap[128 + rd_t - 4'd5] <= r_valid[0];
    end

    // (the last reads: every lane's line in the cycle found)
    rdv_r <= rd_valid;
    if (st == S_VRDE && rdv_r) begin
        seen <= 1'b1;
        if (seen || !(&eq_r))
            ok <= 1'b0;
    end

    if (rst) begin
        st <= S_RST0;
        wait_n <= 17'd0;
        o_cke <= 1'b0;
        o_reset_n <= 1'b0;
        done <= 1'b0;
        fail <= 1'b0;
        info <= 8'd0;
        l_hold <= 0;
        l_rmove <= 0;
        l_slip <= 0;
        rd_t <= 4'd15;
        g_cyc <= 0;
        g_rot <= 0;
        g_sel <= 0;
        rd_raw <= 1'b1;
        inv <= 1'b0;
    end
end

endmodule
