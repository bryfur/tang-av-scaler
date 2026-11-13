// cpu_ddr.v: the hard CPU's data memory port (the A25's "customized data memory": AHB, 64 bits,
// 0x00000000 to 0x3FFFFFFF: rtl/cpu.v) on the DDR3, all 1 GB of it, as ddr_arb.v's fourth user.
// A line of the memory (32 bytes: a burst, and the core's cache line) is the unit; the line at
// address A is the arbiter's line A / 32, its byte A % 32 the line's bits [8 x that +: 8].
//
//   reads    one line kept (rline): a read in it is answered from it; another line is read from
//            the memory first (the bus waits)
//   writes   gathered in a line (wline, the bytes written marked) and written with those bytes'
//            mask when the bus goes to another line, reads a line not kept, or does nothing; a
//            write to the line kept changes that too
//
// The memory keeps order: a read after a write of its line sees it.  The picture's fields are in
// the same memory (rtl/cap_ddr.v says where): the program can read them, and must keep its own
// data out of them.
//
// The bus side is on the SoC's bus clock, the memory's on the controller's: a request (its line
// and data still) and its answer cross as levels that change.  The core's outputs come late in the
// clock and it wants HREADY early: both are registers here, a transfer takes two clocks at least.
// Every response OKAY; BUSY as IDLE.
//
// While the memory is not calibrated (ok low) the port is not there: reads give 0, writes go
// nowhere, at once (the core itself reads a line here as it starts, before the memory is up: on
// the board, the first build, that read waited for ever; the program asks rtl/top.v's DDR register
// before it uses the memory).  And a memory that stops answering must not stop the core for
// ever: after 2^TMO_LOG2 clocks without an answer the port is `dead` until the core's next
// reset, and answers the same way.  first_line: the first line the bus ever asked for (for a
// report: what the core reads as it starts).

