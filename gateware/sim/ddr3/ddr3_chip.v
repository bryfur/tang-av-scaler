// A DDR3 SDRAM chip for the PHY's and the controller's simulation (ours:
// written from JEDEC's JESD79-3, not a vendor's model): LANES bytes wide
// (2: an x16 chip, 15 rows, 10 columns, 8 banks: the console's 4 Gb
// H5TQ4G63), BL8 only, the DLL on.  It checks what it is given and counts
// what is wrong in `errors` (each a line: "ERROR"):
//
//   - the power-up sequence (RESET#, CKE, the mode registers, ZQCL), the
//     commands' state and timing (tRCD, tRP, tRAS, tRC, tRRD, tFAW, tWR,
//     tWTR, tRTP, tRFC, tCCD, tMRD, tMOD, tDLLK, the refresh interval);
//   - a write's strobe: its preamble, the first rising edge within a
//     quarter clock of CK's (tDQSS), eight edges, the data and its mask
//     still for TDS before and TDH after each, ODT high;
//   - a read gives its data edge aligned with the strobe it drives, TDQSCK
//     after CK, a line never written reads as x and each data edge passes
//     through x for TDQSQ (a capture at the strobe's edge itself is wrong).
//
// Write leveling (MR1 A7): each rising strobe samples CK onto the lane's
// data pins TWLO later.  The multi purpose register (MR3 A2): a read gives
// 0, 1, 0, 1, ... on every data pin.
//
// The wires' flight: CKDLY (the clock and the commands to this chip) and
// DQDLY (the data and strobes, each way), in ns.  The memory kept: 2^ABITS
// lines (a line: one burst), each with its address: a line pushed out by
// another reads as x again.

