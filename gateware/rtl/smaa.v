// smaa.v: the anti-aliasing: SMAA 1x's orthogonal patterns as sim/smaa.py has them (smaa_words()), on
// the stream of 4:2:2 lines (a pixel: luma and one chroma sample, Cb the even pixels, Cr the odd)
// before they are scaled.  On the DDR3's user clock.
//
// In: a line's pixels on successive clocks (i_v, i_x, i_j the line, i_last with the last), then
// 24 clocks or more of nothing; the lines in order from 0, and N + 4 more after the picture's last
// (H to H + N + 3: whatever).  Out: the same lines mixed, LAG = N + 3 lines later, and after the last
// one more (H: whatever is in it).
//
// A line is taken through as W + K columns, the K after the picture empty (K = NH + 4): what looks NH
// columns to each side then needs no thought for the picture's edge.  Three steps, each a column or
// two behind the one before:
//
//   edges    of the line before the one coming in (it wants the line below): for column x - 1 as
//            column x passes
//   weights  of the line N + 1 above the edges' (the edges of the 2N + 3 lines round it are kept for
//            each column): for the column NH + 2 behind.  The four searches (left, right: how far
//            the edge runs, to NH; up, down: to N; which way it turns there), then the area table
//            ({the turns 4, the two lengths 4 each, 5 each along a line} -> {the part cut off above
//            the edge, below})
//            With diag: first, for a pixel with a top edge, the two diagonal lines through it
//            (SMAA's diagonal patterns: along each, to ND = 8 pixels, the run of pixels with both
//            edges; the edges that cross at its ends; a second table): if they give a weight the
//            pixel has that, and neither search across.
//   mixing   of the line above the weights' (it wants the weights below): the pixel with the one of
//            its four neighbours whose weight is greatest; chroma with the one above or below only
//
// en 0: no edges, the picture through as it is (as late).  thr: the luma step that is an edge.
// dbg: what it finds, in the picture's place: the picture dimmed to a quarter and grey; a pixel
// with an edge and nothing mixed green; a pixel mixed with the one above or below blue, with the
// one beside it red, the brighter the more.

`ifndef SMAA_HEX
`define SMAA_HEX "smaa.hex"
`define SMAA_DHEX "smaad.hex"
`endif
`ifndef SMAA_HHEX
`define SMAA_HHEX "smaah.hex"
`endif

module smaa_rom #(
    parameter FILE = "",
    parameter AW = 12
) (
    input             clk,
    input      [AW - 1:0] a,
    output reg [15:0] q
);
    reg [15:0] mem [0:(1 << AW) - 1];
    initial $readmemh(FILE, mem);
    reg [15:0] q1;
    always @(posedge clk) begin
        q1 <= mem[a];
        q <= q1;
    end
endmodule

// the same read at two places at once (two of the searches use one table): one set of block RAMs,
// their two ports.  The synthesis makes two ROMs of this, so for the build the block RAMs are
// named: the included file is sim/smaa.py dpb's (DIAG: the diagonals' table, else the plain one's).
// The data two clocks after the address.
module smaa_rom2 #(
    parameter FILE = "",
    parameter DIAG = 0
) (
    input             clk,
    input      [11:0] a,
    input      [11:0] b,
    output reg [15:0] qa,
    output reg [15:0] qb
);
`ifdef AVB_GOWIN
    wire [15:0] xa, xb;
    generate
        if (DIAG) begin : g_d
            wire [15:0] da, db;
`include "smaad_dpb.vh"
            assign xa = da;
            assign xb = db;
        end else begin : g_o
            wire [15:0] da, db;
`include "smaa_dpb.vh"
            assign xa = da;
            assign xb = db;
        end
    endgenerate
    always @(posedge clk) begin
        qa <= xa;
        qb <= xb;
    end
`else
    reg [15:0] mem [0:4095];
    initial $readmemh(FILE, mem);
    reg [15:0] a1, b1;
    always @(posedge clk) begin
        a1 <= mem[a];
        b1 <= mem[b];
        qa <= a1;
        qb <= b1;
    end
`endif
endmodule

