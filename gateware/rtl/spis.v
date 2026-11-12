// spis.v: the link's SPI port (the XIAO the master: mode 0, a byte's high bit first, 6 MHz at
// most: the lines are sampled by clk), two things on it, by a frame's first byte:
//
// Registers (no program needed: the link can always reach them, e.g. to give the CPU a new one):
//   01 addr d0 d1 d2 d3 [d0 d1 d2 d3 ...]   words written to a register (each word as it is in)
//   02 addr xx -> d0 d1 d2 d3               a register read (the byte xx is the time for it)
// A turn on the register bus each, as the CPU's (cpu.v): between the monitor's words and the CPU's.
//
// Messages for the CPU's program (sw/): a request, then its answer when the program has it:
//   03 bytes ...        a request (252 bytes at most): the program sees it when the frame is over
//   04 -> st lo hi bytes ...   st bit 0: an answer is there, of lo + 256 hi bytes; read whole, it is
//                              gone.  irq_n is low while one waits.
// The program's side, on the register bus:
//   70 SPIS   read: 0 a request waits, 1 an answer waits to be read, 15:8 the request's bytes;
//             write: bit 0 the request is done with, bit 1 an answer of 27:16 bytes is there
//   71 SPIRX  write: which word of the request; read: that word (bytes as they came, the first lowest)
//   72 SPITXA write: the answer's word the next SPITXD writes (it counts on)
//   73 SPITXD write: a word of the answer (2048 bytes at most)
//   74 SPIP   read: the lines as they are: 0 CS, 1 SCK, 2 MOSI, 3 MISO, 4 IRQ