module cpu_ddr #(
    parameter TMO_LOG2 = 16
) (
    input              clk,             // the SoC's DDR_CLK
    input              rstn,            // its DDR_HRSTN
    input      [31:0]  haddr,
    input      [1:0]   htrans,
    input              hwrite,
    input      [2:0]   hsize,
    input      [63:0]  hwdata,
    output     [63:0]  hrdata,
    output             hready,

    input              ok,              // the memory is calibrated (a level from its clock)
    input              pclk,            // the memory's side: ddr_arb.v's user d
    output reg         d_valid = 1'b0,
    output             d_wr,
    output     [24:0]  d_line,
    output     [255:0] d_data,
    output     [31:0]  d_mask,          // (1: the byte not written)
    input              d_ack,
    input              d_rvalid,
    input      [255:0] d_rdata,

    output reg [23:0]  n_rd = 24'd0,    // lines read, lines written (for a report)
    output reg [23:0]  n_wr = 24'd0,
    output reg         dead = 1'b0,
    output reg [25:0]  first_line = 26'd0       // (25: there was one, 24:0 the line)
);
    // the transfer in its data phase
    reg          dp = 1'b0, dp_write = 1'b0, ready = 1'b1;
    reg  [29:0]  dp_addr = 30'd0;
    reg  [2:0]   dp_size = 3'd0;
    wire [24:0]  dp_line = dp_addr[29:5];
    wire [1:0]   dp_lane = dp_addr[4:3];
    reg  [63:0]  hrd = 64'd0;
    assign hready = ready;
    assign hrdata = hrd;

    // the line kept, the line gathered
    reg  [255:0] rline = 256'd0, wline = 256'd0;
    reg  [24:0]  rtag = 25'd0, wtag = 25'd0;
    reg  [31:0]  wbytes = 32'd0;
    reg          rvalid = 1'b0, wpend = 1'b0;

    // the bytes a transfer covers in its 64 bits, then in the line
    reg  [7:0]   be;
    always @(*)
        case (dp_size)
            3'd0: be = 8'h01 << dp_addr[2:0];
            3'd1: be = 8'h03 << {dp_addr[2:1], 1'b0};
            3'd2: be = 8'h0f << {dp_addr[2], 2'b00};
            default: be = 8'hff;
        endcase
    wire [31:0]  be_line = {24'd0, be} << {dp_lane, 3'b000};
    wire [255:0] wd_line = {192'd0, hwdata} << {dp_lane, 6'b000000};
    wire [255:0] bm_line;
    genvar g;
    generate for (g = 0; g < 32; g = g + 1) begin : g_bm
        assign bm_line[g * 8 +: 8] = {8{be_line[g]}};
    end endgenerate

    // a request to the memory: its line and data stay until its answer
    reg          req_t = 1'b0, q_wr = 1'b0, rd_out = 1'b0;
    reg  [24:0]  q_line = 25'd0;
    reg  [255:0] q_data = 256'd0;
    reg  [31:0]  q_mask = 32'd0;
    reg          done_t = 1'b0, dn0 = 1'b0, dn1 = 1'b0;
    reg  [255:0] r_line = 256'd0;        // (a read's line, on the memory's clock: still when done_t changes)
    wire         busy = req_t != dn1;
    assign d_wr = q_wr;
    assign d_line = q_line;
    assign d_data = q_data;
    assign d_mask = q_mask;

    wire r_hit = rvalid && rtag == dp_line;
    wire w_same = wtag == dp_line;
    reg [TMO_LOG2:0] tmo = 0;
    reg          ok0 = 1'b0, okc = 1'b0;
    wire         off = dead || !okc;
    always @(posedge clk) begin
        dn0 <= done_t;
        dn1 <= dn0;
        ok0 <= ok;
        okc <= ok0;
        tmo <= busy ? tmo + 1'b1 : 0;
        if (tmo[TMO_LOG2])
            dead <= 1'b1;
        // a read's line is back
        if (rd_out && !busy) begin
            rline <= r_line;
            rtag <= q_line;
            rvalid <= 1'b1;
            rd_out <= 1'b0;
        end
        if (ready) begin
            // the data phase ends: a write's bytes into the gather (and the line kept); the next
            // transfer's address
            if (dp && dp_write) begin
                wline <= ((wpend ? wline : 256'd0) & ~bm_line) | (wd_line & bm_line);
                wbytes <= (wpend ? wbytes : 32'd0) | be_line;
                wtag <= dp_line;
                wpend <= 1'b1;
                if (r_hit)
                    rline <= (rline & ~bm_line) | (wd_line & bm_line);
            end
            dp <= htrans[1];
            dp_write <= hwrite;
            dp_addr <= haddr[29:0];
            dp_size <= hsize;
            if (htrans[1]) begin
                ready <= 1'b0;
                if (!first_line[25])
                    first_line <= {1'b1, haddr[29:5]};
            end
        end else if (off) begin
            hrd <= 64'd0;
            ready <= 1'b1;
        end else if (dp_write) begin
            if (!wpend || w_same)
                ready <= 1'b1;
        end else if (r_hit && !(rd_out && !busy)) begin
            hrd <= rline[dp_lane * 64 +: 64];
            ready <= 1'b1;
        end
        // the memory: the gather written when the bus is not writing its line; the line the bus
        // waits for read
        if (off) begin
            wpend <= 1'b0;
            rvalid <= 1'b0;
        end else if (!busy && !rd_out) begin
            if (wpend && !(dp && dp_write && w_same)) begin
                q_wr <= 1'b1;
                q_line <= wtag;
                q_data <= wline;
                q_mask <= ~wbytes;
                req_t <= !req_t;
                wpend <= 1'b0;
                n_wr <= n_wr + 24'd1;
            end else if (dp && !ready && !dp_write && !r_hit) begin
                q_wr <= 1'b0;
                q_line <= dp_line;
                req_t <= !req_t;
                rd_out <= 1'b1;
                rvalid <= 1'b0;
                n_rd <= n_rd + 24'd1;
            end
        end
        // (the core in reset: the bus side as at the start; a request at the memory goes on to
        // its answer)
        if (!rstn) begin
            dp <= 1'b0;
            ready <= 1'b1;
            wpend <= 1'b0;
            rvalid <= 1'b0;
            dead <= 1'b0;
        end
    end

    // the memory's side
    reg rq0 = 1'b0, rq1 = 1'b0, rq2 = 1'b0, wait_r = 1'b0;
    always @(posedge pclk) begin
        rq0 <= req_t;
        rq1 <= rq0;
        rq2 <= rq1;
        if (rq1 != rq2)
            d_valid <= 1'b1;
        if (d_valid && d_ack) begin
            d_valid <= 1'b0;
            if (q_wr)
                done_t <= !done_t;
            else
                wait_r <= 1'b1;
        end
        if (wait_r && d_rvalid) begin
            r_line <= d_rdata;
            wait_r <= 1'b0;
            done_t <= !done_t;
        end
    end
endmodule
