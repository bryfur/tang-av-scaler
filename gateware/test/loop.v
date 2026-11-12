// loop.v: a wiring test of the XIAO's lines, read with the XIAO's own pin-level command:
//   ESP_RX and ESP_MISO follow ESP_TX; ESP_IRQ follows ESP_CS (both idle high)
//   the LED blinks from the oscillator, no PLL (1.5 Hz)
module top (
    input  sys_clk,
    input  esp_tx,
    input  esp_cs,
    output esp_rx,
    output esp_miso,
    output esp_irq,
    output in_led
);
    assign esp_rx = esp_tx;
    assign esp_miso = esp_tx;
    assign esp_irq = esp_cs;
    reg [24:0] n = 25'd0;
    always @(posedge sys_clk)
        n <= n + 25'd1;
    assign in_led = n[24];
endmodule
