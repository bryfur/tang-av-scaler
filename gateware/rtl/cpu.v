// cpu.v: the SOM's hard CPU (the GW5AST-138's Andes A25, RV32IMAFDC: Gowin's RiscV_AE350_SOC,
// rtl/riscv_ae350_config.v) and what it stands in: for the work that is not every pixel's (sw/).
//
// - Its program: WORDS x 32 bits of block RAM at 0x80000000 (the SoC's ROM AHB port), HEX in it
//   from the bitstream; the register bus can write it (pm_*: a new program without a new
//   bitstream: the core held in reset meanwhile, rst_n).  Its data: the core's own DLM.
// - The register bus (top.v's: the monitor's) at 0xE8000000 + 4 x the register (the SoC's extended
//   AHB slave): a word read or written is a turn on the bus between the monitor's (stall keeps
//   the monitor where it is; mon_busy: it is in the middle of one).  The AHB side runs on the
//   clock the SoC gives back, the bus on clk: a request and an answer across, each a level that
//   changes.
// - Clocks: core_clk is PLL_R[0]'s CLKOUT1, wired to the core inside the chip (Gowin MUG1031
//   8.3.2: gowin/avb.cst places the PLL there), clk (the system's 50 MHz, CLKOUT0) the SoC's
//   buses: 8 to 1, as the fpc console runs it (800 and 100 there).

