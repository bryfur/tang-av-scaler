// dline.v: a delay of D clocks (4 to 4096) in a RAM as deep as it needs (the next power of two
// over D + 4: a delay of 26 is 32 words, not a block RAM's 4096).
module dline #(
    parameter W = 8,
    parameter D = 2200
) (
    input              clk,
    input              ce,            // a pixel's clock (0: everything here stays as it is)
    input      [W - 1:0] d,
    output reg [W - 1:0] q
);
    localparam AW = $clog2(D + 4);
    reg [W - 1:0] mem [0:(1 << AW) - 1];
    reg [AW - 1:0] wa = 0;
    reg [AW - 1:0] ra = 0;
    reg [W - 1:0] q1;
    always @(posedge clk) if (ce) begin
        wa <= wa + 1'b1;
        ra <= wa - (D - 3);             // (written at wa; read into q1 at ra, a clock after ra is set)
        mem[wa] <= d;
        q1 <= mem[ra];
        q <= q1;
    end
endmodule
