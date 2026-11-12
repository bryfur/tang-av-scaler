// uart.v: 8N1, DIV system clocks a bit

module uart_rx #(parameter DIV = 50) (
    input            clk,
    input            rx,
    output reg [7:0] data,
    output reg       valid
);
    reg [2:0]  s = 3'b111;
    reg [15:0] cnt;
    reg [3:0]  n;
    reg        busy = 1'b0;
    reg [7:0]  sh;
    always @(posedge clk) begin
        s <= {s[1:0], rx};
        valid <= 1'b0;
        if (!busy) begin
            if (!s[2]) begin                    // the start bit's edge: bit 0's middle is 1.5 bits on
                busy <= 1'b1;
                cnt <= DIV + DIV / 2 - 2;
                n <= 4'd0;
            end
        end else if (cnt == 0) begin
            cnt <= DIV - 1;
            if (n == 4'd8) begin                // the stop bit
                busy <= 1'b0;
                if (s[2]) begin
                    data <= sh;
                    valid <= 1'b1;
                end
            end else begin
                sh <= {s[2], sh[7:1]};
                n <= n + 4'd1;
            end
        end else
            cnt <= cnt - 16'd1;
    end
endmodule

module uart_tx #(parameter DIV = 50) (
    input       clk,
    input [7:0] data,
    input       start,      // with ready
    output      ready,
    output reg  tx = 1'b1
);
    reg [15:0] cnt;
    reg [3:0]  n = 4'd0;    // bits left, the stop bit included
    reg [8:0]  sh;
    assign ready = n == 4'd0;
    always @(posedge clk) begin
        if (ready) begin
            if (start) begin
                sh <= {1'b1, data};
                tx <= 1'b0;
                cnt <= DIV - 1;
                n <= 4'd10;
            end
        end else if (cnt == 0) begin
            cnt <= DIV - 1;
            tx <= sh[0];
            sh <= {1'b1, sh[8:1]};
            n <= n - 4'd1;
        end else
            cnt <= cnt - 16'd1;
    end
endmodule
