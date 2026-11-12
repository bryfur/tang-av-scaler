// focus.v: how sharp the captured fields are across a line: the sum over a field of the squares
// (in sixteenths) of the luma steps between pixels next to each other (vcap.v's words: within a
// pair, and from the pair before).  The decoder samples a line at a phase that can be set (its DLL:
// 32 steps); a console's pixels come at the same rate as the samples (13.5 MHz for a picture 640
// wide), so a phase at the pixels' middles gives whole steps between neighbours, one between the
// pixels half steps twice: the same sum of steps, half the sum of their squares.  The host tries
// the phases on a still picture and keeps the one with the greatest sum.
//
// sum: the last whole field's (for another clock: it changes once a field; read twice); n counts
// the fields.

module focus (
    input             llc,
    input             we,
    input      [8:0]  w_col,
    input      [31:0] wd,               // {Cb, Y0, Cr, Y1}
    input             eof,
    output reg [27:0] sum = 28'd0,
    output reg [3:0]  n = 4'd0
);
    reg [28:0] acc = 29'd0;
    reg        q_v = 1'b0, r_v = 1'b0;
    reg [7:0]  q_a, q_b, y1;
    reg [12:0] r_s;
    wire [15:0] sa = q_a * q_a, sb = q_b * q_b;
    function [7:0] absd(input [7:0] a, input [7:0] b);
        absd = a > b ? a - b : b - a;
    endfunction
    always @(posedge llc) begin
        q_v <= we;
        if (we) begin
            q_a <= absd(wd[23:16], wd[7:0]);
            q_b <= w_col == 9'd0 ? 8'd0 : absd(wd[23:16], y1);
            y1 <= wd[7:0];
        end
        r_v <= q_v;
        r_s <= {1'b0, sa[15:4]} + {1'b0, sb[15:4]};
        if (eof) begin
            sum <= acc[28] ? 28'hFFFFFFF : acc[27:0];
            n <= n + 4'd1;
            acc <= 29'd0;
        end else if (r_v && !acc[28])
            acc <= acc + {16'd0, r_s};
    end
endmodule
