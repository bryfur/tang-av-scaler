// temp.v: a test: the chip's own temperature sensor (the ADC in its upper left corner, ADCULC) by
// itself: does the flow take it.  led: a measurement is there.
module top (
    input  sys_clk,
    output in_led
);
    wire        rdy;
    wire [13:0] val;
    reg  [24:0] n = 25'd0;
    reg         got = 1'b0;
    always @(posedge sys_clk) begin
        n <= n + 25'd1;
        if (rdy)
            got <= 1'b1;
    end
    ADCULC #(.DYN_BKEN("FALSE"), .CLK_SEL(1'b0), .PIOCLK_SEL(1'b0), .VSEN_CTL(3'b000), .VSEN_CTL_SEL(1'b0),
             .ADC_MODE(1'b0), .DIV_CTL(2'd0), .SAMPLE_CNT_SEL(3'd4), .RATE_CHANGE_CTRL(3'd4))
        u_adc (.ADCINBK6A(1'b0), .ADCINBK6B(1'b0), .ADCINBK7A(1'b0), .ADCINBK7B(1'b0), .VSENCTL(3'b000),
               .FSCAL_VALUE(10'd730), .OFFSET_VALUE(-12'sd1180), .ADCEN(1'b1), .CLK(sys_clk), .DRSTN(1'b1),
               .ADCREQI(n[24]), .ADCRDY(rdy), .ADCVALUE(val));
    assign in_led = got ^ val[2];
endmodule
