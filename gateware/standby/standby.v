// standby.v: the image the board stands by in.  The link (the XIAO) loads it into the FPGA in the
// scaler's place when the board is to stand by, and the flash's image again to wake it
// (firmware/xiao-wifi: gowin.c, scaler.c).  No clock, no register: wires.
//
//   - the HDMI redriver's enable low (its outputs off), the video decoder in reset, the DDR3 in reset
//     with its clock enable low
//   - the carrier's three LEDs off: the status LED, and the two that show the FPGA's DONE and READY
//     (those pins are the design's here: gowin/avb.tcl GW_STANDBY)
//   - the first button (low while pressed) passed on to the link on its interrupt line, which it
//     watches while the board stands by: the button wakes the board
// Everything else is left alone: pins not named here are inputs with a weak pull-up (the flash's
// select stays high); the transceivers and the CPU are not in it.
module top (
    input  in_key1,
    input  in_key2,
    output esp_irq,
    output in_led,
    output dp_oe,
    output in_reset_n,
    output fpga_done,
    output fpga_ready,
    output ddr_reset_n,
    output ddr_cke
);
    assign esp_irq = in_key1 & in_key2;     // (either button: low while one is pressed)
    assign in_led = 1'b0;
    assign dp_oe = 1'b0;
    assign in_reset_n = 1'b0;
    assign fpga_done = 1'b0;
    assign fpga_ready = 1'b0;
    assign ddr_reset_n = 1'b0;
    assign ddr_cke = 1'b0;
endmodule