`timescale 1ns / 1ps

module ddr3_chip #(
    parameter      LANES   = 2,
    parameter real CKDLY   = 0.0,
    parameter real DQDLY   = 0.0,
    parameter real TDQSCK  = 0.0,
    parameter real TDQSQ   = 0.10,
    parameter real TDS     = 0.15,
    parameter real TDH     = 0.15,
    parameter real TWLO    = 3.0,
    parameter      ABITS   = 14,
    parameter real T_RESET = 200000.0,    // RESET# low at power up
    parameter real T_CKE   = 500000.0,    // RESET# high to CKE high
    parameter real TRCD    = 15.0,
    parameter real TRP     = 15.0,
    parameter real TRAS    = 37.5,
    parameter real TRC     = 52.5,
    parameter real TRRD    = 10.0,
    parameter real TFAW    = 50.0,
    parameter real TWR     = 15.0,
    parameter real TWTR    = 7.5,
    parameter real TRTP    = 7.5,
    parameter real TRFC    = 260.0,
    parameter real TREFI   = 7800.0,
    parameter      TRACE   = 0
) (
    input  wire               ck,
    input  wire               ck_n,
    input  wire               cke,
    input  wire               cs_n,
    input  wire               ras_n,
    input  wire               cas_n,
    input  wire               we_n,
    input  wire [2:0]         ba,
    input  wire [14:0]        a,
    input  wire               odt,
    input  wire               reset_n,
    input  wire [LANES-1:0]   dm,
    inout  wire [8*LANES-1:0] dq,
    inout  wire [LANES-1:0]   dqs,
    inout  wire [LANES-1:0]   dqs_n
);

integer errors = 0;
integer n_rd = 0, n_wr = 0, n_ref = 0;

// ---- the wires (transport delays: nothing is filtered) ----
reg               ckd = 1'b0, cked = 1'b0, csd = 1'b1, rasd = 1'b1, casd = 1'b1, wed = 1'b1;
reg               odtd = 1'b0, rstd = 1'b0;
reg [2:0]         bad = 0;
reg [14:0]        ad = 0;
reg [LANES-1:0]   dmi = 0, dqsi = 0;
reg [8*LANES-1:0] dqi = 0;
always @(ck)      ckd  <= #(CKDLY) ck;
always @(cke)     cked <= #(CKDLY) cke;
always @(cs_n)    csd  <= #(CKDLY) cs_n;
always @(ras_n)   rasd <= #(CKDLY) ras_n;
always @(cas_n)   casd <= #(CKDLY) cas_n;
always @(we_n)    wed  <= #(CKDLY) we_n;
always @(odt)     odtd <= #(CKDLY) odt;
always @(reset_n) rstd <= #(CKDLY) reset_n;
always @(ba)      bad  <= #(CKDLY) ba;
always @(a)       ad   <= #(CKDLY) a;
always @(dm)      dmi  <= #(DQDLY) dm;
always @(dq)      dqi  <= #(DQDLY) dq;
always @(dqs)     dqsi <= #(DQDLY) dqs;

reg               o_dqs_en = 1'b0, o_dq_en = 1'b0, o_dqs = 1'b0;
reg [8*LANES-1:0] o_dq = 0;
reg [8*LANES-1:0] wl_dq = 0;             // write leveling's answer
reg               wl_on = 1'b0;
reg [8*LANES-1:0] p_dq;
reg [LANES-1:0]   p_dqs, p_dqsn;
wire [8*LANES-1:0] drv_dq  = wl_on ? wl_dq : o_dq_en ? o_dq : {8*LANES{1'bz}};
wire [LANES-1:0]   drv_dqs  = o_dqs_en ? {LANES{o_dqs}} : {LANES{1'bz}};
wire [LANES-1:0]   drv_dqsn = o_dqs_en ? {LANES{!o_dqs}} : {LANES{1'bz}};
initial begin p_dq = {8*LANES{1'bz}}; p_dqs = {LANES{1'bz}}; p_dqsn = {LANES{1'bz}}; end
always @(drv_dq)   p_dq   <= #(TDQSCK + DQDLY) drv_dq;
always @(drv_dqs)  p_dqs  <= #(TDQSCK + DQDLY) drv_dqs;
always @(drv_dqsn) p_dqsn <= #(TDQSCK + DQDLY) drv_dqsn;
assign dq = p_dq;
assign dqs = p_dqs;
assign dqs_n = p_dqsn;

// ---- the clock ----
real    tck = 0.0, t_ck = 0.0;
integer cyc = 0;

// ---- the registers and the banks ----
reg [14:0] mr0 = 0, mr1 = 0, mr2 = 0, mr3 = 0;
reg [3:0]  mr_set = 0;
reg        zq_done = 1'b0, cke_seen = 1'b0;
reg [7:0]  open = 0;
reg [14:0] row [0:7];
real t_act [0:7], t_pre [0:7], t_rdc [0:7], t_wend [0:7];
real t_ref = -1.0e9, t_mrs = -1.0e9, t_zq = -1.0e9, t_anyact = -1.0e9, t_dllrst = -1.0e9;
real t_rst_fall = 0.0, t_rst_rise = -1.0, t_cke_rise = -1.0, t_wend_any = -1.0e9;
real t_act3 [0:3];                       // the last four activations (tFAW)
integer c_cas = -100, c_rd = -100, c_wr = -100, c_mrs = -100, c_zq = -100000, c_dllrst = -100000;
integer zq_len = 0;
integer k;
initial begin
    for (k = 0; k < 8; k = k + 1) begin
        t_act[k] = -1.0e9; t_pre[k] = -1.0e9; t_rdc[k] = -1.0e9; t_wend[k] = -1.0e9; row[k] = 0;
    end
    for (k = 0; k < 4; k = k + 1) t_act3[k] = -1.0e9;
end

wire [3:0] cl  = mr0[6:4] + 4'd4;        // (CL 5 to 11: A2 0)
wire [3:0] cwl = mr2[5:3] + 4'd5;
wire [3:0] al  = mr1[4:3] == 0 ? 4'd0 : cl - mr1[4:3];
wire       wlev = mr1[7];
wire       mpr = mr3[2];
wire       inited = mr_set == 4'hf && zq_done;

task err(input [1023:0] what);
    begin
        errors = errors + 1;
        $display("ERROR %m at %0.3f ns (cycle %0d): %0s", $realtime, cyc, what);
    end
endtask

// ---- the memory: a line (8 beats) a lane, its address beside it ----
reg [63:0]      mem [0:LANES*(1<<ABITS)-1];
reg [25:0]      tag [0:(1<<ABITS)-1];    // {valid, bank, row, column's 7}
integer mi;
initial for (mi = 0; mi < (1 << ABITS); mi = mi + 1) tag[mi] = 0;

function [ABITS-1:0] slot(input [24:0] key);
    slot = key[ABITS-1:0] ^ (key >> ABITS) ^ (key >> (2 * ABITS));
endfunction

// ---- reads: the bursts on their way out (half clocks) ----
integer rq_h [0:7];                      // a burst's first half clock
reg [64*LANES-1:0] rq_d [0:7];
reg [7:0] rq_v = 0;
integer hc = 0;                          // the half clock: 2 * cyc, +1 on the falling edge
integer rb;
reg [64*LANES-1:0] rline;
reg [24:0] key;
integer ln, bt;

task read_line(input [24:0] kk);
    begin
        for (ln = 0; ln < LANES; ln = ln + 1)
            if (mpr)
                rline[ln * 64 +: 64] = 64'hff00_ff00_ff00_ff00;
            else if (tag[slot(kk)] == {1'b1, kk})
                rline[ln * 64 +: 64] = mem[ln * (1 << ABITS) + slot(kk)];
            else
                rline[ln * 64 +: 64] = 64'hx;
    end
endtask

task out_edge;
    reg drive, pre;
    integer b, beat;
    begin
        drive = 1'b0;
        pre = 1'b0;
        beat = 0;
        for (b = 0; b < 8; b = b + 1)
            if (rq_v[b]) begin
                if (hc >= rq_h[b] && hc < rq_h[b] + 8) begin
                    drive = 1'b1;
                    beat = hc - rq_h[b];
                    rline = rq_d[b];
                end else if (hc >= rq_h[b] - 2 && hc < rq_h[b])
                    pre = 1'b1;
                else if (hc >= rq_h[b] + 8)
                    rq_v[b] = 1'b0;
            end
        o_dqs_en <= drive | pre;
        o_dqs <= drive & !hc[0];
        o_dq_en <= drive;
        if (drive) begin
            o_dq = {8*LANES{1'bx}};
            for (ln = 0; ln < LANES; ln = ln + 1)
                o_dq[ln * 8 +: 8] <= #(TDQSQ) rline[ln * 64 + beat * 8 +: 8];
        end
    end
endtask

// ---- writes: the bursts expected (each lane takes them by its strobe) ----
real       wq_t [0:7];                   // the first rising edge expected
reg [24:0] wq_k [0:7];
reg        wq_odt [0:7];
reg [2:0]  wq_w = 0;
reg [2:0]  wq_r [0:LANES-1];
integer    wbeat [0:LANES-1];
reg [63:0] wbuf [0:LANES-1];
reg [7:0]  wmask [0:LANES-1];
real       t_dqchg [0:LANES-1], t_cap [0:LANES-1], t_wdone [0:LANES-1];
initial for (k = 0; k < LANES; k = k + 1) begin
    wq_r[k] = 0; wbeat[k] = 0; t_dqchg[k] = -1.0; t_cap[k] = -1.0e9; t_wdone[k] = -1.0e9;
end

// ---- commands ----
reg [2:0] cmd;
reg       prev_cke = 1'b0;
real      need;
integer   b2;

always @(negedge rstd) begin
    t_rst_fall = $realtime;
    mr_set = 0; zq_done = 1'b0; open = 0; cke_seen = 1'b0; rq_v = 0;
    mr0 = 0; mr1 = 0; mr2 = 0; mr3 = 0;
    wl_on = 1'b0;
end
always @(posedge rstd) begin
    t_rst_rise = $realtime;
    if ($realtime - t_rst_fall < T_RESET) err("RESET# low too short");
    if (cked !== 1'b0) err("CKE not low as RESET# rises");
end

always @(negedge ckd) begin
    hc = 2 * cyc + 1;
    out_edge;
end

always @(posedge ckd) begin
    if (t_ck > 0.0)
        tck = $realtime - t_ck;
    t_ck = $realtime;
    cyc = cyc + 1;
    hc = 2 * cyc;
    out_edge;
    // (a write's strobe that never came)
    for (ln = 0; ln < LANES; ln = ln + 1)
        if (wq_r[ln] != wq_w && wbeat[ln] == 0 && $realtime > wq_t[wq_r[ln]] + 0.6 * tck) begin
            err("a write without its strobe");
            wq_r[ln] = wq_r[ln] + 1'b1;
        end
    if (rstd === 1'b1 && cked === 1'b1 && !cke_seen) begin
        cke_seen = 1'b1;
        t_cke_rise = $realtime;
        if ($realtime - t_rst_rise < T_CKE) err("CKE high too soon after RESET#");
    end
    if (rstd === 1'b1 && cke_seen && cked !== 1'b1) err("CKE low (power down is not modelled)");
    if (inited && !mpr && !wlev && $realtime - t_ref > 9.0 * TREFI && $realtime - t_cke_rise > 9.0 * TREFI) begin
        err("no refresh for nine intervals");
        t_ref = $realtime;
    end
    cmd = {rasd, casd, wed};
    if (rstd === 1'b1 && cke_seen && prev_cke && csd === 1'b0 && cmd != 3'b111) begin
        if (TRACE)
            $display("%m %0.3f ns cycle %0d: cmd %b ba %0d a %h", $realtime, cyc, cmd, bad, ad);
        if ($realtime - t_cke_rise < TRFC + 10.0 || cyc - c_zq < zq_len)
            err("a command too soon (tXPR, tZQ)");
        if (cmd != 3'b000 && (cyc - c_mrs < 12 || $realtime - t_mrs < 15.0)) err("tMOD");
        if (wlev && cmd != 3'b000) err("a command while write leveling");
        case (cmd)
        3'b000: begin                    // MRS
            if (open != 0) err("MRS with a bank open");
            if (cyc - c_mrs < 4) err("tMRD");
            case (bad)
            3'd0: begin
                mr0 = ad;
                if (ad[8]) begin t_dllrst = $realtime; c_dllrst = cyc; end
                if (ad[1:0] != 2'b00) err("MR0: only BL8 is modelled");
                if (ad[2]) err("MR0: CL above 11");
            end
            3'd1: begin
                mr1 = ad;
                wl_on <= ad[7] && !ad[12];
                if (ad[0]) err("MR1: the DLL off is not modelled");
            end
            3'd2: mr2 = ad;
            3'd3: mr3 = ad;
            default: err("MRS: no such register");
            endcase
            mr_set[bad[1:0]] = 1'b1;
            t_mrs = $realtime;
            c_mrs = cyc;
        end
        3'b001: begin                    // REF
            if (!inited) err("REF before the registers and ZQCL");
            if (open != 0) err("REF with a bank open");
            for (b2 = 0; b2 < 8; b2 = b2 + 1)
                if ($realtime - t_pre[b2] < TRP - 0.01) err("REF: tRP");
            if ($realtime - t_ref < TRFC - 0.01) err("REF: tRFC");
            t_ref = $realtime;
            n_ref = n_ref + 1;
        end
        3'b010: begin                    // PRE (A10: all)
            for (b2 = 0; b2 < 8; b2 = b2 + 1)
                if ((ad[10] || bad == b2) && open[b2]) begin
                    if ($realtime - t_act[b2] < TRAS - 0.01) err("PRE: tRAS");
                    need = TRTP > 4.0 * tck ? TRTP : 4.0 * tck;
                    if ($realtime - t_rdc[b2] < need - 0.01) err("PRE: tRTP");
                    if ($realtime - t_wend[b2] < TWR - 0.01) err("PRE: tWR");
                    open[b2] = 1'b0;
                    t_pre[b2] = $realtime;
                end
        end
        3'b011: begin                    // ACT
            if (!inited) err("ACT before the registers and ZQCL");
            if (mpr) err("ACT with the MPR on");
            if (open[bad]) err("ACT: the bank is open");
            if ($realtime - t_pre[bad] < TRP - 0.01) err("ACT: tRP");
            if ($realtime - t_act[bad] < TRC - 0.01) err("ACT: tRC");
            if ($realtime - t_ref < TRFC - 0.01) err("ACT: tRFC");
            need = TRRD > 4.0 * tck ? TRRD : 4.0 * tck;
            if ($realtime - t_anyact < need - 0.01) err("ACT: tRRD");
            if ($realtime - t_act3[0] < TFAW - 0.01) err("ACT: tFAW");
            t_act3[0] = t_act3[1]; t_act3[1] = t_act3[2]; t_act3[2] = t_act3[3]; t_act3[3] = $realtime;
            open[bad] = 1'b1;
            row[bad] = ad;
            t_act[bad] = $realtime;
            t_anyact = $realtime;
        end
        3'b100, 3'b101: begin            // WRITE, READ
            if (!inited) err("a read or a write before the registers and ZQCL");
            if (cyc - c_cas < 4) err("tCCD");
            if (cyc - c_dllrst < 512) err("tDLLK");
            if (ad[10]) err("auto precharge is not modelled");
            if (!mpr) begin
                if (!open[bad]) err("a read or a write to a closed bank");
                if ($realtime - t_act[bad] < TRCD - 0.01) err("tRCD");
                if (ad[2:0] != 0) err("a burst not at a multiple of 8 columns");
            end
            key = {bad, row[bad], ad[9:3]};
            if (cmd == 3'b101) begin
                need = TWTR > 4.0 * tck ? TWTR : 4.0 * tck;
                if ($realtime - t_wend_any < need - 0.01) err("READ: tWTR");
                read_line(key);
                rb = 0;
                while (rb < 7 && rq_v[rb]) rb = rb + 1;
                rq_v[rb] = 1'b1;
                rq_h[rb] = 2 * (cyc + cl + al);
                rq_d[rb] = rline;
                t_rdc[bad] = $realtime;
                c_rd = cyc;
                n_rd = n_rd + 1;
            end else begin
                if (mpr) err("WRITE with the MPR on");
                if (cyc - c_rd < cl + 4 + 2 - cwl) err("WRITE too soon after a READ");
                wq_t[wq_w] = $realtime + (cwl + al) * tck;
                wq_k[wq_w] = key;
                wq_w = wq_w + 1'b1;
                t_wend[bad] = $realtime + (cwl + al + 4) * tck;
                t_wend_any = t_wend[bad];
                c_wr = cyc;
                n_wr = n_wr + 1;
            end
            c_cas = cyc;
        end
        3'b110: begin                    // ZQCL (A10), ZQCS
            if (open != 0) err("ZQ with a bank open");
            zq_len = !ad[10] ? 64 : zq_done ? 256 : 512;
            c_zq = cyc;
            if (ad[10] && mr_set == 4'hf) zq_done = 1'b1;
        end
        default: ;
        endcase
    end
    prev_cke = cked === 1'b1;
end

// ---- a lane's strobe: write leveling, the writes' data ----
genvar l;
generate for (l = 0; l < LANES; l = l + 1) begin : lane
    wire [7:0] d = dqi[l * 8 +: 8];
    wire       m = dmi[l];
    wire       s = dqsi[l];
    reg [24:0] wk;
    // (the strobe's last fall: the preamble's start)
    real t_slow;
    initial t_slow = 0.0;
    always @(s) if (s === 1'b0) t_slow = $realtime;
    always @(d or m) begin
        t_dqchg[l] = $realtime;
        if ($realtime - t_cap[l] < TDH - 0.001) begin
            errors = errors + 1;
            $display("ERROR %m at %0.3f ns: write data moved %0.3f ns after its strobe (TDH)",
                $realtime, $realtime - t_cap[l]);
        end
    end
    always @(s) begin
        if (wlev) begin
            if (s === 1'b1)
                wl_dq[l * 8 +: 8] <= #(TWLO) {8{ckd}};
        end else if (wbeat[l] == 0) begin
            if (s === 1'b1 && wq_r[l] != wq_w && $realtime > wq_t[wq_r[l]] - 0.5 * tck
                    && $realtime < wq_t[wq_r[l]] + 0.5 * tck) begin
                if ($realtime - wq_t[wq_r[l]] > 0.25 * tck || wq_t[wq_r[l]] - $realtime > 0.25 * tck) begin
                    errors = errors + 1;
                    $display("ERROR %m at %0.3f ns: the write strobe %0.3f ns from CK (tDQSS)",
                        $realtime, $realtime - wq_t[wq_r[l]]);
                end
                // (the preamble: low for most of a clock before, unless a
                // burst just ended on this lane)
                if ($realtime - t_wdone[l] > 0.75 * tck && $realtime - t_slow < 0.7 * tck) begin
                    errors = errors + 1;
                    $display("ERROR %m at %0.3f ns: the write preamble %0.3f ns low", $realtime, $realtime - t_slow);
                end
                if (odtd !== 1'b1) begin
                    errors = errors + 1;
                    $display("ERROR %m at %0.3f ns: a write without ODT", $realtime);
                end
                take(0);
            end
        end else if (s === (wbeat[l] % 2 == 0 ? 1'b1 : 1'b0))
            take(wbeat[l]);
        else begin
            errors = errors + 1;
            $display("ERROR %m at %0.3f ns: the write strobe is %b at beat %0d", $realtime, s, wbeat[l]);
            wbeat[l] = 0;
            wq_r[l] = wq_r[l] + 1'b1;
        end
    end
    task take(input integer beat);
        begin
            if ($realtime - t_dqchg[l] < TDS - 0.001) begin
                errors = errors + 1;
                $display("ERROR %m at %0.3f ns: write data moved %0.3f ns before its strobe (TDS), beat %0d",
                    $realtime, $realtime - t_dqchg[l], beat);
            end
            t_cap[l] = $realtime;
            wbuf[l][beat * 8 +: 8] = d;
            wmask[l][beat] = m;
            wbeat[l] = beat + 1;
            if (beat == 7) begin
                wk = wq_k[wq_r[l]];
                // (the line's address: set by the first lane to write it)
                if (tag[slot(wk)] != {1'b1, wk}) begin : fresh
                    integer q;
                    for (q = 0; q < LANES; q = q + 1)
                        mem[q * (1 << ABITS) + slot(wk)] = 64'hx;
                    tag[slot(wk)] = {1'b1, wk};
                end
                begin : put
                    integer q;
                    for (q = 0; q < 8; q = q + 1)
                        if (wmask[l][q] === 1'b0)
                            mem[l * (1 << ABITS) + slot(wk)][q * 8 +: 8] = wbuf[l][q * 8 +: 8];
                        else if (wmask[l][q] !== 1'b1)
                            mem[l * (1 << ABITS) + slot(wk)][q * 8 +: 8] = 8'hx;
                end
                wbeat[l] = 0;
                wq_r[l] = wq_r[l] + 1'b1;
                t_wdone[l] = $realtime;
            end
        end
    endtask
end endgenerate

endmodule
