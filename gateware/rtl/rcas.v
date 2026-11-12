// rcas.v: the scaler's second step: FSR 1's robust contrast adaptive sharpening (RCAS) as
// sim/fsr.py has it (rcas()), on the luma of easu.v's 1440 x 1080 picture; then Y'CbCr [BT.601,
// 16-235] to R'G'B'.
//
// A pixel is sharpened with the ones left, right, above and below it, so the picture comes out a
// row later than it goes in: x, y are the output's pixel as easu.v's y, cb, cr have it; r, g, b of
// that pixel come a row (2200 clocks) and LAT clocks later.  The row after the picture's last is worked
// through too (x and y run on through the blanking).
//
// sharp: 0 (nothing: the picture as it is) to 16.

module rcas (
    input             clk,
    input      [12:0] x,
    input      [11:0] y,
    input      [7:0]  yi,
    input      [7:0]  cbi,
    input      [7:0]  cri,
    input      [4:0]  sharp,
    output reg [7:0]  r,
    output reg [7:0]  g,
    output reg [7:0]  b
) /* synthesis syn_dspstyle = "logic" */;
    localparam LAT = 23;
    localparam P = 219;
    integer i;
    function [7:0] min2(input [7:0] a, input [7:0] b);
        min2 = a < b ? a : b;
    endfunction
    function [7:0] max2(input [7:0] a, input [7:0] b);
        max2 = a > b ? a : b;
    endfunction
    // 4096 / v, and 65536 / (256 - 4k) rounded: tables (a function of these is a divider in logic)
    reg [12:0] recip [0:255];
    reg [10:0] rdiv [0:63];
    initial begin
        recip[0] = 13'd0;
        for (i = 1; i < 256; i = i + 1)
            recip[i] = 4096 / i;
        for (i = 0; i < 64; i = i + 1)
            rdiv[i] = i > 48 ? 11'd0 : (65536 + (128 - 2 * i)) / (256 - 4 * i);
    end

    // 1: the pixel in; the row before and the one before that, by column
    wire [10:0] ox = x[10:0] - 11'd240;
    wire        inw = x >= 13'd240 && x < 13'd1680 && y <= 12'd1080;
    reg [31:0] lm [0:2047];             // {luma of the row before, of the one before that, its chroma}
    reg [31:0] l1, l2;
    reg        v1, v2, top1, top2, bot1, bot2, ok1, ok2;
    reg [10:0] x1, x2;
    reg [7:0]  y1, y2;
    reg [15:0] c1, c2;
    wire [7:0] yc = yi < 8'd16 ? 8'd0 : yi > 8'd235 ? 8'd219 : yi - 8'd16;
    always @(posedge clk) begin
        l1 <= lm[ox];
        l2 <= l1;
        {v2, v1} <= {v1, inw};
        {x2, x1} <= {x1, ox};
        {y2, y1} <= {y1, yc};
        {c2, c1} <= {c1, cbi, cri};
        {top2, top1} <= {top1, y == 12'd1};         // the row above is the picture's first: nothing above it
        {bot2, bot1} <= {bot1, y == 12'd1080};      // ... its last: nothing below
        // (the pixel coming out: one to the left, a row above: in the picture?)
        {ok2, ok1} <= {ok1, x >= 13'd241 && x < 13'd1681 && y >= 12'd1 && y <= 12'd1080};
        if (v2)
            lm[x2] <= {y2, l2[31:24], c2};
    end
    // 3: this column (k0): the middle row's pixel e, above it b, below it h; 4: the column before
    // (k1), the one worked on, between its left (k2) and its right (k0); 5: the five
    reg [7:0]  k0_e, k0_b, k0_h, k1_e, k1_b, k1_h, k2_e;
    reg [15:0] k0_c, k1_c;
    reg        k0_first, k0_last, k1_first, k1_last, k0_ok;
    reg [7:0]  m_e, m_b, m_h, m_d, m_f;
    reg [15:0] m_c;
    reg        m_ok;
    wire [7:0] ce = l2[31:24];
    always @(posedge clk) begin
        k0_e <= ce;
        k0_b <= top2 ? ce : l2[23:16];
        k0_h <= bot2 ? ce : y2;
        k0_c <= l2[15:0];
        k0_first <= x2 == 11'd0;
        k0_last <= x2 == 11'd1439;
        k0_ok <= ok2;                   // (of the column before this one: as k1 is when it is used)
        k1_e <= k0_e;
        k1_b <= k0_b;
        k1_h <= k0_h;
        k1_c <= k0_c;
        k1_first <= k0_first;
        k1_last <= k0_last;
        k2_e <= k1_e;
        m_e <= k1_e;
        m_b <= k1_b;
        m_h <= k1_h;
        m_d <= k1_first ? k1_e : k2_e;
        m_f <= k1_last ? k1_e : k0_e;
        m_c <= k1_c;
        m_ok <= k0_ok;
    end

    // 6: two and two; 7: the four's least, greatest and sum; 8: with the middle, and the reciprocals
    reg [7:0]  mnA, mnB, mxA, mxB, e5, e6, e7, mn4, mx4, mne, pmx;
    reg [8:0]  sA, sB;
    reg [9:0]  s6, s7;
    reg [12:0] r1, r2;
    reg [15:0] c5, c6, c7;
    reg        ok5, ok6, ok7;
    always @(posedge clk) begin
        mnA <= min2(m_b, m_d);
        mnB <= min2(m_f, m_h);
        mxA <= max2(m_b, m_d);
        mxB <= max2(m_f, m_h);
        sA <= m_b + m_d;
        sB <= m_f + m_h;
        e5 <= m_e;
        c5 <= m_c;
        ok5 <= m_ok;
        mn4 <= min2(mnA, mnB);
        mx4 <= max2(mxA, mxB);
        s6 <= sA + sB;
        e6 <= e5;
        c6 <= c5;
        ok6 <= ok5;
        mne <= min2(mn4, e6);
        pmx <= P - max2(mx4, e6);
        r1 <= recip[mx4];
        r2 <= recip[8'd219 - mn4];
        s7 <= s6;
        e7 <= e6;
        c7 <= c6;
        ok7 <= ok6;
    end
    // 9, 10: the two limits; 11: the least of them and 48; 12: times sharp / 16
    wire signed [22:0] t1, t2;
    easu_mul #(.AW(9), .BW(14)) u_t1 (.clk(clk), .a({1'b0, mne}), .b({1'b0, r1}), .p(t1));
    easu_mul #(.AW(9), .BW(14)) u_t2 (.clk(clk), .a({1'b0, pmx}), .b({1'b0, r2}), .p(t2));
    reg [5:0]  l10, ls;
    reg [10:0] lsm;
    reg [9:0]  s8, s9, s10, s11;
    reg [7:0]  e8, e9, e10, e11;
    reg [15:0] c8, c9, c10, c11;
    reg        ok8, ok9, ok10, ok11;
    wire [16:0] u1 = t1[22:6], u2 = t2[22:6];
    wire [16:0] um = u1 < u2 ? u1 : u2;
    always @(posedge clk) begin
        {s9, s8} <= {s8, s7};
        {e9, e8} <= {e8, e7};
        {c9, c8} <= {c8, c7};
        {ok9, ok8} <= {ok8, ok7};
        l10 <= um > 17'd48 ? 6'd48 : um[5:0];
        s10 <= s9;
        e10 <= e9;
        c10 <= c9;
        ok10 <= ok9;
        lsm = l10 * sharp;
        ls <= lsm[9:4];
        s11 <= s10;
        e11 <= e10;
        c11 <= c10;
        ok11 <= ok10;
    end
    // 13, 14: the neighbours' part; 15: taken off; 16, 17: divided; 18: luma again
    wire signed [17:0] q;
    easu_mul #(.AW(7), .BW(11)) u_q (.clk(clk), .a({1'b0, ls}), .b({1'b0, s11}), .p(q));
    reg [10:0] rd12, rd13, rd14;
    reg [7:0]  e12, e13;
    reg [16:0] num;
    reg [15:0] c12, c13, c14, c15, c16, c17;
    reg        ok12, ok13, ok14, ok15, ok16, ok17;
    wire signed [29:0] pq;
    easu_mul #(.AW(18), .BW(12)) u_d (.clk(clk), .a({1'b0, num}), .b({1'b0, rd14}), .p(pq));
    reg [7:0]  yo;
    wire [29:0] pr = pq + 30'd32768;
    wire [17:0] dif = {2'b00, e13, 8'd0} - q;
    always @(posedge clk) begin
        rd12 <= rdiv[ls];
        rd13 <= rd12;
        rd14 <= rd13;
        {e13, e12} <= {e12, e11};
        {c17, c16, c15, c14, c13, c12} <= {c16, c15, c14, c13, c12, c11};
        {ok17, ok16, ok15, ok14, ok13, ok12} <= {ok16, ok15, ok14, ok13, ok12, ok11};
        num <= dif[17] ? 17'd0 : dif[16:0];
        yo <= pr[29:16] > P ? 8'd235 : pr[23:16] + 8'd16;
    end

    // 19 to 23: R'G'B'
    reg signed [9:0]  yv;
    reg signed [8:0]  cbv, crv;
    reg signed [19:0] my, mrv, mgu, mgv, mbu;
    reg signed [19:0] sr, sg, sb;
    reg [7:0]  r20, g20, b20;
    reg        ok18, ok19, ok20, ok21;
    function [7:0] clamp(input signed [19:0] v);
        clamp = v[19] ? 8'd0 : |v[18:16] ? 8'hFF : v[15:8];
    endfunction
    always @(posedge clk) begin
        yv <= yo < 8'd16 ? 10'sd0 : $signed({2'b00, yo}) - 10'sd16;
        cbv <= $signed({1'b0, c17[15:8]}) - 9'sd128;
        crv <= $signed({1'b0, c17[7:0]}) - 9'sd128;
        my <= yv * 11'sd298;
        mrv <= crv * 11'sd409;
        mgu <= cbv * 11'sd100;
        mgv <= crv * 11'sd208;
        mbu <= cbv * 11'sd516;
        sr <= my + mrv + 20'sd128;
        sg <= my - mgu - mgv + 20'sd128;
        sb <= my + mbu + 20'sd128;
        r20 <= clamp(sr);
        g20 <= clamp(sg);
        b20 <= clamp(sb);
        {ok21, ok20, ok19, ok18} <= {ok20, ok19, ok18, ok17};
        r <= ok21 ? r20 : 8'd0;
        g <= ok21 ? g20 : 8'd0;
        b <= ok21 ? b20 : 8'd0;
    end
endmodule
