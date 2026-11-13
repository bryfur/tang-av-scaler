// ddr_arb.v: the DDR3 controller's one port (rtl/ddr3/ddr3_top.v: Gowin's DDR3 interface's, a line
// of 256 bits a command) shared by four users, on its user clock:
//   a   writes (the capture): first
//   b   reads (the picture)
//   c   reads and writes (the host's monitor)
//   d   reads and writes, a write's bytes by a mask (the CPU's data memory: rtl/cpu_ddr.v): last
// A user holds valid, its line's number and data until ack (a clock: the command was taken the
// clock before: ack is a register, so a user need not be beside the arbiter; its request, still up
// in ack's clock, is not taken twice: the register that took it is full then).  A
// command taken waits in a register for the controller's ready (so the controller's ready, late in
// its clock, goes no further than that register: a command every other clock at most).  Reads come
// back in the order asked, a user's own with its rvalid: a clock after the controller's
// rd_data_valid (registered here: the user takes rd_data a clock later too).

module ddr_arb (
    input              clk,
    input              cmd_ready,
    output      [2:0]  cmd,
    output reg         cmd_en = 1'b0,
    output      [28:0] addr,
    output      [255:0] wr_data,
    output      [31:0] wr_mask,         // (1: the byte not written)
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
    output             c_rvalid,

    input              d_valid,
    input              d_wr,
    input       [24:0] d_line,
    input      [255:0] d_data,
    input       [31:0] d_mask,
    output             d_ack,
    output             d_rvalid
);
    reg         h_v = 1'b0, h_wr;
    reg [24:0]  h_line;
    reg [255:0] h_data;
    reg [31:0]  h_mask = 32'd0;
    // (the command goes out the clock after it is given up: the register still holds it then; the
    // ready, late in its clock, goes to cmd_en, wr_data_en and h_v only)
    assign cmd = h_wr ? 3'd0 : 3'd1;
    assign addr = {1'b0, h_line, 3'b000};
    assign wr_data = h_data;
    assign wr_mask = h_mask;
    wire free = !h_v && !cmd_en;
    wire a_take = free && a_valid;
    wire b_take = free && !a_valid && b_valid;
    wire c_take = free && !a_valid && !b_valid && c_valid;
    wire d_take = free && !a_valid && !b_valid && !c_valid && d_valid;
    reg  a_ack_r = 1'b0, b_ack_r = 1'b0, c_ack_r = 1'b0, d_ack_r = 1'b0;
    assign a_ack = a_ack_r;
    assign b_ack = b_ack_r;
    assign c_ack = c_ack_r;
    assign d_ack = d_ack_r;

    // whose each read in flight is
    reg [63:0] who, who_d;
    reg [5:0]  wp = 6'd0, rp = 6'd0;
    reg        rv = 1'b0, rv_b = 1'b0, rv_c = 1'b0, rv_d = 1'b0;    // (whose the word is: registers: what they gate is wide)
    wire [5:0] rp_n = rv ? rp + 6'd1 : rp;
    always @(posedge clk) begin
        cmd_en <= 1'b0;
        wr_data_en <= 1'b0;
        a_ack_r <= a_take;
        b_ack_r <= b_take;
        c_ack_r <= c_take;
        d_ack_r <= d_take;
        if (h_v && cmd_ready) begin
            cmd_en <= 1'b1;
            wr_data_en <= h_wr;
            h_v <= 1'b0;
        end
        // (not in the clock the command goes out in: cmd_en is up then, and h_v already down)
        if (a_take || b_take || c_take || d_take) begin
            h_v <= 1'b1;
            h_wr <= a_take || (c_take && c_wr) || (d_take && d_wr);
            h_line <= a_take ? a_line : b_take ? b_line : c_take ? c_line : d_line;
            h_data <= a_take ? a_data : c_take ? c_data : d_data;
            h_mask <= d_take ? d_mask : 32'd0;
        end
        if (b_take || (c_take && !c_wr) || (d_take && !d_wr)) begin
            who[wp] <= c_take;
            who_d[wp] <= d_take;
            wp <= wp + 6'd1;
        end
        rv <= rd_data_valid;
        rv_b <= rd_data_valid && !who[rp_n] && !who_d[rp_n];
        rv_c <= rd_data_valid && who[rp_n];
        rv_d <= rd_data_valid && who_d[rp_n];
        if (rv)
            rp <= rp + 6'd1;
    end
    assign b_rvalid = rv_b;
    assign c_rvalid = rv_c;
    assign d_rvalid = rv_d;
endmodule
