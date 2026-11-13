// OSER8_MEM as the GW5AST-138C's behaves (sim/ddr3/Makefile gives Gowin's
// model the name OSER8_MEM_gowin and puts this one in its place): Gowin's
// model for the data, and the output enable as measured on the board
// (2026-11-11, tools/console/ddr3lab.py's write windows):
//
//   - on a data pin (TCLK_SOURCE "DQSW270") the pin drives only once its
//     enable has been on for two slots, and stops at once;
//   - on the strobe (TCLK_SOURCE "DQSW") it drives in the slot it is told
//     to, as in Gowin's model.

`timescale 1ns / 1ps

module OSER8_MEM #(
    parameter HWL = "false",
    parameter TCLK_SOURCE = "DQSW",
    parameter TXCLK_POL = 1'b0
) (
    input  wire D0, D1, D2, D3, D4, D5, D6, D7,
    input  wire TX0, TX1, TX2, TX3,
    input  wire PCLK, FCLK, TCLK, RESET,
    output wire Q0,
    output wire Q1
);

wire q1;
OSER8_MEM_gowin #(
    .HWL(HWL), .TCLK_SOURCE(TCLK_SOURCE), .TXCLK_POL(TXCLK_POL)
) u (
    .D0(D0), .D1(D1), .D2(D2), .D3(D3), .D4(D4), .D5(D5), .D6(D6), .D7(D7),
    .TX0(TX0), .TX1(TX1), .TX2(TX2), .TX3(TX3),
    .PCLK(PCLK), .FCLK(FCLK), .TCLK(TCLK), .RESET(RESET), .Q0(Q0), .Q1(q1)
);

wire tclk = TCLK_SOURCE == "DQSW" ? TCLK : !TCLK;
reg  q1_a = 1'b1, q1_b = 1'b1;
always @(posedge tclk) begin
    q1_a <= q1;
    q1_b <= q1_a;
end
assign Q1 = TCLK_SOURCE == "DQSW" ? q1 : q1 | q1_a | q1_b;

endmodule
