// deint_edi.v: the deinterlacer's edge search (deint.v edi; sim/model.py edge_line(), edge_dirs()):
// a line made between the line above (A) and the line below (B) along the picture's edges: each
// pixel the mean of A at x + d and B at x - d, d of -8 to 8, held between the pixels straight
// above and below.  A direction d is one only where
//   - there is a step to bridge: |A[x] - B[x]| >= T1
//   - its two ends are alike over five columns: c = the sum over k of -2 to 2 of
//     |A[x + k + d] - B[x + k - d]| is under a third of straight down's (the same sum at d = 0)
//   - the edge goes on through the field's next lines out (A2 above A, B2 below B):
//     e = the sum over the five columns of |A2[x + k + 3 d] - A[x + k + d]| +
//     |B2[x + k - 3 d] - B[x + k - d]| is under E
//   - its own two pixels differ by a quarter of the step at most
// and the least 2 c + e + 2 |d| wins (the first of equals in the order -1, 1, -2, 2, ...); then the
// pixels beside must agree: a direction more than 1 from the median of the five about it is
// dropped.  The 26 pixels at each side of a line: straight down (the search reaches that far).
// The chroma goes the way of its pair's first pixel, half as far.
//
// In: a line's words (a pair of pixels: {Cb, Y0, Cr, Y1}) of the four lines, a clock each, in
// order (v_i, q_i the pair's number; between lines: anything, v_i low).  Out: bob: the pair's word
// made, LAT clocks after its words came in.  All the registers that move on are plain vectors
// (arrays of registers written by parts were built wrongly by the synthesis: sim/edi_synth_tb.py
// tests what it makes of this file).
//
// The stages (a word in at clock 0):
//   13      the columns' differences (for the two columns of the word that came 13 clocks ago: the
//           lines' words 12 before and after it are all there)
//   15..18  a pair's sums over five columns (the columns of three words), in two clocks; e, the
//           tests; the scores
//   19..22  the least of sixteen, a comparison a stage
//   24      the pixels beside agree
//   25..27  the pixels along the direction; their mean; held
// (all registers: the synthesis would make block RAMs of the ones that only move on)

