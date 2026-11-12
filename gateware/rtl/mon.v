// mon.v: the bring-up monitor, a register bus on the UART (the XIAO's USB serial port).
//
//   'W' addr d0 d1 d2 d3      write a 32-bit word (little-endian); no reply
//   'R' addr                  read: four bytes back
//
// Any other byte between commands is skipped; a command cut short is dropped after 40 ms of
// silence, so a host that starts with a pause is in step.  Until the first command byte the
// monitor says "AVB1\r\n" every 0.67 s: a sign of life with nothing asked.  Commands queue in a
// 4096-byte FIFO: a write may hold the next command (hold, e.g. an I2C line still rising).

module mon #(parameter DIV = 50) (
    input             clk,
    input             rx,
    output            tx,
    output reg [7:0]  addr,
    output reg [31:0] wdata,
    output reg        we = 1'b0,
    input      [31:0] rdata,        // of addr, a clock later
    input             hold
);
    wire [7:0] rx_data;
    wire       rx_valid;
    uart_rx #(.DIV(DIV)) u_rx (.clk(clk), .rx(rx), .data(rx_data), .valid(rx_valid));

    reg  [7:0] tx_data;
    reg        tx_start = 1'b0;
    wire       tx_ready;
    uart_tx #(.DIV(DIV)) u_tx (.clk(clk), .data(tx_data), .start(tx_start), .ready(tx_ready), .tx(tx));

    // the FIFO: q is mem[rp] once rp has stood for a clock and its entry was written before that
    reg [7:0]  mem [0:4095];
    reg [11:0] wp = 12'd0, wp_d = 12'd0, rp = 12'd0;
    reg [7:0]  q;
    reg        popped = 1'b0;
    wire       ready = wp_d != rp && !popped;
    reg        pop;
    always @(posedge clk) begin
        if (rx_valid && wp + 12'd1 != rp) begin
            mem[wp] <= rx_data;
            wp <= wp + 12'd1;
        end
        wp_d <= wp;
        q <= mem[rp];
        popped <= pop;
        if (pop)
            rp <= rp + 12'd1;
    end

    localparam S_CMD = 0, S_ADDR = 1, S_DATA = 2, S_WR = 3, S_HOLD = 4, S_RD = 5, S_RD2 = 6, S_TX = 7, S_BAN = 8;
    reg [3:0]  state = S_CMD;
    reg        is_w;
    reg [2:0]  n;
    reg [31:0] rsh;
    reg [21:0] quiet;
    reg        seen = 1'b0;
    reg [24:0] ban_t = 25'd0;
    reg [1:0]  held;

    function [7:0] banner(input [2:0] k);
        case (k)
            3'd0: banner = "A";
            3'd1: banner = "V";
            3'd2: banner = "B";
            3'd3: banner = "1";
            3'd4: banner = 8'h0D;
            default: banner = 8'h0A;
        endcase
    endfunction

    always @* pop = ready && (state == S_CMD || state == S_ADDR || state == S_DATA);

    always @(posedge clk) begin
        we <= 1'b0;
        tx_start <= 1'b0;
        ban_t <= ban_t + 25'd1;
        quiet <= pop ? 22'd0 : quiet + 22'd1;
        case (state)
            S_CMD:
                if (ready) begin
                    seen <= 1'b1;
                    is_w <= q == "W";
                    if (q == "W" || q == "R")
                        state <= S_ADDR;
                end else if (!seen && &ban_t) begin
                    n <= 3'd0;
                    state <= S_BAN;
                end
            S_ADDR:
                if (ready) begin
                    addr <= q;
                    n <= 3'd0;
                    state <= is_w ? S_DATA : S_RD;
                end else if (&quiet)
                    state <= S_CMD;
            S_DATA:
                if (ready) begin
                    wdata <= {q, wdata[31:8]};
                    n <= n + 3'd1;
                    if (n == 3'd3)
                        state <= S_WR;
                end else if (&quiet)
                    state <= S_CMD;
            S_WR: begin
                we <= 1'b1;
                held <= 2'd0;
                state <= S_HOLD;
            end
            S_HOLD: begin                           // two clocks for the write to raise hold
                if (held != 2'd2)
                    held <= held + 2'd1;
                else if (!hold)
                    state <= S_CMD;
            end
            S_RD:
                state <= S_RD2;
            S_RD2: begin
                rsh <= rdata;
                n <= 3'd0;
                state <= S_TX;
            end
            S_TX:
                if (tx_ready && !tx_start) begin
                    if (n == 3'd4)
                        state <= S_CMD;
                    else begin
                        tx_data <= rsh[7:0];
                        rsh <= {8'd0, rsh[31:8]};
                        tx_start <= 1'b1;
                        n <= n + 3'd1;
                    end
                end
            S_BAN:
                if (tx_ready && !tx_start) begin
                    if (n == 3'd6)
                        state <= S_CMD;
                    else begin
                        tx_data <= banner(n);
                        tx_start <= 1'b1;
                        n <= n + 3'd1;
                    end
                end
            default:
                state <= S_CMD;
        endcase
    end
endmodule
