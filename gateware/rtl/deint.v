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
//   m' = max(m of the pixel before, m, m of the pixel after)
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
// stay so: the CPU's frame lock); a line of C is waited for if it is not in yet (a step wants the
// line after its new one too).
//
// At the picture's edge the missing one of old, new is the other.  mode 1: bob everywhere; 2: weave
// everywhere; bob too until four fields of alternating parity are there (hist).  top_f: the F of
// the top field.
//
// edi: the mean of old and new (bob) is taken along the picture's edges instead of straight down
// (sim/model.py edge_line(): for each pixel the offset d of -4 to 4 for which old at x + d and new
// at x - d are most alike, by a sum over five columns; used only where it clearly beats straight
// down and its own two pixels are alike enough; the result held between the pixels straight above
// and below; the chroma goes the way of its pair's first pixel, half as far).
//
// mc: motion compensation.  Each block of eight pixels of each line made has a vector (dx, dyr):
// what is at (x, row) of a field is at (x + dx, row + dyr) of the field two before (the same
// lines).  Where the picture moves and is that (C against P2 moved by (dx, dyr) on old and new, P1
// moved by half of it against P3 moved by three halves, at the line itself: as m, with thr), the
// line made is P1's moved by half of it (half a pixel: the mean of two), not the mean of old and
// new: the picture as it was drawn.  dyr even only (the field before has no line at half a line);
// a block that does not move has none of it.
//
// The vectors are found here, a line at a time (sim/model.py me_line()): each block tries six:
// its own of the line above; a neighbour's of the line above (left and right in turn); no move, or
// the frame's pan (mv: {it is known, dyr 4 bits, dx 6 bits, signed}, as the CPU found it: in turn);
// one of all the vectors there are (a different one each line and block); its own nudged, twice.
// Each is scored by the sum of |C - P2 moved| over the block's eight pixels in C's four rows about
// the line made, and a small penalty; the least wins, the first of equals.  A frame's first line
// begins from the pan (or no move).  first: no vectors for lines made before this one (a part of
// the picture shown: its lines above are not seen, and are wanted fast).
//
// pg: what comes in is progressive: each field in the memory is a whole frame, and the frame made
// is the newest one's lines as they are, two a step (line 2k + 1 read as C's, line 2k in P1's
// place and taken as it is: weave, no noise reduction); with ll, the one coming in.
//
// How: the fields' rows are read from the DDR3 whole, into line buffers (a RAM a row; a window of
// rows of each field around the step's: C 4, P1 N1, P2 N2, P3 N3: the rows the vectors can reach; a row
// r in the buffer r mod N), each row once; then the step's passes go through them, a pair of
// pixels (a word) a clock:
//   - the load: the rows the step's windows still want, a DDR3 line (16 pixels) at a time, the four
//     fields' in turn; a line's eight words are written a clock each (deint_fill)
//   - the estimator's pass (mc): for each block six times five words of P2's four rows at the
//     candidate's place, and C's; the sums; the least's vector kept (vec)
//   - the vectors' pass (mc), by the blocks: C's old and new, P2's two rows, P1's and P3's at the
//     moved places (five words of each: the block may begin at an odd pixel, and half a pixel
//     wants one more); the differences' greatest and P1's moved words go to a RAM (vram)
//   - the output's pass: the words of all the rows at the place itself, the noise reduction, the
//     motion, the edges, the blends; the two lines' words out (r_*)
//
// The lines go to lstream.v's store of four, a word of each of two lines together (the one as it
// is, D, and the one made, I: r_*: a line's place its number's low bits); emitted: the frame's
// lines all there; fstart: a clock at a frame's start.  hold: no new step (the store's lines are
// not read out yet).  The output asks by ev (a change: an event): ev_first with it: a new frame.
// goal (this clock's): lines are made while emitted <= goal.
//
// A step k has C's line k as new and line k - 1 as old, and makes
//   C a top field     (k >= 1) D = line 2(k-1) = old, I = line 2(k-1)+1, P1's line k-1
//   C a bottom field  I = line 2k, P1's line k; D = line 2k+1 = new

// a RAM of 512 words; read: the word two clocks after its address (the rows' buffers are bram.v's
// bram32: the same, a row in one block RAM; no read while a row is written)
module deint_ram #(
    parameter W = 32
) (
    input              clk,
    input              we,
    input      [8:0]   wa,
    input      [W-1:0] wd,
    input      [8:0]   ra,
    output reg [W-1:0] q
);
    reg [W-1:0] mem [0:511];
    reg [W-1:0] q0;
    always @(posedge clk) begin
        if (we)
            mem[wa] <= wd;
        q0 <= mem[ra];
        q <= q0;
    end
endmodule

