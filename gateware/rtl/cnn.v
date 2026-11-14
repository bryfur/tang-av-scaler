// cnn.v: a small network that makes the picture's luma twice the size (docs/cnn-upscaler.md; the
// arithmetic is sim/cnn_ref.py's): three layers of 3 x 3, 1 -> 8 -> 8 -> 4 channels, the last one's
// four the 2 x 2 output pixels of a source pixel, added to the plain two-tap stretch.  It is the
// scaler's first stage when it is on: bicu.v stretches its picture to the output.
//
// On the output's clock, a line at a time (a pass): pass n makes the lines 2n and 2n + 1 of the
// picture at twice the size from the source's lines n - 1 to n + 3, read from easu.v's ring (five of
// its eight lines at once), a pixel every six clocks, so that a multiplier does six products a pixel:
//   layer 1 three times over (the lines n, n + 1, n + 2: it is small, and no line of it is kept):
//           3 x 8 sums of 9 products, two multipliers each
//   layer 2 (the line n + 1): 8 sums of 72, twelve multipliers each; its lines n - 1 and n are kept
//           (two lines of 8 channels in block RAM)
//   layer 3 (the line n): 4 sums of 72
// 192 multipliers of 9 x 8 bits.  At the picture's edges each layer's input is repeated (first, last:
// the lines the picture is taken to have; the columns 0 and W - 1).  A pass can be told to write
// nothing (quiet): the first ones of a frame, which are there for layer 2's lines (the pass first - 1
// at the picture's top; two passes where the frame's passes begin lower down).
//
// A pass's clocks: the period P (six clocks, k = 0 to 5) and what is where:
//   P = a          the source's column min(a, W - 1) (asked in the period before), in the window from k 5
//   P = x + 4      layer 1's column x out (k 1), in layer 2's window from k 2
//   P = x + 7      layer 2's column x out (k 4), in layer 3's window from k 5; written to its line
//   P = x + 11     layer 3's column x out (k 1); the four pixels written k 2 to 5
// and a column more at each window's end (the last again).  W + 12 periods a pass, with the one before the
// first.
//
// The weights: LUT RAM (a multiplier's six, a byte each), as the build's model has them (cnn_init.vh,
// on the include path: sim/model.py net_init()), and written through the port (l_*) between passes, so another
// network of this shape can be put in while the picture runs.  l_a: 0 to 1279 the multipliers'
// weights (multiplier g's phase p at 8 g + p: g = 2 co + m in layer 1, 16 + 12 co + j in layer 2, 112 +
// 12 co + j in layer 3); 2048 + co' a sum's first value (the bias, and half of what the shift drops:
// 22 bits, co' = 0 to 7, 8 to 15, 16 to 19); 2304 + l layer l's shift.

// a sum of products over a pixel's six clocks: NM multipliers (their operands and weights come
// registered, the same clock; ph0 with them: the first of the six), then the sum's first value added
// in; s: the sum, whole, 13 clocks after the first operands (acc), and through the shift and the
// limits a clock after that
module cnn_sum #(
    parameter NM = 12
) (
    input                       clk,
    input      [8 * NM - 1:0]   a,      // 0..255 each
    input      [8 * NM - 1:0]   w,      // signed
    input                       ph0,
    input      signed [21:0]    b,
    input      [3:0]            sh,
    // (both there in the fourteenth clock after the first operands, for that clock: the sum goes on)
    output reg [7:0]            q,      // limited to 0..255
    output reg signed [14:0]    r       // signed (the last layer's)
) /* synthesis syn_srlstyle = "registers" */;
    wire signed [16:0] p [0:NM - 1];
    genvar g;
    generate
        for (g = 0; g < NM; g = g + 1) begin : g_m
            easu_mul #(.AW(9), .BW(8)) u (.clk(clk), .a({1'b0, a[8 * g +: 8]}), .b(w[8 * g +: 8]), .p(p[g]));
        end
    endgenerate
    // the products in pairs, the pairs in pairs (the multipliers' blocks take these two steps into
    // themselves, each pair of blocks one value); then a running sum of each of the three over the
    // pixel's six clocks, beside its blocks (they lie apart: one long net and one sum a clock); the
    // three and the first value put together when they are whole; the shift; the limits
    reg signed [17:0] s1 [0:5];
    reg signed [18:0] s2 [0:2];
    reg signed [21:0] ac [0:2];
    reg signed [21:0] tot;
    reg signed [21:0] sft;
    reg signed [21:0] br /* synthesis syn_preserve = 1 */;      // (the first value and the shift: their own registers here)
    reg [3:0]  shr /* synthesis syn_preserve = 1 */;
    reg [3:0]  f0 /* synthesis syn_preserve = 1 */ = 4'd0;       // (each sum its own)
    integer i;
    always @(posedge clk) begin
        br <= b;
        shr <= sh;
        f0 <= {f0[2:0], ph0};
        for (i = 0; i < 6; i = i + 1)
            s1[i] <= (2 * i < NM ? p[2 * i < NM ? 2 * i : 0] : 17'sd0) + (2 * i + 1 < NM ? p[2 * i + 1 < NM ? 2 * i + 1 : 0] : 17'sd0);
        for (i = 0; i < 3; i = i + 1) begin
            s2[i] <= s1[2 * i] + s1[2 * i + 1];
            ac[i] <= f0[3] ? s2[i] : ac[i] + s2[i];         // (all signed: the pair's sum with its sign)
        end
        tot <= ac[0] + ac[1] + ac[2] + br;
        sft <= tot >>> shr;
        q <= sft < 0 ? 8'd0 : sft > 22'sd255 ? 8'd255 : sft[7:0];
        r <= sft[14:0];
    end
