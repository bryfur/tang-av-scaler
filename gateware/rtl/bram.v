// bram.v: memories put into the FPGA's block RAM by hand, where the synthesis would take twice the
// room.  A block here is 18 kbit and at most 18 bits wide: a memory of 512 words of 32 bits, left to
// the synthesis, becomes one "36 bits wide" RAM, which the placement puts on two blocks, each half
// empty (seen: gowin/ notes, 2026-11-13: 10 RAMs in the netlist, 16 blocks placed).
//
// bram32: 512 words of 32 bits in one block: a dual-port RAM of 1024 x 16, the words' low halves in
// its lower 512 through one port and the high halves in its upper 512 through the other, both ports
// writing (we) or both reading.  So: no read in a clock with a write (the word read then is not
// taken: q keeps what it had); what uses it writes and reads at different times.  LAT 2: q two clocks
// after ra (the RAM's own output register: like a register after the RAM in logic); LAT 1: one.
//
// AVB_GOWIN (gowin/avb.tcl's defines): the primitive; else the same in plain Verilog (the tests;
// sim/bram_tb.py puts the two side by side with the vendor's model of the primitive).

module bram32 #(
    parameter LAT = 2
) (
    input              clk,
    input              we,
    input      [8:0]   wa,
    input      [31:0]  wd,
    input      [8:0]   ra,
    output     [31:0]  q
);
`ifdef AVB_GOWIN
    wire [8:0] a = we ? wa : ra;
    DPB #(.READ_MODE0(LAT == 2), .READ_MODE1(LAT == 2), .WRITE_MODE0(2'b00), .WRITE_MODE1(2'b00),
          .BIT_WIDTH_0(16), .BIT_WIDTH_1(16), .BLK_SEL_0(3'b000), .BLK_SEL_1(3'b000), .RESET_MODE("SYNC"))
        u (.DOA(q[15:0]), .DOB(q[31:16]), .DIA(wd[15:0]), .DIB(wd[31:16]), .BLKSELA(3'b000), .BLKSELB(3'b000),
           .ADA({1'b0, a, 2'b00, 2'b11}), .ADB({1'b1, a, 2'b00, 2'b11}), .WREA(we), .WREB(we),
           .CLKA(clk), .CLKB(clk), .CEA(1'b1), .CEB(1'b1), .OCEA(1'b1), .OCEB(1'b1), .RESETA(1'b0), .RESETB(1'b0));
`else
    reg [31:0] mem [0:511];
    reg [31:0] q0 = 32'd0, q1 = 32'd0;
    always @(posedge clk) begin
        if (we)
            mem[wa] <= wd;
        else
            q0 <= mem[ra];
        q1 <= q0;
    end
    assign q = LAT == 2 ? q1 : q0;
`endif
endmodule

// bram16d: 1024 words of 16 bits in one block, written at one place (we, wa) or read at two at once
// (ra_a, ra_b; LAT 2: two clocks after the addresses): the block's two ports.  No read in a clock
// with a write.
module bram16d (
    input              clk,
    input              we,
    input      [9:0]   wa,
    input      [15:0]  wd,
    input      [9:0]   ra_a,
    input      [9:0]   ra_b,
    output     [15:0]  qa,
    output     [15:0]  qb
);
`ifdef AVB_GOWIN
    wire [9:0] a = we ? wa : ra_a;
    DPB #(.READ_MODE0(1'b1), .READ_MODE1(1'b1), .WRITE_MODE0(2'b00), .WRITE_MODE1(2'b00),
          .BIT_WIDTH_0(16), .BIT_WIDTH_1(16), .BLK_SEL_0(3'b000), .BLK_SEL_1(3'b000), .RESET_MODE("SYNC"))
        u (.DOA(qa), .DOB(qb), .DIA(wd), .DIB(16'd0), .BLKSELA(3'b000), .BLKSELB(3'b000),
           .ADA({a, 2'b00, 2'b11}), .ADB({ra_b, 2'b00, 2'b11}), .WREA(we), .WREB(1'b0),
           .CLKA(clk), .CLKB(clk), .CEA(1'b1), .CEB(!we), .OCEA(1'b1), .OCEB(1'b1), .RESETA(1'b0), .RESETB(1'b0));
`else
    reg [15:0] mem [0:1023];
    reg [15:0] a0 = 16'd0, a1 = 16'd0, b0 = 16'd0, b1 = 16'd0;
    always @(posedge clk) begin
        if (we)
            mem[wa] <= wd;
        else begin
            a0 <= mem[ra_a];
            b0 <= mem[ra_b];
        end
        a1 <= a0;
        b1 <= b0;
    end
    assign qa = a1;
    assign qb = b1;
`endif
endmodule