// a row's words written as its DDR3 lines come: a line being written (eight clocks) and one more
// held; room: another may be asked for (two asked for and not written out at most)
module deint_fill (
    input              clk,
    input              start,           // a row begins (nothing of one before is left)
    input      [9:0]   nw,              // its words
    input              asked,           // a line of it was asked for
    output             room,
    input              push,            // a line of it is here
    input      [255:0] d,
    output reg         we = 1'b0,
    output reg [9:0]   wa,
    output reg [31:0]  wd,
    output reg         done = 1'b0      // (a clock) the row's last word is being written
);
    reg [1:0]   held = 2'd0;
    reg         hv = 1'b0, busy = 1'b0;
    reg [255:0] hb, wb;
    reg [2:0]   j;
    reg [9:0]   n;
    wire        last = j == 3'd7;
    assign room = !held[1];
    always @(posedge clk) begin
        we <= 1'b0;
        done <= 1'b0;
        if (start) begin
            n <= 10'd0;
            held <= 2'd0;
            hv <= 1'b0;
            busy <= 1'b0;
        end else begin
            held <= held + {1'b0, asked} - {1'b0, busy && last};
            if (busy) begin
                we <= 1'b1;
                wa <= n;
                wd <= wb[31:0];
                wb <= {32'd0, wb[255:32]};
                n <= n + 10'd1;
                j <= j + 3'd1;
                if (last) begin
                    done <= n + 10'd1 == nw;
                    if (hv) begin
                        wb <= hb;
                        hv <= 1'b0;
                    end else if (push)
                        wb <= d;
                    else
                        busy <= 1'b0;
                end
            end else if (push) begin
                wb <= d;
                busy <= 1'b1;
                j <= 3'd0;
            end
            if (push && busy && !(last && !hv)) begin
                hb <= d;
                hv <= 1'b1;
            end
        end
    end
endmodule

module deint #(
    parameter N1 = 5,                   // P1's rows kept: the line's own and two each way
    parameter N2 = 12,                  // P2's: the four about the line made, and four each way
    parameter N3 = 13                   // P3's: the line's own and six each way
) (
    input              clk,
    input      [6:0]   nch,             // DDR3 lines (16 pixels) a line of picture (45: 720; 80: 1280)
    input              pg,              // a progressive picture: a field is a frame (above)
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
    input              mc,              // motion compensation
    input      [10:0]  mv,              // the picture's pan: {known, dyr, dx}
    input      [9:0]   first,           // no vectors for the lines made before this one
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

    localparam S_IDLE = 0, S_LD = 1, S_LDW = 2, S_V = 3, S_VW = 4, S_O = 5, S_OW = 6, S_NEXT = 7,
               S_MP = 8, S_M = 9, S_MW = 10, S_GAP = 11, S_GAP2 = 12, S_VP = 13;
    reg [3:0]  st = S_IDLE;
    reg        active = 1'b0, pc, hist, ll_used = 1'b0;
    // (pg and nch as they were when the frame was begun: a change of them in the middle of a step
    // must not leave it waiting for lines it did not ask for: seen on the board, 2026-11-12)
    reg        pgf = 1'b0;
    reg [6:0]  nchf = 7'd45;
    wire [9:0] nw = {nchf, 3'b000};     // a row's words
    wire [10:0] wpix = {nchf, 4'b0000}; // its pixels
    // (a frame from the field coming in: four fields before it in order, and enough of it there)
    wire [2:0] nxt = latest + 3'd1;
    wire       ll_now = pg ? ll && nfields != 3'd0 && prog_slot == nxt && prog >= {2'd0, ll_min} :
                        ll && nfields >= 3'd4 && prog_slot == nxt && prog >= {2'd0, ll_min} &&
                        par[latest - 3'd1] != par[latest] && par[latest - 3'd2] == par[latest];
    wire       hist_n = nfields >= 3'd4 && par[latest - 3'd1] != par[latest] &&
                        par[latest - 3'd2] == par[latest] && par[latest - 3'd3] != par[latest];
    reg        line_ok = 1'b1;          // (C's lines of this step are in the memory)
    reg [2:0]  fc, f1, f2, f3;          // the fields' slots
    reg [9:0]  nl;                      // a field's lines
    reg [9:0]  k;                       // the step
    reg [3:0]  km1, km2, km3;           // k mod N1, N2, N3

    // a row's buffer: row + o's, from k mod n (o within a ring of n either way)
    function [3:0] wrap(input [3:0] km, input signed [4:0] o, input integer n);
        reg signed [6:0] t;
        begin
            t = $signed({3'b000, km}) + o;
            if (t < 0)
                t = t + n;
            else if (t >= n)
                t = t - n;
            wrap = t[3:0];
        end
    endfunction
    // the last row a window wants: r, or the field's last
    function [10:0] head(input [10:0] r, input [9:0] n);
        head = r < {1'b0, n} ? r : {1'b0, n} - 11'd1;
    endfunction

    // the motion compensation, as the frame has it: on; the pan (known, and what); the first line
    reg                mc_f = 1'b0, pan_k = 1'b0;
    reg signed [5:0]   dxf = 6'sd0;
    reg signed [3:0]   dyf = 4'sd0;
    reg [9:0]          firstf = 10'd0;
    reg                vfirst = 1'b0;                           // (no line of this frame has vectors yet)
    wire [9:0]         pz = pan_k ? {dyf, dxf} : 10'd0;        // what the vectors begin from
    wire signed [4:0]  ow = pc ? 5'sd0 : -5'sd1;                // the line's own row of P1, from k
    wire [7:0]         nblk = {nchf, 1'b0};                     // a line's blocks of eight pixels

    // the step's lines (registered: k changes between steps only, clocks before they are used)
    wire [9:0] kmax = pgf ? {1'b0, nl[9:1]} - 10'd1 : pc ? nl - 10'd1 : nl;
    wire [9:0] row_w = pc ? k : k - 10'd1;
    wire       new_w = pgf || k < nl, old_w = k != 10'd0;
    wire [9:0] line_i_w = pc ? {k[8:0], 1'b0} : {k[8:0] - 9'd1, 1'b1};
    reg        new_ok, old_ok;
    reg        mc_s = 1'b0;             // the step has vectors
    reg [9:0]  line_i, line_d;
    reg        can = 1'b0;              // a step may start (a clock behind what it is made from)
    reg [10:0] hC, h1, h2, h3;          // the windows' last rows
    reg [1:0]  sCA, sCB;                // the rows' buffers: C's old and new,
    reg [1:0]  sCm, sCp;                // the one before old and the one after new (the nearest in the field),
    reg [3:0]  s2A, s2B, s1W, s3W;      // P2's, P1's and P3's own
    reg [8:0]  hk;                      // 37 k (mod 512) and 3 k (mod 16): the estimator's turns
    reg [3:0]  uk;
    wire signed [11:0] nl_s = $signed({2'b00, nl});
    always @(posedge clk) begin
        line_ok <= !ll_used || latest == fc ||
                   (prog_slot == fc && (pgf ? {k[8:0], 1'b1} : head({1'b0, k} + 11'd1, nl)) < prog);
        can <= active && !hold && k <= kmax && emitted <= goal && line_ok;
        new_ok <= new_w;
        old_ok <= old_w;
        mc_s <= mc_f && new_w && old_w && line_i_w >= firstf;
        line_i <= line_i_w;
        line_d <= pc ? {k[8:0], 1'b1} : {k[8:0] - 9'd1, 1'b0};
        hC <= head({1'b0, k} + 11'd1, nl);
        h2 <= head({1'b0, k} + 11'd5, nl);
        h1 <= head({1'b0, row_w} + 11'd2, nl);
        h3 <= head({1'b0, row_w} + 11'd6, nl);
        sCA <= old_w ? k[1:0] - 2'd1 : k[1:0];
        sCB <= new_w ? k[1:0] : k[1:0] - 2'd1;
        sCm <= k >= 10'd2 ? k[1:0] - 2'd2 : 2'd0;
        sCp <= {1'b0, k} + 11'd1 < {1'b0, nl} ? k[1:0] + 2'd1 : nl[1:0] - 2'd1;
        s2A <= wrap(km2, old_w ? -5'sd1 : 5'sd0, N2);
        s2B <= wrap(km2, new_w ? 5'sd0 : -5'sd1, N2);
        s1W <= wrap(km1, ow, N1);
        s3W <= wrap(km3, ow, N3);
    end

    function [7:0] absd(input [7:0] a, input [7:0] b);
        absd = a > b ? a - b : b - a;
    endfunction
    function [7:0] max2(input [7:0] a, input [7:0] b);
        max2 = a > b ? a : b;
    endfunction
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

    // ---- the rows' buffers ----
    // one address for a field's buffers (the passes read its rows at one place), a write to one
    reg  [8:0]  ra_c, ra_1, ra_2, ra_3;
    wire [3:0]  f_we;                   // the fields' writers: C, P1, P2, P3
    wire [39:0] f_wa;
    wire [127:0] f_wd;
    reg  [10:0] nrow [0:3];             // the next row to load
    reg  [3:0]  wsl [0:3];              // ... and its buffer
    wire [31:0] qc [0:3];
    wire [31:0] q1 [0:N1-1];
    wire [31:0] q2 [0:N2-1];
    wire [31:0] q3 [0:N3-1];
    genvar gi;
    generate
        for (gi = 0; gi < 4; gi = gi + 1) begin : g_c
            bram32 u (.clk(clk), .we(f_we[0] && (pgf ? {1'b0, f_wa[9]} : wsl[0][1:0]) == gi), .wa(f_wa[8:0]),
                      .wd(f_wd[31:0]), .ra(ra_c), .q(qc[gi]));
        end
        for (gi = 0; gi < N1; gi = gi + 1) begin : g_1
            bram32 u (.clk(clk), .we(f_we[1] && (pgf ? {3'd0, f_wa[19]} : wsl[1]) == gi), .wa(f_wa[18:10]),
                      .wd(f_wd[63:32]), .ra(ra_1), .q(q1[gi]));
        end
        for (gi = 0; gi < N2; gi = gi + 1) begin : g_2
            bram32 u (.clk(clk), .we(f_we[2] && wsl[2] == gi), .wa(f_wa[28:20]), .wd(f_wd[95:64]), .ra(ra_2), .q(q2[gi]));
        end
        for (gi = 0; gi < N3; gi = gi + 1) begin : g_3
            bram32 u (.clk(clk), .we(f_we[3] && wsl[3] == gi), .wa(f_wa[38:30]), .wd(f_wd[127:96]), .ra(ra_3), .q(q3[gi]));
        end
    endgenerate

    // ---- the load ----
    reg  [3:0]  act = 4'd0;             // a row of the field is being loaded
    reg  [9:0]  lrow [0:3];             // which
    reg  [6:0]  giss [0:3];             // its next line to ask for
    reg  [3:0]  f_start = 4'd0, f_asked = 4'd0, f_push = 4'd0;
    wire [3:0]  f_room, f_done;
    reg  [255:0] rdq, rdq2;
    reg         rdv = 1'b0;
    reg  [1:0]  pgd = 2'd0;             // (pg: the step's two rows are loaded)
    generate
        for (gi = 0; gi < 4; gi = gi + 1) begin : g_f
            deint_fill u (.clk(clk), .start(f_start[gi]), .nw(nw), .asked(f_asked[gi]), .room(f_room[gi]),
                          .push(f_push[gi]), .d(rdq2), .we(f_we[gi]), .wa(f_wa[10 * gi +: 10]),
                          .wd(f_wd[32 * gi +: 32]), .done(f_done[gi]));
        end
    endgenerate
    // whose each line asked for is (they come back in the order asked)
    reg  [31:0] tagq;
    reg  [3:0]  twp = 4'd0, trp = 4'd0;
    // a field wants a row loaded
    wire [3:0]  need = pgf ? {2'b00, !pgd[1], !pgd[0]} :
                       {nrow[3] <= h3, nrow[2] <= h2, nrow[1] <= h1, nrow[0] <= hC};
    // a line to ask for: the fields in turn
    reg  [1:0]  rr = 2'd0;
    wire [3:0]  want = {act[3] && giss[3] != nchf && f_room[3], act[2] && giss[2] != nchf && f_room[2],
                        act[1] && giss[1] != nchf && f_room[1], act[0] && giss[0] != nchf && f_room[0]};
    wire [1:0]  r1n = rr + 2'd1, r2n = rr + 2'd2, r3n = rr + 2'd3;
    wire [1:0]  pick = want[rr] ? rr : want[r1n] ? r1n : want[r2n] ? r2n : r3n;
    wire [2:0]  pick_f = pick == 2'd0 ? fc : pick == 2'd1 ? f1 : pick == 2'd2 ? f2 : f3;

    // a row's ten pixels from its five words: pixel n's luma
    function [7:0] pix(input [159:0] w, input [3:0] n);
        reg [31:0] t;
        begin
            t = w[32 * n[3:1] +: 32];
            pix = n[0] ? t[7:0] : t[23:16];
        end
    endfunction

    // ---- the vectors: a block's {dyr, dx}; the line above's until the step's estimator writes its own ----
    reg  [9:0]  vec [0:255];
    reg  [7:0]  vec_ra;
    wire [9:0]  vec_q = vec[vec_ra];
    reg         vec_we = 1'b0;
    reg  [7:0]  vec_wa;
    reg  [9:0]  vec_wd;
    always @(posedge clk)
        if (vec_we)
            vec[vec_wa] <= vec_wd;

    // ---- the estimator's pass ----
    // a block's six candidates in turn, five words of P2's four rows for each: the candidate
    // (cdx, cdy; cok: it is one) is worked out the clock before its first word is asked for, from
    // the line above's vectors about the block (wm1, w0, wp1: the block before's, its own, the
    // next's)
    reg  [7:0]  mb;                     // the block
    reg  [2:0]  mcd;                    // the candidate
    reg  [2:0]  mi;                     // the word of its five
    reg  [9:0]  wm1, w0, wp1;
    reg  [8:0]  hb;                     // 37 k + 101 b (mod 512)
    reg  [3:0]  ub;                     // 3 k + 5 b (mod 16)
    reg signed [5:0] cdx;
    reg signed [3:0] cdy;
    reg         cok;
    reg signed [7:0] pdx;                // (the next one, a clock or two before: what it is; then whether it may be)
    reg signed [5:0] pdy;
    reg         pso;
    // the nudges: {dyr 3 bits, dx 4 bits} (signed)
    function [6:0] ups(input [3:0] i);
        case (i)
            4'd0: ups = {3'sd0, 4'sd1};
            4'd1: ups = {3'sd0, -4'sd1};
            4'd2: ups = {3'sd1, 4'sd0};
            4'd3: ups = {-3'sd1, 4'sd0};
            4'd4: ups = {3'sd0, 4'sd2};
            4'd5: ups = {3'sd0, -4'sd2};
            4'd6: ups = {3'sd0, 4'sd3};
            4'd7: ups = {3'sd0, -4'sd3};
            4'd8: ups = {3'sd1, 4'sd1};
            4'd9: ups = {-3'sd1, -4'sd1};
            4'd10: ups = {3'sd0, 4'sd4};
            4'd11: ups = {3'sd0, -4'sd4};
            4'd12: ups = {3'sd2, 4'sd0};
            4'd13: ups = {-3'sd2, 4'sd0};
            4'd14: ups = {-3'sd1, 4'sd1};
            default: ups = {3'sd1, -4'sd1};
        endcase
    endfunction
    // the next candidate (of this block, or the next block's first: adv)
    wire        adv = mcd == 3'd5;
    wire [7:0]  n_b = adv ? mb + 8'd1 : mb;
    wire [2:0]  n_cd = adv ? 3'd0 : mcd + 3'd1;
    wire [9:0]  n_own = vfirst ? pz : adv ? wp1 : w0;
    wire [9:0]  n_left = vfirst ? pz : adv ? w0 : wm1;
    wire [9:0]  n_right = vfirst ? pz : adv ? vec_q : wp1;
    wire [8:0]  n_hb = adv ? hb + 9'd101 : hb;
    wire [3:0]  n_ub = adv ? ub + 4'd5 : ub;
    wire [1:0]  n_kb = k[1:0] + n_b[1:0];
    wire        n_side_ok = n_kb[0] ? n_b + 8'd1 != nblk : n_b != 8'd0;
    wire [9:0]  n_side = n_kb[0] ? n_right : n_left;
    wire [6:0]  n_up = ups(n_ub + (n_cd == 3'd5 ? 4'd7 : 4'd0));
    wire signed [7:0] n_ux = $signed(n_own[5:0]) + $signed(n_up[3:0]);
    wire signed [5:0] n_uy = $signed(n_own[9:6]) + $signed(n_up[6:4]);
    reg signed [7:0] n_dx;
    reg signed [5:0] n_dy;
    always @(*)
        case (n_cd)
            3'd0: begin n_dx = $signed(n_own[5:0]); n_dy = $signed(n_own[9:6]); end
            3'd1: begin n_dx = $signed(n_side[5:0]); n_dy = $signed(n_side[9:6]); end
            3'd2: begin n_dx = n_kb[1] ? $signed(pz[5:0]) : 8'sd0; n_dy = n_kb[1] ? $signed(pz[9:6]) : 6'sd0; end
            3'd3: begin
                n_dx = $signed({~n_hb[5], n_hb[4:0]});
                n_dy = n_hb[8:6] == 3'd0 || n_hb[8:6] == 3'd5 ? -6'sd4 : n_hb[8:6] == 3'd1 || n_hb[8:6] == 3'd6 ? -6'sd2 :
                       n_hb[8:6] == 3'd3 ? 6'sd2 : n_hb[8:6] == 3'd4 ? 6'sd4 : 6'sd0;
            end
            default: begin n_dx = n_ux; n_dy = n_uy; end
        endcase
    wire signed [12:0] n_x = $signed({2'b00, n_b, 3'b000}) + pdx;       // the block's first pixel, moved
    wire        n_ok = pso && pdx >= -8'sd31 && pdx <= 8'sd31 && pdy >= -6'sd4 && pdy <= 6'sd4 &&
                       n_x >= 13'sd0 && n_x + 13'sd8 <= $signed({2'b00, wpix});
    // the token through the stages: {valid, word, candidate, block, dx, dyr, it is a candidate}; the
    // four rows' buffers; whether they are in the field
    reg  [25:0] mta = 26'd0, mtb = 26'd0, mtc = 26'd0, mtd = 26'd0;
    reg  [15:0] msa, msb, msc;
    reg  [3:0]  mka, mkb, mkc, mkd;
    wire signed [12:0] m_x = $signed({2'b00, mb, 3'b000}) + cdx;
    wire signed [4:0]  cdy5 = {cdy[3], cdy};
    wire signed [11:0] m_r = $signed({2'b00, k}) + cdy;                 // new's row, moved
    // d: the four rows of P2 and of C; the block's first four words of each kept
    reg  [31:0] m2r [0:3], mcr [0:3];
    reg  [127:0] ms2 [0:3], msw [0:3];
    // e1: the block's pixels; e2: their differences; e3: the rows' sums; e4: the sum, with the
    // candidate's penalty; then the least
    reg  [22:0] me1 = 23'd0, me2 = 23'd0, me3 = 23'd0, me4 = 23'd0;    // {valid, candidate, block, dx, dyr, ok}
    reg  [3:0]  mk1, mk2;
    reg  [63:0] mp2 [0:3], mcp [0:3], mad [0:3];
    reg  [10:0] mrs [0:3];
    reg  [12:0] mct, bestc;
    reg         bestn = 1'b1, mfin = 1'b0;
    reg  [9:0]  bestv;
    reg  [7:0]  mfb;
    integer     mr, mj;
    reg  [159:0] m_w;
    always @(posedge clk) begin
        mtb <= mta;
        mtc <= mtb;
        mtd <= mtc;
        msb <= msa;
        msc <= msb;
        {mkb, mkc, mkd} <= {mka, mkb, mkc};
        for (mr = 0; mr < 4; mr = mr + 1) begin
            m2r[mr] <= q2[msc[4 * mr +: 4]];
            if (mtd[25] && mtd[24:22] != 3'd4) begin
                ms2[mr][32 * mtd[23:22] +: 32] <= m2r[mr];
                msw[mr][32 * mtd[23:22] +: 32] <= mcr[mr];
            end
            // e1 (the candidate's fifth word is here)
            m_w = {m2r[mr], ms2[mr]};
            for (mj = 0; mj < 8; mj = mj + 1) begin
                mp2[mr][8 * mj +: 8] <= pix(m_w, mj + mtd[5]);
                mcp[mr][8 * mj +: 8] <= mj % 2 ? msw[mr][32 * (mj / 2) +: 8] : msw[mr][32 * (mj / 2) + 16 +: 8];
                // e2
                mad[mr][8 * mj +: 8] <= absd(mcp[mr][8 * mj +: 8], mp2[mr][8 * mj +: 8]);
            end
            // e3 (a row outside the field: 512)
            mrs[mr] <= !mk2[mr] ? 11'd512 :
                       {3'd0, mad[mr][7:0]} + {3'd0, mad[mr][15:8]} + {3'd0, mad[mr][23:16]} + {3'd0, mad[mr][31:24]} +
                       {3'd0, mad[mr][39:32]} + {3'd0, mad[mr][47:40]} + {3'd0, mad[mr][55:48]} + {3'd0, mad[mr][63:56]};
        end
        mcr[0] <= qc[sCm];
        mcr[1] <= qc[sCA];
        mcr[2] <= qc[sCB];
        mcr[3] <= qc[sCp];
        me1 <= {mtd[25] && mtd[24:22] == 3'd4, mtd[21:0]};
        mk1 <= mkd;
        me2 <= me1;
        mk2 <= mk1;
        me3 <= me2;
        // e4 (the penalties: 0, 2, 2, 6, 4, 4)
        me4 <= me3;
        mct <= {2'd0, mrs[0]} + {2'd0, mrs[1]} + {2'd0, mrs[2]} + {2'd0, mrs[3]} +
               (me3[21:19] == 3'd0 ? 13'd0 : me3[21:19] == 3'd3 ? 13'd6 : me3[21:19] >= 3'd4 ? 13'd4 : 13'd2);
        // the least: the block's first candidate begins it (none: no move); the last ends it
        mfin <= 1'b0;
        if (me4[22]) begin
            if (me4[21:19] == 3'd0) begin
                bestn <= !me4[0];
                bestc <= mct;
                bestv <= me4[0] ? {me4[4:1], me4[10:5]} : 10'd0;
            end else if (me4[0] && (bestn || mct < bestc)) begin
                bestn <= 1'b0;
                bestc <= mct;
                bestv <= {me4[4:1], me4[10:5]};
            end
            mfin <= me4[21:19] == 3'd5;
            mfb <= me4[18:11];
        end
        vec_we <= mfin;
        vec_wa <= mfb;
        vec_wd <= bestv;
    end

    // ---- the vectors' pass ----
    // a block of eight pixels, five words of each row read: the token through the stages
    reg  [7:0]  vb;                     // the block
    reg  [2:0]  vi;                     // the word of its five
    reg  [9:0]  vvec;                   // its vector
    wire signed [5:0]  bdx = vvec[5:0];
    wire signed [3:0]  bdy = vvec[9:6];
    wire signed [5:0]  bsh1 = bdx >>> 1;                        // P1's pixels over (and half a pixel: bdx[0])
    wire signed [6:0]  bsh3 = {bdx[5], bdx} + {bsh1[5], bsh1};  // P3's
    wire signed [3:0]  bdyh = bdy >>> 1;
    wire signed [4:0]  bdy5 = {bdy[3], bdy}, bdyh5 = {bdyh[3], bdyh};
    wire        buse = !bdy[0] && vvec != 10'd0;                // (dyr even, and the block moves)
    wire signed [11:0] rn_w = $signed({2'b00, k}) + bdy;
    wire signed [11:0] ro_w = $signed({2'b00, k}) - 12'sd1 + bdy;
    wire signed [11:0] r1_w = $signed({2'b00, row_w}) + bdyh;
    wire signed [11:0] r3_w = $signed({2'b00, row_w}) + bdyh + bdy;
    reg  [11:0] vta = 12'd0, vtb = 12'd0, vtc = 12'd0, vtd = 12'd0;   // {valid, word, block}
    // with it: {the vector is used, dx, the buffers of P2's row for new, for old, of P1's, of P3's,
    // and whether those rows are in the field}
    reg  [26:0] vxa, vxb, vxc, vxd;
    wire [10:0] vx0 = {vb, 3'b000};     // the block's first pixel
    wire signed [12:0] vt2 = $signed({2'b00, vx0}) + bdx;
    wire signed [12:0] vt1 = $signed({2'b00, vx0}) + bsh1;
    wire signed [12:0] vt3 = $signed({2'b00, vx0}) + bsh3;
    // the rows' words, chosen
    reg  [31:0] d2n, d2o, d1v, d3v, dcn, dco;
    reg  [127:0] s2n, s2o, s1v, s3v, scn, sco;     // the block's first four words of each
    // the block's pixels: ten of each row, from its first word's first
    wire [159:0] w2n = {d2n, s2n}, w2o = {d2o, s2o}, w1v = {d1v, s1v}, w3v = {d3v, s3v};
    wire signed [5:0] ddx = vxd[25:20];
    wire signed [5:0] dsh1 = ddx >>> 1;
    wire signed [6:0] dsh3 = {ddx[5], ddx} + {dsh1[5], dsh1};
    reg         x1v = 1'b0, x2v = 1'b0, x3v = 1'b0, x1u, x2u, x3u, x1h;
    reg  [7:0]  x1b, x2b, x3b;
    reg  [63:0] p2n, p2o, cnl, col, p1a, p1b, p3a, p3b, p1v, p3v, dnv, dov, p1x, mwv, mabv;
    reg  [7:0]  k2n, k2o, k1, k3, k13, k1b, k1c;
    reg  [63:0] vch, vch2, vch3;        // P1's chroma: a pair's {Cb, Cr}
    reg  [191:0] vblk;                  // the block's four words for the RAM: {the differences' greatest of a
                                        // pair's two pixels, P1's word moved}
    reg  [2:0]  vwn = 3'd4;
    reg  [8:0]  vwa;
    reg         vwe = 1'b0;
    reg  [47:0] vwd;
    reg  [8:0]  vra;
    wire [47:0] vq;
    bram32 u_vram (.clk(clk), .we(vwe), .wa(vwa), .wd(vwd[31:0]), .ra(vra), .q(vq[31:0]));
    deint_ram #(.W(16)) u_vram_m (.clk(clk), .we(vwe), .wa(vwa), .wd(vwd[47:32]), .ra(vra), .q(vq[47:32]));
    integer     xj, xq;
    reg signed [12:0] x_t;
    reg  [3:0]  x_n;
    always @(posedge clk) begin
        // the token: a word's address now (a), its RAM's first register (b), its second (c), the row
        // chosen (d)
        vtb <= vta;
        vtc <= vtb;
        vtd <= vtc;
        vxb <= vxa;
        vxc <= vxb;
        vxd <= vxc;
        d2n <= q2[vxc[19:16]];
        d2o <= q2[vxc[15:12]];
        d1v <= q1[vxc[11:8]];
        d3v <= q3[vxc[7:4]];
        dcn <= qc[sCB];
        dco <= qc[sCA];
        if (vtd[11] && vtd[10:8] != 3'd4) begin
            s2n[32 * vtd[9:8] +: 32] <= d2n;
            s2o[32 * vtd[9:8] +: 32] <= d2o;
            s1v[32 * vtd[9:8] +: 32] <= d1v;
            s3v[32 * vtd[9:8] +: 32] <= d3v;
            scn[32 * vtd[9:8] +: 32] <= dcn;
            sco[32 * vtd[9:8] +: 32] <= dco;
        end
        // 1: the block's five words are in: its pixels moved (pixel j: number j + the first's odd bit),
        // and whether they are in the picture
        x1v <= vtd[11] && vtd[10:8] == 3'd4;
        x1b <= vtd[7:0];
        x1u <= vxd[26];
        x1h <= ddx[0];
        for (xj = 0; xj < 8; xj = xj + 1) begin
            x_n = xj + ddx[0];
            p2n[8 * xj +: 8] <= pix(w2n, x_n);
            p2o[8 * xj +: 8] <= pix(w2o, x_n);
            x_n = xj + dsh1[0];
            p1a[8 * xj +: 8] <= pix(w1v, x_n);
            p1b[8 * xj +: 8] <= pix(w1v, x_n + 4'd1);
            x_n = xj + dsh3[0];
            p3a[8 * xj +: 8] <= pix(w3v, x_n);
            p3b[8 * xj +: 8] <= pix(w3v, x_n + 4'd1);
            cnl[8 * xj +: 8] <= xj % 2 ? scn[32 * (xj / 2) +: 8] : scn[32 * (xj / 2) + 16 +: 8];
            col[8 * xj +: 8] <= xj % 2 ? sco[32 * (xj / 2) +: 8] : sco[32 * (xj / 2) + 16 +: 8];
            x_t = $signed({2'b00, vtd[7:0], 3'b000}) + ddx + xj;
            k2n[xj] <= vxd[3] && x_t >= 13'sd0 && x_t < $signed({2'b00, wpix});
            k2o[xj] <= vxd[2] && x_t >= 13'sd0 && x_t < $signed({2'b00, wpix});
            x_t = $signed({2'b00, vtd[7:0], 3'b000}) + dsh1 + xj;
            k1[xj] <= vxd[1] && x_t >= 13'sd0 && x_t + $signed({12'd0, ddx[0]}) < $signed({2'b00, wpix});
            x_t = $signed({2'b00, vtd[7:0], 3'b000}) + dsh3 + xj;
            k3[xj] <= vxd[0] && x_t >= 13'sd0 && x_t + $signed({12'd0, ddx[0]}) < $signed({2'b00, wpix});
        end
        for (xq = 0; xq < 4; xq = xq + 1)       // (the chroma of the pair the first pixel moved lies in)
            vch[16 * xq +: 16] <= {s1v[32 * xq + 24 +: 8], s1v[32 * xq + 8 +: 8]};
        // 2: the half pixel; C against P2
        x2v <= x1v;
        x2b <= x1b;
        x2u <= x1u;
        for (xj = 0; xj < 8; xj = xj + 1) begin
            p1v[8 * xj +: 8] <= x1h ? mean(p1a[8 * xj +: 8], p1b[8 * xj +: 8]) : p1a[8 * xj +: 8];
            p3v[8 * xj +: 8] <= x1h ? mean(p3a[8 * xj +: 8], p3b[8 * xj +: 8]) : p3a[8 * xj +: 8];
            dnv[8 * xj +: 8] <= k2n[xj] ? absd(cnl[8 * xj +: 8], p2n[8 * xj +: 8]) : 8'd255;
            dov[8 * xj +: 8] <= k2o[xj] ? absd(col[8 * xj +: 8], p2o[8 * xj +: 8]) : 8'd255;
            k13[xj] <= k1[xj] && k3[xj];
        end
        k1b <= k1;
        vch2 <= vch;
        // 3: P1 against P3
        x3v <= x2v;
        x3b <= x2b;
        x3u <= x2u;
        for (xj = 0; xj < 8; xj = xj + 1) begin
            mwv[8 * xj +: 8] <= k13[xj] ? absd(p1v[8 * xj +: 8], p3v[8 * xj +: 8]) : 8'd255;
            mabv[8 * xj +: 8] <= max2(dnv[8 * xj +: 8], dov[8 * xj +: 8]);
        end
        p1x <= p1v;
        k1c <= k1b;
        vch3 <= vch2;
        // the block's four words written, a clock each (done before the next block's are there)
        vwe <= 1'b0;
        if (vwn != 3'd4) begin
            vwe <= 1'b1;
            vwd <= vblk[47:0];
            vblk <= {48'd0, vblk[191:48]};
            vwn <= vwn + 3'd1;
            if (vwe)
                vwa <= vwa + 9'd1;
        end
        // 4: the greatest (255: no use of the vector here: it is not used at all (dyr odd, no
        // move), or a pair has a pixel of P1's outside the picture); the block's words
        if (x3v) begin
            for (xq = 0; xq < 4; xq = xq + 1) begin
                vblk[48 * xq + 40 +: 8] <= !x3u || !(k1c[2 * xq] && k1c[2 * xq + 1]) ? 8'd255 :
                                           max2(mabv[16 * xq +: 8], mwv[16 * xq +: 8]);
                vblk[48 * xq + 32 +: 8] <= !x3u || !(k1c[2 * xq] && k1c[2 * xq + 1]) ? 8'd255 :
                                           max2(mabv[16 * xq + 8 +: 8], mwv[16 * xq + 8 +: 8]);
                vblk[48 * xq +: 32] <= {vch3[16 * xq + 8 +: 8], p1x[16 * xq +: 8], vch3[16 * xq +: 8], p1x[16 * xq + 8 +: 8]};
            end
            vwn <= 3'd0;
            vwa <= {x3b[6:0], 2'b00};
        end
    end

    // ---- the output's pass ----
    // the noise reduction: a sample with the same one two fields before: the difference; how much
    // of it is taken (a table: by nr and the difference, under 16); the sample
    reg [3:0]   tnr_t [0:63];           // [{nr, the difference}]
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
    reg [5:0]   nrq /* synthesis syn_preserve = 1 */;   // nr (none without the fields' history): copies
    // the token: {valid, the word's place}
    reg         o_run = 1'b0;
    reg  [9:0]  oq;
    reg  [10:0] ota = 11'd0, otb = 11'd0, otc = 11'd0, otd = 11'd0, ote = 11'd0, otf = 11'd0, otg = 11'd0, oth = 11'd0,
                oti = 11'd0, otj = 11'd0, otk = 11'd0, ot1 = 11'd0, ot2 = 11'd0, ot3 = 11'd0;
    // d: the rows' words, chosen: C's old and new, P2's, P1's and P3's own; the pan's word
    reg  [31:0] xA, xB, yA, yB, xW, yW;
    reg  [47:0] vd;
    // e, f, g: the noise reduction's three clocks, and the differences' greatest
    reg  [35:0] tA, tB, tW;
    reg  [19:0] cA, cB, cW;
    reg  [31:0] xAe, xBe, xWe, xAf, xBf, xWf, nA, nB, nW;
    reg  [7:0]  dA0, dA1, dB0, dB1, dW0, dW1, mab0, mab1, dwf0, dwf1, m0, m1;
    reg  [47:0] ve, vf, vg;
    reg  [7:0]  mv0, mv1;
    // h, i, j, k: with the pixels beside (the word before's second, the word after's first): a
    reg  [7:0]  hm0, hm1, hv0, hv1, im1, iv1, l0, l1, r0, r1, lv0, lv1, rv0, rv1, md0, md1, mdv0, mdv1;
    reg  [4:0]  al0, al1, alv0, alv1;
    reg  [31:0] nAh, nBh, nWh, nAi, nBi, nWi, nAj, nBj, nWj, nWk;
    reg  [31:0] vwh, vwi, vwj, vwk;
    // the window for the edges: the words of old and new around the pair made (the pair: three words
    // behind the newest); what goes with it, three clocks on
    reg  [31:0] WA [0:6] /* synthesis syn_srlstyle = "registers" */;      // ([0]: stage k's own words, below)
    reg  [31:0] WB [0:6] /* synthesis syn_srlstyle = "registers" */;
    reg  [31:0] cw1, cw2, cw3, cv1, cv2, cv3;
    reg  [19:0] ca1, ca2, ca3;          // {a of its two pixels, the pan's a of them}
    integer     wi;
    function [4:0] a_of(input [7:0] md);
        reg [7:0] d;
        begin
            d = md > thr ? md - thr : 8'd0;
            a_of = d > 8'd16 ? 5'd16 : d[4:0];
        end
    endfunction
    integer     nb;

    // W: a pair a clock: the pair's words, their means, the blends
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
    // (registers, all of these that move on: a block RAM as a shift register costs room and a long wire)
    reg [135:0] pd [0:7] /* synthesis syn_srlstyle = "registers" */;
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

    // ---- the edges' way (edi) ----
    // stage 0 (with wo, wn): luma i of 0 to 13 (the pair's two pixels: 6 and 7), chroma pair j of 0
    // to 4 (the pair's own: 2); and these through the stages to where the pixel is taken (8)
    reg [111:0] wa, wb;
    reg [79:0]  ca, cn;
    reg [111:0] wad [1:7] /* synthesis syn_srlstyle = "registers" */;
    reg [111:0] wbd [1:7] /* synthesis syn_srlstyle = "registers" */;
    reg [79:0]  cad [1:7] /* synthesis syn_srlstyle = "registers" */;
    reg [79:0]  cnd [1:7] /* synthesis syn_srlstyle = "registers" */;
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

    // the output's pass: its stages (not held by the state: the token says what is in them)
    always @(posedge clk) begin
        nrq <= {3{hist ? nr : 2'd0}};
        // a: the address (below); b, c: the RAMs; d: the rows chosen (pg: the frame's two lines, a row
        // of more than 512 words in two buffers)
        otb <= ota;
        otc <= otb;
        otd <= otc;
        xA <= qc[sCA];
        xB <= pgf ? qc[{1'b0, otc[9]}] : qc[sCB];
        yA <= q2[s2A];
        yB <= q2[s2B];
        xW <= pgf ? q1[{3'd0, otc[9]}] : q1[s1W];
        yW <= q3[s3W];
        vd <= vq;
        // e: each sample's difference from the one two fields before; the lumas' for the motion
        ote <= otd;
        for (nb = 0; nb < 4; nb = nb + 1) begin
            tA[9 * nb +: 9] <= tnr_a(xA[8 * nb +: 8], yA[8 * nb +: 8]);
            tB[9 * nb +: 9] <= tnr_a(xB[8 * nb +: 8], yB[8 * nb +: 8]);
            tW[9 * nb +: 9] <= tnr_a(xW[8 * nb +: 8], yW[8 * nb +: 8]);
        end
        dA0 <= absd(xA[23:16], yA[23:16]);
        dA1 <= absd(xA[7:0], yA[7:0]);
        dB0 <= absd(xB[23:16], yB[23:16]);
        dB1 <= absd(xB[7:0], yB[7:0]);
        dW0 <= absd(xW[23:16], yW[23:16]);
        dW1 <= absd(xW[7:0], yW[7:0]);
        xAe <= xA;
        xBe <= xB;
        xWe <= xW;
        ve <= vd;
        // f: the part of it taken
        otf <= ote;
        for (nb = 0; nb < 4; nb = nb + 1) begin
            cA[5 * nb +: 5] <= {tA[9 * nb + 8], |tA[9 * nb + 4 +: 4] ? 4'd0 : tnr_t[{nrq[1:0], tA[9 * nb +: 4]}]};
            cB[5 * nb +: 5] <= {tB[9 * nb + 8], |tB[9 * nb + 4 +: 4] ? 4'd0 : tnr_t[{nrq[3:2], tB[9 * nb +: 4]}]};
            cW[5 * nb +: 5] <= {tW[9 * nb + 8], |tW[9 * nb + 4 +: 4] ? 4'd0 : tnr_t[{nrq[5:4], tW[9 * nb +: 4]}]};
        end
        mab0 <= max2(dA0, dB0);
        mab1 <= max2(dA1, dB1);
        dwf0 <= dW0;
        dwf1 <= dW1;
        xAf <= xAe;
        xBf <= xBe;
        xWf <= xWe;
        vf <= ve;
        // g: the samples; the differences' greatest (none past the line's ends)
        otg <= otf;
        for (nb = 0; nb < 4; nb = nb + 1) begin
            nA[8 * nb +: 8] <= cA[5 * nb + 4] ? xAf[8 * nb +: 8] - {4'd0, cA[5 * nb +: 4]} : xAf[8 * nb +: 8] + {4'd0, cA[5 * nb +: 4]};
            nB[8 * nb +: 8] <= cB[5 * nb + 4] ? xBf[8 * nb +: 8] - {4'd0, cB[5 * nb +: 4]} : xBf[8 * nb +: 8] + {4'd0, cB[5 * nb +: 4]};
            nW[8 * nb +: 8] <= cW[5 * nb + 4] ? xWf[8 * nb +: 8] - {4'd0, cW[5 * nb +: 4]} : xWf[8 * nb +: 8] + {4'd0, cW[5 * nb +: 4]};
        end
        m0 <= otf[10] ? max2(mab0, dwf0) : 8'd0;
        m1 <= otf[10] ? max2(mab1, dwf1) : 8'd0;
        mv0 <= otf[10] ? vf[47:40] : 8'd0;
        mv1 <= otf[10] ? vf[39:32] : 8'd0;
        vg <= vf;
        // h: (the word after is in g now)
        oth <= otg;
        {hm0, hm1, hv0, hv1} <= {m0, m1, mv0, mv1};
        {nAh, nBh, nWh, vwh} <= {nA, nB, nW, vg[31:0]};
        // i: with the pixel before, and the pixel after
        oti <= oth;
        im1 <= hm1;
        iv1 <= hv1;
        l0 <= max2(im1, hm0);
        l1 <= max2(hm0, hm1);
        r0 <= hm1;
        r1 <= m0;
        lv0 <= max2(iv1, hv0);
        lv1 <= max2(hv0, hv1);
        rv0 <= hv1;
        rv1 <= mv0;
        {nAi, nBi, nWi, vwi} <= {nAh, nBh, nWh, vwh};
        // j
        otj <= oti;
        md0 <= max2(l0, r0);
        md1 <= max2(l1, r1);
        mdv0 <= max2(lv0, rv0);
        mdv1 <= max2(lv1, rv1);
        {nAj, nBj, nWj, vwj} <= {nAi, nBi, nWi, vwi};
        // k: a (the pan's a the same way from its differences; 16 without it: the mean)
        otk <= otj;
        al0 <= pgf ? 5'd0 : mode == 2'd1 || (!hist && mode != 2'd2) ? 5'd16 : mode == 2'd2 ? 5'd0 : a_of(md0);
        al1 <= pgf ? 5'd0 : mode == 2'd1 || (!hist && mode != 2'd2) ? 5'd16 : mode == 2'd2 ? 5'd0 : a_of(md1);
        alv0 <= mc_s ? a_of(mdv0) : 5'd16;
        alv1 <= mc_s ? a_of(mdv1) : 5'd16;
        {WA[0], WB[0], nWk, vwk} <= {nAj, nBj, nWj, vwj};
        // the window: old's and new's words move on; the pair made is three words behind
        for (wi = 1; wi <= 6; wi = wi + 1) begin
            WA[wi] <= WA[wi - 1];
            WB[wi] <= WB[wi - 1];
        end
        ot1 <= otk;
        ot2 <= ot1;
        ot3 <= ot2;
        {cw1, cv1, ca1} <= {nWk, vwk, al0, al1, alv0, alv1};
        {cw2, cv2, ca2} <= {cw1, cv1, ca1};
        {cw3, cv3, ca3} <= {cw2, cv2, ca2};
        // stage 0: the pair (WA[3]: its word of old), the fourteen pixels and five pairs about it
        s0_v <= ot3[10];
        s0_wa <= ot3[9:0];
        wo <= WA[3];
        wn <= WB[3];
        ww <= cw3;
        wvp <= cv3;
        {a_y0, a_y1, v_y0, v_y1} <= ca3;
        for (wi = 0; wi < 14; wi = wi + 1) begin
            wa[8 * wi +: 8] <= wi % 2 ? WA[6 - wi / 2][7:0] : WA[6 - wi / 2][23:16];
            wb[8 * wi +: 8] <= wi % 2 ? WB[6 - wi / 2][7:0] : WB[6 - wi / 2][23:16];
        end
        for (wi = 0; wi < 5; wi = wi + 1) begin
            ca[16 * wi +: 16] <= {WA[5 - wi][31:24], WA[5 - wi][15:8]};
            cn[16 * wi +: 16] <= {WB[5 - wi][31:24], WB[5 - wi][15:8]};
        end
        s0_side <= ot3[9:0] < 10'd3 || ot3[9:0] + 10'd3 >= nw;
        // (what goes with the pair through the edges' stages: its place, P1's word, the word
        // that is as it is, the three a)
        pv <= {pv[6:0], s0_v};
        pd[0] <= {wvp, v0g, v1g, v0g > v1g ? v0g : v1g, s0_wa, ww, pc ? wn : wo, a_y0, a_y1, a_c};
        for (wi = 1; wi < 8; wi = wi + 1)
            pd[wi] <= pd[wi - 1];
        s1_v <= pv[7];
        {s1_wv, s1_v0, s1_v1, s1_vc, s1_wa, s1_w, s1_d, s1_ay0, s1_ay1, s1_ac} <= pd[7];
        // (the pan's word against the mean, by its a; then P1's own against that, by a)
        s2_v <= s1_v;
        s2_wa <= s1_wa;
        s2_w <= s1_w;
        s2_d <= s1_d;
        {s2_ay0, s2_ay1, s2_ac} <= {s1_ay0, s1_ay1, s1_ac};
        s2_x <= {blend(s1_wv[31:24], s1_bob[31:24], s1_vc), blend(s1_wv[23:16], s1_bob[23:16], s1_v0),
                 blend(s1_wv[15:8], s1_bob[15:8], s1_vc), blend(s1_wv[7:0], s1_bob[7:0], s1_v1)};
        r_we <= s2_v;
        r_wa <= s2_wa;
        r_slot_d <= line_d[2:0];
        r_slot_i <= line_i[2:0];
        r_wd_d <= s2_d;
        r_wd_i <= {blend(s2_w[31:24], s2_x[31:24], s2_ac), blend(s2_w[23:16], s2_x[23:16], s2_ay0),
                   blend(s2_w[15:8], s2_x[15:8], s2_ac), blend(s2_w[7:0], s2_x[7:0], s2_ay1)};
    end

    // ---- the steps ----
    reg [5:0]   wt;                     // (a pass's last words through its stages)
    integer     fi;
    always @(posedge clk) begin
        start_clr <= 1'b0;
        fstart <= 1'b0;
        f_start <= 4'd0;
        f_asked <= 4'd0;
        rdv <= b_rvalid;
        rdq <= rd_data;
        rdq2 <= rdq;
        // a line read: whose it is
        f_push <= 4'd0;
        if (rdv) begin
            f_push[tagq[2 * trp +: 2]] <= 1'b1;
            trp <= trp + 4'd1;
        end
        // a row all written: the field's next
        for (fi = 0; fi < 4; fi = fi + 1)
            if (f_done[fi]) begin
                act[fi] <= 1'b0;
                nrow[fi] <= nrow[fi] + 11'd1;
                wsl[fi] <= wsl[fi] + 4'd1 == (fi == 0 ? 4 : fi == 1 ? N1 : fi == 2 ? N2 : N3) ? 4'd0 : wsl[fi] + 4'd1;
                if (fi < 2)
                    pgd[fi] <= 1'b1;
            end
        ota <= 11'd0;
        vta <= 12'd0;
        mta <= 26'd0;
        if ((st == S_M && mi == 3'd2) || (st == S_MP && wt == 6'd2)) begin
            pdx <= n_dx;
            pdy <= n_dy;
            pso <= n_cd != 3'd1 || n_side_ok;
        end
        if ((st == S_M && mi == 3'd4) || (st == S_MP && wt == 6'd3)) begin
            mb <= n_b;
            mcd <= n_cd;
            hb <= n_hb;
            ub <= n_ub;
            cdx <= pdx[5:0];
            cdy <= pdy[3:0];
            cok <= n_ok;
            if (adv) begin
                wm1 <= w0;
                w0 <= wp1;
                wp1 <= vec_q;
                vec_ra <= n_b + 8'd2;
            end
        end
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
                    // (a top field's first step has no line to make: from the second)
                    if (pg || (ll_now ? par[latest] == top_f : par[latest] != top_f)) begin
                        k <= 10'd0;
                        {km1, km2, km3} <= 12'd0;
                        hk <= 9'd0;
                        uk <= 4'd0;
                    end else begin
                        k <= 10'd1;
                        {km1, km2, km3} <= {4'd1, 4'd1, 4'd1};
                        hk <= 9'd37;
                        uk <= 4'd3;
                    end
                    emitted <= 10'd0;
                    active <= nfields != 3'd0;
                    for (fi = 0; fi < 4; fi = fi + 1) begin
                        nrow[fi] <= 11'd0;
                        wsl[fi] <= 4'd0;
                    end
                    // (the vectors: with the fields' history, in the motion adaptive mode; the pan a
                    // candidate if it is within what the estimator may find)
                    mc_f <= mc && !pg && mode == 2'd0 && (ll_now || hist_n);
                    pan_k <= mv[10] && mv[5:0] != 6'b100000 && $signed(mv[9:6]) >= -4'sd4 && $signed(mv[9:6]) <= 4'sd4;
                    dxf <= mv[5:0];
                    dyf <= mv[9:6];
                    firstf <= first;
                    vfirst <= 1'b1;
                end else if (can && !start_clr && !fstart) begin
                    pgd <= 2'd0;
                    st <= S_LD;
                end
            // the rows the step's windows still want: a row of a field begun, its lines asked for
            // (the fields' in turn), until none is wanted and none is on its way
            S_LD: begin
                for (fi = 0; fi < 4; fi = fi + 1)
                    if (need[fi] && !act[fi] && !f_done[fi] && !f_start[fi]) begin
                        act[fi] <= 1'b1;
                        f_start[fi] <= 1'b1;
                        giss[fi] <= 7'd0;
                        lrow[fi] <= pgf ? {k[8:0], fi == 0} : nrow[fi][9:0];
                    end
                if ((!b_valid || b_ack) && want != 4'd0) begin
                    b_valid <= 1'b1;
                    b_line <= {pick_f, 5'd0, lrow[pick], giss[pick]};
                    giss[pick] <= giss[pick] + 7'd1;
                    f_asked[pick] <= 1'b1;
                    tagq[2 * twp +: 2] <= pick;
                    twp <= twp + 4'd1;
                    rr <= pick + 2'd1;
                end else if (b_ack)
                    b_valid <= 1'b0;
                if (need == 4'd0 && act == 4'd0 && f_done == 4'd0 && f_start == 4'd0 && !b_valid)
                    st <= S_LDW;
            end
            S_LDW: begin                            // (the last word written is in its RAM)
                oq <= 10'd0;
                wt <= 6'd0;
                st <= mc_s ? S_MP : S_O;
            end
            // the estimator: before its first block: the line above's vector of block 0 into the
            // next's place, as if a block before it had just been done
            S_MP: begin
                wt <= wt + 6'd1;
                if (wt == 6'd0)
                    vec_ra <= 8'd0;
                else if (wt == 6'd1) begin
                    wp1 <= vec_q;
                    vec_ra <= 8'd1;
                    mb <= 8'hFF;
                    mcd <= 3'd5;
                    hb <= hk - 9'd101;
                    ub <= uk - 4'd5;
                end else if (wt == 6'd3) begin
                    mi <= 3'd0;
                    st <= S_M;
                end
            end
            // a candidate's five words' addresses, a clock each
            S_M: begin
                mta <= {1'b1, mi, mcd, mb, cdx, cdy, cok};
                msa <= {wrap(km2, cdy5 + 5'sd1, N2), wrap(km2, cdy5, N2), wrap(km2, cdy5 - 5'sd1, N2), wrap(km2, cdy5 - 5'sd2, N2)};
                mka <= {m_r + 12'sd1 >= 12'sd0 && m_r + 12'sd1 < nl_s, m_r >= 12'sd0 && m_r < nl_s,
                        m_r - 12'sd1 >= 12'sd0 && m_r - 12'sd1 < nl_s, m_r - 12'sd2 >= 12'sd0 && m_r - 12'sd2 < nl_s};
                ra_2 <= m_x[9:1] + {6'd0, mi};
                ra_c <= {mb[6:0], 2'b00} + {6'd0, mi};
                if (mi == 3'd4) begin
                    mi <= 3'd0;
                    if (adv && mb + 8'd1 == nblk) begin
                        wt <= 6'd0;
                        st <= S_MW;
                    end
                end else
                    mi <= mi + 3'd1;
            end
            S_MW: begin                             // (its last block through the stages, its vector kept)
                wt <= wt + 6'd1;
                if (wt == 6'd15) begin
                    vfirst <= 1'b0;
                    wt <= 6'd0;
                    st <= S_VP;
                end
            end
            // the vectors' pass: its first block's vector; then a block's five words' addresses, a
            // clock each
            S_VP: begin
                wt <= wt + 6'd1;
                vb <= 8'd0;
                vi <= 3'd0;
                if (wt == 6'd0)
                    vec_ra <= 8'd0;
                else begin
                    vvec <= vec_q;
                    vec_ra <= 8'd1;
                    wt <= 6'd0;
                    st <= S_V;
                end
            end
            S_V: begin
                vta <= {1'b1, vi, vb};
                vxa <= {buse, bdx, wrap(km2, bdy5, N2), wrap(km2, bdy5 - 5'sd1, N2), wrap(km1, ow + bdyh5, N1),
                        wrap(km3, ow + bdyh5 + bdy5, N3), rn_w >= 12'sd0 && rn_w < nl_s, ro_w >= 12'sd0 && ro_w < nl_s,
                        r1_w >= 12'sd0 && r1_w < nl_s, r3_w >= 12'sd0 && r3_w < nl_s};
                ra_2 <= vt2[9:1] + {6'd0, vi};
                ra_1 <= vt1[9:1] + {6'd0, vi};
                ra_3 <= vt3[9:1] + {6'd0, vi};
                ra_c <= {vb[6:0], 2'b00} + {6'd0, vi};
                if (vi == 3'd4) begin
                    vi <= 3'd0;
                    vb <= vb + 8'd1;
                    vvec <= vec_q;
                    vec_ra <= vb + 8'd2;
                    if (vb + 8'd1 == nblk)
                        st <= S_VW;
                end else
                    vi <= vi + 3'd1;
            end
            S_VW: begin                             // (its last block through the stages, and written)
                wt <= wt + 6'd1;
                if (wt == 6'd15) begin
                    wt <= 6'd0;
                    st <= S_O;
                end
            end
            // the output's pass: a word's address a clock
            S_O: begin
                ota <= {1'b1, oq};
                ra_c <= oq[8:0];
                ra_1 <= oq[8:0];
                ra_2 <= oq[8:0];
                ra_3 <= oq[8:0];
                vra <= oq[8:0];
                oq <= oq + 10'd1;
                if (oq + 10'd1 == nw)
                    st <= S_OW;
            end
            S_OW: begin                             // (its last words through the stages)
                wt <= wt + 6'd1;
                if (wt == 6'd31)
                    st <= S_NEXT;
            end
            S_NEXT: begin
                k <= k + 10'd1;
                km1 <= km1 + 4'd1 == N1 ? 4'd0 : km1 + 4'd1;
                km2 <= km2 + 4'd1 == N2 ? 4'd0 : km2 + 4'd1;
                km3 <= km3 + 4'd1 == N3 ? 4'd0 : km3 + 4'd1;
                hk <= hk + 9'd37;
                uk <= uk + 4'd3;
                emitted <= emitted + 10'd2;
                st <= S_GAP;                        // (two clocks: lstream.v's hold follows emitted)
            end
            S_GAP:
                st <= S_GAP2;
            S_GAP2:
                st <= S_IDLE;
            default:
                st <= S_IDLE;
        endcase
        state_o <= {active, hist, pc, ll_used, st};
    end
endmodule
