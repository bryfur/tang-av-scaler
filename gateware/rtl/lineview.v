// lineview.v: deint.v's progressive picture (720 x 480, {Cb, Y0, Cr, Y1} a word) as a 1920 x 1080
// one: 1440 x 1080 in the middle (4:3), each row the nearest line (row r: line floor((4r + 2)/9)),
// a pixel two columns; black beside it.  Y'CbCr [BT.601, 16-235] to R'G'B' 0-255.
//
// The lines come through a ring of eight, a line's place its number's low three bits, written on
// deint.v's clock (w_*: two lines' words together).  The ring is asked for by events (ev changes at
// the end of each row of picture): ev_first: the frame is over, the next one's lines from 0;
// ev_goal: the line wanted in the ring by now, four past the next row's.
//
// de, x, y: the output's pixel (pattern.v's ox, oy); r, g, b are that pixel's LAT clocks later.

module lineview (
    input             clk,
    input             de,
    input      [12:0] x,
    input      [11:0] y,
    input             swap,
    output reg        ev = 1'b0,
    output reg        ev_first = 1'b0,
    output reg [8:0]  ev_goal = 9'd0,

    input             w_clk,
    input             w_we,
    input      [2:0]  w_slot_d,
    input      [2:0]  w_slot_i,
    input      [8:0]  w_wa,
    input      [31:0] w_wd_d,
    input      [31:0] w_wd_i,

    output reg [7:0]  r,
    output reg [7:0]  g,
    output reg [7:0]  b
);
    localparam LAT = 10;

    // the row's line; at a row's end the next row's, and the event
    reg [8:0] sy = 9'd0;
    reg [3:0] acc = 4'd2;
    reg       eol = 1'b0, eol_q = 1'b0, last = 1'b0;
    always @(posedge clk) begin
        eol <= de && x == 13'd1918;
        last <= y == 12'd1079;
        eol_q <= eol;
        if (eol) begin
            if (last) begin
                sy <= 9'd0;
                acc <= 4'd2;
            end else begin
                sy <= acc >= 4'd5 ? sy + 9'd1 : sy;
                acc <= acc >= 4'd5 ? acc - 4'd5 : acc + 4'd4;
            end
        end
        if (eol_q) begin
            ev <= !ev;
            ev_first <= last;
            ev_goal <= sy >= 9'd475 ? 9'd479 : sy + 9'd4;
        end
    end

    // the ring: eight lines of 512 words, each two block RAMs of 16 bits with its own address and
    // write registers beside it (the RAMs lie apart)
    wire [8:0] ra_n = x[10:2] - 9'd60;
    reg [31:0] q [0:7];
    genvar k;
    generate
        for (k = 0; k < 8; k = k + 1) begin : g_line
            reg [15:0] hi [0:511];
            reg [15:0] lo [0:511];
            reg [8:0]  ra /* synthesis syn_preserve = 1 */;
            reg [8:0]  wa /* synthesis syn_preserve = 1 */;
            reg        wen;
            reg [31:0] wd;
            always @(posedge w_clk) begin
                wen <= w_we && (w_slot_d == k || w_slot_i == k);
                wd <= w_slot_d == k ? w_wd_d : w_wd_i;
                wa <= w_wa;
                if (wen) begin
                    hi[wa] <= wd[31:16];
                    lo[wa] <= wd[15:0];
                end
            end
            always @(posedge clk) begin
                ra <= ra_n;
                q[k] <= {hi[ra], lo[ra]};
            end
        end
    endgenerate

    // 1: the address; 3: the word; 5: as fbview.v from its word on
    reg [31:0] rd3, rd4, rd;
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
        rd3 <= q[sy[2:0]];
        rd4 <= rd3;
        rd <= rd4;
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
