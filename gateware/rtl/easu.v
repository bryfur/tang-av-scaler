// easu.v: the scaler: the 720 x 480 picture in the ring (lstream.v), or a part of it, to 1440 x 1080 in the middle of
// 1920 x 1080, FSR 1's edge adaptive upsampling as sim/fsr.py has it (scale_hw()): for each output
// pixel the twelve source pixels round it, weighed by a table's entry for the pixel's place between
// them (8 x 8 places), the edge's direction there (32 bins) and its strength (8 levels); held
// between the least and greatest of the nearest four.  Y'CbCr out (rcas.v goes on from there).
//
// The ring: eight lines, a line's place its number's low three bits, 1024 words of 54 bits
// ({dx 9, dy 9, ls 8, 2'd0, y 8, cb 8, cr 8, 2'd0}), written on lstream.v's clock.  It is asked for
// by events (ev changes at the end of each row of picture): ev_first: the frame is over, the next
// one's lines from 0; ev_goal: lines are to be made while fewer than this + 1 are (the line five
// below the next row's upper one in the ring, and the one after it for the stream).
//
// de, x, y: the output's pixel (pattern.v's ox, oy); o_y, o_cb, o_cr are that pixel's LAT clocks
// later (whatever, outside the 1440 columns).

`ifndef EASU_HEX0
`define EASU_HEX0 "easu0.hex"
`define EASU_HEX1 "easu1.hex"
`define EASU_HEX2 "easu2.hex"
`define EASU_HEX3 "easu3.hex"
`endif

// a quarter of the table (three of the twelve weights), its address register beside it: the data
// three clocks after the address
module easu_rom #(
    parameter FILE = ""
) (
    input             clk,
    input      [12:0] a,
    output reg [29:0] q /* synthesis syn_preserve = 1 */
);
    reg [29:0] mem [0:8191];
    initial $readmemh(FILE, mem);
    reg [12:0] a1 /* synthesis syn_preserve = 1 */;
    reg [29:0] q1;
    // (q: a register of its own beside what uses it; q1 is the block RAM's)
    always @(posedge clk) begin
        a1 <= a;
        q1 <= mem[a1];
        q <= q1;
    end
endmodule

// a signed number times another, in a DSP multiplier with its own registers in and out: the
// product two clocks after (in logic a multiplier takes 10 ns here; and a multiplier left to the
// synthesis is merged with the adders after it into DSP blocks far apart)
module easu_mul #(
    parameter AW = 9,
    parameter BW = 10
) (
    input                               clk,
    input      signed [AW - 1:0]        a,
    input      signed [BW - 1:0]        b,
    output reg signed [AW + BW - 1:0]   p
) /* synthesis syn_dspstyle = "dsp" */;
    reg signed [AW - 1:0] a_r;
    reg signed [BW - 1:0] b_r;
    always @(posedge clk) begin
        a_r <= a;
        b_r <= b;
        p <= a_r * b_r;
    end
endmodule

