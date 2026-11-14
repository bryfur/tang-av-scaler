// cnn_top.v: rtl/cnn.v alone, 96 pixels wide, for the synthesis: its netlist is simulated against the
// test pictures (sim/cnn_tb.py synth)
module top (input clk, input go, input signed [10:0] n, input quiet, input [9:0] first, input [9:0] last, output busy, output rdy,
            output [9:0] s_col, output [49:0] s_line, input [55:0] s_r, output o_we, output [10:0] o_line, output [10:0] o_col,
            output [7:0] o_d, output c_we, output [9:0] c_line, output [9:0] c_col, output [15:0] c_d);
    wire l_ack;
    cnn #(.W(96)) u (.clk(clk), .go(go), .n(n), .quiet(quiet), .first(first), .last(last), .busy(busy), .rdy(rdy), .s_col(s_col),
                     .s_line(s_line), .s_r(s_r), .o_we(o_we), .o_line(o_line), .o_col(o_col), .o_d(o_d), .c_we(c_we),
                     .c_line(c_line), .c_col(c_col), .c_d(c_d), .l_req(1'b0), .l_a(12'd0), .l_d(22'd0), .l_ack(l_ack));
endmodule
