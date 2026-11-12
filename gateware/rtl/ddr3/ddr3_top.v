// Our DDR3 memory interface for the Tang Console 138K's 1 GB (two x16
// chips, 32 bits), in the place of Gowin's DDR3 Memory Interface IP and
// with its ports as the console uses them (the same names: rtl/ddr3test.v
// and rtl/top.v take either): ddr3_phy.v (the pins), ddr3_dp.v (a write's
// and a read's timing), ddr3_cal.v (the chips' power-up, the calibration),
// ddr3_ctl.v (the controller).
//
//   memory_clk  the PLL's memory clock (rtl/ddr_pll.v), stopped while
//               pll_stop is low (its output enable)
//   clk         the board's 50 MHz;  clk_out: the user clock, memory_clk / 4
//   CL, CWL     the chips' latencies for the memory clock (6, 5: DDR3-800)
//   TCK_PS, PCLK_KHZ  the memory clock's period, the user clock's rate
//
// cal_fail, cal_info, cal_dbg, cal_map, dll_step: the calibration's
// result (ddr3_cal.v), for a report.

module ddr3_top #(
    parameter CL       = 6,
    parameter CWL      = 5,
    parameter TCK_PS   = 2500,
    parameter PCLK_KHZ = 100000,
    parameter FAST     = 0
) (
    input  wire         clk,
    input  wire         memory_clk,
    input  wire         pll_lock,
    input  wire         rst_n,
    output wire         pll_stop,
    output wire         clk_out,
    output wire         init_calib_complete,

    output wire         cmd_ready,
    input  wire [2:0]   cmd,
    input  wire         cmd_en,
    input  wire [28:0]  addr,
    output wire         wr_data_rdy,
    input  wire [255:0] wr_data,
    input  wire         wr_data_en,
    input  wire         wr_data_end,
    input  wire [31:0]  wr_data_mask,
    output wire [255:0] rd_data,
    output wire         rd_data_valid,
    output wire         rd_data_end,

    output wire         cal_fail,
    output wire [7:0]   cal_info,
    output wire [127:0] cal_dbg,
    output wire [127:0] cal_map,
    output wire [135:0] cal_snap,
    output wire         rd_stray,         // (ddr3_dp.v: a burst out of place: it stays)
    input  wire [15:0]  cal_opt,          // (16'h0020: ddr3_cal.v)
    output wire [7:0]   dll_step,

    output wire [14:0]  O_ddr_addr,
    output wire [2:0]   O_ddr_ba,
    output wire         O_ddr_cs_n,
    output wire         O_ddr_ras_n,
    output wire         O_ddr_cas_n,
    output wire         O_ddr_we_n,
    output wire         O_ddr_clk,
    output wire         O_ddr_clk_n,
    output wire         O_ddr_cke,
    output wire         O_ddr_odt,
    output wire         O_ddr_reset_n,
    output wire [3:0]   O_ddr_dqm,
    inout  wire [31:0]  IO_ddr_dq,
    inout  wire [3:0]   IO_ddr_dqs,
    inout  wire [3:0]   IO_ddr_dqs_n
);

wire        pclk, ready;
wire        cal_done;
wire [3:0]  k_cmd, u_cmd;
wire [1:0]  k_slot, u_slot;
wire [2:0]  k_ba, u_ba;
wire [14:0] k_a, u_a;
wire        k_cke, k_reset_n, k_wr_go, k_rd_go, u_wr_go, u_rd_go;
wire [255:0] k_wdata, u_wdata;
wire [31:0] u_wmask;
wire [7:0]  g_cyc, g_rot;
wire [11:0] g_sel;
wire [3:0]  l_hold, l_rmove, l_rdir, l_slip, r_valid;
wire [255:0] r_data;
wire        rd_raw;
wire        dqs_pulse, dp_rd_valid;

// ---- the command: the calibration's until it is done ----
wire [3:0]  m_cmd  = cal_done ? u_cmd : k_cmd;
wire [1:0]  m_slot = cal_done ? u_slot : k_slot;
wire [2:0]  m_ba   = cal_done ? u_ba : k_ba;
wire [14:0] m_a    = cal_done ? u_a : k_a;
wire [3:0]  at = 4'b0001 << m_slot;
wire [3:0]  c_cs_n  = ~at | {4{m_cmd[3]}};
wire [3:0]  c_ras_n = ~at | {4{m_cmd[2]}};
wire [3:0]  c_cas_n = ~at | {4{m_cmd[1]}};
wire [3:0]  c_we_n  = ~at | {4{m_cmd[0]}};

