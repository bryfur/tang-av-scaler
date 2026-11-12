// fbview.v: the frame store (vcap.v's field: 720 x 240, {Cb, Y0, Cr, Y1} a word) as a 1920 x 1080
// picture: 1440 x 1080 in the middle (4:3), a store's pixel two columns and four or five rows,
// black beside it.  Y'CbCr [BT.601, 16-235] to R'G'B' 0-255.
//
// The rows: the store's line n is line 2n of the 480-line frame if its field is the top one, 2n + 1
// if the bottom one, and a row shows the nearest: row r's place in the frame is (8r - 5)/18 lines,
// so line floor((8r + 13)/36) of a top field, floor((8r - 5)/36) of a bottom one.  bob: each line's
// field is asked of the flags vcap.v writes (f_*: the store may hold part of one field and part of
// the next), top the F of the top field; else every line is taken as a top field's.
//
// de, x, y: the output's pixel (pattern.v's ox, oy); r, g, b are that pixel's LAT clocks later.
// base0: the store's address of the first line shown, less 60 (the picture's left edge is column
// 240: a word is four columns); voff that line's number.

module fbview #(
    parameter LAST = 239                // the last line shown, from the first
) (
    input             clk,
    input             de,
    input      [12:0] x,
    input      [11:0] y,
    input      [16:0] base0,
    input      [7:0]  voff,
    input             swap,             // Cb and Cr the other way round
    input             bob,
    input             top,
    input             f_clk,
    input             f_we,
    input      [7:0]  f_wa,
    input             f_wd,
    output reg [16:0] ra,
    input      [31:0] rd,               // the word at ra four clocks before
    output reg [7:0]  r,
    output reg [7:0]  g,
    output reg [7:0]  b
);
    localparam LAT = 10;

    reg        flag [0:255];
    always @(posedge f_clk)
        if (f_we)
            flag[f_wa] <= f_wd;

    // at the end of a row the next one's lines, as a top and as a bottom field's; then the flag of
    // the first, and the choice
    reg [16:0] base, base_t, base_b;
    reg [5:0]  acc_t, acc_b;
    reg [7:0]  nt;
    reg        neg, fl_q;
    reg [2:0]  eol_d;
    wire       eol = de && x == 13'd1919;
    always @(posedge clk) begin
        eol_d <= {eol_d[1:0], eol};
        if (eol) begin
            if (y == 12'd1079) begin
                acc_t <= 6'd13;
                nt <= 8'd0;
                base_t <= base0;
                acc_b <= 6'd31;         // -5: the line before the first, shown as the first
                neg <= 1'b1;
                base_b <= base0;
            end else begin
                if (acc_t >= 6'd28) begin
                    acc_t <= acc_t - 6'd28;
                    if (nt != LAST) begin
                        nt <= nt + 8'd1;
                        base_t <= base_t + 17'd360;
                    end
                end else
                    acc_t <= acc_t + 6'd8;
                if (acc_b >= 6'd28) begin
                    acc_b <= acc_b - 6'd28;
                    neg <= 1'b0;
                    if (!neg)
                        base_b <= base_b + 17'd360;
                end else
                    acc_b <= acc_b + 6'd8;
            end
        end
        fl_q <= flag[nt + voff];
        if (eol_d[2])
            base <= bob && fl_q != top ? base_b : base_t;
    end

    // 1: the address; 5: the word; 6: the pixel; 7: less the offsets; 8: the products; 9: the sums;
    // 10: r, g, b
    reg [5:1]  win, sub;
    reg [7:0]  py, pcb, pcr;
    reg        win6, win7, win8, win9;
    reg signed [9:0]  yv;
    reg signed [8:0]  cbv, crv;
    reg signed [19:0] my, mrv, mgu, mgv, mbu;
    reg signed [19:0] sr, sg, sb;
    function [7:0] clamp(input signed [19:0] v);
        clamp = v[19] ? 8'd0 : |v[18:16] ? 8'hFF : v[15:8];
    endfunction
    always @(posedge clk) begin
        ra <= base + {8'd0, x[10:2]};
        win <= {win[4:1], de && x >= 13'd240 && x < 13'd1680};
        sub <= {sub[4:1], x[1]};
        py <= sub[5] ? rd[7:0] : rd[23:16];
        pcb <= swap ? rd[15:8] : rd[31:24];
        pcr <= swap ? rd[31:24] : rd[15:8];
        win6 <= win[5];
        yv <= py < 8'd16 ? 10'sd0 : $signed({2'b00, py}) - 10'sd16;
        cbv <= $signed({1'b0, pcb}) - 9'sd128;
        crv <= $signed({1'b0, pcr}) - 9'sd128;
        win7 <= win6;
        my <= yv * 11'sd298;
        mrv <= crv * 11'sd409;
        mgu <= cbv * 11'sd100;
        mgv <= crv * 11'sd208;
        mbu <= cbv * 11'sd516;
        win8 <= win7;
        win9 <= win8;
        sr <= my + mrv + 20'sd128;
        sg <= my - mgu - mgv + 20'sd128;
        sb <= my + mbu + 20'sd128;
        r <= win9 ? clamp(sr) : 8'd0;
        g <= win9 ? clamp(sg) : 8'd0;
        b <= win9 ? clamp(sb) : 8'd0;
    end
endmodule
