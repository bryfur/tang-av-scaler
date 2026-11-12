// top.v: AV board rev C-B bring-up image: the monitor (mon.v) on the XIAO's UART and what it reaches;
// the SOM's hard CPU (cpu.v) reaches the same registers, at 0xE8000000 + 4 x the register.
//
// Registers (32 bits):
//   00 R   ID        "AVB1" (0x31425641)
//   01 R   BUILD     `AVB_BUILD
//   02 RW  CTRL      0 LED from bit 1 (else it blinks), 1 LED, 2 DP_OE, 3 IN_RESET_N (the ADV7181D's),
//                    4 CEC pulled low
//   03 R   STAT      0 KEY1, 1 KEY2 (pressed = 0), 2 DP_HPD, 3 IN_INT, 4 CEC, 8 an I2C SCL never rose
//                    (sticky, cleared by reading)
//   04 RW  I2C       the four buses' lines, open drain, one bit each: a 1 written pulls the line
//                    low.  Bits 0 PLL_SCL, 1 PLL_SDA, 2 DP_SCL, 3 DP_SDA, 4 DDC_SCL, 5 DDC_SDA,
//                    6 IN_SCL, 7 IN_SDA; read: 7:0 as written, 15:8 the lines themselves, 16 the
//                    lines are still settling (the CPU waits for it; the monitor is held).
//                    A write holds the next command until the lines have settled and every SCL let
//                    go has risen (a device stretching the clock; 84 ms at most).
//   05-08 R I2C_SH   bus 0-3's SDA at each of its SCL's rises, shifted in from bit 0: a byte read is
//                    eight clock pulses and one register read
//   10-17 R FREQ     fmeter.v counts (x 23.84 Hz at 50 MHz): 0 PLL_CLK2, 1 IN_LLC, 2 the transmit
//                    word clock (lane 0's), 3 lane 0's PLL reference as the quad sees it, 4 lane 1's
//                    word clock
//   20 RW  GT_CTRL   the transceiver lanes (gtx_quad.v), a bit a lane: 3:0 lane resets released,
//                    7:4 transmit PCS resets, 11:8 data valid
//   21 R   GT_STAT   3:0 the lanes' own PLLs locked (not used: gowin/serdes.py), 7:4 FIFOs full,
//                    11:8 almost full, 13:12 the quad's PLLs locked: bit 13 the LC PLL all four
//                    lanes run from
//   22-23 R GT_ST    lanes 1,0 and 3,2: STAT (13 bits) at 12:0 and 28:16
//   24 R   GT_AST    the lanes' ASTAT, six bits each
//   26 RW  HDMI      0 characters scrambled [HDMI 2.0], 1 the video preamble and guard band sent (else
//                    DVI's plain blanking), 2 data islands: the sound and the InfoFrames
//                    (hdmi_audio.v: with bit 1; 1080p60 only), 7:4 the scrambler's open choices
//                    (hdmi_scr.v opt); 0 and 7:4 set before the lanes are started
//   27 R   LAT      11:0 how old the newest field was when the frame now shown was begun (from the
//                    field's last line), in 10 us; 25:16 how many lines of the field coming in were
//                    in the memory then
//   28 RW  OSD      0 the on-screen text shown (osd.v)
//   29 W   OSDW     a character of it: 16:8 where (line * 64 + column), 7:0 the character
//   2A R   TEMP     the chip's temperature: 13:0 degrees C x 4 (signed), 31 measured
//   60 RW  CPU      0 the hard CPU runs (else held in reset: for a new program)
//   61 RW  CPUA     the program's word the next CPUD writes (it counts on)
//   62 W   CPUD     a word of the CPU's program (0x80000000 + 4 x CPUA)
//   64-67 RW CPUM   four words the CPU's program leaves for the host (sw/main.c: 64 counts up while
//                    it runs, 65 says what it is)
//   70-74    SPIS     the link's SPI port (spis.v): the CPU's program's side of its messages, and (74) the
//                    port's lines as they are
//   30 RW  VID       0 the picture is the component input's (else pattern.v's), 1 the fields in the
//                    DDR3 are left as they are, 2 the pixel port is 16 bits wide (the CP core's:
//                    vcap.v), 3 Cb and Cr the other way round, 4 the sharpening leaves noise alone
//                    (rcas.v dn), 20:16 the sharpening (rcas.v: 0 none to 16)
//   37 R   FOCUS    focus.v: 27:0 the last field's sharpness across a line, 31:28 a count of fields
//   35 RW  DEINT     deint.v: 1:0 mode (0 motion adaptive, 1 bob, 2 weave), 2 the F of the top field,
//                    15:8 the motion threshold, 5:4 temporal noise reduction (0 none, 1 to 3),
//                    6 a frame made from the field still coming in (deint.v ll: not while frozen)
//                    16 the anti-aliasing on (smaa.v), 17 what it finds shown in the picture's place
//                    (its edges green, what it mixes blue and red), 18 its diagonal patterns too, 19 corners kept,
//                    31:24 its edge threshold (a luma step)
//   3A-3D RW GEOM   the part of the source the scaler shows (sim/fsr.py geom(): XR, DX, YS, DY;
//                    DX's bit 31: the picture 16:9's, all 1920 columns, not the middle 1440)
//   3E RW  BORDER   border.v: where the captured fields have picture: a write starts it again (7:0 the
//                    luma a pixel of picture is above); read: 8:0 the first pair of pixels, 24:16 the
//                    last, 31 there was picture
//   3F R   BORDERL  9:0 the first line of a field with picture, 25:16 the last
//   2B RW  LLMIN    7:0 the lines of a field that must be in for a frame to be made from it (deint.v
//                    ll_min)
//   36 R   DSTAT     2:0 fields seen (to 7), 5:3 the newest field's slot, 15:8 deint.v's state (12:
//                    the frame is made from the field coming in),
//                    31:16 frames it has begun
//   31 R   CAP       vcap.v: 10:0 the Y samples of a line, 20:11 the lines of picture of a field,
//                    21 its F, 31 the raw capture is done
//   32 R   FIELDS    15:0 a count of fields
//   33 W   RAW       takes 1024 samples of the pixel port: 1:0 from when (vcap.v mode)
//   34 RW  RAWD      written: the sample's number; read: that sample: 7:0 Y pins, 15:8 C pins, 16 HS,
//                    17 VS, 18 DE
//   38 RW  GRAB      written: eight rows of the next frame's picture are taken (grab.v): 10:0 the first
//                    row, 15:12 the step between them; read: 31 they are in
//   39 RW  GRABD     written: the place in the rows taken ({which, column}); read: the pixel there
//                    (R, G, B from bit 23), and the place moves on by one
//   40 RW  DDR       the DDR3 (rtl/ddr3): read: 0 calibrated, 1 its calibration failed, 2 the host's
//                    command is done, 15:8 the calibration's code, 23:16 the DLL's step; written: the
//                    host's command: 24:0 the line (256 bits), 31 a write (of DDRD), else a read
//   48-4F RW DDRD    the line: written, a write's; read, the last read's
//   50-51 R AUD      the PCM1808's last left and right words as they came (audio_in.v: 32 bits; the
//                    24-bit sample at 30:7)
//   52 R   AUDPK     the greatest |sample| since it was last read: 15:0 left, 31:16 right (the
//                    sample's upper 16 bits)
//   25 R   MODE      pixels a word clock: 1 = 1920x1080p60 (10-bit words, 1.485 Gb/s), 2 = 3840x2160p30
//                    (20-bit words, 2.97 Gb/s), 4 = 3840x2160p60 (40 bits a clock, 5.94 Gb/s, the
//                    TMDS clock a fortieth); `AVB_PPC, with the transceivers' register file
//
// HDMI: pattern.v's picture, framed and scrambled as asked (hdmi_scr.v), through three TMDS
// encoders on the word clock;
// lane 0 = channel 2 (red), lane 3 = channel 1 (green), lane 2 = channel 0 (blue and the syncs),
// lane 1 = the TMDS clock as a word of five ones and five zeros (hardware/av-board/rev-cb/board.py LANES).
//
// The LED blinks at 1.5 Hz from configuration on: the FPGA's own sign of life.

