// deint.v: the fields in the DDR3 (cap_ddr.v) made into a progressive picture, a line when the
// output wants it, motion adaptive: on the DDR3's user clock.
//
// At a frame's start the last four fields are taken: C the newest, then P1, P2, P3.  C's lines
// are the frame's lines of its parity as they are.  A line between two of them, `old` above and
// `new` below, is P1's line there (weave) where nothing moves and the mean of old and new (bob)
// where something does.  What moves: for each pixel
//
//   m = max(|C - P2| on old, on new, |P1 - P3| on the line itself)        (luma; two fields apart:
//                                                                           the same lines)
//   m' = max(m of the pixel before, m, m of the pixel after)              (within the 16 pixels of
//                                                                           a DDR3 line, and the
//                                                                           last of those before)
//   a = min(16, max(0, m' - thr))
//   out = (weave (16 - a) + bob a + 8) / 16                               (chroma: the pair's
//                                                                           greater a)
//
// Noise (nr 1 to 3, with four fields in order): C's and P1's lines are first made quieter where
// the picture is still: each sample (luma and chroma) with the same one two fields before (P2's,
// P3's: the same line a frame earlier): their mean while they differ by T = 1 << nr or less, less
// and less of the older one from there, none from 2 T on (sim/model.py tnr()).  What moves is still
// seen in the fields as they are.
//
// ll: a frame begun while a field is still coming in is made from that field (C the one coming in,
// P1 to P3 the three before it) if ll_min of its lines are in already (cap_ddr.v's prog): the
// output a few lines behind the input, not a field (the output's clock must be in step for it to
// stay so: the CPU's frame lock); a line of C is waited for if it is not in yet.
//
// At the picture's edge the missing one of old, new is the other.  mode 1: bob everywhere; 2: weave
// everywhere; bob too until four fields of alternating parity are there (hist).  top_f: the F of
// the top field.
//
// edi: the mean of old and new (bob) is taken along the picture's edges instead of straight down
// (sim/model.py edge_line(): for each pixel the offset d of -4 to 4 for which old at x + d and new
// at x - d are most alike, by a sum over five columns; used only where it clearly beats straight
// down and its own two pixels are alike enough; the result held between the pixels straight above
// and below; the chroma goes the way of its pair's first pixel, half as far).  A pixel's search
// reaches six pixels each way: the sixteen pixels of a step are made when the sixteen after them
// are in too.
//
// mv: the picture's pan, {it is known, dyr (4 bits, signed), dx (6 bits, signed)}: what is at
// (x, row) of a field is at (x + dx, row + dyr) of the field two before (the same lines); taken at
// a frame's start, used while dyr is even, in the motion adaptive mode.  Where the picture moves
// and is that (C against P2 moved by (dx, dyr) on old and new, P1 moved by half of it against P3
// moved by three halves, at the line itself: as m, with thr), the line made is P1's moved by half
// of it (half a pixel: the mean of two), not the mean of old and new (sim/model.py deinterlace()
// mv): the picture as it was drawn, where it only pans.  A pass before each step's own reads P2,
// P1 and P3 at their moved lines for the whole line (so each field's row stays open through a
// pass) and keeps the words and the differences by the sixteen pixels; the step's pass mixes
// them in.
//
// pg: what comes in is progressive: each field in the memory is a whole frame, and the frame made
// is the newest one's lines as they are, two a step (line 2k + 1 read as C's, line 2k in P1's
// place and taken as it is: weave, no noise reduction); with ll, the one coming in.
//
// The lines go to lstream.v's store of four, 16 pixels at a time, two lines together (the one as it
// is, D, and the one made, I), eight words each (r_*: a line's place its number's low bits);
// emitted: the frame's lines all there; fstart: a clock at a frame's start.  hold: no new step (the
// store's lines are not read out yet).  The output asks by ev (a change: an event): ev_first with
// it: a new frame.  goal (this clock's): lines are made while emitted <= goal.
//
// A step k reads C's line k (new) into the place of line k - 1 (old, kept in cbuf with its |C - P2|
// in mbuf), and makes
//   C a top field     (k >= 1) D = line 2(k-1) = old, I = line 2(k-1)+1, P1's line k-1
//   C a bottom field  I = line 2k, P1's line k; D = line 2k+1 = new
// reading four lines of the DDR3 for each sixteen pixels (the fields' rows stay open: a slot is a
// bank).