module easu (
    input             clk,
    input             de,
    input      [12:0] x,
    input      [11:0] y,
    output reg        ev = 1'b0,
    output reg        ev_first = 1'b0,
    output reg [9:0]  ev_goal = 10'd0,

    input             w_clk,
    input             w_we,
    input      [2:0]  w_slot,
    input      [9:0]  w_x,
    input      [53:0] w_d,

    // the part of the source shown (fsr.py geom(); they stay as they are): a raster column's place
    // g_xr + (x + 120) g_dx (counted from 120 columns before the raster's first), a row's g_ys + y g_dy, in 65536ths of a source pixel
    input             g_wide,           // the picture all 1920 columns (16:9), not the middle 1440
    input signed [27:0] g_xr,
    input      [16:0] g_dx,
    input signed [26:0] g_ys,
    input      [16:0] g_dy,

    output     [7:0]  o_y,
    output     [7:0]  o_cb,
    output     [7:0]  o_cr
) /* synthesis syn_dspstyle = "logic" */;       // (small multipliers: in DSP blocks they are far apart)
    localparam LAT = 26;
    localparam W = 720, H = 480;

    // the row: fy the source row above its place (-1 to H - 1), ky its place below it; the four
    // source rows' places in the ring; the weights of the four pixels' analyses
    reg signed [26:0] yp = 27'sd0;      // the row's place
    // (the next row's: yp + g_dy in two clocks, the low half first: yp stays a row long)
    reg [16:0] ypl;
    reg signed [10:0] yph;
    reg signed [26:0] ypn;
    wire signed [10:0] fy = yp[26:16];
    // (ky a register of its own: yp changes between rows only, and what ky gates is wide and far)
    reg  [2:0] ky = 3'd0;               // below fy: (2 ky + 1) sixteenths
    always @(posedge clk)
        ky <= yp[15:13];
    wire       mir = ky[2];             // the lower half: the table's entry for the mirror image
    wire [1:0] kyt = mir ? ~ky[1:0] : ky[1:0];
    reg        eol = 1'b0, eol_q = 1'b0, eol_q2 = 1'b0, last = 1'b0, row = 1'b0;
    reg [2:0]  slot [0:3] /* synthesis syn_ramstyle = "registers" */;
    function [2:0] rowslot(input signed [10:0] v);
        reg signed [10:0] c;
        begin
            c = v < 0 ? 11'sd0 : v > H - 1 ? H - 1 : v;
            rowslot = c[2:0];
        end
    endfunction
    wire [4:0] wy0 = 5'd15 - {1'b0, ky, 1'b0}, wy1 = {1'b0, ky, 1'b1};
    wire signed [10:0] fy5 = fy + 11'sd5;
    always @(posedge clk) begin
        // (a row's end: after its last pixel has its weights, 40 columns into the blanking)
        if (x == 13'd1918)
            row <= de;
        eol <= row && x == 13'd1958;
        last <= y == 12'd1079;
        ypl <= {1'b0, yp[15:0]} + {1'b0, g_dy[15:0]};
        yph <= yp[26:16] + {10'd0, g_dy[16]};
        ypn <= {yph + {10'd0, ypl[16]}, ypl[15:0]};
        eol_q <= eol;
        eol_q2 <= eol_q;
        if (eol) begin
            yp <= last ? g_ys : ypn;
        end
        if (eol_q) begin
            slot[0] <= rowslot(fy - 11'sd1);
            slot[1] <= rowslot(fy);
            slot[2] <= rowslot(fy + 11'sd1);
            slot[3] <= rowslot(fy + 11'sd2);
        end
        if (eol_q2) begin
            ev <= !ev;
            ev_first <= last;
            ev_goal <= fy5 > H - 1 ? H : fy5[9:0] + 10'd1;
        end
    end

    // the column's place: xq the pixel's now at x (counted on from g_xr, 120 columns before the line's first), xc: it has a source
    // column more than the pixel before
    // 1, 2: the column asked of the ring: the newest of the four, the one left of its place and 2, in 0 to W - 1
    reg signed [27:0] xq = 28'sd0;
    reg        xc = 1'b0;
    wire signed [27:0] x_from = x == 13'd2080 ? g_xr : xq;     // (2200 a line: 120 before column 0)
    wire signed [27:0] x_next = x_from + $signed({11'd0, g_dx});
    wire signed [12:0] cn = $signed(xq[27:16]) + 13'sd2;
    reg [9:0]  ra_n;                    // (a register of its own before the eight beside the lines)
    always @(posedge clk) begin
        xq <= x_next;
        xc <= x_next[16] != x_from[16];
        ra_n <= cn < 0 ? 10'd0 : cn > W - 1 ? W - 1 : cn[9:0];
    end
    reg [53:0] q [0:7] /* synthesis syn_ramstyle = "registers" */;
    genvar k;
    generate
        for (k = 0; k < 8; k = k + 1) begin : g_line
            reg [17:0] m2 [0:1023];
            reg [17:0] m1 [0:1023];
            reg [17:0] m0 [0:1023];
            reg [9:0]  ra /* synthesis syn_preserve = 1 */;
            reg [9:0]  wa /* synthesis syn_preserve = 1 */;
            reg        wen;
            reg [53:0] wd;
            always @(posedge w_clk) begin
                wen <= w_we && w_slot == k;
                wd <= w_d;
                wa <= w_x;
                if (wen) begin
                    m2[wa] <= wd[53:36];
                    m1[wa] <= wd[35:18];
                    m0[wa] <= wd[17:0];
                end
            end
            reg [53:0] q1;
            always @(posedge clk) begin
                ra <= ra_n;
                q1 <= {m2[ra], m1[ra], m0[ra]};         // 3 (the RAM's own register)
                q[k] <= q1;                             // 4
            end
        end
    endgenerate

    // 3: the four rows' words; 4: the window, four columns of four rows, a new column at each odd pixel
    reg [53:0] cd [0:3] /* synthesis syn_ramstyle = "registers" */;
    reg [53:0] win [0:15] /* synthesis syn_ramstyle = "registers" */;     // [row][col]: col 3 the newest
    reg [29:0] odd, inw;                // ([k]: of the pixel k + 1 clocks on; odd: a new source column)
    reg [2:0]  kxs [0:15] /* synthesis syn_srlstyle = "registers" */;     // its place right of the column: eighths
    integer    i, j;
    always @(posedge clk) begin
        odd <= {odd[28:0], xc};
        kxs[0] <= xq[15:13];
        for (i = 1; i <= 15; i = i + 1)
            kxs[i] <= kxs[i - 1];
        inw <= {inw[28:0], de && (g_wide || x >= 13'd240 && x < 13'd1680)};
        for (i = 0; i < 4; i = i + 1) begin
            cd[i] <= q[slot[i]];
            if (odd[4]) begin
                win[4 * i + 3] <= cd[i];
                for (j = 0; j < 3; j = j + 1)
                    win[4 * i + j] <= win[4 * i + j + 1];
            end
        end
    end
    // the twelve pixels (b c / e f g h / i j k l / n o) and the four in the middle's analyses
    function [23:0] pixel(input [53:0] w);
        pixel = w[25:2];
    endfunction
    // (for a mirror image the rows the other way up)
    wire [287:0] taps_n = {pixel(win[14]), pixel(win[13]),
                           pixel(win[11]), pixel(win[10]), pixel(win[9]), pixel(win[8]),
                           pixel(win[7]), pixel(win[6]), pixel(win[5]), pixel(win[4]),
                           pixel(win[2]), pixel(win[1])};    // tap t at [24 t +: 24]
    wire [287:0] taps_m = {pixel(win[2]), pixel(win[1]),
                           pixel(win[7]), pixel(win[6]), pixel(win[5]), pixel(win[4]),
                           pixel(win[11]), pixel(win[10]), pixel(win[9]), pixel(win[8]),
                           pixel(win[14]), pixel(win[13])};
    wire [287:0] taps4 = mir ? taps_m : taps_n;

    // 5, 6: the four analyses times their weight (their row's sixteenths times their column's
    // eighths, by the pixel's place); 7: a register; 8: summed
    wire signed [16:0] qdx [0:3], qdy [0:3];
    wire signed [16:0] qls [0:3];
    reg signed [17:0] pdx [0:3], pdy [0:3];
    reg signed [17:0] pls [0:3];
    reg signed [18:0] ax, ay;
    reg [16:0] al;
    reg [6:0]  wg [0:3];
    genvar gi;
    generate
        for (gi = 0; gi < 4; gi = gi + 1) begin : g_q       // gi: {row, col} of f g / j k
            localparam WI = (gi[1] ? 8 : 4) + (gi[0] ? 2 : 1);
            wire [3:0] wxs = gi[0] ? {1'b0, kxs[4]} : 4'd8 - {1'b0, kxs[4]};
            always @(posedge clk)
                wg[gi] <= wxs * (gi[1] ? wy1 : wy0);
            easu_mul #(.AW(9), .BW(8)) u_dx (.clk(clk), .a(win[WI][53:45]), .b({1'b0, wg[gi]}), .p(qdx[gi]));
            easu_mul #(.AW(9), .BW(8)) u_dy (.clk(clk), .a(win[WI][44:36]), .b({1'b0, wg[gi]}), .p(qdy[gi]));
            easu_mul #(.AW(9), .BW(8)) u_ls (.clk(clk), .a({1'b0, win[WI][35:28]}), .b({1'b0, wg[gi]}), .p(qls[gi]));
        end
    endgenerate
    always @(posedge clk) begin
        for (i = 0; i < 4; i = i + 1) begin
            pdx[i] <= qdx[i];
            pdy[i] <= qdy[i];
            pls[i] <= qls[i];
        end
        ax <= pdx[0] + pdx[1] + pdx[2] + pdx[3];
        ay <= pdy[0] + pdy[1] + pdy[2] + pdy[3];
        al <= pls[0] + pls[1] + pls[2] + pls[3];
    end

    // 9: the direction's parts without their signs, the strength's level; 10: the greater and the
    // lesser; 11, 12: the greater times each bin's tangent; 13: the lesser compared; 14: the bin,
    // and the table's address
    reg [17:0] aax, aay;
    reg        sx9, sy9, zx9, zy9;
    reg [17:0] dm, dn;
    reg        swp, opp, swp11, opp11, swp12, opp12, swp13, opp13;
    reg [6:0]  li9;                     // (the strength against each level's edge; then their count)
    reg [2:0]  li10, li11, li12, li13;
    wire signed [29:0] mt [0:7];
    reg [27:0] nn11, nn12, nn13;
    reg [27:0] mtq [0:7] /* synthesis syn_preserve = 1 */;
    reg        swp12b, opp12b;
    reg [2:0]  li12b;
    reg [7:0]  ge;
    reg        dz1, dz2, dz3;           // no direction at all (the greater part nothing), beside the products
    reg [12:0] ta;
    function [9:0] tanq(input integer n);
        case (n)
            0: tanq = 10'd50;   1: tanq = 10'd152;  2: tanq = 10'd256;  3: tanq = 10'd366;
            4: tanq = 10'd484;  5: tanq = 10'd614;  6: tanq = 10'd759;  default: tanq = 10'd928;
        endcase
    endfunction
    generate
        for (gi = 0; gi < 8; gi = gi + 1) begin : g_tan
            easu_mul #(.AW(19), .BW(11)) u_mt (.clk(clk), .a({1'b0, dm}), .b({1'b0, tanq(gi)}), .p(mt[gi]));
        end
    endgenerate
    reg [4:0]  t;
    reg [4:0]  bin;
    always @(posedge clk) begin
        aax <= ax[18] ? -ax : ax;
        aay <= ay[18] ? -ay : ay;
        sx9 <= ax[18];
        sy9 <= ay[18];
        zx9 <= ax == 19'sd0;
        zy9 <= ay == 19'sd0;
        li9 <= {al >= 17'd15214, al >= 17'd12874, al >= 17'd10533, al >= 17'd8192, al >= 17'd5852, al >= 17'd3511,
                al >= 17'd1171};
        swp <= aay > aax;
        opp <= sx9 != sy9 && !zx9 && !zy9;
        dm <= aay > aax ? aay : aax;
        dn <= aay > aax ? aax : aay;
        li10 <= li9[6] ? 3'd7 : li9[5] ? 3'd6 : li9[4] ? 3'd5 : li9[3] ? 3'd4 : li9[2] ? 3'd3 : li9[1] ? 3'd2 :
                {2'd0, li9[0]};
        nn11 <= {dn, 10'd0};
        nn12 <= nn11;
        {swp12, swp11} <= {swp11, swp};
        {opp12, opp11} <= {opp11, opp};
        {li12, li11} <= {li11, li10};
        for (i = 0; i < 8; i = i + 1) begin                         // (a register after each multiplier)
            mtq[i] <= mt[i][27:0];
            ge[i] <= nn13 >= mtq[i] && !dz3;                        // (no direction at all: bin 0)
        end
        nn13 <= nn12;
        {dz3, dz2, dz1} <= {dz2, dz1, dm == 18'd0};
        {swp13, swp12b} <= {swp12b, swp12};
        {opp13, opp12b} <= {opp12b, opp12};
        {li13, li12b} <= {li12b, li12};
        t = ge[0] + ge[1] + ge[2] + ge[3] + ge[4] + ge[5] + ge[6] + ge[7];
        if (swp13)
            t = 5'd16 - t;
        bin = opp13 != mir ? 5'd0 - t : t;      // (a mirror image's direction the other way)
        ta <= {kyt, kxs[15], bin, li13};
    end

    // 15 to 17: the table; the twelve pixels wait for it
    wire [119:0] wt;
    easu_rom #(.FILE(`EASU_HEX0)) u_rom0 (.clk(clk), .a(ta), .q(wt[29:0]));
    easu_rom #(.FILE(`EASU_HEX1)) u_rom1 (.clk(clk), .a(ta), .q(wt[59:30]));
    easu_rom #(.FILE(`EASU_HEX2)) u_rom2 (.clk(clk), .a(ta), .q(wt[89:60]));
    easu_rom #(.FILE(`EASU_HEX3)) u_rom3 (.clk(clk), .a(ta), .q(wt[119:90]));
    reg [287:0] tp [5:18] /* synthesis syn_srlstyle = "registers" */;
    always @(posedge clk) begin
        tp[5] <= taps4;
        for (i = 6; i <= 18; i = i + 1)
            tp[i] <= tp[i - 1];
    end

    // 18, 19: a pixel times a weight; 20 to 22: summed; 23: held between the nearest four's least and
    // greatest
    wire signed [18:0] pr [0:35];
    genvar gc, gt;
    generate
        for (gc = 0; gc < 3; gc = gc + 1) begin : g_ch
            for (gt = 0; gt < 12; gt = gt + 1) begin : g_tap
                easu_mul #(.AW(9), .BW(10)) u_mul (.clk(clk), .a({1'b0, tp[18][24 * gt + 8 * (2 - gc) +: 8]}),
                                                   .b(wt[10 * gt +: 10]), .p(pr[12 * gc + gt]));
            end
        end
    endgenerate
    reg signed [20:0] s3 [0:11];
    reg signed [21:0] s2 [0:5];
    reg signed [21:0] sm [0:2];
    reg [7:0]  mn [18:22][0:2], mx [18:22][0:2];
    reg [7:0]  mnp [0:5], mxp [0:5];
    reg [7:0]  oy_, ocb, ocr;
    function [7:0] min2(input [7:0] a, input [7:0] b);
        min2 = a < b ? a : b;
    endfunction
    function [7:0] max2(input [7:0] a, input [7:0] b);
        max2 = a > b ? a : b;
    endfunction
    function [7:0] hold3(input signed [21:0] v, input [7:0] lo, input [7:0] hi);
        reg signed [13:0] w;
        begin
            w = v >>> 8;
            hold3 = w < $signed({6'd0, lo}) ? lo : w > $signed({6'd0, hi}) ? hi : w[7:0];
        end
    endfunction
    integer    c;
    always @(posedge clk) begin
        for (c = 0; c < 3; c = c + 1) begin
            // (the nearest four: taps 3 f, 4 g, 7 j, 8 k; a channel c of tap t at 24 t + 8 (2 - c)):
            // 17: two and two; 18: the four
            mnp[2 * c] <= min2(tp[17][24 * 3 + 8 * (2 - c) +: 8], tp[17][24 * 4 + 8 * (2 - c) +: 8]);
            mnp[2 * c + 1] <= min2(tp[17][24 * 7 + 8 * (2 - c) +: 8], tp[17][24 * 8 + 8 * (2 - c) +: 8]);
            mxp[2 * c] <= max2(tp[17][24 * 3 + 8 * (2 - c) +: 8], tp[17][24 * 4 + 8 * (2 - c) +: 8]);
            mxp[2 * c + 1] <= max2(tp[17][24 * 7 + 8 * (2 - c) +: 8], tp[17][24 * 8 + 8 * (2 - c) +: 8]);
            mn[18][c] <= min2(mnp[2 * c], mnp[2 * c + 1]);
            mx[18][c] <= max2(mxp[2 * c], mxp[2 * c + 1]);
            for (i = 19; i <= 22; i = i + 1) begin
                mn[i][c] <= mn[i - 1][c];
                mx[i][c] <= mx[i - 1][c];
            end
            for (i = 0; i < 4; i = i + 1)
                s3[4 * c + i] <= pr[12 * c + 3 * i] + pr[12 * c + 3 * i + 1] + pr[12 * c + 3 * i + 2];
            s2[2 * c] <= s3[4 * c] + s3[4 * c + 1];
            s2[2 * c + 1] <= s3[4 * c + 2] + s3[4 * c + 3] + 21'sd128;
            sm[c] <= s2[2 * c] + s2[2 * c + 1];
        end
        oy_ <= hold3(sm[0], mn[22][0], mx[22][0]);
        ocb <= hold3(sm[1], mn[22][1], mx[22][1]);
        ocr <= hold3(sm[2], mn[22][2], mx[22][2]);
    end

    assign o_y = oy_;
    assign o_cb = ocb;
    assign o_cr = ocr;
endmodule