ddr3_dp #(.CL(CL), .CWL(CWL)) u_dp (
    .clk(clk), .rst(!pll_lock || !rst_n), .mclk(memory_clk), .mclk_en(pll_stop), .pclk(pclk),
    .ready(ready),
    .c_cs_n(c_cs_n), .c_ras_n(c_ras_n), .c_cas_n(c_cas_n), .c_we_n(c_we_n),
    .c_ba({4{m_ba}}), .c_a({4{m_a}}), .c_cke(k_cke), .c_reset_n(k_reset_n),
    .wr_go(cal_done ? u_wr_go : k_wr_go), .wr_data(cal_done ? u_wdata : k_wdata),
    .wr_mask(cal_done ? u_wmask : 32'd0),
    .rd_go(cal_done ? u_rd_go : k_rd_go), .rd_valid(dp_rd_valid), .rd_data(rd_data),
    .rd_raw(rd_raw), .r_data(r_data), .rd_stray(rd_stray),
    .g_cyc(g_cyc), .g_rot(g_rot), .g_sel(g_sel), .dqs_pulse(dqs_pulse),
    .l_hold(l_hold), .l_rmove(l_rmove), .l_rdir(l_rdir), .l_slip(l_slip), .r_valid(r_valid),
    .dll_step(dll_step),
    .ddr_addr(O_ddr_addr), .ddr_bank(O_ddr_ba), .ddr_cs(O_ddr_cs_n), .ddr_ras(O_ddr_ras_n),
    .ddr_cas(O_ddr_cas_n), .ddr_we(O_ddr_we_n), .ddr_ck(O_ddr_clk), .ddr_ck_n(O_ddr_clk_n),
    .ddr_cke(O_ddr_cke), .ddr_odt(O_ddr_odt), .ddr_reset_n(O_ddr_reset_n), .ddr_dm(O_ddr_dqm),
    .ddr_dq(IO_ddr_dq), .ddr_dqs(IO_ddr_dqs), .ddr_dqs_n(IO_ddr_dqs_n)
);

ddr3_cal #(.CL(CL), .CWL(CWL), .PCLK_KHZ(PCLK_KHZ), .FAST(FAST)) u_cal (
    .clk(pclk), .rst(!ready),
    .o_cmd(k_cmd), .o_slot(k_slot), .o_ba(k_ba), .o_a(k_a), .o_cke(k_cke), .o_reset_n(k_reset_n),
    .wr_go(k_wr_go), .wr_data(k_wdata), .rd_go(k_rd_go), .rd_raw(rd_raw), .r_data(r_data),
    .r_valid(r_valid), .rd_valid(dp_rd_valid), .rd_data(rd_data),
    .dll_step(dll_step),
    .g_cyc(g_cyc), .g_rot(g_rot), .g_sel(g_sel), .dqs_pulse(dqs_pulse),
    .l_hold(l_hold), .l_rmove(l_rmove), .l_rdir(l_rdir), .l_slip(l_slip),
    .done(cal_done), .fail(cal_fail), .info(cal_info), .dbg(cal_dbg),
    .map_all(cal_map[63:0]), .map_first(cal_map[127:64]), .opt(cal_opt), .snap(cal_snap)
);

ddr3_ctl #(.CL(CL), .CWL(CWL), .TCK_PS(TCK_PS), .PCLK_KHZ(PCLK_KHZ)) u_ctl (
    .clk(pclk), .rst(!cal_done),
    .cmd_ready(cmd_ready), .cmd_en(cmd_en), .cmd_wr(cmd == 3'd0), .addr(addr),
    .wr_data(wr_data), .wr_mask(wr_data_mask),
    .o_cmd(u_cmd), .o_slot(u_slot), .o_ba(u_ba), .o_a(u_a), .wr_go(u_wr_go), .o_wdata(u_wdata),
    .o_wmask(u_wmask), .rd_go(u_rd_go)
);

assign clk_out = pclk;
assign init_calib_complete = cal_done;
assign wr_data_rdy = cmd_ready;
assign rd_data_valid = dp_rd_valid && cal_done;
assign rd_data_end = rd_data_valid;

endmodule
