// The DDR3's memory clock: 400 MHz (DDR3-800) from the board's 50 MHz, VCO
// 800 MHz, on CLKOUT2 gated by the controller (enclk: its pll_stop, as
// Gowin's DDR3 IP wants), the loop's charge pump and filter set by
// PLL_INIT (as Sipeed's DDR3 example, TangMega-138K-example ddr_memory).
// Placed at PLL_L[0] (console.cst), beside the DDR3's banks.  Another
// memory clock: DDR_PLL_IDIV, _MDIV, _ODIV (50 / IDIV the PFD, 19 to 81
// MHz; x MDIV the VCO, 650 to 1300 MHz; / ODIV the clock): 525 MHz 1, 21,
// 2; 650 MHz 1, 26, 2.

`ifndef DDR_PLL_IDIV
`define DDR_PLL_IDIV 1
`define DDR_PLL_MDIV 16
`define DDR_PLL_ODIV 2
`endif

module ddr_pll (
    input  wire clkin,                    // 50 MHz
    input  wire rst,
    input  wire enclk,
    output wire memory_clk,
    output wire lock
);

wire gnd = 1'b0;
wire vcc = 1'b1;
wire pll_lock;
wire pll_rst;
wire [5:0] icpsel;
wire [2:0] lpfres;

PLL u (
    .LOCK(pll_lock), .CLKOUT0(), .CLKOUT1(), .CLKOUT2(memory_clk),
    .CLKOUT3(), .CLKOUT4(), .CLKOUT5(), .CLKOUT6(), .CLKFBOUT(),
    .CLKIN(clkin), .CLKFB(gnd), .RESET(pll_rst), .PLLPWD(gnd), .RESET_I(gnd),
    .RESET_O(gnd), .FBDSEL(6'd0), .IDSEL(6'd0), .MDSEL(7'd0),
    .MDSEL_FRAC(3'd0), .ODSEL0(7'd0), .ODSEL0_FRAC(3'd0), .ODSEL1(7'd0),
    .ODSEL2(7'd0), .ODSEL3(7'd0), .ODSEL4(7'd0), .ODSEL5(7'd0),
    .ODSEL6(7'd0), .DT0(4'd0), .DT1(4'd0), .DT2(4'd0), .DT3(4'd0),
    .ICPSEL(icpsel), .LPFRES(lpfres), .LPFCAP(2'b00), .PSSEL(3'd0),
    .PSDIR(gnd), .PSPULSE(gnd), .ENCLK0(vcc), .ENCLK1(vcc), .ENCLK2(enclk),
    .ENCLK3(vcc), .ENCLK4(vcc), .ENCLK5(vcc), .ENCLK6(vcc), .SSCPOL(gnd),
    .SSCON(gnd), .SSCMDSEL(7'd0), .SSCMDSEL_FRAC(3'd0)
);

PLL_INIT ui (
    .CLKIN(clkin), .I_RST(rst), .O_RST(pll_rst), .PLLLOCK(pll_lock),
    .O_LOCK(lock), .ICPSEL(icpsel), .LPFRES(lpfres)
);
defparam ui.CLK_PERIOD = 20;
defparam ui.MULTI_FAC = `DDR_PLL_MDIV;