`ifndef AVB_BUILD
`define AVB_BUILD 32'd0
`endif
`ifndef AVB_PPC
`define AVB_PPC 1
`endif

module top (
    input  sys_clk,                 // the SOM's 50 MHz
    input  esp_tx,                  // the XIAO's TX
    // the XIAO's SPI port (spis.v): registers, and messages for the CPU's program
    input  esp_cs,
    input  esp_sck,
    input  esp_mosi,
    output esp_miso,
    output esp_irq,
    output esp_rx,                  // the XIAO's RX
    output in_led,
    input  in_key1,
    input  in_key2,
    inout  pll_scl,
    inout  pll_sda,
    inout  dp_scl,
    inout  dp_sda,
    inout  ddc_scl,
    inout  ddc_sda,
    inout  in_scl,
    inout  in_sda,
    output dp_oe,
    input  dp_hpd,
    inout  cec_fpga,
    output in_reset_n,
    input  in_int,
    input  pll_clk2,
    input  in_llc,                  // the ADV7181D's pixel port
    input  [7:0] in_y,
    input  [7:0] in_c,
    input  in_hs,
    input  in_vs,
    input  in_de,
    // the PCM1808 (audio in)
    output in_scki,
    output in_bck,
    output in_lrck,
    input  in_dout,
    // the SOM's DDR3
    output [14:0] ddr_addr,
    output [2:0]  ddr_bank,
    output        ddr_cs,
    output        ddr_ras,
    output        ddr_cas,
    output        ddr_we,
    output        ddr_ck,
    output        ddr_ck_n,
    output        ddr_cke,
    output        ddr_odt,
    output        ddr_reset_n,
    output [3:0]  ddr_dm,
    inout  [31:0] ddr_dq,
    inout  [3:0]  ddr_dqs,
    inout  [3:0]  ddr_dqs_n
);
    wire clk, core_clk, pll_lock;
    sys_pll u_pll (.clkin(sys_clk), .clk(clk), .core(core_clk), .lock(pll_lock));

    // the register bus: the monitor's, and between its words the CPU's and the link's SPI port's
    wire [7:0]  m_addr, c_addr, s_addr;
    wire [31:0] m_wdata, c_wdata, s_wdata;
    wire        m_we, c_we, c_own, s_we, s_own, c_stall, s_stall, m_busy;
    wire        m_stall = c_stall || s_stall;
    wire [7:0]  addr = c_own ? c_addr : s_own ? s_addr : m_addr;
    wire [31:0] wdata = c_own ? c_wdata : s_own ? s_wdata : m_wdata;
    wire        we = c_own ? c_we : s_own ? s_we : m_we;
    reg  [31:0] rdata;
    wire        hold;
    mon #(.DIV(50)) u_mon (.clk(clk), .rx(esp_tx), .tx(esp_rx), .addr(m_addr), .wdata(m_wdata), .we(m_we),
                          .rdata(rdata), .hold(hold), .stall(m_stall), .busy(m_busy));

    // the hard CPU (cpu.v): its program's memory and its reset from the bus; four words for what it says
    reg         cpu_run = 1'b1;
    reg  [12:0] cpu_pa = 13'd0;
    reg  [31:0] cpu_m0 = 32'd0, cpu_m1 = 32'd0, cpu_m2 = 32'd0, cpu_m3 = 32'd0;
    wire        cpu_pwe = we && addr == 8'h62;
    always @(posedge clk) begin
        if (we && addr == 8'h60)
            cpu_run <= wdata[0];
        if (we && addr == 8'h61)
            cpu_pa <= wdata[12:0];
        else if (cpu_pwe)
            cpu_pa <= cpu_pa + 13'd1;
        if (we && addr == 8'h64)
            cpu_m0 <= wdata;
        if (we && addr == 8'h65)
            cpu_m1 <= wdata;
        if (we && addr == 8'h66)
            cpu_m2 <= wdata;
        if (we && addr == 8'h67)
            cpu_m3 <= wdata;
    end
    cpu #(.HEX(`CPU_HEX)) u_cpu (.clk(clk), .core_clk(core_clk), .rst_n(pll_lock && cpu_run), .pm_we(cpu_pwe),
                                .pm_wa(cpu_pa), .pm_wd(wdata), .stall(c_stall), .mon_busy(m_busy), .other(s_own), .c_own(c_own),
                                .c_we(c_we), .c_addr(c_addr), .c_wdata(c_wdata), .rdata(rdata), .txd(), .rxd(1'b1),
                                .wfi());

    wire [31:0] sp_stat, sp_rx, sp_pins;
    spis u_spi (.clk(clk), .cs_n(esp_cs), .sck(esp_sck), .mosi(esp_mosi), .miso(esp_miso), .irq_n(esp_irq),
                .stall(s_stall), .mon_busy(m_busy), .other(c_stall), .s_own(s_own), .s_we(s_we), .s_addr(s_addr),
                .s_wdata(s_wdata), .rdata(rdata), .we(we), .addr(addr), .wdata(wdata), .q_stat(sp_stat), .q_rx(sp_rx),
                .q_pins(sp_pins));

    // the chip's temperature (the ADC in its corner, in temperature mode: Gowin UG299): asked for
    // every 0.67 s (beat), the answer some tens of ms later
    wire        t_rdy;
    wire [13:0] t_val;
    reg         t_r0 = 1'b0, t_r1 = 1'b0;
    reg  [14:0] temp = 15'd0;

    reg [24:0] beat = 25'd0;
    wire       tick = &beat;
    always @(posedge clk) begin
        t_r0 <= t_rdy;
        t_r1 <= t_r0;
        if (t_r0 && !t_r1)
            temp <= {1'b1, t_val};
    end
    ADCULC #(.DYN_BKEN("FALSE"), .CLK_SEL(1'b0), .PIOCLK_SEL(1'b0), .VSEN_CTL(3'b000), .VSEN_CTL_SEL(1'b0),
             .ADC_MODE(1'b0), .DIV_CTL(2'd0), .SAMPLE_CNT_SEL(3'd4), .RATE_CHANGE_CTRL(3'd4))
        u_adc (.ADCINBK6A(1'b0), .ADCINBK6B(1'b0), .ADCINBK7A(1'b0), .ADCINBK7B(1'b0), .VSENCTL(3'b000),
               .FSCAL_VALUE(10'd730), .OFFSET_VALUE(-12'sd1180), .ADCEN(1'b1), .CLK(clk), .DRSTN(pll_lock),
               .ADCREQI(beat[24]), .ADCRDY(t_rdy), .ADCVALUE(t_val));
    always @(posedge clk)
        beat <= beat + 25'd1;

    // CTRL
    reg [4:0] ctrl = 5'd0;
    always @(posedge clk)
        if (we && addr == 8'h02)
            ctrl <= wdata[4:0];
    assign in_led = ctrl[0] ? ctrl[1] : beat[24];
    assign dp_oe = ctrl[2];
    assign in_reset_n = ctrl[3];
    assign cec_fpga = ctrl[4] ? 1'b0 : 1'bz;

    // I2C: lines in pairs {SDA, SCL}, bus k at bits 2k+1, 2k
    reg  [7:0] i2c_drv = 8'd0;
    wire [7:0] i2c_pin = {in_sda, in_scl, ddc_sda, ddc_scl, dp_sda, dp_scl, pll_sda, pll_scl};
    assign pll_scl = i2c_drv[0] ? 1'b0 : 1'bz;
    assign pll_sda = i2c_drv[1] ? 1'b0 : 1'bz;
    assign dp_scl  = i2c_drv[2] ? 1'b0 : 1'bz;
    assign dp_sda  = i2c_drv[3] ? 1'b0 : 1'bz;
    assign ddc_scl = i2c_drv[4] ? 1'b0 : 1'bz;
    assign ddc_sda = i2c_drv[5] ? 1'b0 : 1'bz;
    assign in_scl  = i2c_drv[6] ? 1'b0 : 1'bz;
    assign in_sda  = i2c_drv[7] ? 1'b0 : 1'bz;
    reg [7:0]  i2c_s0, i2c_in;
    reg [3:0]  rose;                // SCLs let go by the last write
    reg [22:0] wait_t;
    reg        waiting = 1'b0;
    reg        stuck = 1'b0;
    reg [31:0] i2c_sh [0:3];
    wire [3:0] scl_low = {!i2c_in[6], !i2c_in[4], !i2c_in[2], !i2c_in[0]} & ~{i2c_drv[6], i2c_drv[4], i2c_drv[2], i2c_drv[0]};
    wire       i2c_we = we && addr == 8'h04;
    assign hold = waiting || i2c_we;
    integer k;
    always @(posedge clk) begin
        i2c_s0 <= i2c_pin;
        i2c_in <= i2c_s0;
        if (addr == 8'h03 && u_mon.state == 4'd6)       // STAT read
            stuck <= 1'b0;
        if (i2c_we) begin
            i2c_drv <= wdata[7:0];
            rose <= {i2c_drv[6] & ~wdata[6], i2c_drv[4] & ~wdata[4], i2c_drv[2] & ~wdata[2], i2c_drv[0] & ~wdata[0]};
            wait_t <= 23'd0;
            waiting <= 1'b1;
        end else if (waiting) begin
            wait_t <= wait_t + 23'd1;
            // 5 us for the lines, then every SCL not held by us high, or 84 ms gone
            if (wait_t[22] || (wait_t >= 23'd256 && scl_low == 4'd0)) begin
                waiting <= 1'b0;
                if (wait_t[22])
                    stuck <= 1'b1;
                for (k = 0; k < 4; k = k + 1)
                    if (rose[k])
                        i2c_sh[k] <= {i2c_sh[k][30:0], i2c_in[2 * k + 1]};
            end
        end
    end

    // the transceivers
    reg  [31:0] gt_ctrl = 32'd0;
    always @(posedge clk)
        if (we && addr == 8'h20)
            gt_ctrl <= wdata;
    wire [3:0]  pcs_tx_clk, cmu_ok, gt_ref_clk, fifo_full, fifo_afull;
    wire [51:0] gt_stat;
    wire [23:0] gt_astat;
    wire [1:0]  qpll_ok;
    wire        tx_clk = pcs_tx_clk[0];
    reg  [319:0] tx_data;
    gtx_quad u_gtx (.ln_rstn(gt_ctrl[3:0]), .pcs_tx_rst(gt_ctrl[7:4]), .tx_clk(tx_clk), .tx_vld(gt_ctrl[11:8]),
                    .tx_data(tx_data), .pcs_tx_clk(pcs_tx_clk), .cmu_ok(cmu_ok), .ref_clk(gt_ref_clk),
                    .fifo_full(fifo_full), .fifo_afull(fifo_afull), .stat(gt_stat), .astat(gt_astat),
                    .qpll_ok(qpll_ok));

    // HDMI's framing and scrambling (hdmi_scr.v), set before a picture is wanted
    reg [7:0] hd_ctrl = 8'd0;
    always @(posedge clk)
        if (we && addr == 8'h26)
            hd_ctrl <= wdata[7:0];
    reg [7:0] hd_s0, hd;
    always @(posedge tx_clk) begin
        hd_s0 <= hd_ctrl;
        hd <= hd_s0;
    end

    // the picture, on the word clock: PPC pixels, so PPC characters a lane, a clock
    localparam PPC = `AVB_PPC;
    wire [PPC - 1:0]      p_de, p_hs, p_vs, p_pre, p_gb, p_ucc;
    wire [8 * PPC - 1:0]  p_r, p_g, p_b;
    wire [12:0]           p_x;
    wire [11:0]           p_y;
    generate
        if (PPC > 1) begin : g_2160p          // 30 Hz two pixels a clock, 60 Hz four
            pattern #(.PPC(PPC), .HA(3840), .HF(176), .HS(88), .HT(4400), .VA(2160), .VF(8), .VS(10), .VT(2250))
                u_pat (.clk(tx_clk), .de(p_de), .hs(p_hs), .vs(p_vs), .pre(p_pre), .gb(p_gb), .ucc(p_ucc),
                       .r(p_r), .g(p_g), .b(p_b), .ox(p_x), .oy(p_y));
        end else begin : g_1080p60
            pattern u_pat (.clk(tx_clk), .de(p_de), .hs(p_hs), .vs(p_vs), .pre(p_pre), .gb(p_gb), .ucc(p_ucc),
                           .r(p_r), .g(p_g), .b(p_b), .ox(p_x), .oy(p_y));
        end
    endgenerate

    // the component input: the ADV7181D's fields decoded on its clock (vcap.v), kept in the DDR3
    // (cap_ddr.v), made a progressive picture (deint.v, lstream.v), scaled (easu.v) and sharpened (rcas.v: 1080p60 only), LAT
    // clocks behind pattern.v's pixel: its timing and its picture wait that long
    localparam LAT_E = 26, LAT = LAT_E + 2200 + 25;      // (easu.v; rcas.v: a row and 24)
    reg [31:0] vid = 32'h00000010;
    reg        raw_arm = 1'b0;
    reg [1:0]  raw_mode = 2'd0;
    reg [9:0]  raw_ra = 10'd0;
    always @(posedge clk) begin
        if (we && addr == 8'h30)
            vid <= wdata;
        if (we && addr == 8'h33) begin
            raw_arm <= !raw_arm;
            raw_mode <= wdata[1:0];
        end
        if (we && addr == 8'h34)
            raw_ra <= wdata[9:0];
    end
    wire        fb_we, cap_field, raw_done, cap_eof;
    wire [9:0]  cap_ln;
    wire [8:0]  cap_col;
    wire [7:0]  l_r, l_g, l_b;
    wire [31:0] fb_wd;
    wire [10:0] cap_pix;
    wire [9:0]  cap_lines;
    wire [15:0] cap_fields;
    wire [18:0] raw_rd;
    vcap u_cap (.llc(in_llc), .y(in_y), .c(in_c), .hs(in_hs), .vs(in_vs), .de(in_de), .freeze(vid[1]), .wide(vid[2]),
                .we(fb_we), .wa(), .wd(fb_wd), .w_ln(cap_ln), .w_col(cap_col), .eof(cap_eof), .f_we(), .f_wa(), .f_wd(), .pix(cap_pix), .lines(cap_lines), .field(cap_field),
                .fields(cap_fields), .arm(raw_arm), .mode(raw_mode), .done(raw_done), .rclk(clk),
                .ra(raw_ra), .rd(raw_rd));
    reg  [7:0]  bd_thr = 8'd40;
    reg         bd_clr = 1'b0;
    wire        bd_any;
    wire [8:0]  bd_x0, bd_x1;
    wire [9:0]  bd_l0, bd_l1;
    always @(posedge clk)
        if (we && addr == 8'h3E) begin
            bd_thr <= wdata[7:0];
            bd_clr <= !bd_clr;
        end
    border u_border (.llc(in_llc), .we(fb_we), .w_ln(cap_ln), .w_col(cap_col), .wd(fb_wd), .thr(bd_thr), .clr(bd_clr),
                     .any(bd_any), .x_min(bd_x0), .x_max(bd_x1), .ln_min(bd_l0), .ln_max(bd_l1));
    wire [27:0] fo_sum;
    wire [3:0]  fo_n;
    focus u_focus (.llc(in_llc), .we(fb_we), .w_col(cap_col), .wd(fb_wd), .eof(cap_eof), .sum(fo_sum), .n(fo_n));
    reg                  vid_s0, vid_on, swap_s0, swap, dn_s0, dn;
    reg [4:0]            sharp_s0, sharp;
    always @(posedge tx_clk) begin
        vid_s0 <= vid[0];
        vid_on <= vid_s0;
        swap_s0 <= vid[3];
        swap <= swap_s0;
        dn_s0 <= vid[4];
        dn <= dn_s0;
        sharp_s0 <= vid[20:16] > 5'd16 ? 5'd16 : vid[20:16];
        sharp <= sharp_s0;
    end
    wire [6 * PPC - 1:0]  dl_t;
    wire [24 * PPC - 1:0] dl_p;
    dline #(.W(6 * PPC), .D(LAT)) u_dlt (.clk(tx_clk), .d({p_de, p_hs, p_vs, p_pre, p_gb, p_ucc}), .q(dl_t));
    dline #(.W(24 * PPC), .D(LAT)) u_dlp (.clk(tx_clk), .d({p_r, p_g, p_b}), .q(dl_p));
    wire [PPC - 1:0]      v_de, v_hs, v_vs, v_pre, v_gb, v_ucc;
    wire [8 * PPC - 1:0]  v_r, v_g, v_b;
    // (the on-screen text over it, at one pixel a clock: osd.v, a few clocks more for everything)
    reg                   osd_on = 1'b0;
    always @(posedge clk)
        if (we && addr == 8'h28)
            osd_on <= wdata[0];
    generate
        if (PPC == 1) begin : g_osd
            osd u_osd (.clk(tx_clk), .on(osd_on), .i_t(dl_t), .i_rgb(vid_on ? {l_r, l_g, l_b} : dl_p),
                       .o_t({v_de, v_hs, v_vs, v_pre, v_gb, v_ucc}), .o_rgb({v_r, v_g, v_b}), .wclk(clk),
                       .we(we && addr == 8'h29), .wa(wdata[16:8]), .wd(wdata[7:0]));
        end else begin : g_noosd
            assign {v_de, v_hs, v_vs, v_pre, v_gb, v_ucc} = dl_t;
            assign {v_r, v_g, v_b} = dl_p;
        end
    endgenerate
    // the channels' control bits: 0 {VSYNC, HSYNC}; 1 {CTL1, CTL0}, 2 {CTL3, CTL2}: the video preamble
    // is CTL0 alone [HDMI 1.4 5.2.1.1], sent with the guard band
    // a data island's preamble is CTL0 and CTL2 [5.2.1.1]; its characters go to the encoders in the
    // control tokens' place (hdmi_audio.v, further down: a_*), two clocks on as hdmi_scr.v's
    wire                  a_pre, a_act;
    wire [9:0]            a_k0, a_k1, a_k2;
    reg  [30:0]           a_d1, a_d2;
    always @(posedge tx_clk) begin
        a_d1 <= {a_act, a_k2, a_k1, a_k0};
        a_d2 <= a_d1;
    end
    wire [2 * PPC - 1:0]  c0, c1, c2;
    genvar gk;
    generate
        for (gk = 0; gk < PPC; gk = gk + 1) begin : g_c
            assign c0[2 * gk +: 2] = {v_vs[gk], v_hs[gk]};
            assign c1[2 * gk +: 2] = {1'b0, (v_pre[gk] & hd[1]) | (PPC == 1 && a_pre)};
            assign c2[2 * gk +: 2] = {1'b0, PPC == 1 && a_pre};
        end
    endgenerate
    wire [8 * PPC - 1:0]  s_r, s_g, s_b;
    wire [PPC - 1:0]      s_r_de, s_g_de, s_b_de;
    wire [10 * PPC - 1:0] q_r, q_g, q_b, k_r, k_g, k_b, t_r, t_g, t_b;
    hdmi_scr #(.N(PPC), .CH(0)) u_s0 (.clk(tx_clk), .frame(hd[1]), .scramble(hd[0]), .opt(hd[7:4]), .d(v_b), .c(c0),
                                     .de(v_de), .gb(v_gb), .ucc(v_ucc), .d_o(s_b), .de_o(s_b_de), .tok(q_b));
    hdmi_scr #(.N(PPC), .CH(1)) u_s1 (.clk(tx_clk), .frame(hd[1]), .scramble(hd[0]), .opt(hd[7:4]), .d(v_g), .c(c1),
                                     .de(v_de), .gb(v_gb), .ucc(v_ucc), .d_o(s_g), .de_o(s_g_de), .tok(q_g));
    hdmi_scr #(.N(PPC), .CH(2)) u_s2 (.clk(tx_clk), .frame(hd[1]), .scramble(hd[0]), .opt(hd[7:4]), .d(v_r),
                                     .c(c2), .de(v_de), .gb(v_gb), .ucc(v_ucc), .d_o(s_r),
                                     .de_o(s_r_de), .tok(q_r));
    generate
        if (PPC == 1) begin : g_isl
            assign k_b = a_d2[30] ? a_d2[9:0] : q_b;
            assign k_g = a_d2[30] ? a_d2[19:10] : q_g;
            assign k_r = a_d2[30] ? a_d2[29:20] : q_r;
        end else begin : g_noisl
            assign k_b = q_b;
            assign k_g = q_g;
            assign k_r = q_r;
        end
    endgenerate
    tmds_enc #(.N(PPC)) u_t2 (.clk(tx_clk), .d(s_r), .tok(k_r), .de(s_r_de), .q(t_r));
    tmds_enc #(.N(PPC)) u_t1 (.clk(tx_clk), .d(s_g), .tok(k_g), .de(s_g_de), .q(t_g));
    tmds_enc #(.N(PPC)) u_t0 (.clk(tx_clk), .d(s_b), .tok(k_b), .de(s_b_de), .q(t_b));
    // a lane's word: its characters in order, the line's first pixel's at the low end (sent
    // first); `AVB_SWAP: the other way round
`ifdef AVB_SWAP
    localparam SWAP = 1;
`else
    localparam SWAP = 0;
`endif
    function [79:0] word(input [10 * PPC - 1:0] w);
        integer ch;
        begin
            word = 80'd0;
            for (ch = 0; ch < PPC; ch = ch + 1)
                word[10 * ch +: 10] = w[10 * (SWAP ? PPC - 1 - ch : ch) +: 10];
        end
    endfunction
    // the TMDS clock's lane: a tenth of the bit rate, five ones and five zeros a character; above
    // 3.4 Gb/s a fortieth [HDMI 2.0 6.1.3.2], twenty and twenty across the clock's four characters
    wire [79:0] ck_word = PPC == 4 ? 80'h00000FFFFF : word({PPC{10'b0000011111}});
    always @(posedge tx_clk)
        tx_data <= {word(t_g), word(t_b), ck_word, word(t_r)};

    // the picture as sent, for the host (grab.v)
    reg         grab_arm = 1'b0;
    reg  [15:0] grab_cfg = 16'd0;
    reg  [13:0] grab_ra = 14'd0;
    wire        grab_done;
    wire [23:0] grab_rd;
    reg         grab_done_s0, grab_done_s;
    always @(posedge clk) begin
        grab_done_s0 <= grab_done;
        grab_done_s <= grab_done_s0;
        if (we && addr == 8'h38) begin
            grab_arm <= !grab_arm;
            grab_cfg <= wdata[15:0];
        end
        if (we && addr == 8'h39)
            grab_ra <= wdata[13:0];
        else if (addr == 8'h39 && u_mon.state == 4'd6)      // read: on to the next (the step's next column)
            grab_ra <= grab_ra + (grab_cfg[15:12] == 4'd0 ? 14'd1 : {10'd0, grab_cfg[15:12]});
    end
    grab u_grab (.clk(tx_clk), .de(v_de[0]), .vs(v_vs[0]), .rgb({v_r[7:0], v_g[7:0], v_b[7:0]}), .row(grab_cfg[10:0]),
                 .step(grab_cfg[15:12]), .arm(grab_arm), .done(grab_done), .rclk(clk), .ra(grab_ra), .rd(grab_rd));

    // the DDR3: its controller on its own clock (pclk, 100 MHz), its users through ddr_arb.v
    reg  [7:0]   por = 8'd0;
    always @(posedge clk)
        if (!pll_lock)
            por <= 8'd0;
        else if (!por[7])
            por <= por + 8'd1;
    wire         memory_clk, ddr_lock, pll_stop, pclk, ddr_ok, cal_fail;
    wire [7:0]   cal_info, dll_step;
    wire         d_cmd_ready, d_cmd_en, d_wr_en, d_rd_valid;
    wire [2:0]   d_cmd;
    wire [28:0]  d_addr;
    wire [255:0] d_wr_data, d_rd_data;
    ddr_pll u_ddr_pll (.clkin(sys_clk), .rst(!por[7]), .enclk(pll_stop), .memory_clk(memory_clk), .lock(ddr_lock));
    ddr3_top #(.CL(6), .CWL(5), .TCK_PS(2500), .PCLK_KHZ(100000), .FAST(0)) u_ddr3 (
        .memory_clk(memory_clk), .pll_stop(pll_stop), .clk(clk), .rst_n(por[7]), .pll_lock(ddr_lock),
        .clk_out(pclk), .init_calib_complete(ddr_ok),
        .cmd_ready(d_cmd_ready), .cmd(d_cmd), .cmd_en(d_cmd_en), .addr(d_addr), .wr_data_rdy(),
        .wr_data(d_wr_data), .wr_data_en(d_wr_en), .wr_data_end(d_wr_en), .wr_data_mask(32'd0),
        .rd_data(d_rd_data), .rd_data_valid(d_rd_valid), .rd_data_end(),
        .cal_fail(cal_fail), .cal_info(cal_info), .cal_dbg(), .cal_map(), .cal_snap(), .rd_stray(),
        .cal_opt(16'h0020), .dll_step(dll_step),
        .O_ddr_addr(ddr_addr), .O_ddr_ba(ddr_bank), .O_ddr_cs_n(ddr_cs), .O_ddr_ras_n(ddr_ras),
        .O_ddr_cas_n(ddr_cas), .O_ddr_we_n(ddr_we), .O_ddr_clk(ddr_ck), .O_ddr_clk_n(ddr_ck_n),
        .O_ddr_cke(ddr_cke), .O_ddr_odt(ddr_odt), .O_ddr_reset_n(ddr_reset_n), .O_ddr_dqm(ddr_dm),
        .IO_ddr_dq(ddr_dq), .IO_ddr_dqs(ddr_dqs), .IO_ddr_dqs_n(ddr_dqs_n));

    reg  [255:0] d_rd_q;                 // (a read's line, with ddr_arb.v's rvalid)
    always @(posedge pclk)
        d_rd_q <= d_rd_data;

    // the host's line: asked for on the system clock, done on pclk
    reg  [31:0]  dm_cmd = 32'd0;
    reg          dm_go = 1'b0;
    reg  [255:0] dm_wdata = 256'd0;
    reg  [255:0] dm_rdata = 256'd0;
    reg          dm_g0, dm_g1, dm_g2, dm_valid = 1'b0, dm_done = 1'b0;
    wire         dm_ack, dm_rvalid;
    always @(posedge clk) begin
        if (we && addr == 8'h40) begin
            dm_cmd <= wdata;
            dm_go <= !dm_go;
        end
        if (we && addr[7:3] == 5'b01001)
            dm_wdata[32 * addr[2:0] +: 32] <= wdata;
    end
    always @(posedge pclk) begin
        dm_g0 <= dm_go;
        dm_g1 <= dm_g0;
        dm_g2 <= dm_g1;
        if (dm_g1 != dm_g2) begin
            dm_valid <= 1'b1;
            dm_done <= 1'b0;
        end else if (dm_ack) begin
            dm_valid <= 1'b0;
            if (dm_cmd[31])
                dm_done <= 1'b1;
        end
        if (dm_rvalid) begin
            dm_rdata <= d_rd_q;
            dm_done <= 1'b1;
        end
    end
    ddr_arb u_arb (.clk(pclk), .cmd_ready(d_cmd_ready), .cmd(d_cmd), .cmd_en(d_cmd_en), .addr(d_addr),
                   .wr_data(d_wr_data), .wr_data_en(d_wr_en), .rd_data_valid(d_rd_valid),
                   .a_valid(ca_valid), .a_line(ca_line), .a_data(ca_data), .a_ack(ca_ack),
                   .b_valid(db_valid), .b_line(db_line), .b_ack(db_ack), .b_rvalid(db_rvalid),
                   .c_valid(dm_valid), .c_wr(dm_cmd[31]), .c_line(dm_cmd[24:0]), .c_data(dm_wdata),
                   .c_ack(dm_ack), .c_rvalid(dm_rvalid));
    // the picture through the DDR3: the fields in (cap_ddr.v), the frame's lines out (deint.v) to
    // lineview.v's ring
    reg  [31:0]  dcfg = 32'h140D0620;
    reg  [7:0]   ll_min = 8'd16;
    wire [9:0]   f_prog;
    wire [2:0]   f_pslot;
    reg  [27:0]  g_xr = -28'sd11808768;
    reg          g_wide = 1'b0;
    reg  [16:0]  g_dx = 17'd32768;
    reg  [26:0]  g_ys = -27'sd18205;
    reg  [16:0]  g_dy = 17'd29127;
    always @(posedge clk) begin
        if (we && addr == 8'h35)
            dcfg <= wdata;
        if (we && addr == 8'h2B)
            ll_min <= wdata[7:0];
        if (we && addr == 8'h3A)
            g_xr <= wdata[27:0];
        if (we && addr == 8'h3B) begin
            g_dx <= wdata[16:0];
            g_wide <= wdata[31];
        end
        if (we && addr == 8'h3C)
            g_ys <= wdata[26:0];
        if (we && addr == 8'h3D)
            g_dy <= wdata[16:0];
    end
    wire         ca_valid, ca_ack, db_valid, db_ack, db_rvalid;
    wire [24:0]  ca_line, db_line;
    wire [255:0] ca_data;
    wire [2:0]   f_latest, f_n;
    wire [7:0]   f_par, d_state;
    wire [9:0]   f_lines;
    wire [15:0]  d_frames;
    wire         l_ev, l_first, r_we, d_fstart, d_hold, w_we;
    wire [9:0]   l_goal, d_emitted, w_x;
    wire [8:0]   r_wa;
    wire [2:0]   r_slot_d, r_slot_i, w_slot;
    wire [31:0]  r_wd_d, r_wd_i;
    wire [53:0]  w_d;
    // (the stream runs 18 lines ahead of the ring for smaa.v; l_goal crosses from the word clock
    // with its event: taken as deint.v takes it)
    reg  [10:0]  s_goal = 11'd0;
    reg          lg0, lg1, lg2;
    always @(posedge pclk) begin
        lg0 <= l_ev;
        lg1 <= lg0;
        lg2 <= lg1;
        if (lg1 != lg2)
            s_goal <= {1'b0, l_goal} + 11'd18;
    end
    cap_ddr u_capd (.llc(in_llc), .we(fb_we), .w_ln(cap_ln), .w_col(cap_col), .wd(fb_wd), .eof(cap_eof),
                    .eof_f(cap_field), .eof_lines(cap_lines), .freeze(vid[1]), .pclk(pclk), .a_valid(ca_valid),
                    .a_line(ca_line), .a_data(ca_data), .a_ack(ca_ack), .latest(f_latest), .par(f_par),
                    .nfields(f_n), .flines(f_lines), .prog(f_prog), .prog_slot(f_pslot));
    deint u_deint (.clk(pclk), .ev(l_ev), .ev_first(l_first), .goal(s_goal[9:0]), .hold(d_hold), .latest(f_latest),
                   .par(f_par), .nfields(f_n), .flines(f_lines), .mode(dcfg[1:0]), .thr(dcfg[15:8]), .nr(dcfg[5:4]), .ll(dcfg[6] && !vid[1]), .ll_min(ll_min),
                   .prog(f_prog), .prog_slot(f_pslot),
                   .top_f(dcfg[2]), .b_valid(db_valid), .b_line(db_line), .b_ack(db_ack), .b_rvalid(db_rvalid),
                   .rd_data(d_rd_q), .r_we(r_we), .r_slot_d(r_slot_d), .r_slot_i(r_slot_i), .r_wa(r_wa),
                   .r_wd_d(r_wd_d), .r_wd_i(r_wd_i), .emitted(d_emitted), .fstart(d_fstart), .frames(d_frames),
                   .state_o(d_state));
    lstream u_ls (.clk(pclk), .fstart(d_fstart), .emitted(d_emitted), .goal(s_goal), .hold(d_hold), .r_we(r_we),
                  .aa_en(dcfg[16]), .aa_dbg(dcfg[17]), .aa_diag(dcfg[18]), .aa_corner(dcfg[19]), .aa_thr(dcfg[31:24]),
                  .r_slot_d(r_slot_d[1:0]), .r_slot_i(r_slot_i[1:0]), .r_wa(r_wa), .r_wd_d(r_wd_d), .r_wd_i(r_wd_i),
                  .w_we(w_we), .w_slot(w_slot), .w_x(w_x), .w_d(w_d));
    // how old the newest field is when a frame is begun: from the field's end (latest changes), in 10 us
    reg  [9:0]   lt_div = 10'd0;
    reg  [11:0]  lt_age = 12'd0, lt_f = 12'd0;
    reg  [9:0]   lt_p = 10'd0;
    reg  [21:0]  lat_s0, lat_s;
    reg  [2:0]   lt_l;
    always @(posedge pclk) begin
        lt_l <= f_latest;
        lt_div <= lt_div == 10'd999 ? 10'd0 : lt_div + 10'd1;
        if (f_latest != lt_l) begin
            lt_age <= 12'd0;
            lt_div <= 10'd0;
        end else if (lt_div == 10'd999 && !(&lt_age))
            lt_age <= lt_age + 12'd1;
        if (d_fstart) begin
            lt_f <= lt_age;
            lt_p <= f_pslot == f_latest + 3'd1 ? f_prog : 10'd0;
        end
    end
    always @(posedge clk) begin
        lat_s0 <= {lt_p, lt_f};
        lat_s <= lat_s0;
    end
    generate
        if (PPC == 1) begin : g_lv
            wire [7:0]  e_y, e_cb, e_cr;
            wire [24:0] e_xy;
            // (the scaler's part of the source: set while nothing depends on a frame of it)
            reg [89:0] geo0, geo;
            always @(posedge tx_clk) begin
                geo0 <= {g_wide, g_xr, g_dx, g_ys, g_dy};
                geo <= geo0;
            end
            easu u_easu (.g_wide(geo[89]), .g_xr(geo[88:61]), .g_dx(geo[60:44]), .g_ys(geo[43:17]), .g_dy(geo[16:0]),
                         .clk(tx_clk), .de(p_de[0]), .x(p_x), .y(p_y), .ev(l_ev), .ev_first(l_first), .ev_goal(l_goal),
                         .w_clk(pclk), .w_we(w_we), .w_slot(w_slot), .w_x(w_x), .w_d(w_d), .o_y(e_y), .o_cb(e_cb),
                         .o_cr(e_cr));
            dline #(.W(25), .D(LAT_E)) u_dxy (.clk(tx_clk), .d({p_x, p_y}), .q(e_xy));
            rcas u_rcas (.dn(dn), .wide(geo[89]), .clk(tx_clk), .x(e_xy[24:12]), .y(e_xy[11:0]), .yi(e_y), .cbi(swap ? e_cr : e_cb),
                         .cri(swap ? e_cb : e_cr), .sharp(sharp), .r(l_r), .g(l_g), .b(l_b));
        end else begin : g_nolv
            assign l_r = 8'd0;
            assign l_g = 8'd0;
            assign l_b = 8'd0;
            assign l_ev = 1'b0;
            assign l_first = 1'b0;
            assign l_goal = 10'd0;
        end
    endgenerate
    reg [29:0] dst_s0, dst_s;
    always @(posedge clk) begin
        dst_s0 <= {d_frames, d_state, f_latest, f_n};
        dst_s <= dst_s0;
    end
    reg [18:0] ddr_s0, ddr_s;
    always @(posedge clk) begin
        ddr_s0 <= {dll_step, cal_info, dm_done, cal_fail, ddr_ok};
        ddr_s <= ddr_s0;
    end

    // the sound in (audio_in.v, on the MS5351M's CLK2); for the host: the last words and the peaks
    wire [31:0] au_l, au_r;
    wire        au_tick;
    audio_in u_au (.clk(pll_clk2), .scki(in_scki), .bck(in_bck), .lrck(in_lrck), .dout(in_dout), .l(au_l), .r(au_r),
                   .tick(au_tick));
    // (to HDMI: the samples as they come, the word clock's side taking them by the tick)
    hdmi_audio u_ha (.clk(tx_clk), .en(hd[2] && hd[1]), .hs(v_hs[0]), .vs(v_vs[0]), .s_tick(au_tick), .s_l(au_l[30:7]),
                     .s_r(au_r[30:7]), .pre(a_pre), .act(a_act), .k0(a_k0), .k1(a_k1), .k2(a_k2));
    reg         au_t0, au_t1, au_t2;
    reg  [31:0] au_ls, au_rs;
    reg  [15:0] au_pl = 16'd0, au_pr = 16'd0;
    wire [15:0] au_al = au_ls[30] ? ~au_ls[30:15] : au_ls[30:15], au_ar = au_rs[30] ? ~au_rs[30:15] : au_rs[30:15];
    reg         au_new;
    always @(posedge clk) begin
        au_t0 <= au_tick;
        au_t1 <= au_t0;
        au_t2 <= au_t1;
        au_new <= au_t1 != au_t2;
        if (au_t1 != au_t2) begin               // (the words have been still for a sample's time)
            au_ls <= au_l;
            au_rs <= au_r;
        end
        if (addr == 8'h52 && u_mon.state == 4'd6) begin
            au_pl <= 16'd0;
            au_pr <= 16'd0;
        end else if (au_new) begin
            if (au_al > au_pl)
                au_pl <= au_al;
            if (au_ar > au_pr)
                au_pr <= au_ar;
        end
    end

    wire [31:0] f0, f1, f2, f3, f4;
    fmeter u_f0 (.clk(clk), .tick(tick), .f(pll_clk2), .count(f0));
    fmeter u_f1 (.clk(clk), .tick(tick), .f(in_llc), .count(f1));
    fmeter u_f2 (.clk(clk), .tick(tick), .f(tx_clk), .count(f2));
    fmeter u_f3 (.clk(clk), .tick(tick), .f(gt_ref_clk[0]), .count(f3));
    fmeter u_f4 (.clk(clk), .tick(tick), .f(pcs_tx_clk[1]), .count(f4));
    reg [13:0] gt_s0, gt_s;
    always @(posedge clk) begin
        gt_s0 <= {qpll_ok, fifo_afull, fifo_full, cmu_ok};
        gt_s <= gt_s0;
    end

    reg [4:0] stat_s0, stat;
    reg [38:0] cap_s0, cap_s;
    always @(posedge clk) begin
        stat_s0 <= {cec_fpga, in_int, dp_hpd, in_key2, in_key1};
        stat <= stat_s0;
        cap_s0 <= {cap_fields, raw_done, cap_field, cap_lines, cap_pix};
        cap_s <= cap_s0;
        case (addr)
            8'h00: rdata <= 32'h31425641;
            8'h01: rdata <= `AVB_BUILD;
            8'h02: rdata <= {27'd0, ctrl};
            8'h03: rdata <= {23'd0, stuck, 3'd0, stat};
            8'h04: rdata <= {15'd0, waiting, i2c_in, i2c_drv};
            8'h05: rdata <= i2c_sh[0];
            8'h06: rdata <= i2c_sh[1];
            8'h07: rdata <= i2c_sh[2];
            8'h08: rdata <= i2c_sh[3];
            8'h10: rdata <= f0;
            8'h11: rdata <= f1;
            8'h12: rdata <= f2;
            8'h13: rdata <= f3;
            8'h14: rdata <= f4;
            8'h20: rdata <= gt_ctrl;
            8'h21: rdata <= {18'd0, gt_s};
            8'h22: rdata <= {3'd0, gt_stat[25:13], 3'd0, gt_stat[12:0]};
            8'h23: rdata <= {3'd0, gt_stat[51:39], 3'd0, gt_stat[38:26]};
            8'h24: rdata <= {8'd0, gt_astat};
            8'h25: rdata <= PPC;
            8'h26: rdata <= {24'd0, hd_ctrl};
            8'h30: rdata <= vid;
            8'h31: rdata <= {cap_s[22], 9'd0, cap_s[21:0]};
            8'h32: rdata <= {16'd0, cap_s[38:23]};
            8'h34: rdata <= {13'd0, raw_rd};
            8'h35: rdata <= dcfg;
            8'h27: rdata <= {6'd0, lat_s[21:12], 4'd0, lat_s[11:0]};
            8'h2B: rdata <= {24'd0, ll_min};
            8'h28: rdata <= {31'd0, osd_on};
            8'h2A: rdata <= {temp[14], 17'd0, temp[13:0]};
            8'h70: rdata <= sp_stat;
            8'h71: rdata <= sp_rx;
            8'h74: rdata <= sp_pins;
            8'h60: rdata <= {31'd0, cpu_run};
            8'h61: rdata <= {19'd0, cpu_pa};
            8'h64: rdata <= cpu_m0;
            8'h65: rdata <= cpu_m1;
            8'h66: rdata <= cpu_m2;
            8'h67: rdata <= cpu_m3;
            8'h37: rdata <= {fo_n, fo_sum};
            8'h3E: rdata <= {bd_any, 6'd0, bd_x1, 7'd0, bd_x0};
            8'h3F: rdata <= {6'd0, bd_l1, 6'd0, bd_l0};
            8'h3A: rdata <= {{4{g_xr[27]}}, g_xr};
            8'h3B: rdata <= {g_wide, 14'd0, g_dx};
            8'h3C: rdata <= {{5{g_ys[26]}}, g_ys};
            8'h3D: rdata <= {15'd0, g_dy};
            8'h36: rdata <= {dst_s[29:14], dst_s[13:6], 2'd0, dst_s[5:0]};
            8'h38: rdata <= {grab_done_s, 15'd0, grab_cfg};
            8'h50: rdata <= au_ls;
            8'h51: rdata <= au_rs;
            8'h52: rdata <= {au_pr, au_pl};
            8'h40: rdata <= {8'd0, ddr_s[18:3], 5'd0, ddr_s[2:0]};
            8'h48, 8'h49, 8'h4A, 8'h4B, 8'h4C, 8'h4D, 8'h4E, 8'h4F: rdata <= dm_rdata[32 * addr[2:0] +: 32];
            8'h39: rdata <= {8'd0, grab_rd};
            default: rdata <= 32'd0;
        endcase
    end
endmodule
