// ddr_arb.v: the DDR3 controller's one port (rtl/ddr3/ddr3_top.v: Gowin's DDR3 interface's, a line
// of 256 bits a command) shared by three users, on its user clock:
//   a   writes (the capture): first
//   b   reads (the picture)
//   c   reads and writes (the host's monitor): last
// A user holds valid, its line's number and data until ack (a clock: the command is taken).  Reads
// come back in the order asked, a user's own with its rvalid: a clock after the controller's
// rd_data_valid (registered here: the user takes rd_data a clock later too).

module ddr_arb (
    input              clk,
    input              cmd_ready,
    output reg  [2:0]  cmd = 3'd0,
    output reg         cmd_en = 1'b0,
    output reg  [28:0] addr = 29'd0,
    output reg  [255:0] wr_data = 256'd0,
    output reg         wr_data_en = 1'b0,
    input              rd_data_valid,

    input              a_valid,
    input       [24:0] a_line,
    input      [255:0] a_data,
    output             a_ack,

    input              b_valid,
    input       [24:0] b_line,
    output             b_ack,
    output             b_rvalid,

    input              c_valid,
    input              c_wr,
    input       [24:0] c_line,
    input      [255:0] c_data,
    output             c_ack,
    output             c_rvalid
);
    assign a_ack = cmd_ready && a_valid;
    assign b_ack = cmd_ready && !a_valid && b_valid;
    assign c_ack = cmd_ready && !a_valid && !b_valid && c_valid;

    // whose each read in flight is
    reg [63:0] who;
    reg [5:0]  wp = 6'd0, rp = 6'd0;
    reg        rv = 1'b0;
    always @(posedge clk) begin
        cmd_en <= a_ack || b_ack || c_ack;
        wr_data_en <= a_ack || (c_ack && c_wr);
        cmd <= (a_ack || (c_ack && c_wr)) ? 3'd0 : 3'd1;
        addr <= {1'b0, a_ack ? a_line : b_ack ? b_line : c_line, 3'b000};
        wr_data <= a_ack ? a_data : c_data;
        if (b_ack || (c_ack && !c_wr)) begin
            who[wp] <= c_ack;
            wp <= wp + 6'd1;
        end
        rv <= rd_data_valid;
        if (rv)
            rp <= rp + 6'd1;
    end
    assign b_rvalid = rv && !who[rp];
    assign c_rvalid = rv && who[rp];
endmodule