defparam u.FCLKIN = "50";
defparam u.IDIV_SEL = `DDR_PLL_IDIV;
defparam u.FBDIV_SEL = 1;
defparam u.MDIV_SEL = `DDR_PLL_MDIV;
defparam u.MDIV_FRAC_SEL = 0;
defparam u.ODIV0_SEL = 8;
defparam u.ODIV0_FRAC_SEL = 0;
defparam u.ODIV1_SEL = 8;
defparam u.ODIV2_SEL = `DDR_PLL_ODIV;
defparam u.ODIV3_SEL = 8;
defparam u.ODIV4_SEL = 8;
defparam u.ODIV5_SEL = 8;
defparam u.ODIV6_SEL = 8;
defparam u.CLKOUT0_EN = "FALSE";
defparam u.CLKOUT1_EN = "FALSE";
defparam u.CLKOUT2_EN = "TRUE";
defparam u.CLKOUT3_EN = "FALSE";
defparam u.CLKOUT4_EN = "FALSE";
defparam u.CLKOUT5_EN = "FALSE";
defparam u.CLKOUT6_EN = "FALSE";
defparam u.CLKFB_SEL = "INTERNAL";
defparam u.CLKOUT0_DT_DIR = 1'b1;
defparam u.CLKOUT1_DT_DIR = 1'b1;
defparam u.CLKOUT2_DT_DIR = 1'b1;
defparam u.CLKOUT3_DT_DIR = 1'b1;
defparam u.CLKOUT0_DT_STEP = 0;
defparam u.CLKOUT1_DT_STEP = 0;
defparam u.CLKOUT2_DT_STEP = 0;
defparam u.CLKOUT3_DT_STEP = 0;
defparam u.CLK0_IN_SEL = 1'b0;
defparam u.CLK0_OUT_SEL = 1'b0;
defparam u.CLK1_IN_SEL = 1'b0;
defparam u.CLK1_OUT_SEL = 1'b0;
defparam u.CLK2_IN_SEL = 1'b0;
defparam u.CLK2_OUT_SEL = 1'b0;
defparam u.CLK3_IN_SEL = 1'b0;
defparam u.CLK3_OUT_SEL = 1'b0;
defparam u.CLK4_IN_SEL = 2'b00;
defparam u.CLK4_OUT_SEL = 1'b0;
defparam u.CLK5_IN_SEL = 1'b0;
defparam u.CLK5_OUT_SEL = 1'b0;
defparam u.CLK6_IN_SEL = 1'b0;
defparam u.CLK6_OUT_SEL = 1'b0;
defparam u.DYN_DPA_EN = "FALSE";
defparam u.CLKOUT0_PE_COARSE = 0;
defparam u.CLKOUT0_PE_FINE = 0;
defparam u.CLKOUT1_PE_COARSE = 0;
defparam u.CLKOUT1_PE_FINE = 0;
defparam u.CLKOUT2_PE_COARSE = 0;
defparam u.CLKOUT2_PE_FINE = 0;
defparam u.CLKOUT3_PE_COARSE = 0;
defparam u.CLKOUT3_PE_FINE = 0;
defparam u.CLKOUT4_PE_COARSE = 0;
defparam u.CLKOUT4_PE_FINE = 0;
defparam u.CLKOUT5_PE_COARSE = 0;
defparam u.CLKOUT5_PE_FINE = 0;
defparam u.CLKOUT6_PE_COARSE = 0;
defparam u.CLKOUT6_PE_FINE = 0;
defparam u.DYN_PE0_SEL = "FALSE";
defparam u.DYN_PE1_SEL = "FALSE";
defparam u.DYN_PE2_SEL = "FALSE";
defparam u.DYN_PE3_SEL = "FALSE";
defparam u.DYN_PE4_SEL = "FALSE";
defparam u.DYN_PE5_SEL = "FALSE";
defparam u.DYN_PE6_SEL = "FALSE";
defparam u.DE0_EN = "FALSE";
defparam u.DE1_EN = "FALSE";
defparam u.DE2_EN = "FALSE";
defparam u.DE3_EN = "FALSE";
defparam u.DE4_EN = "FALSE";
defparam u.DE5_EN = "FALSE";
defparam u.DE6_EN = "FALSE";
defparam u.RESET_I_EN = "FALSE";
defparam u.RESET_O_EN = "FALSE";
defparam u.ICP_SEL = 6'bXXXXXX;
defparam u.LPF_RES = 3'bXXX;
defparam u.LPF_CAP = 2'b00;
defparam u.SSC_EN = "FALSE";
defparam u.DYN_IDIV_SEL = "FALSE";
defparam u.DYN_FBDIV_SEL = "FALSE";
defparam u.DYN_MDIV_SEL = "FALSE";
defparam u.DYN_ODIV0_SEL = "FALSE";
defparam u.DYN_ODIV1_SEL = "FALSE";
defparam u.DYN_ODIV2_SEL = "FALSE";
defparam u.DYN_ODIV3_SEL = "FALSE";
defparam u.DYN_ODIV4_SEL = "FALSE";
defparam u.DYN_ODIV5_SEL = "FALSE";
defparam u.DYN_ODIV6_SEL = "FALSE";
defparam u.DYN_DT0_SEL = "FALSE";
defparam u.DYN_DT1_SEL = "FALSE";
defparam u.DYN_DT2_SEL = "FALSE";
defparam u.DYN_DT3_SEL = "FALSE";
defparam u.DYN_ICP_SEL = "TRUE";
defparam u.DYN_LPF_SEL = "TRUE";

endmodule