module deint (
    input              clk,
    input      [6:0]   nch,             // DDR3 lines (16 pixels) a line of picture (45: 720; 80: 1280)
    input              pg,              // a progressive picture: a field is a frame (below)
    input              ev,
    input              ev_first,
    input      [9:0]   goal,
    input              hold,
    input      [2:0]   latest,
    input      [7:0]   par,
    input      [2:0]   nfields,
    input      [9:0]   flines,
    input      [1:0]   mode,
    input      [7:0]   thr,
    input      [1:0]   nr,              // temporal noise reduction: 0 none, 1 to 3
    input              edi,             // bob along the edges
    input      [10:0]  mv,              // the picture's pan: {known, dyr, dx}
    input              ll,
    input      [7:0]   ll_min,
    input      [9:0]   prog,
    input      [2:0]   prog_slot,
    input              top_f,

    output reg         b_valid = 1'b0,
    output reg [24:0]  b_line,
    input              b_ack,
    input              b_rvalid,
    input      [255:0] rd_data,

    output reg         r_we = 1'b0,     // both lines' word
    output reg [2:0]   r_slot_d,
    output reg [2:0]   r_slot_i,
    output reg [9:0]   r_wa,
    output reg [31:0]  r_wd_d,
    output reg [31:0]  r_wd_i,
    output reg [9:0]   emitted = 10'd0,
    output reg         fstart = 1'b0,
    output reg [15:0]  frames = 16'd0,  // (for the host: frames begun, and the last one's state)
    output reg [7:0]   state_o
);
    // the output's events
    reg        e0, e1, e2, start = 1'b0;
    reg        start_clr;
    always @(posedge clk) begin
        e0 <= ev;
        e1 <= e0;
        e2 <= e1;
        if (e1 != e2) begin
            if (ev_first)
                start <= 1'b1;
        end
        if (start_clr)
            start <= 1'b0;
    end

    localparam S_IDLE = 0, S_RQ = 1, S_WAIT = 2, S_C1 = 3, S_C2 = 4, S_W = 5, S_NEXT = 6, S_C1B = 7, S_C2B = 8,
               S_GO = 9, S_C1C = 10, S_GAP = 11, S_GAP2 = 12, S_C1D = 13, S_C2A = 14, S_E0 = 15, S_SH = 16, S_FL = 17, S_SH2 = 18,
               S_P0 = 19, S_PA = 20, S_PRQ = 21, S_PW = 22, S_PW2 = 23, S_PX1 = 24, S_PX2 = 25, S_PX3 = 26, S_PX4 = 27, S_PN = 28, S_WL = 29;
    reg [4:0]  st = S_IDLE;
    reg        active = 1'b0, pc, hist, ll_used = 1'b0;
    // (pg and nch as they were when the frame was begun: a change of them in the middle of a step
    // must not leave it waiting for lines it did not ask for: seen on the board, 2026-11-12)
    reg        pgf = 1'b0;
    reg [6:0]  nchf = 7'd45;
    // (a frame from the field coming in: four fields before it in order, and enough of it there)
    wire [2:0] nxt = latest + 3'd1;
    wire       ll_now = pg ? ll && nfields != 3'd0 && prog_slot == nxt && prog >= {2'd0, ll_min} :
                        ll && nfields >= 3'd4 && prog_slot == nxt && prog >= {2'd0, ll_min} &&
                        par[latest - 3'd1] != par[latest] && par[latest - 3'd2] == par[latest];
    wire       hist_n = nfields >= 3'd4 && par[latest - 3'd1] != par[latest] &&
                        par[latest - 3'd2] == par[latest] && par[latest - 3'd3] != par[latest];
    reg        line_ok = 1'b1;          // (C's line of this step is in the memory)
    reg [2:0]  fc, f1, f2, f3;          // the fields' slots
    reg [9:0]  nl;                      // a field's lines
    reg [9:0]  k;                       // the step
    reg [6:0]  c;                       // the sixteen pixels
    reg [2:0]  i;
    reg [2:0]  rx;
    reg [3:0]  p;
    reg [255:0] d0, d1, d2, d3;

    // the step's lines (registered: k changes between steps only, a clock at least before they
    // are used)
    wire [9:0] kmax = pgf ? {1'b0, nl[9:1]} - 10'd1 : pc ? nl - 10'd1 : nl;
    reg        new_ok, old_ok, emit;
    reg [9:0]  row_new, row_w, line_i, line_d;
    reg        can = 1'b0;              // a step may start (a clock behind what it is made from)
    // the pan (mv), as the frame has it
    reg                mc_f = 1'b0;
    reg signed [5:0]   dxf = 6'sd0;
    reg signed [3:0]   dyf = 4'sd0;
    wire signed [5:0]  sh1 = dxf >>> 1;                         // P1's pixels over (and half a pixel: dxf[0])
    wire signed [6:0]  sh3 = {dxf[5], dxf} + {sh1[5], sh1};     // P3's
    wire signed [5:0]  o2w = dxf >>> 4, o1w = sh1 >>> 4;
    wire signed [6:0]  o3w = sh3 >>> 4;
    wire signed [2:0]  o2 = o2w[2:0], o1 = o1w[2:0], o3 = o3w[2:0];     // the sixteens over
    wire [3:0]         r2 = dxf[3:0], r1 = sh1[3:0], r3 = sh3[3:0];     // and the pixels within
    wire signed [3:0]  dyh = dyf >>> 1;
    wire signed [11:0] row2_w = $signed({2'b00, row_new}) + dyf;
    wire signed [11:0] row1_w = $signed({2'b00, row_w}) + dyh;
    wire signed [11:0] row3_w = $signed({2'b00, row_w}) + dyh + dyf;
    reg signed [11:0]  row2, row1, row3;
    reg                ok2, ok1, ok3;
    always @(posedge clk) begin
        line_ok <= !ll_used || latest == fc || (prog_slot == fc && (pgf ? {k[8:0], 1'b1} : k) < prog) || (!pgf && k >= nl);
        can <= active && !hold && k <= kmax && emitted <= goal && line_ok;
        new_ok <= pgf || k < nl;
        old_ok <= k != 10'd0;
        emit <= pc ? 1'b1 : k != 10'd0;
        row_new <= pgf ? {k[8:0], 1'b1} : k < nl ? k : nl - 10'd1;
        row_w <= pgf ? {k[8:0], 1'b0} : pc ? k : (k != 10'd0 ? k - 10'd1 : 10'd0);
        line_i <= pc ? {k[8:0], 1'b0} : {k[8:0] - 9'd1, 1'b1};
        line_d <= pc ? {k[8:0], 1'b1} : {k[8:0] - 9'd1, 1'b0};
        // (the pan's lines: P2's for new, P1's, P3's; and whether they are in the field)
        row2 <= row2_w;
        row1 <= row1_w;
        row3 <= row3_w;
        ok2 <= new_ok && row2_w >= 12'sd0 && row2_w < $signed({2'b00, nl});
        ok1 <= row1_w >= 12'sd0 && row1_w < $signed({2'b00, nl});
        ok3 <= row3_w >= 12'sd0 && row3_w < $signed({2'b00, nl});
    end

    // old's line and its |C - P2|, by the sixteen pixels
    reg [255:0] cbuf [0:127];
    reg [127:0] mbuf [0:127];
    reg [255:0] old_c, oc1;             // (two registers after the RAM: its own, and one beside the logic)
    reg [127:0] old_m, om1;
    reg         buf_we;
    reg [6:0]   buf_a;                  // (its own register: a RAM with two ports, not one)
    reg [255:0] buf_c;
    reg [127:0] buf_m;
    always @(posedge clk) begin
        oc1 <= cbuf[c];
        om1 <= mbuf[c];
        old_c <= oc1;
        old_m <= om1;
        if (buf_we) begin
            cbuf[buf_a] <= buf_c;
            mbuf[buf_a] <= buf_m;
        end
    end

    // a DDR3 line's pixel n: its luma; pair q's word
    function [7:0] luma(input [255:0] d, input integer n);
        luma = n % 2 ? d[32 * (n / 2) +: 8] : d[32 * (n / 2) + 16 +: 8];
    endfunction
    function [7:0] absd(input [7:0] a, input [7:0] b);
        absd = a > b ? a - b : b - a;
    endfunction
    function [7:0] max2(input [7:0] a, input [7:0] b);
        max2 = a > b ? a : b;
    endfunction

    // the noise reduction: C's line (d0 with d1) and P1's (d2 with d3),
    // three clocks behind them (they are read by C1 and stay; used from C2B on): the difference;
    // how much of it is taken (a table: by nr and the difference, under 16); the sample
    reg [287:0] tac, taw;               // a sample's nine bits: {the older one is the lesser, the difference}
    reg [159:0] tcc, tcw;               // five: {the older one is the lesser, the part taken}
    reg [255:0] nrc, nrw;
    reg [3:0]   tnr_t [0:63];           // [{nr, the difference}]
    reg [15:0]  nrq /* synthesis syn_preserve = 1 */;   // nr (none without the fields' history): a copy for every four samples
    integer     ti, tt;
    initial
        for (ti = 0; ti < 64; ti = ti + 1) begin
            tt = 1 << (ti >> 4);
            tnr_t[ti] = ti < 16 || (ti & 15) >= 2 * tt ? 0 :
                        ((ti & 15) * ((2 * tt - (ti & 15)) < tt ? (2 * tt - (ti & 15)) : tt) + tt) >> ((ti >> 4) + 1);
        end
    function [8:0] tnr_a(input [7:0] cur, input [7:0] oth);
        tnr_a = {oth < cur, oth > cur ? oth - cur : cur - oth};
    endfunction
    integer     nb;
    always @(posedge clk) begin
        nrq <= {8{hist ? nr : 2'd0}};
        for (nb = 0; nb < 32; nb = nb + 1) begin
            tac[9 * nb +: 9] <= tnr_a(d0[8 * nb +: 8], d1[8 * nb +: 8]);
            taw[9 * nb +: 9] <= tnr_a(d2[8 * nb +: 8], d3[8 * nb +: 8]);
            tcc[5 * nb +: 5] <= {tac[9 * nb + 8], |tac[9 * nb + 4 +: 4] ? 4'd0 : tnr_t[{nrq[2 * (nb / 4) +: 2], tac[9 * nb +: 4]}]};
            tcw[5 * nb +: 5] <= {taw[9 * nb + 8], |taw[9 * nb + 4 +: 4] ? 4'd0 : tnr_t[{nrq[2 * (nb / 4) +: 2], taw[9 * nb +: 4]}]};
            nrc[8 * nb +: 8] <= tcc[5 * nb + 4] ? d0[8 * nb +: 8] - {4'd0, tcc[5 * nb +: 4]} : d0[8 * nb +: 8] + {4'd0, tcc[5 * nb +: 4]};
            nrw[8 * nb +: 8] <= tcw[5 * nb + 4] ? d2[8 * nb +: 8] - {4'd0, tcw[5 * nb +: 4]} : d2[8 * nb +: 8] + {4'd0, tcw[5 * nb +: 4]};
        end
    end

    // C1: new and old as used, the three differences' greatest
    reg [127:0] dn, m, dnr, dwr, md, dor, mab, dw2, mlc, mrr;
    reg         rdv = 1'b0;
    reg [255:0] rdq, rdq2;
    reg [3:0]   rde = 4'd0;             // (which of the four a word read is: a clock before it is kept)
    reg [7:0]   carry;                  // m of the pixel before these sixteen
    reg [79:0]  al;                     // a, 5 bits a pixel
    integer     n;
    reg [7:0]   t_dn, t_do, t_dw, t_m, t_l, t_r, t_d;
    reg [8:0]   t_a;

    // W: a pair a clock, three stages: the pair's words, their means, the blend
    reg         s0_v = 1'b0;
    reg [9:0]   s0_wa;
    reg [31:0]  wo, wn, ww;
    reg [4:0]   a_y0, a_y1;
    wire [4:0]  a_c = a_y0 > a_y1 ? a_y0 : a_y1;
    reg         s1_v = 1'b0;
    reg [9:0]   s1_wa;
    reg [31:0]  s1_bob, s1_w, s1_d;
    reg [4:0]   s1_ay0, s1_ay1, s1_ac;
    reg [7:0]   pv = 8'd0;
    reg [135:0] pd0, pd1, pd2, pd3, pd4, pd5, pd6, pd7;
    reg [3:0]   fl;
    reg [31:0]  wvp, s1_wv, s2_x, s2_w, s2_d;
    reg [4:0]   v_y0, v_y1, s1_v0, s1_v1, s1_vc, s2_ay0, s2_ay1, s2_ac;
    reg         s2_v = 1'b0;
    reg [9:0]   s2_wa;
    // (the pan's pixel must lie near the pixels above and below: else the mean)
    function near(input [7:0] v, input [7:0] a, input [7:0] b);
        near = {1'b0, v} + 9'd12 >= {1'b0, a < b ? a : b} && {1'b0, v} <= {1'b0, a < b ? b : a} + 9'd12;
    endfunction
    wire [4:0]  v0g = near(wvp[23:16], wo[23:16], wn[23:16]) ? v_y0 : 5'd16;
    wire [4:0]  v1g = near(wvp[7:0], wo[7:0], wn[7:0]) ? v_y1 : 5'd16;
    function [7:0] mean(input [7:0] a, input [7:0] b);
        reg [8:0] t;
        begin
            t = {1'b0, a} + {1'b0, b} + 9'd1;
            mean = t[8:1];
        end
    endfunction
    function [7:0] blend(input [7:0] w, input [7:0] bb, input [4:0] a);
        reg [12:0] t;
        begin
            t = w * (5'd16 - a) + bb * a + 13'd8;
            blend = t[11:4];
        end
    endfunction

    // ---- the pan's way (mv): its pass ----
    reg signed [7:0] cc = -8'sd1;       // the pass's sixteen pixels (-1: the ones before the line's first)
    reg         in_p2 = 1'b0;
    reg [3:0]   need = 4'd0, pend = 4'd0, rde2 = 4'd0;
    // P2's, P1's and P3's sixteens, two of each side by side (lo: number cc + o, hi: the next), and
    // whether they are in the field
    reg [255:0] lo2, hi2, lo1, hi1, lo3, hi3;
    reg         lo2k = 1'b0, hi2k = 1'b0, lo1k = 1'b0, hi1k = 1'b0, lo3k = 1'b0, hi3k = 1'b0;
    wire signed [7:0] g2 = cc + 8'sd1 + o2, g1 = cc + 8'sd1 + o1, g3 = cc + 8'sd1 + o3;    // (hi's number)
    wire        g2k = !g2[7] && g2 < $signed({1'b0, nchf});
    wire        g1k = !g1[7] && g1 < $signed({1'b0, nchf});
    wire        g3k = !g3[7] && g3 < $signed({1'b0, nchf});
    // the line the pass leaves: {the differences' greatest (8 bits a pixel), P1's words moved} by the
    // sixteen pixels; and |C - P2 moved| on new, for the step after (its old)
    reg [383:0] mcb [0:127];
    reg [127:0] mbv [0:127];
    reg [383:0] mq1, mq;
    reg [127:0] ov1, ovq;
    reg         mc_we = 1'b0;
    reg [383:0] mc_d;
    reg [127:0] mc_n;
    reg [6:0]   mc_a;
    always @(posedge clk) begin
        mq1 <= mcb[c];
        mq <= mq1;
        ov1 <= mbv[cc[6:0]];
        ovq <= ov1;
        if (mc_we) begin
            mcb[mc_a] <= mc_d;
            mbv[mc_a] <= mc_n;
        end
    end
    reg [7:0]   carry_v;
    reg [127:0] mlv, mrv, mdv;
    reg [79:0]  alv;
    reg [255:0] eWV;
    reg [79:0]  eALV;
    // pixel n of the 32 of lo and hi: its luma; pair q of their 16: its word
    function [7:0] lw(input [255:0] lo, input [255:0] hi, input [4:0] n);
        reg [255:0] d;
        begin
            d = n[4] ? hi : lo;
            lw = n[0] ? d[32 * n[3:1] +: 8] : d[32 * n[3:1] + 16 +: 8];
        end
    endfunction
    // three clocks: the pixels moved (a pixel j of the sixteen: number j + r of the 32); P1's and
    // P3's with the half pixel; the differences, the greatest with old's
    reg [127:0] p2v, p1a, p1b, p3a, p3b, cnl, p1v, p3v, mnv;
    reg [15:0]  p2k, p1k, p3k, p13k;
    reg [63:0]  cbv, crv, cbv2, crv2;
    integer     xj, xq;
    reg [4:0]   x_n;
    reg [3:0]   x_p;
    reg [7:0]   x_w, x_t;
    always @(posedge clk) begin
        for (xj = 0; xj < 16; xj = xj + 1) begin
            // 1
            x_n = xj + r2;
            p2v[8 * xj +: 8] <= lw(lo2, hi2, x_n);
            p2k[xj] <= x_n[4] ? hi2k : lo2k;
            x_n = xj + r1;
            p1a[8 * xj +: 8] <= lw(lo1, hi1, x_n);
            p1b[8 * xj +: 8] <= lw(lo1, hi1, x_n + 5'd1);
            p1k[xj] <= (x_n[4] ? hi1k : lo1k) && (!dxf[0] || (x_n == 5'd15 || x_n[4] ? hi1k : lo1k));
            x_n = xj + r3;
            p3a[8 * xj +: 8] <= lw(lo3, hi3, x_n);
            p3b[8 * xj +: 8] <= lw(lo3, hi3, x_n + 5'd1);
            p3k[xj] <= (x_n[4] ? hi3k : lo3k) && (!dxf[0] || (x_n == 5'd15 || x_n[4] ? hi3k : lo3k));
            cnl[8 * xj +: 8] <= luma(d0, xj);
            // 2
            p1v[8 * xj +: 8] <= dxf[0] ? mean(p1a[8 * xj +: 8], p1b[8 * xj +: 8]) : p1a[8 * xj +: 8];
            p3v[8 * xj +: 8] <= dxf[0] ? mean(p3a[8 * xj +: 8], p3b[8 * xj +: 8]) : p3a[8 * xj +: 8];
            mnv[8 * xj +: 8] <= p2k[xj] ? absd(cnl[8 * xj +: 8], p2v[8 * xj +: 8]) : 8'd255;
            p13k[xj] <= p1k[xj] && p3k[xj];
            // 3: the line's, kept
            x_w = p13k[xj] ? absd(p1v[8 * xj +: 8], p3v[8 * xj +: 8]) : 8'd255;
            x_t = max2(max2(ovq[8 * xj +: 8], mnv[8 * xj +: 8]), x_w);
            mc_d[256 + 8 * xj +: 8] <= old_ok && new_ok ? x_t : 8'd255;
            mc_n[8 * xj +: 8] <= mnv[8 * xj +: 8];
        end
        for (xq = 0; xq < 8; xq = xq + 1) begin
            // (the chroma of the pair the first pixel moved lies in)
            x_p = (2 * xq + r1) >> 1;
            cbv[8 * xq +: 8] <= x_p[3] ? hi1[32 * x_p[2:0] + 24 +: 8] : lo1[32 * x_p[2:0] + 24 +: 8];
            crv[8 * xq +: 8] <= x_p[3] ? hi1[32 * x_p[2:0] + 8 +: 8] : lo1[32 * x_p[2:0] + 8 +: 8];
            cbv2[8 * xq +: 8] <= cbv[8 * xq +: 8];
            crv2[8 * xq +: 8] <= crv[8 * xq +: 8];
            mc_d[32 * xq +: 32] <= {cbv2[8 * xq +: 8], p1v[16 * xq +: 8], crv2[8 * xq +: 8], p1v[16 * xq + 8 +: 8]};
        end
        mc_a <= cc[6:0];
    end

    // ---- the edges' way (edi) ----
    // three sixteens side by side, old and new as they are used: [0] the ones before the ones made,
    // [1] the ones made, [2] the ones after; P1's words and the a of the ones made
    reg [255:0] eO0, eO1, eO2, eN0, eN1, eN2, eW;
    reg [79:0]  eAL;
    reg [6:0]   ec;
    reg         elast = 1'b0;
    wire [255:0] o_used, n_used;
    assign o_used = old_ok ? old_c : nrc;
    assign n_used = new_ok ? nrc : old_c;
    // their luma, a pixel 8 bits (pixel i of sixteen g at 8 (16 g + i)); their chroma, a pair's
    // {Cb, Cr} 16 bits (pair q of sixteen g at 16 (8 g + q))
    wire [383:0] la, lb, ka, kb;
    genvar gg;
    generate
        for (gg = 0; gg < 16; gg = gg + 1) begin : g_la
            assign la[8 * gg +: 8] = luma(eO0, gg);
            assign la[8 * (16 + gg) +: 8] = luma(eO1, gg);
            assign la[8 * (32 + gg) +: 8] = luma(eO2, gg);
            assign lb[8 * gg +: 8] = luma(eN0, gg);
            assign lb[8 * (16 + gg) +: 8] = luma(eN1, gg);
            assign lb[8 * (32 + gg) +: 8] = luma(eN2, gg);
        end
        for (gg = 0; gg < 8; gg = gg + 1) begin : g_ka
            assign ka[16 * gg +: 16] = {eO0[32 * gg + 24 +: 8], eO0[32 * gg + 8 +: 8]};
            assign ka[16 * (8 + gg) +: 16] = {eO1[32 * gg + 24 +: 8], eO1[32 * gg + 8 +: 8]};
            assign ka[16 * (16 + gg) +: 16] = {eO2[32 * gg + 24 +: 8], eO2[32 * gg + 8 +: 8]};
            assign kb[16 * gg +: 16] = {eN0[32 * gg + 24 +: 8], eN0[32 * gg + 8 +: 8]};
            assign kb[16 * (8 + gg) +: 16] = {eN1[32 * gg + 24 +: 8], eN1[32 * gg + 8 +: 8]};
            assign kb[16 * (16 + gg) +: 16] = {eN2[32 * gg + 24 +: 8], eN2[32 * gg + 8 +: 8]};
        end
    endgenerate
    // The sixteen made go through a pair a clock: what a pair needs is at the low end of registers
    // that move on each clock (no choosing by the pair's number): the pair's words, its a, and its
    // surroundings: the luma of fourteen pixels (six before its first to six after its second) and
    // the chroma of five pairs (two each side)
    reg [255:0] shO, shN, shW, shWV;
    reg [79:0]  shAL, shALV;
    reg [383:0] shLA, shLB, shKA, shKB;
    // stage 0 (with wo, wn): luma i of 0 to 13 (the pair's two pixels: 6 and 7), chroma pair j of 0
    // to 4 (the pair's own: 2); and these through the stages to where the pixel is taken (8)
    reg [111:0] wa, wb;
    reg [79:0]  ca, cn;
    reg [111:0] wad [1:7], wbd [1:7];
    reg [79:0]  cad [1:7], cnd [1:7];
    reg         s0_side;
    reg [6:0]   sided;
    // stage 1: |old(i + d) - new(i - d)| for d of -4 to 4, the columns i of 4 to 9: at 8 (6 (d + 4) + i - 4)
    reg [431:0] ad;
    // stage 2: each pixel's sums (t 0, 1; 11 bits at 11 (9 t + d + 4)) and its candidates' own
    // |old - new| (8 bits at 8 (9 t + d + 4))
    reg [197:0] sm;
    reg [143:0] adc;
    // a candidate: {its sum, its place in the order tried, its own |old - new|}: the least by the
    // first two is the first of the least sums (straight down, then -1, 1, -2, 2, ...)
    function [3:0] ord(input integer d);
        ord = d == 0 ? 4'd0 : d < 0 ? 4'd2 * (-d) - 4'd1 : 4'd2 * d;
    endfunction
    function signed [3:0] dof(input [3:0] o);
        dof = o == 4'd0 ? 4'sd0 : o[0] ? -$signed({1'b0, o[3:1]} + 4'd1) : $signed({1'b0, o[3:1]});
    endfunction
    function [22:0] least(input [22:0] x, input [22:0] y);
        least = y[22:8] < x[22:8] ? y : x;
    endfunction
    // stages 3 to 6: the least of nine, a comparison a stage: in each three the first two (3), then
    // the third (4); the threes' first two (5), then the third (6); straight down's own sum and
    // |old - new| beside them
    reg [68:0]  m1a [0:1], m1c [0:1], m2 [0:1];
    reg [45:0]  m3 [0:1];
    reg [22:0]  m4 [0:1];
    reg [18:0]  z3 [0:1], z4 [0:1], z5 [0:1], z6 [0:1];     // {its sum, its |old - new|}
    // stage 7: the offsets
    reg signed [3:0] ed [0:1];
    // stage 8: the pixels taken (old's and new's along the offset, and straight above and below),
    // the chroma pairs; stage 9: the word: s1_bob (with the pair's other things in s1_*)
    reg [31:0]  ey [0:1];
    reg [31:0]  ec8 [0:1];
    integer     ei, ej, et, eg;
    reg [22:0]  e_c [0:8];
    reg [12:0]  e_3b;
    reg signed [3:0] e_d, e_dq;
    function signed [3:0] half(input signed [3:0] d);
        half = d == -4'sd4 ? -4'sd2 : d <= -4'sd2 ? -4'sd1 : d == 4'sd4 ? 4'sd2 : d >= 4'sd2 ? 4'sd1 : 4'sd0;
    endfunction
    function [7:0] hold8(input [7:0] v, input [7:0] a, input [7:0] b);
        hold8 = v < (a < b ? a : b) ? (a < b ? a : b) : v > (a < b ? b : a) ? (a < b ? b : a) : v;
    endfunction
    always @(posedge clk) begin
        // 1
        for (ej = -4; ej <= 4; ej = ej + 1)
            for (ei = 4; ei <= 9; ei = ei + 1)
                ad[8 * (6 * (ej + 4) + ei - 4) +: 8] <= absd(wa[8 * (ei + ej) +: 8], wb[8 * (ei - ej) +: 8]);
        wad[1] <= wa;
        wbd[1] <= wb;
        cad[1] <= ca;
        cnd[1] <= cn;
        for (ei = 2; ei <= 7; ei = ei + 1) begin
            wad[ei] <= wad[ei - 1];
            wbd[ei] <= wbd[ei - 1];
            cad[ei] <= cad[ei - 1];
            cnd[ei] <= cnd[ei - 1];
        end
        sided <= {sided[5:0], s0_side};
        // 2
        for (et = 0; et < 2; et = et + 1)
            for (ej = -4; ej <= 4; ej = ej + 1) begin
                sm[11 * (9 * et + ej + 4) +: 11] <= {3'd0, ad[8 * (6 * (ej + 4) + et) +: 8]} + {3'd0, ad[8 * (6 * (ej + 4) + et + 1) +: 8]} +
                                                      {3'd0, ad[8 * (6 * (ej + 4) + et + 2) +: 8]} + {3'd0, ad[8 * (6 * (ej + 4) + et + 3) +: 8]} +
                                                      {3'd0, ad[8 * (6 * (ej + 4) + et + 4) +: 8]} + (ej < 0 ? -2 * ej : 2 * ej);
                adc[8 * (9 * et + ej + 4) +: 8] <= ad[8 * (6 * (ej + 4) + et + 2) +: 8];
            end
        for (et = 0; et < 2; et = et + 1) begin
            // 3, 4
            for (ej = -4; ej <= 4; ej = ej + 1)
                e_c[ord(ej)] = {sm[11 * (9 * et + ej + 4) +: 11], ord(ej), adc[8 * (9 * et + ej + 4) +: 8]};
            for (eg = 0; eg < 3; eg = eg + 1) begin
                m1a[et][23 * eg +: 23] <= least(e_c[3 * eg], e_c[3 * eg + 1]);
                m1c[et][23 * eg +: 23] <= e_c[3 * eg + 2];
                m2[et][23 * eg +: 23] <= least(m1a[et][23 * eg +: 23], m1c[et][23 * eg +: 23]);
            end
            z3[et] <= {sm[11 * (9 * et + 4) +: 11], adc[8 * (9 * et + 4) +: 8]};
            z4[et] <= z3[et];
            // 5, 6
            m3[et] <= {m2[et][68:46], least(m2[et][22:0], m2[et][45:23])};
            z5[et] <= z4[et];
            m4[et] <= least(m3[et][22:0], m3[et][45:23]);
            z6[et] <= z5[et];
            // 7: used where it is clearly under straight down's and its own two pixels are no less
            // alike than those; not at the picture's sides; not without edi
            e_3b = {2'd0, m4[et][22:12]} + {1'b0, m4[et][22:12], 1'b0};
            ed[et] <= edi && !sided[5] && e_3b < {1'b0, z6[et][18:8], 1'b0} && m4[et][7:0] <= z6[et][7:0] ? dof(m4[et][11:8]) : 4'sd0;
            // 8
            e_d = ed[et];
            ey[et] <= {wad[7][8 * (6 + et + e_d) +: 8], wbd[7][8 * (6 + et - e_d) +: 8], wad[7][8 * (6 + et) +: 8], wbd[7][8 * (6 + et) +: 8]};
        end
        e_dq = half(ed[0]);                     // (towards straight down)
        for (et = 0; et < 2; et = et + 1)       // (0: Cb, the pairs' upper byte; 1: Cr)
            ec8[et] <= {cad[7][16 * (2 + e_dq) + 8 * (1 - et) +: 8], cnd[7][16 * (2 - e_dq) + 8 * (1 - et) +: 8],
                        cad[7][16 * 2 + 8 * (1 - et) +: 8], cnd[7][16 * 2 + 8 * (1 - et) +: 8]};
        // 9
        s1_bob <= {hold8(mean(ec8[0][31:24], ec8[0][23:16]), ec8[0][15:8], ec8[0][7:0]),
                   hold8(mean(ey[0][31:24], ey[0][23:16]), ey[0][15:8], ey[0][7:0]),
                   hold8(mean(ec8[1][31:24], ec8[1][23:16]), ec8[1][15:8], ec8[1][7:0]),
                   hold8(mean(ey[1][31:24], ey[1][23:16]), ey[1][15:8], ey[1][7:0])};
    end

    always @(posedge clk) begin
        start_clr <= 1'b0;
        fstart <= 1'b0;
        buf_we <= 1'b0;
        s0_v <= 1'b0;
        // (what goes with the pair through the edges' stages: its place, P1's word, the word
        // that is as it is, the three a)
        pv <= {pv[6:0], s0_v};
        pd0 <= {wvp, v0g, v1g, v0g > v1g ? v0g : v1g, s0_wa, ww, pc ? wn : wo, a_y0, a_y1, a_c};
        pd1 <= pd0;
        pd2 <= pd1;
        pd3 <= pd2;
        pd4 <= pd3;
        pd5 <= pd4;
        pd6 <= pd5;
        pd7 <= pd6;
        s1_v <= pv[7];
        {s1_wv, s1_v0, s1_v1, s1_vc, s1_wa, s1_w, s1_d, s1_ay0, s1_ay1, s1_ac} <= pd7;
        // (the pan's word against the mean, by its a; then P1's own against that, by a)
        s2_v <= s1_v;
        s2_wa <= s1_wa;
        s2_w <= s1_w;
        s2_d <= s1_d;
        {s2_ay0, s2_ay1, s2_ac} <= {s1_ay0, s1_ay1, s1_ac};
        s2_x <= {blend(s1_wv[31:24], s1_bob[31:24], s1_vc), blend(s1_wv[23:16], s1_bob[23:16], s1_v0),
                 blend(s1_wv[15:8], s1_bob[15:8], s1_vc), blend(s1_wv[7:0], s1_bob[7:0], s1_v1)};
        r_we <= s2_v;
        rdv <= b_rvalid;
        rdq <= rd_data;
        if (rdv)
            rx <= rx + 3'd1;
        // (pgf: the two lines of the one frame, in turn the one first and the other: the memory's row
        // changes once for sixteen pixels, not twice)
        rde <= rdv && !in_p2 ? 4'd1 << (pgf ? {rx[0] ^ c[0], 1'b0} : rx[1:0]) : 4'd0;
        rdq2 <= rdq;
        // (the pan's pass: the words come back in the order asked: the lowest still owed)
        rde2 <= rdv && in_p2 ? pend & ~(pend - 4'd1) : 4'd0;
        if (rdv && in_p2)
            pend <= pend & (pend - 4'd1);
        mc_we <= 1'b0;
        if (rde2[0])
            d0 <= rdq2;
        if (rde2[1])
            hi2 <= rdq2;
        if (rde2[2])
            hi1 <= rdq2;
        if (rde2[3])
            hi3 <= rdq2;
        if (rde[0])
            d0 <= rdq2;
        if (rde[1])
            d1 <= rdq2;
        if (rde[2])
            d2 <= rdq2;
        if (rde[3])
            d3 <= rdq2;
        case (st)
            S_IDLE:
                if (start && !start_clr) begin
                    start_clr <= 1'b1;
                    fstart <= 1'b1;
                    frames <= frames + 16'd1;
                    ll_used <= ll_now;
                    pgf <= pg;
                    nchf <= nch;
                    if (pg) begin
                        fc <= ll_now ? nxt : latest;
                        f1 <= ll_now ? nxt : latest;
                        pc <= 1'b1;
                        hist <= 1'b0;
                    end else if (ll_now) begin
                        fc <= nxt;
                        f1 <= latest;
                        f2 <= latest - 3'd1;
                        f3 <= latest - 3'd2;
                        pc <= par[latest] == top_f;         // (the field coming in: the other parity)
                        hist <= 1'b1;
                    end else begin
                        fc <= latest;
                        f1 <= latest - 3'd1;
                        f2 <= latest - 3'd2;
                        f3 <= latest - 3'd3;
                        pc <= par[latest] != top_f;
                        hist <= hist_n;
                    end
                    nl <= flines;
                    k <= 10'd0;
                    emitted <= 10'd0;
                    active <= nfields != 3'd0;
                    // (the pan: with the fields' history, in the motion adaptive mode, dyr even)
                    mc_f <= mv[10] && !mv[6] && !pg && mode == 2'd0 && (ll_now || hist_n);
                    dxf <= mv[5:0];
                    dyf <= mv[9:6];
                end else if (can && !start_clr && !fstart) begin
                    c <= 7'd0;
                    i <= 3'd0;
                    rx <= 3'd0;
                    carry <= 8'd0;
                    carry_v <= 8'd0;
                    st <= mc_f ? S_P0 : S_GO;
                end
            // ---- the pan's pass: the sixteens of the line in turn, from the ones before its first ----
            S_P0: begin
                cc <= -8'sd1;
                {lo2k, hi2k, lo1k, hi1k, lo3k, hi3k} <= 6'd0;
                in_p2 <= 1'b1;
                st <= S_PA;
            end
            S_PA: begin                             // what is read: C's new, P2's, P1's, P3's (if they are in the field)
                need <= {ok3 && g3k, ok1 && g1k, ok2 && g2k, !cc[7]};
                pend <= {ok3 && g3k, ok1 && g1k, ok2 && g2k, !cc[7]};
                {hi3k, hi1k, hi2k} <= {ok3 && g3k, ok1 && g1k, ok2 && g2k};
                st <= S_PRQ;
            end
            S_PRQ:
                if (need == 4'd0) begin
                    if (!b_valid)
                        st <= S_PW;
                    else if (b_ack) begin
                        b_valid <= 1'b0;
                        st <= S_PW;
                    end
                end else if (!b_valid || b_ack) begin
                    b_valid <= 1'b1;
                    b_line <= need[0] ? {fc, 5'd0, row_new, cc[6:0]} : need[1] ? {f2, 5'd0, row2[9:0], g2[6:0]} :
                              need[2] ? {f1, 5'd0, row1[9:0], g1[6:0]} : {f3, 5'd0, row3[9:0], g3[6:0]};
                    need <= need & (need - 4'd1);       // (the lowest of them asked for)
                end
            S_PW:
                if (pend == 4'd0)
                    st <= S_PW2;
            S_PW2:
                st <= S_PX1;
            S_PX1:
                st <= S_PX2;
            S_PX2:
                st <= S_PX3;
            S_PX3:
                st <= S_PX4;
            S_PX4: begin
                mc_we <= !cc[7];
                st <= S_PN;
            end
            S_PN: begin
                {lo2, lo1, lo3} <= {hi2, hi1, hi3};
                {lo2k, lo1k, lo3k} <= {hi2k, hi1k, hi3k};
                if (cc == $signed({1'b0, nchf}) - 8'sd1) begin
                    in_p2 <= 1'b0;
                    rx <= 3'd0;                     // (the pass's words were counted too)
                    st <= S_GO;
                end else begin
                    cc <= cc + 8'sd1;
                    st <= S_PA;
                end
            end
            S_GO:
                st <= S_RQ;
            S_RQ: begin                             // the four reads: C new, P2 new, P1, P3
                if (i == 3'd4) begin
                    if (b_ack) begin
                        b_valid <= 1'b0;
                        st <= S_WAIT;
                    end
                end else if (!b_valid || b_ack) begin
                    b_valid <= 1'b1;
                    b_line <= {i == 3'd0 ? fc : i == 3'd1 ? f2 : i == 3'd2 ? f1 : f3, 5'd0,
                               (pgf ? i[1] ^ c[0] : i[1]) ? row_w : row_new, c};
                    i <= i + (pgf ? 3'd2 : 3'd1);        // (pgf: the two lines of the one frame)
                end
            end
            S_WAIT:
                if (rx == (pgf ? 3'd2 : 3'd4))
                    st <= S_C1;
            // (the differences, the greatest of them and those with the pixels beside are worked out
            // below, a clock each, from the lines read and the buffers: both stay as they are until
            // the step is over)
            S_C1:
                st <= S_C1B;
            S_C1B:
                st <= S_C1C;
            S_C1C:
                st <= S_C1D;
            S_C1D:
                st <= S_C2;
            S_C2:                                   // (carry is still the sixteen pixels before's)
                st <= S_C2A;
            S_C2A: begin
                carry <= m[8 * 15 +: 8];
                carry_v <= mq[256 + 8 * 15 +: 8];
                st <= S_C2B;
            end
            S_C2B: begin
                for (n = 0; n < 16; n = n + 1) begin
                    t_m = md[8 * n +: 8];
                    t_d = t_m > thr ? t_m - thr : 8'd0;
                    al[5 * n +: 5] <= pgf ? 5'd0 : mode == 2'd1 || (!hist && mode != 2'd2) ? 5'd16 : mode == 2'd2 ? 5'd0 :
                                      t_d > 8'd16 ? 5'd16 : t_d[4:0];
                    // (the pan's a, the same way from its differences; 16 without it: the mean)
                    t_m = mdv[8 * n +: 8];
                    t_d = t_m > thr ? t_m - thr : 8'd0;
                    alv[5 * n +: 5] <= !mc_f || t_d > 8'd16 ? 5'd16 : t_d[4:0];
                end
                p <= 4'd0;
                st <= S_E0;
            end
            // (the sixteen pixels just read are the ones after the sixteen now made: old and new
            // as they are used; then the ones made, if there are some: not at a line's first)
            S_E0: begin
                eO2 <= o_used;
                eN2 <= n_used;
                elast <= 1'b0;
                st <= emit && c != 7'd0 ? S_WL : S_SH;
            end
            // (on by sixteen; a line's last sixteen are made here, with none after them)
            S_SH: begin
                eO0 <= eO1;
                eO1 <= eO2;
                eN0 <= eN1;
                eN1 <= eN2;
                eW <= nrw;
                eAL <= al;
                eWV <= mq[255:0];
                eALV <= alv;
                ec <= c;
                p <= 4'd0;
                if (emit && c == nchf - 7'd1 && !elast) begin
                    elast <= 1'b1;
                    st <= S_SH2;
                end else
                    st <= S_NEXT;
            end
            S_SH2:
                st <= S_WL;
            // (a line's last words through the stages below before the line counts as made)
            S_FL: begin
                fl <= fl + 4'd1;
                if (fl == 4'd12)
                    st <= S_NEXT;
            end
            S_GAP:
                st <= S_GAP2;
            S_GAP2:
                st <= S_IDLE;
            S_WL: begin                             // the sixteen made, into the registers that move on
                shO <= eO1;
                shN <= eN1;
                shW <= eW;
                shWV <= eWV;
                shAL <= eAL;
                shALV <= eALV;
                shLA <= la;
                shLB <= lb;
                shKA <= ka;
                shKB <= kb;
                p <= 4'd0;
                st <= S_W;
            end
            S_W: begin
                s0_v <= 1'b1;
                s0_wa <= {ec, p[2:0]};
                wo <= shO[31:0];
                wn <= shN[31:0];
                ww <= shW[31:0];
                a_y0 <= shAL[4:0];
                a_y1 <= shAL[9:5];
                wvp <= shWV[31:0];
                v_y0 <= shALV[4:0];
                v_y1 <= shALV[9:5];
                wa <= shLA[8 * 10 +: 112];
                wb <= shLB[8 * 10 +: 112];
                ca <= shKA[16 * 6 +: 80];
                cn <= shKB[16 * 6 +: 80];
                shO <= {32'd0, shO[255:32]};
                shN <= {32'd0, shN[255:32]};
                shW <= {32'd0, shW[255:32]};
                shWV <= {32'd0, shWV[255:32]};
                shAL <= {10'd0, shAL[79:10]};
                shALV <= {10'd0, shALV[79:10]};
                shLA <= {16'd0, shLA[383:16]};
                shLB <= {16'd0, shLB[383:16]};
                shKA <= {16'd0, shKA[383:16]};
                shKB <= {16'd0, shKB[383:16]};
                s0_side <= (ec == 7'd0 && p[2:0] < 3'd3) || (ec == nchf - 7'd1 && p[2:0] > 3'd4);
                p <= p + 4'd1;
                fl <= 4'd0;
                if (p == 4'd7)
                    st <= elast ? S_FL : S_SH;
            end
            S_NEXT: begin
                buf_we <= new_ok;                   // new's line and differences kept for the next step
                buf_a <= c;
                buf_c <= nrc;
                buf_m <= dn;
                if (c == nchf - 7'd1) begin
                    k <= k + 10'd1;
                    if (emit)
                        emitted <= emitted + 10'd2;
                    st <= S_GAP;                    // (two clocks: lstream.v's hold follows emitted)
                end else begin
                    c <= c + 7'd1;
                    i <= 3'd0;
                    rx <= 3'd0;
                    st <= S_RQ;
                end
            end
            default:
                st <= S_IDLE;
        endcase
        // C1 to C2B's work, a clock each (not held by the state)
        for (n = 0; n < 16; n = n + 1) begin
            dnr[8 * n +: 8] <= absd(luma(d0, n), luma(d1, n));
            dwr[8 * n +: 8] <= absd(luma(d2, n), luma(d3, n));
            t_dn = new_ok ? dnr[8 * n +: 8] : old_m[8 * n +: 8];
            dn[8 * n +: 8] <= t_dn;
            dor[8 * n +: 8] <= old_ok ? old_m[8 * n +: 8] : t_dn;
            mab[8 * n +: 8] <= max2(dn[8 * n +: 8], dor[8 * n +: 8]);
            dw2[8 * n +: 8] <= dwr[8 * n +: 8];
            m[8 * n +: 8] <= max2(mab[8 * n +: 8], dw2[8 * n +: 8]);
            t_l = n == 0 ? carry : m[8 * (n - 1) +: 8];
            mlc[8 * n +: 8] <= max2(t_l, m[8 * n +: 8]);
            mrr[8 * n +: 8] <= n == 15 ? m[8 * 15 +: 8] : m[8 * (n + 1) +: 8];
            md[8 * n +: 8] <= max2(mlc[8 * n +: 8], mrr[8 * n +: 8]);
            // (the pan's differences, from its pass: with the pixels beside, the same way)
            t_l = n == 0 ? carry_v : mq[256 + 8 * (n - 1) +: 8];
            mlv[8 * n +: 8] <= max2(t_l, mq[256 + 8 * n +: 8]);
            mrv[8 * n +: 8] <= n == 15 ? mq[256 + 8 * 15 +: 8] : mq[256 + 8 * (n + 1) +: 8];
            mdv[8 * n +: 8] <= max2(mlv[8 * n +: 8], mrv[8 * n +: 8]);
        end
        // the second stage: the word made, and the word as it is
        r_wa <= s2_wa;
        r_slot_d <= line_d[2:0];
        r_slot_i <= line_i[2:0];
        r_wd_d <= s2_d;
        r_wd_i <= {blend(s2_w[31:24], s2_x[31:24], s2_ac), blend(s2_w[23:16], s2_x[23:16], s2_ay0),
                   blend(s2_w[15:8], s2_x[15:8], s2_ac), blend(s2_w[7:0], s2_x[7:0], s2_ay1)};
        state_o <= {active, hist, pc, ll_used, st[3:0]};
    end
endmodule