module cpu #(
    parameter HEX = "cpu.hex",
    parameter WORDS = 8192
) (
    input             clk,
    input             core_clk,
    input             rst_n,            // (low: the core in reset)
    input             pm_we,
    input      [12:0] pm_wa,
    input      [31:0] pm_wd,
    output            stall,
    input             mon_busy,
    input             other,            // (another's turn: the link's SPI port)
    output reg        c_own = 1'b0,
    output reg        c_we = 1'b0,
    output reg [7:0]  c_addr,
    output reg [31:0] c_wdata,
    input      [31:0] rdata,
    output            txd,
    input             rxd,
    output            wfi
);
    localparam AW = $clog2(WORDS);

    // the core out of reset 2.6 ms after rst_n
    reg [17:0] por = 18'd0;
    reg        rstn = 1'b0;
    always @(posedge clk)
        if (!rst_n) begin
            por <= 18'd0;
            rstn <= 1'b0;
        end else if (!por[17])
            por <= por + 18'd1;
        else
            rstn <= 1'b1;
    // the RTC's clock: 50 MHz / 1526 = 32.765 kHz
    reg [10:0] rtc_div = 11'd0;
    reg        rtc_clk = 1'b0;
    always @(posedge clk)
        if (rtc_div == 11'd762) begin
            rtc_div <= 11'd0;
            rtc_clk <= !rtc_clk;
        end else
            rtc_div <= rtc_div + 11'd1;

    // the program
    wire [31:0] rom_haddr;
    wire [1:0]  rom_htrans;
    wire        rom_hclk;
    reg  [31:0] rom_hrdata;
    reg  [31:0] mem [0:WORDS - 1];
    initial $readmemh(HEX, mem);
    always @(posedge clk)
        if (pm_we)
            mem[pm_wa[AW - 1:0]] <= pm_wd;
    always @(posedge rom_hclk)
        if (rom_htrans[1])
            rom_hrdata <= mem[rom_haddr[AW + 1:2]];

    // the register bus's AHB side: an address phase taken when the one before is over; a write's
    // word a clock later; then the request, and HREADY low until the answer
    wire [31:0] s_haddr, s_hwdata;
    wire [1:0]  s_htrans;
    wire        s_hwrite, s_hsel, s_hclk;
    reg         s_busy = 1'b0, s_ph = 1'b0, s_wr, req_t = 1'b0;
    reg  [7:0]  s_a;
    reg  [31:0] s_wd, s_hrdata;
    reg         ack_t = 1'b0, a0, a1, a2;
    reg  [31:0] c_rd;
    always @(posedge s_hclk) begin
        a0 <= ack_t;
        a1 <= a0;
        a2 <= a1;
        if (!s_busy) begin
            if (s_hsel && s_htrans[1]) begin
                s_busy <= 1'b1;
                s_ph <= 1'b1;
                s_a <= s_haddr[9:2];
                s_wr <= s_hwrite;
            end
        end else if (s_ph) begin
            s_ph <= 1'b0;
            s_wd <= s_hwdata;
            req_t <= !req_t;
        end else if (a1 != a2) begin
            s_hrdata <= c_rd;
            s_busy <= 1'b0;
        end
    end

    // its turn on the bus: the monitor stalled for a clock and not in the middle of a word; the
    // address a clock, the write's strobe or the read's word a clock, then the answer
    reg        r0, r1, r2, pend = 1'b0, pend_q = 1'b0;
    reg [1:0]  cs = 2'd0;
    assign stall = pend || c_own;
    always @(posedge clk) begin
        r0 <= req_t;
        r1 <= r0;
        r2 <= r1;
        if (r1 != r2)
            pend <= 1'b1;
        pend_q <= pend;
        c_we <= 1'b0;
        case (cs)
            2'd0:
                if (pend && pend_q && !mon_busy && !other) begin
                    c_own <= 1'b1;
                    c_addr <= s_a;
                    c_wdata <= s_wd;
                    cs <= 2'd1;
                end
            2'd1: begin
                c_we <= s_wr;
                cs <= 2'd2;
            end
            2'd2: begin
                c_rd <= rdata;
                cs <= 2'd3;
            end
            default: begin
                c_own <= 1'b0;
                pend <= 1'b0;
                ack_t <= !ack_t;
                cs <= 2'd0;
            end
        endcase
    end

    RiscV_AE350_SOC_Top u_soc (
        .ROM_HRDATA(rom_hrdata), .ROM_HREADY(1'b1), .ROM_HRESP(1'b0), .ROM_HADDR(rom_haddr), .ROM_HTRANS(rom_htrans),
        .ROM_HWRITE(), .ROM_HCLK(rom_hclk), .ROM_HRSTN(),
        .DDR_HRDATA(64'd0), .DDR_HREADY(1'b1), .DDR_HRESP(1'b0), .DDR_HADDR(), .DDR_HBURST(), .DDR_HPROT(),
        .DDR_HSIZE(), .DDR_HTRANS(), .DDR_HWDATA(), .DDR_HWRITE(), .DDR_HCLK(), .DDR_HRSTN(),
        .TCK_IN(1'b0), .TMS_IN(1'b1), .TRST_IN(1'b1), .TDI_IN(1'b0), .TDO_OUT(), .TDO_OE(),
        .EXT_INT(16'd0),
        .EXTS_HRDATA(s_hrdata), .EXTS_HREADYIN(!s_busy), .EXTS_HRESP(1'b0), .EXTS_HADDR(s_haddr), .EXTS_HBURST(),
        .EXTS_HPROT(), .EXTS_HSEL(s_hsel), .EXTS_HSIZE(), .EXTS_HTRANS(s_htrans), .EXTS_HWDATA(s_hwdata),
        .EXTS_HWRITE(s_hwrite), .EXTS_HCLK(s_hclk), .EXTS_HRSTN(),
        .UART2_TXD(txd), .UART2_RTSN(), .UART2_RXD(rxd), .UART2_CTSN(1'b0), .UART2_DCDN(1'b1), .UART2_DSRN(1'b1),
        .UART2_RIN(1'b1), .UART2_DTRN(), .UART2_OUT1N(), .UART2_OUT2N(),
        .GPIO_IN(32'd0), .GPIO_OE(), .GPIO_OUT(),
        .CORE0_WFI_MODE(wfi), .RTC_WAKEUP(),
        .CORE_CLK(core_clk), .DDR_CLK(clk), .AHB_CLK(clk), .APB_CLK(clk), .RTC_CLK(rtc_clk),
        .POR_RSTN(rstn), .HW_RSTN(rstn)
    );
endmodule