module deint_edi #(
    parameter T1 = 24,
    parameter E = 60
) (
    input             clk,
    input             en,
    input      [9:0]  nw,               // a line's words
    input             v_i,
    input      [9:0]  q_i,
    input      [31:0] a2_i,
    input      [31:0] a_i,
    input      [31:0] b_i,
    input      [31:0] b2_i,
    output reg [31:0] bob
) /* synthesis syn_srlstyle = "registers" */;     // (no block RAM for what only moves on)
    localparam LAT = 28;

    function [7:0] absd(input [7:0] a, input [7:0] b);
        absd = a > b ? a - b : b - a;
    endfunction
    function [7:0] mean(input [7:0] a, input [7:0] b);
        reg [8:0] t;
        begin
            t = {1'b0, a} + {1'b0, b} + 9'd1;
            mean = t[8:1];
        end
    endfunction
    function [7:0] hold8(input [7:0] v, input [7:0] a, input [7:0] b);
        hold8 = v < (a < b ? a : b) ? (a < b ? a : b) : v > (a < b ? b : a) ? (a < b ? b : a) : v;
    endfunction

    // ---- the lines' pixels as they come: luma, a pixel 8 bits, the oldest at 0 ----
    // A2, B2: the words 0 to 25 clocks old (52 pixels); A, B: 0 to 29 (60 pixels); the chroma of A
    // and B: {Cb, Cr} a word, 0 to 29 clocks old
    reg [415:0] la2 = 0 /* synthesis syn_srlstyle = "registers" */;
    reg [415:0] lb2 = 0 /* synthesis syn_srlstyle = "registers" */;
    reg [479:0] la = 0 /* synthesis syn_srlstyle = "registers" */;
    reg [479:0] lb = 0 /* synthesis syn_srlstyle = "registers" */;
    reg [479:0] ka = 0 /* synthesis syn_srlstyle = "registers" */;
    reg [479:0] kb = 0 /* synthesis syn_srlstyle = "registers" */;
    // {valid, the pair's number} of the words 0 to 18 clocks old (the oldest at 0)
    reg [208:0] tok = 0 /* synthesis syn_preserve = 1 */;       // (its own: not the same registers as deint.v's, far away)
    always @(posedge clk) begin
        la2 <= {a2_i[7:0], a2_i[23:16], la2[415:16]};
        lb2 <= {b2_i[7:0], b2_i[23:16], lb2[415:16]};
        la <= {a_i[7:0], a_i[23:16], la[479:16]};
        lb <= {b_i[7:0], b_i[23:16], lb[479:16]};
        ka <= {a_i[31:24], a_i[15:8], ka[479:16]};
        kb <= {b_i[31:24], b_i[15:8], kb[479:16]};
        tok <= {v_i, q_i, tok[208:11]};
    end
    // (the word 13 clocks old: its pixels are 24, 25 of A2 and B2's 52, and 32, 33 of A and B's 60;
    // the word 25 clocks old: pixels 8, 9 of A and B, word 4 of the chroma's 30)

    // ---- stage 13 -> 14: the columns' differences: column h (0, 1) of the word 13 clocks old ----
    // c1: |A[x + d] - B[x - d]| for d of -8 to 8, at 8 (2 (d + 8) + h)
    // ea1, eb1: |A2[x + 3 d] - A[x + d]|, |B2[x - 3 d] - B[x - d]| for d of -8 to 8 but 0: at
    // 8 (2 i + h), i the direction's place in the order tried (-1, 1, -2, 2, ...: 2 (|d| - 1), and
    // 1 more for d over 0); c1's too could be, but straight down is among them
    reg [271:0] c1;
    reg [271:0] c1p /* synthesis syn_srlstyle = "registers" */;
    reg [271:0] c1pp /* synthesis syn_srlstyle = "registers" */;
    reg [255:0] ea1, eb1;
    reg [255:0] ea1p /* synthesis syn_srlstyle = "registers" */;
    reg [255:0] ea1pp /* synthesis syn_srlstyle = "registers" */;
    reg [255:0] eb1p /* synthesis syn_srlstyle = "registers" */;
    reg [255:0] eb1pp /* synthesis syn_srlstyle = "registers" */;
    integer d, h, i;
    always @(posedge clk) begin
        for (d = -8; d <= 8; d = d + 1)
            for (h = 0; h < 2; h = h + 1) begin
                c1[8 * (2 * (d + 8) + h) +: 8] <= absd(la[8 * (32 + h + d) +: 8], lb[8 * (32 + h - d) +: 8]);
                if (d != 0) begin
                    i = d < 0 ? 2 * (-d - 1) : 2 * (d - 1) + 1;
                    ea1[8 * (2 * i + h) +: 8] <= absd(la2[8 * (24 + h + 3 * d) +: 8], la[8 * (32 + h + d) +: 8]);
                    eb1[8 * (2 * i + h) +: 8] <= absd(lb2[8 * (24 + h - 3 * d) +: 8], lb[8 * (32 + h - d) +: 8]);
                end
            end
        c1p <= c1;
        c1pp <= c1p;
        ea1p <= ea1;
        ea1pp <= ea1p;
        eb1p <= eb1;
        eb1pp <= eb1p;
    end

    // ---- 15 -> 17: a pair's sums, in two clocks: its pixel t's five columns are in the words before it
    // (c1pp), its own (c1p) and the one after (c1): for t 0 both of the first, both of its own, the
    // first of the third; for t 1 the second of the first, both of its own, both of the third.
    // First (h: 10 bits): its own word's two columns and, for t 0, the first word's two; for t 1 the
    // third word's two; the fifth column kept beside (r) ----
    // sc: at 11 (17 t + d + 8); sea, seb: at 11 (16 t + i); pr: the pixel's own |A[x + d] -
    // B[x - d]|, at 8 (17 t + d + 8) (d = 0: the step)
    reg [373:0] sc;
    reg [351:0] sea, seb;
    reg [271:0] pr, pr0;
    reg [339:0] hc;                     // 10 (17 t + d + 8): four columns' sum
    reg [271:0] rc;                     // 8 (17 t + d + 8): the fifth
    reg [319:0] hea, heb;               // 10 (16 t + i)
    reg [255:0] rea, reb;
    function [9:0] sum4(input [7:0] a, input [7:0] b, input [7:0] c, input [7:0] dd);
        sum4 = {2'd0, a} + {2'd0, b} + {2'd0, c} + {2'd0, dd};
    endfunction
    integer d2, i2;
    always @(posedge clk) begin
        for (d2 = -8; d2 <= 8; d2 = d2 + 1) begin
            hc[10 * (d2 + 8) +: 10] <= sum4(c1pp[8 * (2 * (d2 + 8)) +: 8], c1pp[8 * (2 * (d2 + 8) + 1) +: 8], c1p[8 * (2 * (d2 + 8)) +: 8],
                                            c1p[8 * (2 * (d2 + 8) + 1) +: 8]);
            rc[8 * (d2 + 8) +: 8] <= c1[8 * (2 * (d2 + 8)) +: 8];
            hc[10 * (17 + d2 + 8) +: 10] <= sum4(c1p[8 * (2 * (d2 + 8)) +: 8], c1p[8 * (2 * (d2 + 8) + 1) +: 8], c1[8 * (2 * (d2 + 8)) +: 8],
                                                 c1[8 * (2 * (d2 + 8) + 1) +: 8]);
            rc[8 * (17 + d2 + 8) +: 8] <= c1pp[8 * (2 * (d2 + 8) + 1) +: 8];
            pr0[8 * (d2 + 8) +: 8] <= c1p[8 * (2 * (d2 + 8)) +: 8];
            pr0[8 * (17 + d2 + 8) +: 8] <= c1p[8 * (2 * (d2 + 8) + 1) +: 8];
            sc[11 * (d2 + 8) +: 11] <= {1'b0, hc[10 * (d2 + 8) +: 10]} + {3'd0, rc[8 * (d2 + 8) +: 8]};
            sc[11 * (17 + d2 + 8) +: 11] <= {1'b0, hc[10 * (17 + d2 + 8) +: 10]} + {3'd0, rc[8 * (17 + d2 + 8) +: 8]};
        end
        pr <= pr0;
        for (i2 = 0; i2 < 16; i2 = i2 + 1) begin
            hea[10 * i2 +: 10] <= sum4(ea1pp[8 * (2 * i2) +: 8], ea1pp[8 * (2 * i2 + 1) +: 8], ea1p[8 * (2 * i2) +: 8], ea1p[8 * (2 * i2 + 1) +: 8]);
            rea[8 * i2 +: 8] <= ea1[8 * (2 * i2) +: 8];
            hea[10 * (16 + i2) +: 10] <= sum4(ea1p[8 * (2 * i2) +: 8], ea1p[8 * (2 * i2 + 1) +: 8], ea1[8 * (2 * i2) +: 8], ea1[8 * (2 * i2 + 1) +: 8]);
            rea[8 * (16 + i2) +: 8] <= ea1pp[8 * (2 * i2 + 1) +: 8];
            heb[10 * i2 +: 10] <= sum4(eb1pp[8 * (2 * i2) +: 8], eb1pp[8 * (2 * i2 + 1) +: 8], eb1p[8 * (2 * i2) +: 8], eb1p[8 * (2 * i2 + 1) +: 8]);
            reb[8 * i2 +: 8] <= eb1[8 * (2 * i2) +: 8];
            heb[10 * (16 + i2) +: 10] <= sum4(eb1p[8 * (2 * i2) +: 8], eb1p[8 * (2 * i2 + 1) +: 8], eb1[8 * (2 * i2) +: 8], eb1[8 * (2 * i2 + 1) +: 8]);
            reb[8 * (16 + i2) +: 8] <= eb1pp[8 * (2 * i2 + 1) +: 8];
            sea[11 * i2 +: 11] <= {1'b0, hea[10 * i2 +: 10]} + {3'd0, rea[8 * i2 +: 8]};
            sea[11 * (16 + i2) +: 11] <= {1'b0, hea[10 * (16 + i2) +: 10]} + {3'd0, rea[8 * (16 + i2) +: 8]};
            seb[11 * i2 +: 11] <= {1'b0, heb[10 * i2 +: 10]} + {3'd0, reb[8 * i2 +: 8]};
            seb[11 * (16 + i2) +: 11] <= {1'b0, heb[10 * (16 + i2) +: 10]} + {3'd0, reb[8 * (16 + i2) +: 8]};
        end
    end

    // ---- 17 -> 18: e; the tests that are sums against sums: a third of straight down's, a quarter of
    // the step, the step itself ----
    // (by the order tried: i; its d: -(i / 2 + 1) for i even, i / 2 + 1 for i odd)
    reg [383:0] e3;                     // 12 (16 t + i)
    reg [351:0] c3;                     // 11 (16 t + i)
    reg [31:0]  ok3;
    reg [12:0]  t_c3;
    reg [10:0]  t_c, t_c0;
    reg [7:0]   t_p, t_v;
    integer d3, i3, t3;
    always @(posedge clk)
        for (t3 = 0; t3 < 2; t3 = t3 + 1)
            for (i3 = 0; i3 < 16; i3 = i3 + 1) begin
                d3 = i3 % 2 ? i3 / 2 + 1 : -(i3 / 2 + 1);
                t_c = sc[11 * (17 * t3 + d3 + 8) +: 11];
                t_c0 = sc[11 * (17 * t3 + 8) +: 11];
                t_p = pr[8 * (17 * t3 + d3 + 8) +: 8];
                t_v = pr[8 * (17 * t3 + 8) +: 8];
                t_c3 = {2'd0, t_c} + {1'b0, t_c, 1'b0};
                e3[12 * (16 * t3 + i3) +: 12] <= {1'b0, sea[11 * (16 * t3 + i3) +: 11]} + {1'b0, seb[11 * (16 * t3 + i3) +: 11]};
                c3[11 * (16 * t3 + i3) +: 11] <= t_c;
                ok3[16 * t3 + i3] <= t_c3 < {2'd0, t_c0} && {t_p, 2'b00} <= {2'd0, t_v} && t_v >= T1;
            end

    // ---- 18 -> 19: the candidates: {it is one, its score 2 c + e + 2 |d|, its place in the order} ----
    wire        tv17 = tok[11 * 0 + 10];                // (the token 18 clocks old: the oldest kept)
    wire [9:0]  tq17 = tok[9:0];
    wire        side = tq17 < 10'd13 || tq17 + 10'd13 >= nw;
    reg [575:0] cnd;                    // 18 (16 t + i)
    reg [13:0]  t_s;
    integer i4, t4;
    always @(posedge clk)
        for (t4 = 0; t4 < 2; t4 = t4 + 1)
            for (i4 = 0; i4 < 16; i4 = i4 + 1) begin
                t_s = {2'd0, c3[11 * (16 * t4 + i4) +: 11], 1'b0} + {2'd0, e3[12 * (16 * t4 + i4) +: 12]} + 2 * (i4 / 2 + 1);
                cnd[18 * (16 * t4 + i4) +: 18] <= {ok3[16 * t4 + i4] && e3[12 * (16 * t4 + i4) +: 12] < E && en && tv17 && !side, t_s[12:0],
                                                   i4[3:0]};
            end

    // ---- 19 -> 23: the least of sixteen: of two, the later only if it is one and (the earlier is not,
    // or its score is less) ----
    function [17:0] least(input [17:0] x, input [17:0] y);
        least = y[17] && (!x[17] || y[16:4] < x[16:4]) ? y : x;
    endfunction
    reg [287:0] l1;                     // 18 (8 t + n)
    reg [143:0] l2;
    reg [71:0]  l3;
    reg [35:0]  l4;
    integer j5, t5;
    always @(posedge clk)
        for (t5 = 0; t5 < 2; t5 = t5 + 1) begin
            for (j5 = 0; j5 < 8; j5 = j5 + 1)
                l1[18 * (8 * t5 + j5) +: 18] <= least(cnd[18 * (16 * t5 + 2 * j5) +: 18], cnd[18 * (16 * t5 + 2 * j5 + 1) +: 18]);
            for (j5 = 0; j5 < 4; j5 = j5 + 1)
                l2[18 * (4 * t5 + j5) +: 18] <= least(l1[18 * (8 * t5 + 2 * j5) +: 18], l1[18 * (8 * t5 + 2 * j5 + 1) +: 18]);
            for (j5 = 0; j5 < 2; j5 = j5 + 1)
                l3[18 * (2 * t5 + j5) +: 18] <= least(l2[18 * (4 * t5 + 2 * j5) +: 18], l2[18 * (4 * t5 + 2 * j5 + 1) +: 18]);
            l4[18 * t5 +: 18] <= least(l3[18 * (2 * t5) +: 18], l3[18 * (2 * t5 + 1) +: 18]);
        end
    // the direction, 5 bits signed (0: none)
    function signed [4:0] dof(input [17:0] x);
        dof = !x[17] ? 5'sd0 : x[0] ? $signed({2'b00, x[3:1]}) + 5'sd1 : -($signed({2'b00, x[3:1]}) + 5'sd1);
    endfunction

    // ---- 23 -> 25: the pixels beside agree: of the four beside a pixel, two at least are its d - 1 or
    // more, and two at least its d + 1 or less (the median of the five is then within 1 of it) ----
    wire signed [4:0] dn0 = dof(l4[17:0]), dn1 = dof(l4[35:18]);       // the pair after
    reg signed [4:0]  dc0 = 0, dc1 = 0, dp0 = 0, dp1 = 0;               // the pair itself, the one before
    reg signed [4:0]  df0 = 0, df1 = 0;                                 // what is kept
    function agree(input signed [4:0] dd, input signed [4:0] a, input signed [4:0] b, input signed [4:0] c, input signed [4:0] e);
        reg signed [5:0] lo, hi;
        reg [2:0] n_lo, n_hi;
        begin
            lo = dd - 6'sd1;
            hi = dd + 6'sd1;
            n_lo = (a >= lo) + (b >= lo) + (c >= lo) + (e >= lo);
            n_hi = (a <= hi) + (b <= hi) + (c <= hi) + (e <= hi);
            agree = n_lo >= 3'd2 && n_hi >= 3'd2;
        end
    endfunction
    always @(posedge clk) begin
        dc0 <= dn0;
        dc1 <= dn1;
        dp0 <= dc0;
        dp1 <= dc1;
        df0 <= agree(dc0, dp0, dp1, dc1, dn0) ? dc0 : 5'sd0;
        df1 <= agree(dc1, dp1, dc0, dn0, dn1) ? dc1 : 5'sd0;
    end

    // ---- 25 -> 28: the pixels along the direction (the pair's word is 25 clocks old: pixels 8, 9 of A
    // and B; its chroma word 4), and straight above and below; their mean; held ----
    reg [63:0]  fy;                     // pixel t: {A along, B along, A, B}
    reg [63:0]  fc;                     // Cb, then Cr: the same four
    reg [63:0]  my, mc;
    // (the places as plain numbers from 0: no signed number in an index)
    reg [4:0]   t_d, t_ia, t_ib;
    reg [4:0]   t_m;
    reg [3:0]   t_q, t_ca, t_cb;
    integer     t6;
    always @(posedge clk) begin
        for (t6 = 0; t6 < 2; t6 = t6 + 1) begin
            t_d = t6 ? df1 : df0;
            t_ia = 5'd8 + t6 + t_d;
            t_ib = 5'd8 + t6 - t_d;
            fy[32 * t6 +: 32] <= {la[8 * t_ia +: 8], lb[8 * t_ib +: 8], la[8 * (8 + t6) +: 8], lb[8 * (8 + t6) +: 8]};
            my[32 * t6 +: 32] <= {mean(fy[32 * t6 + 24 +: 8], fy[32 * t6 + 16 +: 8]), 8'd0, fy[32 * t6 +: 16]};
        end
        // (half as far, towards straight down: t_q its 4 bits, two's complement)
        t_m = -df0;
        t_q = df0[4] ? -{1'b0, t_m[3:1]} : {1'b0, df0[3:1]};
        t_ca = 4'd4 + t_q;
        t_cb = 4'd4 - t_q;
        for (t6 = 0; t6 < 2; t6 = t6 + 1) begin     // (0: Cb, the words' upper byte; 1: Cr)
            fc[32 * t6 +: 32] <= {ka[16 * t_ca + 8 * (1 - t6) +: 8], kb[16 * t_cb + 8 * (1 - t6) +: 8],
                                  ka[16 * 4 + 8 * (1 - t6) +: 8], kb[16 * 4 + 8 * (1 - t6) +: 8]};
            mc[32 * t6 +: 32] <= {mean(fc[32 * t6 + 24 +: 8], fc[32 * t6 + 16 +: 8]), 8'd0, fc[32 * t6 +: 16]};
        end
        bob <= {hold8(mc[31:24], mc[15:8], mc[7:0]), hold8(my[31:24], my[15:8], my[7:0]),
                hold8(mc[63:56], mc[47:40], mc[39:32]), hold8(my[63:56], my[47:40], my[39:32])};
    end
endmodule