endmodule

// a multiplier's six weights: a LUT RAM of sixteen bytes (two RAM16SDP4), read by the phase, written
// through the port
module cnn_w #(
    parameter [47:0] INIT = 48'd0
) (
    input        clk,
    input        we,
    input  [2:0] wa,
    input  [7:0] wd,
    input  [2:0] ra,
    output [7:0] q
);
`ifdef AVB_GOWIN
    genvar b;
    generate
        for (b = 0; b < 2; b = b + 1) begin : g_h
            // (INIT_n: the bit 4 b + n of each byte, the byte a's at a)
            RAM16SDP4 #(.INIT_0({10'd0, INIT[40 + 4 * b], INIT[32 + 4 * b], INIT[24 + 4 * b], INIT[16 + 4 * b], INIT[8 + 4 * b], INIT[4 * b]}),
                        .INIT_1({10'd0, INIT[41 + 4 * b], INIT[33 + 4 * b], INIT[25 + 4 * b], INIT[17 + 4 * b], INIT[9 + 4 * b], INIT[1 + 4 * b]}),
                        .INIT_2({10'd0, INIT[42 + 4 * b], INIT[34 + 4 * b], INIT[26 + 4 * b], INIT[18 + 4 * b], INIT[10 + 4 * b], INIT[2 + 4 * b]}),
                        .INIT_3({10'd0, INIT[43 + 4 * b], INIT[35 + 4 * b], INIT[27 + 4 * b], INIT[19 + 4 * b], INIT[11 + 4 * b], INIT[3 + 4 * b]}))
                u (.DO(q[4 * b +: 4]), .DI(wd[4 * b +: 4]), .WAD({1'b0, wa}), .RAD({1'b0, ra}), .WRE(we), .CLK(clk));
        end
    endgenerate
`else
    reg [7:0] m [0:7];
    integer i;
    initial
        for (i = 0; i < 8; i = i + 1)
            m[i] = i < 6 ? INIT[8 * i +: 8] : 8'd0;
    always @(posedge clk)
        if (we)
            m[wa] <= wd;
    assign q = m[ra];
