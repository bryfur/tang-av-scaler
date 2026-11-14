create_clock -name osc -period 20 -waveform {0 10} [get_ports {sys_clk}]
create_clock -name sys -period 20 -waveform {0 10} [get_pins {u_pll/u/CLKOUT0}]
create_clock -name core -period 1.25 -waveform {0 0.625} [get_nets {core_clk}]
create_clock -name pll_clk2 -period 40 -waveform {0 20} [get_ports {pll_clk2}]
create_clock -name in_llc -period 13 -waveform {0 6.5} [get_ports {in_llc}]
create_clock -name tx -period 6.5 -waveform {0 3.25} [get_pins {u_gtx/u_quad/LANE0_PCS_TX_O_FABRIC_CLK}]
create_clock -name mem -period 2.5 -waveform {0 1.25} [get_nets {memory_clk}]
create_clock -name ddr -period 10 -waveform {0 5} [get_pins {u_ddr3/u_dp/u_phy/u_div/CLKOUT}]
set_clock_groups -asynchronous -group [get_clocks {sys}] -group [get_clocks {core}] -group [get_clocks {pll_clk2}] -group [get_clocks {in_llc}] -group [get_clocks {osc}] -group [get_clocks {tx}] -group [get_clocks {mem}] -group [get_clocks {ddr}]
// The DDR3's pins' side (rtl/ddr3/ddr3_dp.v): the registers that take the deserializers' words and
// the DQS blocks' RVALID are a register after a register with a whole cycle allowed, and the
// placer used it: on the board one placement lost a lane's RVALID now and then (its bursts went
// to the wrong reads: the memory right, that lane's bytes another line's) and its twin failed the
// calibration, with nothing in the timing report: what the pins' blocks give comes later in the
// clock than the tool's model says.  Half a cycle for those (3.3 ns of net then: met with 1.2 to
// spare).  The registers before the serializers and the DQS blocks: 8 ns (the ones for a whole
// lane or for all of them reach along the chip's edge: 5 ns they cannot make).
set_max_delay -to [get_regs {u_ddr3/u_dp/rdat_q_*}] 5
set_max_delay -to [get_regs {u_ddr3/u_dp/rv_q_*}] 5
set_max_delay -from [get_regs {u_ddr3/u_dp/p_*}] 8
// Settings that stand still while a picture is made (the part shown, the 720p pass-through's
// flag, what comes in, the network's switch): each a register in the clock of the logic it goes
// to, changed by the CPU's program now and then.  What they go into is deep (the part shown: a
// multiplier and its sum), and none of it matters in the clock they change: four clocks for them.
set_multicycle_path -from [get_regs {g_lv.geo_*_s0}] -setup -end 4
set_multicycle_path -from [get_regs {g_lv.geo_*_s0}] -hold -end 3
set_multicycle_path -from [get_regs {hd_t_s0}] -setup -end 4
set_multicycle_path -from [get_regs {hd_t_s0}] -hold -end 3
set_multicycle_path -from [get_regs {src_p_*_s0}] -setup -end 4
set_multicycle_path -from [get_regs {src_p_*_s0}] -hold -end 3
set_multicycle_path -from [get_regs {g_lv.n_on_s0}] -setup -end 4
set_multicycle_path -from [get_regs {g_lv.n_on_s0}] -hold -end 3
// The scaler's row place (it changes between rows, and the next row's pixels are hundreds of clocks
// off) and the first line a frame makes (it changes with a frame's start: lstream.v is begun again
// then): two clocks for what they go into.
set_multicycle_path -from [get_regs {g_lv.u_easu/yp_*_s0}] -setup -end 2
set_multicycle_path -from [get_regs {g_lv.u_easu/yp_*_s0}] -hold -end 1
set_multicycle_path -from [get_regs {u_ls/skf_*_s0}] -setup -end 2
set_multicycle_path -from [get_regs {u_ls/skf_*_s0}] -hold -end 1