module spis (
    input             clk,
    input             cs_n,
    input             sck,
    input             mosi,
    output reg        miso = 1'b0,
    output            irq_n,
    // its turns on the bus
    output            stall,
    input             mon_busy,
    input             other,            // (the CPU's turn, or about to be)
    output reg        s_own = 1'b0,
    output reg        s_we = 1'b0,
    output reg [7:0]  s_addr,
    output reg [31:0] s_wdata,
    input      [31:0] rdata,
    // the bus (for 70 to 74)
    input             we,
    input      [7:0]  addr,
    input      [31:0] wdata,
    output     [31:0] q_stat,
    output reg [31:0] q_rx,
    output     [31:0] q_pins
);
    // the lines, two registers each, then their edges
    reg [2:0] ck = 3'd0, cs = 3'b111;
    reg [1:0] mo = 2'd0;
    always @(posedge clk) begin
        ck <= {ck[1:0], sck};
        cs <= {cs[1:0], cs_n};
        mo <= {mo[0], mosi};
    end
    wire rise = ck[2:1] == 2'b01 && !cs[1], fall = ck[2:1] == 2'b10 && !cs[1];
    wire start = cs[2:1] == 2'b10, stop = cs[2:1] == 2'b01;

    // the messages' memories
    reg [31:0] rxm [0:63];
    reg [31:0] txm [0:511];
    reg [5:0]  rxa = 6'd0;
    reg [8:0]  txa = 9'd0, tra;
    reg [31:0] txq;
    reg        rx_ready = 1'b0, tx_ready = 1'b0;
    reg [7:0]  rx_len = 8'd0;
    reg [11:0] tx_len = 12'd0;
    assign irq_n = !tx_ready;
    assign q_stat = {16'd0, rx_len, 6'd0, tx_ready, rx_ready};
    assign q_pins = {27'd0, irq_n, miso, mo[1], ck[1], cs[1]};

    // a frame's bytes
    reg [2:0]  bitn = 3'd0;
    reg [6:0]  sh;
    reg        b_stb = 1'b0;            // a byte is in: b_d, the frame's b_n-th
    reg [7:0]  b_d, cmd;
    reg [11:0] b_n = 12'd0;
    reg [7:0]  txsh = 8'd0, ob = 8'd0;  // the byte going out; the next one
    reg [7:0]  r_addr;
    reg [31:0] w, rd;
    reg        rx_we = 1'b0;
    reg [5:0]  rx_wa;
    reg        got = 1'b0;              // (an answer's bytes all went out)
    // its turn on the bus
    reg        pend = 1'b0, pend_q = 1'b0, p_wr;
    reg [1:0]  ts = 2'd0;
    assign stall = pend || s_own;
    wire [11:0] k = b_n - 12'd3;        // (the answer's byte going out next but one)
    always @(posedge clk) begin
        b_stb <= 1'b0;
        rx_we <= 1'b0;
        s_we <= 1'b0;
        pend_q <= pend;
        txq <= txm[tra];
        q_rx <= rxm[rxa];
        if (rx_we)
            rxm[rx_wa] <= w;
        // the CPU's side
        if (we && addr == 8'h70) begin
            if (wdata[0])
                rx_ready <= 1'b0;
            if (wdata[1]) begin
                tx_ready <= 1'b1;
                tx_len <= wdata[27:16];
            end
        end
        if (we && addr == 8'h71)
            rxa <= wdata[5:0];
        if (we && addr == 8'h72)
            txa <= wdata[8:0];
        if (we && addr == 8'h73) begin
            txm[txa] <= wdata;
            txa <= txa + 9'd1;
        end

        // bits
        if (start) begin
            bitn <= 3'd0;
            b_n <= 12'd0;
            txsh <= 8'd0;
            miso <= 1'b0;
            ob <= 8'd0;
            cmd <= 8'd0;
            got <= 1'b0;
        end else if (rise) begin
            sh <= {sh[5:0], mo[1]};
            bitn <= bitn + 3'd1;
            if (bitn == 3'd7) begin
                b_d <= {sh, mo[1]};
                b_stb <= 1'b1;
            end
        end else if (fall) begin
            if (bitn == 3'd0) begin
                txsh <= ob;
                miso <= ob[7];
            end else begin
                txsh <= {txsh[6:0], 1'b0};
                miso <= txsh[6];
            end
        end

        // bytes
        if (b_stb) begin
            b_n <= b_n + 12'd1;
            if (b_n == 12'd0) begin
                cmd <= b_d;
                // (an answer's first byte out: is there one)
                ob <= b_d == 8'h04 ? {7'd0, tx_ready} : 8'd0;
            end else
                case (cmd)
                    8'h01: begin
                        if (b_n == 12'd1)
                            r_addr <= b_d;
                        else begin
                            w <= {b_d, w[31:8]};
                            if (b_n[1:0] == 2'd1) begin         // (the word's fourth byte: 5, 9, ...)
                                pend <= 1'b1;
                                p_wr <= 1'b1;
                            end
                        end
                    end
                    8'h02: begin
                        if (b_n == 12'd1) begin
                            r_addr <= b_d;
                            pend <= 1'b1;
                            p_wr <= 1'b0;
                        end
                        ob <= b_n == 12'd2 ? rd[7:0] : b_n == 12'd3 ? rd[15:8] : b_n == 12'd4 ? rd[23:16] : rd[31:24];
                    end
                    8'h03: if (!rx_ready && b_n <= 12'd252) begin
                        w <= {b_d, w[31:8]};
                        rx_len <= b_n[7:0];
                        if (b_n[1:0] == 2'd0) begin             // (a word's fourth byte: 4, 8, ...)
                            rx_we <= 1'b1;
                            rx_wa <= b_n[7:2] - 6'd1;
                        end
                    end
                    8'h04: begin
                        tra <= k[10:2] + (k[1:0] == 2'd3 ? 9'd1 : 9'd0);
                        ob <= b_n == 12'd1 ? tx_len[7:0] : b_n == 12'd2 ? {4'd0, tx_len[11:8]} :
                              k[1:0] == 2'd0 ? txq[7:0] : k[1:0] == 2'd1 ? txq[15:8] : k[1:0] == 2'd2 ? txq[23:16] : txq[31:24];
                        if (tx_ready && b_n == tx_len + 12'd3)
                            got <= 1'b1;
                    end
                    default: ;
                endcase
            if (b_n == 12'd0 && b_d == 8'h04)
                tra <= 9'd0;
        end
        // (a write's word as the turn takes it: w has it until the next word's first byte)
        if (stop) begin
            if (cmd == 8'h03 && !rx_ready && b_n > 12'd1) begin
                rx_ready <= 1'b1;
                // (the last word, if it is not whole: its bytes at the top of w)
                if (rx_len[1:0] != 2'd0) begin
                    rx_we <= 1'b1;
                    rx_wa <= rx_len[7:2];
                    w <= rx_len[1:0] == 2'd1 ? {24'd0, w[31:24]} : rx_len[1:0] == 2'd2 ? {16'd0, w[31:16]} : {8'd0, w[31:8]};
                end
            end
            if (cmd == 8'h04 && got)
                tx_ready <= 1'b0;
        end

        // the turn on the bus (as cpu.v's)
        case (ts)
            2'd0:
                if (pend && pend_q && !mon_busy && !other) begin
                    s_own <= 1'b1;
                    s_addr <= r_addr;
                    s_wdata <= w;
                    ts <= 2'd1;
                end
            2'd1: begin
                s_we <= p_wr;
                ts <= 2'd2;
            end
            2'd2: begin
                rd <= rdata;
                ts <= 2'd3;
            end
            default: begin
                s_own <= 1'b0;
                pend <= 1'b0;
                ts <= 2'd0;
            end
        endcase
    end
endmodule