`endif
endmodule

module cnn #(
    parameter W = 720
) (
    input              clk,
    // a pass asked for (go, a clock; n: its line, from first - 1; busy until it is done)
    input              go,
    input signed [10:0] n,
    input              quiet,           // this pass writes nothing (it is there for layer 2's line)
    input      [9:0]   first,
    input      [9:0]   last,
    output reg         busy = 1'b0,
    output             rdy,             // a pass may be asked (none goes on, and no weight is being written)
    // the source: five lines of easu.v's ring (the lines' numbers; the column; easu.v's n_rows: their
    // lumas and the second's chroma, four clocks after s_col)
    output reg [9:0]   s_col,
    output     [49:0]  s_line,          // the five lines' numbers (the ring's slot: the low three bits)
    input      [55:0]  s_r,
    // the picture at twice the size, a pixel a clock in pairs of lines (bicu.v's ring)
    output reg         o_we = 1'b0,
    output reg [10:0]  o_line,
    output reg [10:0]  o_col,
    output reg [7:0]   o_d,
    // the line n's chroma as it is ({cb, cr}: bicu.v's other ring)
    output reg         c_we = 1'b0,
    output reg [9:0]   c_line,
    output reg [9:0]   c_col,
    output reg [15:0]  c_d,
    // the weights' port (taken between passes)
    input              l_req,
    input      [11:0]  l_a,
    input      [21:0]  l_d,
    output reg         l_ack = 1'b0
) /* synthesis syn_srlstyle = "registers" syn_romstyle = "logic" */;      // (the delays here are registers, the port's decode logic: the synthesis would make block RAM of both)
    `include "cnn_init.vh"

    // ---- the pass: its periods and their clocks ----
    reg [2:0]  k = 3'd0;
    reg [9:0]  pp = 10'd0;
    reg signed [10:0] nn;
    reg        prime = 1'b0;            // (the pass writes nothing)
    wire       k5 = k == 3'd5;
    always @(posedge clk) begin
        if (go && !busy) begin
            busy <= 1'b1;
            nn <= n;
            prime <= quiet;
            k <= 3'd0;
            pp <= 10'd1023;             // (a period before the first: the first column is asked in it)
        end else if (busy) begin
            k <= k5 ? 3'd0 : k + 3'd1;
            if (k5) begin
                pp <= pp + 10'd1;
                if (pp == W + 10)
                    busy <= 1'b0;
            end
        end
    end
    // the lines: n - 1 to n + 3, held between first and last
    function [9:0] lim(input signed [11:0] v);
        lim = v < $signed({2'b00, first}) ? first : v > $signed({2'b00, last}) ? last : v[9:0];
    endfunction
    reg [9:0]  ln [0:4];
    reg signed [11:0] lu [0:4];
    reg        top_a, bot_c, bot_b, top_3;
    integer    i, j, c;
    always @(posedge clk) begin
        for (i = 0; i < 5; i = i + 1) begin
            lu[i] <= $signed({nn[10], nn}) + i - 1;
            ln[i] <= lim(lu[i]);
        end
        top_a <= nn < $signed({1'b0, first});                    // layer 1's line n is above the picture: line n + 1's
        bot_c <= nn + 11'sd2 > $signed({1'b0, last});            // its line n + 2 below it: line n + 1's
        bot_b <= nn + 11'sd1 > $signed({1'b0, last});            // layer 2's line n + 1 below it: line n's
        top_3 <= nn - 11'sd1 < $signed({1'b0, first});           // layer 2's line n - 1 above it: line n's
    end
    assign s_line = {ln[4], ln[3], ln[2], ln[1], ln[0]};

    // ---- the source's window: five lines of three columns ----
    reg [7:0]  sw [0:14];               // [3 line + column]: column 2 the newest
    reg [7:0]  sy [0:4];
    reg [15:0] sc;
    reg        swe = 1'b0;              // (the windows' enables: registers of their own, one beside each word)
    reg [8:0]  v2e /* synthesis syn_preserve = 1 */ = 9'd0;
    reg [8:0]  v3e /* synthesis syn_preserve = 1 */ = 9'd0;
    wire [9:0] pn = pp + 10'd1;
    // (what the period's number says, in registers from the period's second clock on: nothing takes
    // them in its first)
    reg        s_in = 1'b0, pp_0 = 1'b0;                        // a column comes in this period; the first
    reg        v2_in = 1'b0, pp_4 = 1'b0;                       // layer 2's window takes a column; its first
    reg        v3_in = 1'b0, pp_7 = 1'b0, v3_dup = 1'b0;        // layer 3's; its first; its last again
    reg        o_in = 1'b0, c_in = 1'b0, m_in = 1'b0;
    always @(posedge clk) begin
        s_in <= pp <= W;
        pp_0 <= pp == 10'd0;
        v2_in <= pp >= 10'd4 && pp <= W + 4;
        pp_4 <= pp == 10'd4;
        v3_in <= pp >= 10'd7 && pp <= W + 7;
        pp_7 <= pp == 10'd7;
        v3_dup <= pp == W + 7;
        o_in <= pp >= 10'd11 && pp <= W + 10 && !prime;
        c_in <= pp < W && !prime;
        m_in <= pp >= 10'd7 && pp < W + 7;
    end
    always @(posedge clk) begin
        // (asked in the period before: its k 4; then k 5 the column, 0 the ring's address, 1 its RAM, 2 its
        // words, 3 the five chosen (easu.v), 4 their lumas and the line n's chroma here, and the window
        // at the end of that)
        if (busy && k == 3'd4)
            s_col <= pn >= W ? W - 1 : pn;
        for (i = 0; i < 5; i = i + 1)
            sy[i] <= s_r[8 * i +: 8];
        sc <= s_r[55:40];
        swe <= busy && k == 3'd3 && s_in;
        if (swe)
            for (i = 0; i < 5; i = i + 1) begin
                sw[3 * i + 2] <= sy[i];
                sw[3 * i + 1] <= pp_0 ? sy[i] : sw[3 * i + 2];
                sw[3 * i] <= sw[3 * i + 1];
            end
        c_we <= busy && k == 3'd4 && c_in;
        c_line <= ln[1];
        c_col <= pp;
        c_d <= sc;
    end

    // ---- the weights: a multiplier's six bytes in a LUT RAM, read by its sum's own phase ----
    // (each sum, and each layer's operands, has a phase counter of its own beside it: 0 in the clock
    // the layer's window is new in (layer 1: k 5; 2: k 2; 3: k 5), so 1, 4, 1 as a pass begins)
    // the port: a value taken when no pass goes on, written two clocks later (hd: nothing begun meanwhile)
    reg [2:0]  l_s = 3'd0;
    reg [3:0]  hd = 4'd0;
    wire       l_take = l_s[2] != l_ack && !busy && !go && hd == 4'd0;
    reg        ld0 = 1'b0;
    reg [11:0] la0;
    reg [21:0] ldd0, ldd1;
    assign rdy = !busy && hd == 4'd0 && !l_take;
    always @(posedge clk) begin
        l_s <= {l_s[1:0], l_req};
        if (l_take)
            l_ack <= l_s[2];
        hd <= {hd[2:0], l_take};
        ld0 <= l_take;
        la0 <= l_a;
        ldd0 <= l_d;
        ldd1 <= ldd0;
    end
    wire [1279:0] wq;                   // each multiplier's weight for its sum's phase
    wire [439:0]  ball;
    wire [11:0]   sall;
    genvar gw, gm;
    generate
        // a sum's group: its phase, and the port's address and value beside its RAMs
        for (gw = 0; gw < 20; gw = gw + 1) begin : g_grp
            localparam NMG = gw < 8 ? 2 : 12;
            localparam G0 = gw < 8 ? 2 * gw : gw < 16 ? 16 + 12 * (gw - 8) : 112 + 12 * (gw - 16);
            reg [2:0] ph /* synthesis syn_preserve = 1 */ = 3'd0;
            reg [2:0] wa /* synthesis syn_preserve = 1 */;
            reg [7:0] wd /* synthesis syn_preserve = 1 */;
            always @(posedge clk) begin
                ph <= go && !busy ? (gw >= 8 && gw < 16 ? 3'd4 : 3'd1) : ph == 3'd5 ? 3'd0 : ph + 3'd1;
                wa <= la0[2:0];
                wd <= ldd0[7:0];
            end
            for (gm = 0; gm < NMG; gm = gm + 1) begin : g_m
                reg we = 1'b0;
                always @(posedge clk)
                    we <= ld0 && la0[11] == 1'b0 && la0[10:3] == G0 + gm;
                cnn_w #(.INIT(CNN_W[48 * (G0 + gm) +: 48])) u (.clk(clk), .we(we), .wa(wa), .wd(wd), .ra(ph), .q(wq[8 * (G0 + gm) +: 8]));
            end
        end
        for (gw = 0; gw < 20; gw = gw + 1) begin : g_b
            reg [21:0] v = CNN_B[22 * gw +: 22];
            reg        we = 1'b0;
            always @(posedge clk) begin
                we <= ld0 && la0[11:8] == 4'd8 && la0[7:0] == gw;
                if (we)
                    v <= ldd1;
            end
            assign ball[22 * gw +: 22] = v;
        end
        for (gw = 0; gw < 3; gw = gw + 1) begin : g_s
            reg [3:0] v = CNN_S[4 * gw +: 4];
            reg       we = 1'b0;
            always @(posedge clk) begin
                we <= ld0 && la0[11:8] == 4'd9 && la0[7:0] == gw;
                if (we)
                    v <= ldd1[3:0];
            end
            assign sall[4 * gw +: 4] = v;
        end
    endgenerate
    // the layers' operands' phases
    reg [2:0]  lam1 /* synthesis syn_preserve = 1 */ = 3'd0;
    reg [2:0]  lam2 /* synthesis syn_preserve = 1 */ = 3'd0;
    reg [2:0]  lam3 /* synthesis syn_preserve = 1 */ = 3'd0;
    always @(posedge clk) begin
        lam1 <= go && !busy ? 3'd1 : lam1 == 3'd5 ? 3'd0 : lam1 + 3'd1;
        lam2 <= go && !busy ? 3'd4 : lam2 == 3'd5 ? 3'd0 : lam2 + 3'd1;
        lam3 <= go && !busy ? 3'd1 : lam3 == 3'd5 ? 3'd0 : lam3 + 3'd1;
    end

    // ---- layer 1, three times: the lines n (0), n + 1 (1), n + 2 (2) ----
    // a sum's two multipliers: the taps 0 to 5 (3 row + column) in the six phases, and 6 to 8 in the
    // first three
    reg [47:0]  b1;                     // [16 line + 8 multiplier]
    reg [127:0] w1;                     // [16 co + 8 multiplier]
    reg         p1;
    wire [7:0]  a1 [0:23];              // [8 line + co]
    always @(posedge clk) begin
        for (i = 0; i < 3; i = i + 1) begin
            b1[16 * i +: 8] <= sw[3 * i + lam1];                                    // (tap lam1: the line i + lam1 / 3, column lam1 % 3)
            b1[16 * i + 8 +: 8] <= sw[3 * (i + 2) + (lam1 < 3'd3 ? lam1 : 3'd0)];
        end
        for (c = 0; c < 8; c = c + 1) begin
            w1[16 * c +: 8] <= wq[8 * (2 * c) +: 8];
            w1[16 * c + 8 +: 8] <= wq[8 * (2 * c + 1) +: 8];
        end
        p1 <= lam1 == 3'd0;
    end
    genvar gi, gc;
    generate
        for (gi = 0; gi < 3; gi = gi + 1) begin : g_l1
            for (gc = 0; gc < 8; gc = gc + 1) begin : g_c
                cnn_sum #(.NM(2)) u (.clk(clk), .a(b1[16 * gi +: 16]), .w(w1[16 * gc +: 16]), .ph0(p1), .b(ball[22 * gc +: 22]),
                                     .sh(sall[3:0]), .q(a1[8 * gi + gc]), .r());
            end
        end
    endgenerate

    // ---- layer 2's window: layer 1's three lines, three columns, eight channels ----
    reg [63:0] v2 [0:8];                // [3 line + column]
    wire [63:0] a1l [0:2];              // layer 1's three lines' eight channels
    generate
        for (gi = 0; gi < 3; gi = gi + 1) begin : g_a1
            assign a1l[gi] = {a1[8 * gi + 7], a1[8 * gi + 6], a1[8 * gi + 5], a1[8 * gi + 4], a1[8 * gi + 3], a1[8 * gi + 2],
                              a1[8 * gi + 1], a1[8 * gi]};
        end
    endgenerate
    // (a line outside the picture: the one next to it)
    wire [63:0] n2a = top_a ? a1l[1] : a1l[0], n2c = bot_c ? a1l[1] : a1l[2];
    always @(posedge clk) begin
        v2e <= {9{busy && k == 3'd0 && pp >= 10'd4 && pp <= W + 4}};
        if (v2e[2]) v2[2] <= n2a;
        if (v2e[5]) v2[5] <= a1l[1];
        if (v2e[8]) v2[8] <= n2c;
        if (v2e[1]) v2[1] <= pp_4 ? n2a : v2[2];
        if (v2e[4]) v2[4] <= pp_4 ? a1l[1] : v2[5];
        if (v2e[7]) v2[7] <= pp_4 ? n2c : v2[8];
        if (v2e[0]) v2[0] <= v2[1];
        if (v2e[3]) v2[3] <= v2[4];
        if (v2e[6]) v2[6] <= v2[7];
    end
    // a sum's twelve multipliers: (line r, channel 4 h + cc) of the column kc, the phase 2 kc + h
    function [95:0] bus(input [575:0] v, input [2:0] lam);
        integer br, bc;
        reg [1:0] kc;
        reg h;
        begin
            kc = lam[2:1];
            h = lam[0];
            for (br = 0; br < 3; br = br + 1)
                for (bc = 0; bc < 4; bc = bc + 1)
                    bus[8 * (4 * br + bc) +: 8] = v[64 * (3 * br + kc) + 8 * (4 * h + bc) +: 8];
        end
    endfunction
    wire [575:0] v2f = {v2[8], v2[7], v2[6], v2[5], v2[4], v2[3], v2[2], v2[1], v2[0]};
    reg [95:0]  b2;
    reg [767:0] w2;                     // [96 co + 8 j]
    reg         p2;
    wire [7:0]  a2 [0:7];
    always @(posedge clk) begin
        b2 <= bus(v2f, lam2);
        for (c = 0; c < 8; c = c + 1)
            for (j = 0; j < 12; j = j + 1)
                w2[96 * c + 8 * j +: 8] <= wq[8 * (16 + 12 * c + j) +: 8];
        p2 <= lam2 == 3'd0;
    end
    generate
        for (gc = 0; gc < 8; gc = gc + 1) begin : g_l2
            cnn_sum #(.NM(12)) u (.clk(clk), .a(b2), .w(w2[96 * gc +: 96]), .ph0(p2), .b(ball[22 * (8 + gc) +: 22]), .sh(sall[7:4]),
                                  .q(a2[gc]), .r());
        end
    endgenerate
    wire [63:0] a2f = {a2[7], a2[6], a2[5], a2[4], a2[3], a2[2], a2[1], a2[0]};

    // ---- layer 2's lines kept: the line l in the RAM l's low bit ----
    // (this pass's is the line n + 1: read at the column for the lines n - 1 and n, then written)
    reg [9:0]  m_ra;
    reg        m_we = 1'b0;
    reg [9:0]  m_wa;
    reg [63:0] m_wd;
    wire       par = nn[0];             // (the line n's RAM; n + 1's and n - 1's: the other)
    // (two lines of 64 bits: eight RAMs of 1024 x 16, a block RAM each: wider ones the tools split
    // their own way into more)
    wire [63:0] qa, qb;
    always @(posedge clk) begin
        if (k == 3'd0)
            m_ra <= pp >= W + 7 ? W - 1 : pp - 10'd7;
        m_we <= busy && k5 && m_in && !bot_b;
        m_wa <= pp - 10'd7;
        if (k == 3'd4)                      // (a sum's result is there for that one clock)
            m_wd <= a2f;
    end
    genvar gr;
    generate
        for (gr = 0; gr < 4; gr = gr + 1) begin : g_m2
            reg [15:0] ma [0:1023];
            reg [15:0] mb [0:1023];
            reg [15:0] a1q, b1q, aq, bq;
            always @(posedge clk) begin
                a1q <= ma[m_ra];
                b1q <= mb[m_ra];
                aq <= a1q;
                bq <= b1q;
                if (m_we && par)
                    ma[m_wa] <= m_wd[16 * gr +: 16];        // (the line n + 1: where n - 1 was)
                if (m_we && !par)
                    mb[m_wa] <= m_wd[16 * gr +: 16];
            end
            assign qa[16 * gr +: 16] = aq;
            assign qb[16 * gr +: 16] = bq;
        end
    endgenerate
    // ---- layer 3's window: layer 2's lines n - 1, n, n + 1 ----
    wire [63:0] l2n = par ? qb : qa;            // the line n
    wire [63:0] l2p = par ? qa : qb;            // n - 1
    reg [63:0] v3 [0:8];
    // (v3_dup: the last column again: from the window, the RAM's line n - 1 is written over by now)
    wire [63:0] n3a = v3_dup ? v3[2] : top_3 ? l2n : l2p;
    wire [63:0] n3b = v3_dup ? v3[5] : l2n;
    wire [63:0] n3c = v3_dup ? v3[8] : bot_b ? l2n : a2f;
    always @(posedge clk) begin
        v3e <= {9{busy && k == 3'd3 && v3_in}};
        if (v3e[2]) v3[2] <= n3a;
        if (v3e[5]) v3[5] <= n3b;
        if (v3e[8]) v3[8] <= n3c;
        if (v3e[1]) v3[1] <= pp_7 ? n3a : v3[2];
        if (v3e[4]) v3[4] <= pp_7 ? n3b : v3[5];
        if (v3e[7]) v3[7] <= pp_7 ? n3c : v3[8];
        if (v3e[0]) v3[0] <= v3[1];
        if (v3e[3]) v3[3] <= v3[4];
        if (v3e[6]) v3[6] <= v3[7];
    end
    wire [575:0] v3f = {v3[8], v3[7], v3[6], v3[5], v3[4], v3[3], v3[2], v3[1], v3[0]};
    reg [95:0]  b3;
    reg [383:0] w3;
    reg         p3;
    wire signed [14:0] r3 [0:3];
    always @(posedge clk) begin
        b3 <= bus(v3f, lam3);
        for (c = 0; c < 4; c = c + 1)
            for (j = 0; j < 12; j = j + 1)
                w3[96 * c + 8 * j +: 8] <= wq[8 * (112 + 12 * c + j) +: 8];
        p3 <= lam3 == 3'd0;
    end
    generate
        for (gc = 0; gc < 4; gc = gc + 1) begin : g_l3
            cnn_sum #(.NM(12)) u (.clk(clk), .a(b3), .w(w3[96 * gc +: 96]), .ph0(p3), .b(ball[22 * (16 + gc) +: 22]), .sh(sall[11:8]),
                                  .q(), .r(r3[gc]));
        end
    endgenerate

    // ---- the two-tap stretch (9 a + 3 b + 3 c + d: the source's lines n - 1, n, n + 1 are the
    // window's 0, 1, 2), kept ten periods for layer 3's column ----
    reg [47:0] sk [0:10];               // {below right, below left, above right, above left}
    // (in two clocks: 9 a + 3 b, and 3 c + d; then their sum: the window stays from k 5 on)
    function [12:0] sk_ab(input [7:0] a, input [7:0] b);
        sk_ab = {5'd0, a} + {2'd0, a, 3'd0} + {5'd0, b} + {4'd0, b, 1'b0};
    endfunction
    function [10:0] sk_cd(input [7:0] cc, input [7:0] d);
        sk_cd = {3'd0, cc} + {2'd0, cc, 1'b0} + {3'd0, d};
    endfunction
    reg [10:0] ske /* synthesis syn_preserve = 1 */ = 11'd0;     // (its steps' enable: one beside each)
    reg [12:0] kab [0:1];               // (above, below)
    reg [10:0] kcd [0:3];               // (above left, above right, below left, below right)
    always @(posedge clk) begin
        if (k5) begin
            kab[0] <= sk_ab(sw[4], sw[1]);
            kab[1] <= sk_ab(sw[4], sw[7]);
            kcd[0] <= sk_cd(sw[3], sw[0]);
            kcd[1] <= sk_cd(sw[5], sw[2]);
            kcd[2] <= sk_cd(sw[3], sw[6]);
            kcd[3] <= sk_cd(sw[5], sw[8]);
        end
        ske <= {11{busy && k5}};
        if (ske[0])
            sk[0] <= {kab[1][11:0] + {1'b0, kcd[3]}, kab[1][11:0] + {1'b0, kcd[2]}, kab[0][11:0] + {1'b0, kcd[1]}, kab[0][11:0] + {1'b0, kcd[0]}};
        for (i = 1; i <= 10; i = i + 1)
            if (ske[i])
                sk[i] <= sk[i - 1];
    end
    // ---- the four pixels: layer 3's four with the stretch; written a clock each ----
    reg [7:0]  o4 [0:3];
    reg signed [16:0] ot;
    wire [10:0] ox = {pp - 10'd11, 1'b0};
    always @(posedge clk) begin
        if (k == 3'd1)
            for (i = 0; i < 4; i = i + 1) begin
                ot = $signed({5'd0, sk[9][12 * i +: 12]}) + r3[i] + 17'sd8;
                o4[i] <= ot < 0 ? 8'd0 : ot > 17'sd4095 ? 8'd255 : ot[11:4];
            end
        o_we <= busy && o_in && k >= 3'd2;
        o_line <= {nn[9:0], k[2]};                              // (k 2, 3: the line 2 n; 4, 5: 2 n + 1)
        o_col <= {ox[10:1], k[0]};
        o_d <= o4[k - 3'd2];
    end
endmodule