module smaa #(
    parameter W = 720,
    parameter N = 15,                   // the searches' reach up and down (the lines kept) ...
    parameter NH = 15                   // ... and along a line (15; 31: a table of 16384, sim/smaa.py NH)
) (
    input             clk,
    input      [9:0]  h,                // the picture's lines (480, or fewer: lstream.v's skip)
    input             en,
    input      [7:0]  thr,
    input             dbg,
    input             diag,             // the diagonal patterns too
    input             corner,           // less mixed where a line ends in a corner
    // the edges of the frame before (smaa_hist.v; keep 0: none of it): asked for by the place (hq_x,
    // hq_l: three clocks before p_e is wanted), and this frame's as they are decided (hg_*)
    input      [2:0]  keep,
    output     [9:0]  hq_x,
    output     [9:0]  hq_l,
    input      [1:0]  p_e,              // {top, left}
    output            hg_v,
    output     [10:0] hg_x,
    output     [9:0]  hg_e,
    output            hg_el,
    output            hg_et,
    input             i_v,
    input      [9:0]  i_x,
    input      [9:0]  i_j,
    input             i_last,
    input      [7:0]  i_y,
    input      [7:0]  i_c,
    output reg        o_v = 1'b0,
    output reg [9:0]  o_x,
    output reg [9:0]  o_j,
    output reg        o_last,
    output reg [7:0]  o_y,
    output reg [7:0]  o_c
) /* synthesis syn_srlstyle = "registers" */;        // (its delays are registers: as block RAM each is two sites, 36 bits wide)
    localparam K = NH + 4;
    localparam M = NH + 1;              // the middle column: this many behind the newest (hk, cv)
    integer i;
    function [7:0] absd(input [7:0] a, input [7:0] b);
        absd = a > b ? a - b : b - a;
    endfunction
    function [7:0] max2(input [7:0] a, input [7:0] b);
        max2 = a > b ? a : b;
    endfunction

    // ---- the columns: the line's, then K empty ones ----
    reg        t_v = 1'b0, t_b;
    reg [10:0] t_x;
    reg [9:0]  t_j;
    reg [7:0]  t_y, t_c;
    reg [5:0]  more = 6'd0;
    always @(posedge clk) begin
        t_v <= i_v || more != 6'd0;
        if (i_v) begin
            t_x <= {1'b0, i_x};
            t_j <= i_j;
            if (i_x == 10'd0)
                ws <= i_j == 10'd0 || ws == PL - 1 ? 5'd0 : ws + 5'd1;
            t_b <= 1'b0;
            t_y <= i_y;
            t_c <= i_c;
            more <= i_last ? K[5:0] : 6'd0;
        end else if (more != 6'd0) begin
            t_x <= t_x + 11'd1;
            t_b <= 1'b1;
            more <= more - 6'd1;
        end
    end

    // the pixels kept, for the mixing, N + 2 lines on: PL = N + 3 lines of them (the one coming in to
    // the one mixed: a block RAM a line, and no more of them than that), a line's place its number
    // modulo PL: counted (ws) as the lines come, from 0 with a frame's first
    // (a RAM a line, named so: of one memory of PL x 1024 the synthesis makes thirty-two blocks a bit
    // wide, as of 32768 words)
    localparam PL = N + 3;
    reg [4:0]  ws = 5'd0;
    reg [14:0] p_ra;
    wire [15:0] p_qs [0:PL - 1];
    reg [4:0]  p_sl;
    genvar gp;
    generate
        for (gp = 0; gp < PL; gp = gp + 1) begin : g_pm
            reg [15:0] m [0:1023];
            reg [15:0] q1;
            always @(posedge clk) begin
                if (t_v && !t_b && ws == gp)
                    m[t_x[9:0]] <= {t_y, t_c};
                q1 <= m[p_ra[9:0]];
            end
            assign p_qs[gp] = q1;
        end
    endgenerate
    always @(posedge clk)
        p_sl <= p_ra[14:10];
    wire [15:0] p_q = p_qs[p_sl];

    // ---- edges ----
    // each column's luma of the three lines before
    reg [23:0] am [0:1023];
    reg [23:0] a_r1;                    // (the RAM's register, then one beside the logic: as each RAM here)
    reg [23:0] a_q /* synthesis syn_preserve = 1 */;
    reg        e0_v = 1'b0, e0_b, e1_v = 1'b0, e1_b;
    reg [10:0] e0_x, e1_x;
    reg        xc_first, xc_le1, xc_last, xc_out;       // xc is 0; is 0 or 1; is W - 1 or more; is W or more
    reg        ee_ge1, ee_ge2, ee_leh2;
    reg [9:0]  e0_j, e1_j;
    reg [7:0]  e0_y, e1_y;
    always @(posedge clk) begin
        a_r1 <= am[t_x[9:0]];
        a_q <= a_r1;
        {e1_v, e0_v} <= {e0_v, t_v};
        {e1_b, e0_b} <= {e0_b, t_b};
        {e1_x, e0_x} <= {e0_x, t_x};
        // (where the column before e1_x's, xc, is in the line: known a clock before: not before the steps' sums)
        xc_first <= e0_x == 11'd1;
        xc_le1 <= e0_x == 11'd1 || e0_x == 11'd2;
        xc_last <= e0_x == 11'd0 || e0_x >= W;
        xc_out <= e0_x == 11'd0 || e0_x > W;
        // (and the edges' line, ee = e1_j - 1: 1 or more, 2 or more, H - 2 or less)
        ee_ge1 <= e0_j != 10'd1;
        ee_ge2 <= e0_j != 10'd1 && e0_j != 10'd2;
        ee_leh2 <= e0_j != 10'd0 && e0_j <= h - 10'd1;
        {e1_j, e0_j} <= {e0_j, t_j};
        {e1_y, e0_y} <= {e0_y, t_y};
        if (e1_v && !e1_b)
            am[e1_x[9:0]] <= {e1_y, a_q[23:8]};
    end
    // the line of the edges: e1_j - 1; this column's luma on it, above it, above that, below it
    wire [9:0] ee = e1_j - 10'd1;
    wire [7:0] cC = a_q[23:16];
    wire [7:0] cT = ee_ge1 ? a_q[15:8] : cC;
    wire [7:0] cTT = ee_ge2 ? a_q[7:0] : cT;
    wire [7:0] cB = ee_leh2 ? e1_y : cC;
    // the column before (the edges' own), and the two before it
    reg [7:0]  n1_c, n1_t, n1_tt, n1_b, n2_c, n3_c, n2_t;
    reg        sl2, sr2, sl3, sr3, g_sl, g_sr;     // (the column's pixel like the one up and to its left, to its right)
    reg        e2_v = 1'b0, e3_v = 1'b0;
    reg [10:0] e2_x, e3_x;
    reg [9:0]  e2_e, e3_e;
    reg [7:0]  dl, dt, dr, db, dll, dtt, mx3b, mx3c, dl3, dt3;
    reg        g_v = 1'b0, g_el, g_et, e2_z, e3_z;
    reg [10:0] g_x;
    reg [9:0]  g_e;
    wire [10:0] xc = e1_x - 11'd1;
    // (twice a step no less than the greatest of the six: than each of the others, side by side)
    // (and keep: an edge the frame before had counts keep levels more, one it had not keep levels
    // less: sim/smaa.py edges(); p_e is the frame before's of the column the steps (2) are of)
    wire signed [3:0] kp = {1'b0, keep};
    wire signed [3:0] kl = p_e[0] ? kp : -kp;
    wire signed [3:0] kt = p_e[1] ? kp : -kp;
    reg  signed [9:0] dl3k, dt3k;
    reg  signed [10:0] dl3x, dt3x;
    wire [10:0] tq = t_x - 11'd1;
    assign hq_x = tq[9:0];
    assign hq_l = t_j - 10'd1;
    assign hg_v = g_v;
    assign hg_x = g_x;
    assign hg_e = g_e;
    assign hg_el = g_el;
    assign hg_et = g_et;
    always @(posedge clk) begin
        e2_v <= 1'b0;
        if (e1_v) begin
            n1_c <= cC;
            n1_t <= cT;
            n1_tt <= cTT;
            n1_b <= cB;
            n2_c <= n1_c;
            n3_c <= n2_c;
            n2_t <= n1_t;
            // (2) the six steps round the column before
            e2_v <= e1_x != 11'd0 && e1_j != 10'd0;
            e2_x <= xc;
            e2_e <= ee;
            e2_z <= xc_out || ee >= h || !en;
            dl <= xc_first ? 8'd0 : absd(n1_c, n2_c);
            dt <= absd(n1_c, n1_t);
            dr <= xc_last ? 8'd0 : absd(n1_c, cC);
            db <= absd(n1_c, n1_b);
            dll <= xc_le1 ? 8'd0 : absd(n2_c, n3_c);
            dtt <= absd(n1_t, n1_tt);
            // (for the turns where edges cross both ways: sim/smaa.py weights(); beyond the picture's
            // side the pixel above itself)
            sl2 <= absd(n1_c, xc_first ? n1_t : n2_t) < thr;
            sr2 <= absd(n1_c, xc_last ? n1_t : cT) < thr;
        end
        // (3) the greatest, two and two
        e3_v <= e2_v;
        e3_x <= e2_x;
        e3_e <= e2_e;
        e3_z <= e2_z;
        mx3b <= max2(dr, db);
        mx3c <= max2(dll, dtt);
        dl3 <= dl;
        dt3 <= dt;
        dl3k <= $signed({2'b00, dl}) + kl;
        dt3k <= $signed({2'b00, dt}) + kt;
        dl3x <= $signed({2'b00, dl, 1'b0}) + kl;
        dt3x <= $signed({2'b00, dt, 1'b0}) + kt;
        {sl3, sr3} <= {sl2, sr2};
        {g_sl, g_sr} <= {sl3, sr3};
        // (4) the edges
        g_v <= e3_v;
        g_x <= e3_x;
        g_e <= e3_e;
        g_el <= !e3_z && dl3k >= $signed({2'b00, thr}) && dl3 != 8'd0 && dl3x >= $signed({3'b000, dt3})
                && dl3x >= $signed({3'b000, mx3b}) && dl3x >= $signed({3'b000, mx3c});
        g_et <= !e3_z && dt3k >= $signed({2'b00, thr}) && dt3 != 8'd0 && dt3x >= $signed({3'b000, dl3})
                && dt3x >= $signed({3'b000, mx3b}) && dt3x >= $signed({3'b000, mx3c});
    end

    // ---- weights ----
    // each column's edges of the 2N + 2 lines before (128 bits: line e - 1 lowest; a line {like the
    // pixel up and to its right, to its left, a left edge, a top edge})
    reg [127:0] bm [0:1023];
    reg [127:0] b_r1;
    reg [127:0] b_q /* synthesis syn_preserve = 1 */;
    reg        w0_v = 1'b0, w0_el, w0_et, w0_sl, w0_sr, w1_v = 1'b0, w1_el, w1_et, w1_sl, w1_sr;
    reg [10:0] w0_x, w1_x;
    reg [9:0]  w0_e, w1_e;
    always @(posedge clk) begin
        b_r1 <= bm[g_x[9:0]];
        b_q <= b_r1;
        {w1_v, w0_v} <= {w0_v, g_v};
        {w1_x, w0_x} <= {w0_x, g_x};
        {w1_e, w0_e} <= {w0_e, g_e};
        {w1_el, w0_el} <= {w0_el, g_el};
        {w1_et, w0_et} <= {w0_et, g_et};
        {w1_sl, w0_sl} <= {w0_sl, g_sl};
        {w1_sr, w0_sr} <= {w0_sr, g_sr};
        if (w1_v && w1_x < W)
            bm[w1_x[9:0]] <= {b_q[123:0], w1_sr, w1_sl, w1_el, w1_et};
    end
    // the column's 2N + 3 lines, e the lowest two bits; those above the picture's first empty
    reg [131:0] vm4;
    reg [65:0]  vm;                     // the edges: {left, top} a line
    reg [32:0]  vsl, vsr;               // like the pixel up and to its left; to its right
    always @* begin
        vm4 = w1_x < W ? {b_q, w1_sr, w1_sl, w1_el, w1_et} : 132'd0;
        for (i = 0; i <= 32; i = i + 1) begin
            vm[2 * i] = vm4[4 * i] && !(i > w1_e);
            vm[2 * i + 1] = vm4[4 * i + 1] && !(i > w1_e);
            vsl[i] = vm4[4 * i + 2];
            vsr[i] = vm4[4 * i + 3];
        end
    end
    // the columns before: all their lines for the last N + 11 (cv[k]: column w1_x - 1 - k; the
    // diagonals look nine columns to the middle one's left); the
    // middle line's {top, left}, the line above's left, and the lefts of the line below and of the
    // line two above (for the corners) for the last 2N + 3 (hk); with them the tops of the lines
    // above and below (does a crossing edge go on: the corners) and the middle line's two
    // likenesses (the turns); and the likenesses of all the lines: to its left of the middle column
    // (svl), to its right of the column before it (svr)
    reg [65:0] cv [0:M + 9] /* synthesis syn_ramstyle = "registers" */;
    reg [8:0]  hk [0:2 * M] /* synthesis syn_ramstyle = "registers" */;
    reg [32:0] svl [0:M], svr [0:M + 1];
    // the middle column: w1_x - (M + 1), hk[M], cv[M]; the one before it cv[M + 1]
    // hz(o): column middle + o, -M <= o <= M: {top, left, left of the line above}
    reg [NH:0] ls, rs;                  // each search's stops: along the line ...
    reg [15:0] us, ds;                  // ... up and down
    reg [4 * NH + 3:0] lc, rc;          // at each step: the edge that crosses a pixel further on the
    reg [63:0] uc, dc;                  // pixel's side, on the other side; the turns {down or own, up or other}
    reg        s_v = 1'b0, s_et, s_el;
    // the diagonals: along "/" (a) and "\\" (b), to the left and to the right, the eight pixels that
    // carry the line on; the pixels that start them; at each distance the two edges crossing there
    reg [8:1]  ga_l, ga_r, gb_l, gb_r;
    reg        sa, sb;
    reg [17:0] ca_l, cb_r;              // (distance d at bits 2d+1:2d: {a top edge, a left edge})
    reg [15:0] ca_r, cb_l;
    reg [10:0] s_x;
    reg [9:0]  s_r;
    // (the lines of a column: line r + m is 16 - m lines back from e)
    `define ET(v, m) v[2 * (16 - (m))]
    `define EL(v, m) v[2 * (16 - (m)) + 1]
    `define SM(v, m) v[16 - (m)]
    // the turn at an end: the crossing edges {the pixel's own side's, the other side's}; both: the
    // one the pixels speak for (ok_o: the other side's; ok_d: the own side's), if only one
    function [1:0] trn(input down, input up, input ok_o, input ok_d);
        trn = down && up && ok_o != ok_d ? {ok_d, ok_o} : {down, up};
    endfunction
    always @(posedge clk) begin
        s_v <= 1'b0;
        if (w1_v) begin
            cv[0] <= vm;
            // {like up-right, like up-left, the top of the line below, of the line above; the left of
            // the line two above, of the line below; the line's top, its left, the line above's left}
            hk[0] <= {vsr[16], vsl[16], vm[30], vm[34], vm[37], vm[31], vm[32], vm[33], vm[35]};
            svl[0] <= vsl;
            svr[0] <= vsr;
            for (i = 1; i <= M; i = i + 1)
                svl[i] <= svl[i - 1];
            for (i = 1; i <= M + 1; i = i + 1)
                svr[i] <= svr[i - 1];
            for (i = 1; i <= M + 9; i = i + 1)
                cv[i] <= cv[i - 1];
            for (i = 1; i <= 2 * M; i = i + 1)
                hk[i] <= hk[i - 1];
            // the searches' steps, from the columns as they were (the middle one M + 1 behind this)
            s_v <= w1_x >= M + 1 && w1_e >= 10'd16;
            s_x <= w1_x - (M + 1);
            s_r <= w1_e - 10'd16;
            s_sl <= ws == PL - 1 ? 5'd0 : ws + 5'd1;    // (that line's place among the pixels kept: N + 2 lines before the one coming in)
            s_et <= hk[M][2];
            s_el <= hk[M][1];
            for (i = 0; i <= NH; i = i + 1) begin
                // left: the boundary on the left of column -i; right: on the right of column +i
                ls[i] <= hk[M + i][1] | hk[M + i][0] | !hk[M + i + 1][2] | (i == NH);
                lc[4 * i +: 4] <= {hk[M + i][3] & !hk[M + i][6] & !hk[M + i + 1][6], hk[M + i][4] & !hk[M + i][5] & !hk[M + i + 1][5],
                                   trn(hk[M + i][1], hk[M + i][0], hk[M + i][7], hk[M + i + 1][8])};
                rs[i] <= hk[M - i - 1][1] | hk[M - i - 1][0] | !hk[M - i - 1][2] | (i == NH);
                rc[4 * i +: 4] <= {hk[M - i - 1][3] & !hk[M - i - 1][6] & !hk[M - i][6], hk[M - i - 1][4] & !hk[M - i - 1][5] & !hk[M - i][5],
                                   trn(hk[M - i - 1][1], hk[M - i - 1][0], hk[M - i][8], hk[M - i - 1][7])};
            end
            for (i = 0; i < 16; i = i + 1) begin
                // up: the boundary above line -i; down: below line +i
                us[i] <= `ET(cv[M], -i) | `ET(cv[M + 1], -i) | !`EL(cv[M], -i - 1) | (i == 15);
                uc[4 * i +: 4] <= {`ET(cv[M - 1], -i) & !`EL(cv[M - 1], -i) & !`EL(cv[M - 1], -i - 1),
                                   `ET(cv[M + 2], -i) & !`EL(cv[M + 1], -i) & !`EL(cv[M + 1], -i - 1),
                                   trn(`ET(cv[M], -i), `ET(cv[M + 1], -i), `SM(svl[M], -i), `SM(svr[M + 1], -i))};
                ds[i] <= `ET(cv[M], i + 1) | `ET(cv[M + 1], i + 1) | !`EL(cv[M], i + 1) | (i == 15);
                dc[4 * i +: 4] <= {`ET(cv[M - 1], i + 1) & !`EL(cv[M - 1], i + 1) & !`EL(cv[M - 1], i),
                                   `ET(cv[M + 2], i + 1) & !`EL(cv[M + 1], i + 1) & !`EL(cv[M + 1], i),
                                   trn(`ET(cv[M], i + 1), `ET(cv[M + 1], i + 1), `SM(svr[M + 1], i + 1), `SM(svl[M], i + 1))};
            end
            // (cv[M - o]: the column o to the middle one's right)
            sa <= `EL(cv[M], 0);
            sb <= `EL(cv[M - 1], 0);
            for (i = 1; i <= 8; i = i + 1) begin
                ga_l[i] <= `ET(cv[M + i], i) & `EL(cv[M + i], i);
                ga_r[i] <= `ET(cv[M - i], -i) & `EL(cv[M - i], -i);
                gb_l[i] <= `ET(cv[M + i], -i) & `EL(cv[M + i - 1], -i);
                gb_r[i] <= `ET(cv[M - i], i) & `EL(cv[M - i - 1], i);
            end
            for (i = 0; i <= 8; i = i + 1) begin
                ca_l[2 * i +: 2] <= {`ET(cv[M + i + 1], i), `EL(cv[M + i], i)};
                cb_r[2 * i +: 2] <= {`ET(cv[M - i - 1], i), `EL(cv[M - i - 1], i)};
            end
            for (i = 0; i <= 7; i = i + 1) begin
                ca_r[2 * i +: 2] <= {`ET(cv[M - i - 1], -i), `EL(cv[M - i - 1], -i - 1)};
                cb_l[2 * i +: 2] <= {`ET(cv[M + i + 1], -i), `EL(cv[M + i], -i - 1)};
            end
        end
    end
    // the first stop of each, and the turn there
    function [7:0] first(input [15:0] stop, input [63:0] turn);
        integer n;
        begin
            first = {turn[63:60], 4'd15};
            for (n = 14; n >= 0; n = n - 1)
                if (stop[n])
                    first = {turn[4 * n +: 4], n[3:0]};
        end
    endfunction
    // (along the line, to NH: {the turn 4, the distance 5}; in two halves, the nearer first: no
    // longer a chain than first()'s)
    function [8:0] firsth(input [NH:0] stop, input [4 * NH + 3:0] turn);
        integer n;
        reg [8:0] lo, hi;
        begin
            lo = {turn[4 * (NH < 16 ? NH : 15) +: 4], NH < 16 ? NH[4:0] : 5'd15};
            for (n = (NH < 16 ? NH : 15) - 1; n >= 0; n = n - 1)
                if (stop[n])
                    lo = {turn[4 * n +: 4], n[4:0]};
            hi = {turn[4 * NH +: 4], NH[4:0]};
            for (n = NH - 1; n >= 16; n = n - 1)
                if (stop[n])
                    hi = {turn[4 * n +: 4], n[4:0]};
            firsth = NH < 16 || |stop[15:0] ? lo : hi;
        end
    endfunction
    // the corners [SMAA_CORNER_ROUNDING 25]: where the edge crossing at the line's nearer end (both
    // ends, if as near) goes on a pixel further, the weight x 1/4 (2), or x 5/8 with one of two (1)
    function [1:0] cnr(input [4:0] d1, input [4:0] d2, input a1, input a2);
        cnr = d1 == d2 ? (a1 && a2 ? 2'd2 : a1 || a2 ? 2'd1 : 2'd0) : (d1 < d2 ? a1 : a2) ? 2'd2 : 2'd0;
    endfunction
    function [7:0] rnd(input [7:0] w, input [1:0] c);
        reg [10:0] t;
        begin
            t = c[1] ? {3'd0, w} + 11'd2 : {1'b0, w, 2'b00} + {3'd0, w} + 11'd4;
            rnd = c == 2'd0 ? w : c[1] ? t[9:2] : t[10:3];
        end
    endfunction
    reg [1:0]  n_ht, n_hu, n_vl, n_vo, n3_ht, n3_hu, n3_vl, n3_vo;
    reg        q_v = 1'b0, q_et, q_el, q2_v = 1'b0, q2_et, q2_el, q3_v = 1'b0, q3_et, q3_el;
    reg [10:0] q_x, q2_x, q3_x;
    reg [9:0]  q_r, q2_r, q3_r;
    reg [4:0]  s_sl, q_sl, q2_sl, q3_sl, k_sl;
    reg [8:0]  fl, fr;                  // {the turn 4, the distance 5}
    reg [7:0]  fu, fd;
    // a diagonal search: {the line goes on past the eighth pixel, pixels before it stops (0-7)}
    function [3:0] dsearch(input [8:1] on);
        integer n;
        begin
            dsearch = 4'b1111;
            for (n = 8; n >= 1; n = n - 1)
                if (!on[n])
                    dsearch = n - 1;
        end
    endfunction
    reg [11:0] fda, fdb;                // the diagonal table's addresses: {the turns 2 and 2, the lengths 4 and 4}
    reg        ga, gb, ga2, gb2, ga3, gb3;
    reg [3:0]  t_al, t_ar, t_bl, t_br, d1a, d2a, d1b, d2b;
    reg [1:0]  c1a, c2a, c1b, c2b;
    wire [15:0] ada, adb;
    smaa_rom2 #(.FILE(`SMAA_DHEX), .DIAG(1)) u_dab (.clk(clk), .a(fda), .b(fdb), .qa(ada), .qb(adb));
    reg [8:0]  dwr, dwg;
    wire [15:0] ah, av;                 // {above, below} of the top edge; {other side, own} of the left
    // (an end still crossing both ways with one turn at the other end: that turn's opposite, the
    // line a Z from end to end: SMAA's own, AreaTex.py areaortho 7, 11, 13, 14)
    function [3:0] zends(input [1:0] t2, input [1:0] t1);
        zends = {t2 == 2'b11 && ^t1 ? ~t1 : t2, t1 == 2'b11 && ^t2 ? ~t2 : t1};
    endfunction
    generate
        if (NH > 15) begin : g_h31
            smaa_rom #(.FILE(`SMAA_HHEX), .AW(14)) u_ah (.clk(clk), .a({zends(fr[6:5], fl[6:5]), fl[4:0], fr[4:0]}), .q(ah));
            smaa_rom #(.FILE(`SMAA_HEX)) u_av (.clk(clk), .a({zends(fd[5:4], fu[5:4]), fu[3:0], fd[3:0]}), .q(av));
        end else begin : g_h15          // (along a line and up and down by the same table: one, read twice)
            smaa_rom2 #(.FILE(`SMAA_HEX)) u_ahv (.clk(clk), .a({zends(fr[6:5], fl[6:5]), fl[3:0], fr[3:0]}),
                                               .b({zends(fd[5:4], fu[5:4]), fu[3:0], fd[3:0]}), .qa(ah), .qb(av));
        end
    endgenerate
    reg        k_v = 1'b0;
    reg [10:0] k_x;
    reg [9:0]  k_r;
    reg [7:0]  k_wt, k_wu, k_wl, k_wo;
    reg [1:0]  k_e;                     // the pixel's own edges {left, top}
    always @(posedge clk) begin
        q_v <= s_v;
        q_x <= s_x;
        q_r <= s_r;
        q_sl <= s_sl;
        q_et <= s_et;
        q_el <= s_el;
        fl <= firsth(ls, lc);
        fr <= firsth(rs, rc);
        fu <= first(us, uc);
        fd <= first(ds, dc);
        // the diagonals' lengths (one more where the line was not seen to end, on the side that has
        // the pixel's own start), the edges crossing at their ends (none where it did not end)
        t_al = dsearch(ga_l);
        t_ar = dsearch(ga_r);
        t_bl = dsearch(gb_l);
        t_br = dsearch(gb_r);
        d1a = sa ? {1'b0, t_al[2:0]} + {3'd0, t_al[3]} : 4'd0;
        d2a = {1'b0, t_ar[2:0]};
        d1b = {1'b0, t_bl[2:0]};
        d2b = sb ? {1'b0, t_br[2:0]} + {3'd0, t_br[3]} : 4'd0;
        c1a = sa && t_al[3] ? 2'd0 : ca_l[2 * d1a +: 2];
        c2a = t_ar[3] ? 2'd0 : ca_r[2 * d2a[2:0] +: 2];
        c1b = t_bl[3] ? 2'd0 : cb_l[2 * d1b[2:0] +: 2];
        c2b = sb && t_br[3] ? 2'd0 : cb_r[2 * d2b +: 2];
        fda <= {c1a, c2a, d1a, d2a};
        fdb <= {c1b, c2b, d1b, d2b};
        ga <= diag && {1'b0, d1a} + {1'b0, d2a} > 5'd2;
        gb <= diag && {1'b0, d1b} + {1'b0, d2b} > 5'd2;
        {ga3, ga2} <= {ga2, ga};
        {gb3, gb2} <= {gb2, gb};
        n_ht <= corner ? cnr(fl[4:0], fr[4:0], fl[8], fr[8]) : 2'd0;
        n_hu <= corner ? cnr(fl[4:0], fr[4:0], fl[7], fr[7]) : 2'd0;
        n_vl <= corner ? cnr({1'b0, fu[3:0]}, {1'b0, fd[3:0]}, fu[7], fd[7]) : 2'd0;
        n_vo <= corner ? cnr({1'b0, fu[3:0]}, {1'b0, fd[3:0]}, fu[6], fd[6]) : 2'd0;
        {n3_ht, n3_hu, n3_vl, n3_vo} <= {n_ht, n_hu, n_vl, n_vo};
        {q3_v, q2_v} <= {q2_v, q_v};
        {q3_x, q2_x} <= {q2_x, q_x};
        {q3_r, q2_r} <= {q2_r, q_r};
        {q3_sl, q2_sl} <= {q2_sl, q_sl};
        {q3_et, q2_et} <= {q2_et, q_et};
        {q3_el, q2_el} <= {q2_el, q_el};
        k_v <= q3_v;
        k_x <= q3_x;
        k_r <= q3_r;
        k_sl <= q3_sl;
        k_e <= {q3_el, q3_et};
        k_wt <= q3_et ? rnd(ah[7:0], n3_ht) : 8'd0;         // the pixel takes this much of the one above
        k_wu <= q3_et ? rnd(ah[15:8], n3_hu) : 8'd0;        // the one above this much of it
        k_wl <= q3_el ? rnd(av[7:0], n3_vl) : 8'd0;         // the pixel of the one to its left
        k_wo <= q3_el ? rnd(av[15:8], n3_vo) : 8'd0;        // the one to its left of it
        // the diagonals' (the table's {first, second}: the second diagonal's the other way round)
        dwr = (ga3 ? {1'b0, ada[15:8]} : 9'd0) + (gb3 ? {1'b0, adb[7:0]} : 9'd0);
        dwg = (ga3 ? {1'b0, ada[7:0]} : 9'd0) + (gb3 ? {1'b0, adb[15:8]} : 9'd0);
        if (q3_et && (dwr != 9'd0 || dwg != 9'd0)) begin
            k_wt <= dwr[8] ? 8'hFF : dwr[7:0];
            k_wu <= dwg[8] ? 8'hFF : dwg[7:0];
            k_wl <= 8'd0;
            k_wo <= 8'd0;
        end
    end

    // ---- mixing ----
    // each column's weights {top, left, of its left} of the line above; its pixels of the two lines
    // above the one the weights are of ({the nearer, the further})
    reg [25:0] cm [0:1023];
    reg [31:0] fm [0:1023];
    reg [25:0] c_r1;
    reg [31:0] f_r1;
    reg [25:0] c_q /* synthesis syn_preserve = 1 */;
    reg [31:0] f_q /* synthesis syn_preserve = 1 */;
    reg [15:0] p_d /* synthesis syn_preserve = 1 */;
    reg        b0_v = 1'b0, b1_v = 1'b0, b1_in;
    reg [10:0] b0_x, b1_x;
    reg [9:0]  b0_r, b1_r;
    reg [7:0]  b0_wt, b0_wu, b0_wl, b0_wo, b1_wt, b1_wu, b1_wl, b1_wo;
    reg [1:0]  b0_e, b1_e;
    always @* p_ra = {k_sl, k_x[9:0]};
    always @(posedge clk) begin
        c_r1 <= cm[k_x[9:0]];
        f_r1 <= fm[k_x[9:0]];
        c_q <= c_r1;
        f_q <= f_r1;
        p_d <= p_q;
        {b1_v, b0_v} <= {b0_v, k_v};
        b1_in <= b0_x < W;
        {b1_x, b0_x} <= {b0_x, k_x};
        {b1_r, b0_r} <= {b0_r, k_r};
        {b1_wt, b0_wt} <= {b0_wt, k_wt};
        {b1_wu, b0_wu} <= {b0_wu, k_wu};
        {b1_wl, b0_wl} <= {b0_wl, k_wl};
        {b1_wo, b0_wo} <= {b0_wo, k_wo};
        {b1_e, b0_e} <= {b0_e, k_e};
        if (b1_v && b1_in) begin
            cm[b1_x[9:0]] <= {b1_e, b1_wt, b1_wl, b1_wo};
            fm[b1_x[9:0]] <= {p_d, f_q[31:16]};
        end
    end
    // the column before: its pixel (the line above the weights'), the ones above and below, its
    // weights; the luma to its left
    reg [15:0] v_ctr, v_top, v_bot;
    reg [7:0]  v_at, v_al, v_ab, v_ly;
    reg [1:0]  v_e, n_e, m_e, m2_e, m3_e;
    reg [7:0]  m2_w, m3_w;
    reg        m_vert, m2_vert, m3_vert;
    reg        m_v = 1'b0, n_v = 1'b0;
    reg [10:0] n_x;
    reg [9:0]  n_b;
    reg [7:0]  n_w, n_ly, n_ry;
    reg [1:0]  n_sel;
    reg [15:0] n_ctr, n_top, n_bot;
    reg [10:0] m_x;
    reg [9:0]  m_b;
    reg [7:0]  m_w, m_y, m_c, m_ny, m_nc;
    wire [7:0] a_r = b1_in ? c_q[7:0] : 8'd0;
    // (the greatest of the four weights and whose it is, the first of equals: by the three
    // comparisons that find it, not by comparing it with each again)
    wire       tb_t = v_at >= v_ab, lr_l = v_al >= a_r;
    wire [7:0] best_tb = tb_t ? v_at : v_ab, best_lr = lr_l ? v_al : a_r;
    wire       tb_best = best_tb >= best_lr;
    wire [7:0] best = tb_best ? best_tb : best_lr;
    wire signed [17:0] py, pc;
    easu_mul #(.AW(9), .BW(9)) u_my (.clk(clk), .a($signed({1'b0, m_ny}) - $signed({1'b0, m_y})), .b({1'b0, m_w}), .p(py));
    easu_mul #(.AW(9), .BW(9)) u_mc (.clk(clk), .a($signed({1'b0, m_nc}) - $signed({1'b0, m_c})), .b({1'b0, m_w}), .p(pc));
    reg        m2_v = 1'b0, m3_v = 1'b0;
    reg [10:0] m2_x, m3_x;
    reg [9:0]  m2_b, m3_b;
    reg [7:0]  m2_y, m2_c, m3_y, m3_c;
    wire signed [17:0] ry = py + 18'sd128, rc_ = pc + 18'sd128;
    always @(posedge clk) begin
        n_v <= 1'b0;
        if (b1_v) begin
            v_ctr <= f_q[31:16];
            v_top <= f_q[15:0];
            v_bot <= p_d;
            v_at <= c_q[23:16];
            v_al <= c_q[15:8];
            v_e <= c_q[25:24];
            v_ab <= b1_wu;
            v_ly <= v_ctr[15:8];
            // the pixel before this column's: which neighbour, how much
            n_v <= b1_x != 11'd0 && b1_x <= W && b1_r != 10'd0 && b1_r <= h + 10'd1;
            n_x <= b1_x - 11'd1;
            n_b <= b1_r - 10'd1;
            n_w <= best;
            n_e <= v_e;
            n_sel <= tb_best ? (tb_t ? 2'd0 : 2'd1) : (lr_l ? 2'd2 : 2'd3);
            n_ctr <= v_ctr;
            n_top <= v_top;
            n_bot <= v_bot;
            n_ly <= v_ly;
            n_ry <= f_q[31:24];
        end
        // (a clock later) the neighbour itself
        m_v <= n_v;
        m_x <= n_x;
        m_b <= n_b;
        m_w <= n_w;
        m_e <= n_e;
        m_vert <= !n_sel[1];
        m_y <= n_ctr[15:8];
        m_c <= n_ctr[7:0];
        m_ny <= n_sel == 2'd0 ? n_top[15:8] : n_sel == 2'd1 ? n_bot[15:8] : n_sel == 2'd2 ? n_ly : n_ry;
        m_nc <= n_sel == 2'd0 ? n_top[7:0] : n_sel == 2'd1 ? n_bot[7:0] : n_ctr[7:0];
        m2_v <= m_v;
        m2_x <= m_x;
        m2_b <= m_b;
        m2_y <= m_y;
        {m3_e, m2_e} <= {m2_e, m_e};
        {m3_w, m2_w} <= {m2_w, m_w};
        {m3_vert, m2_vert} <= {m2_vert, m_vert};
        m2_c <= m_c;
        m3_v <= m2_v;
        m3_x <= m2_x;
        m3_b <= m2_b;
        m3_y <= m2_y;
        m3_c <= m2_c;
        o_v <= m3_v;
        o_x <= m3_x[9:0];
        o_j <= m3_b;
        o_last <= m3_x == W - 1;
        o_y <= m3_y + ry[15:8];
        o_c <= m3_c + rc_[15:8];
        if (dbg) begin
            if (m3_w != 8'd0) begin
                o_y <= 8'd128 + m3_w[7:1];
                o_c <= m3_vert == !m3_x[0] ? 8'd224 : 8'd96;        // (Cb the even pixels': blue up and down, red sideways)
            end else if (m3_e != 2'd0) begin
                o_y <= 8'd110;
                o_c <= 8'd64;
            end else begin
                o_y <= m3_y < 8'd16 ? 8'd16 : 8'd16 + {2'b00, m3_y[7:2]} - 8'd4;
                o_c <= 8'd128;
            end
        end
    end
endmodule
