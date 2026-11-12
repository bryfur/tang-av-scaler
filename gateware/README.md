# Gateware: rev C-B's bring-up image

For the AV board rev C-B (Tang Mega 138K SOM, GW5AST-LV138PG484AC1/I0 version C): a monitor on the
XIAO's UART that reaches every chip on the board, HDMI out of the FPGA's transceivers, and the
component input shown on the HDMI output. `rtl/top.v` lists the registers.

State on the board (2026-11-12):

| | |
|---|---|
| Component in, HDMI out | 480i YPbPr -> 1080p60 (59.94 Hz), in colour: the fields kept in the SOM's DDR3, deinterlaced motion adaptive to 720 x 480 from the last four (weave where nothing moves, the lines' mean where something does), shown 1440 x 1080 (4:3, nearest pixel for now). No tear: a frame is made of whole fields (one repeated or dropped as the rates drift). 480p, 720p, 1080i: decoder settings not found yet. |
| HDMI out | 1080p60 and 2160p30 clean on the sink's own counters (SN65DP159 as a redriver: as a retimer it corrupts 2.97 Gb/s). 2160p60: the link is clean and the sink sees scrambling, no picture yet. |
| Audio | not started |

## Build, load, run

    GW_MODE=1080p60 GW_OUT=$PWD/gowin/build/vid gowin/build.sh    # Gowin 1.9.12 in fpc's fpga-tools container
    tools/video.py --load                    # load it (USB JTAG), HDMI up, the decoder set, the input shown
    tools/hdmi.py --load gowin/build/hdmi/avb/impl/pnr/avb.fs     # the test picture alone

`GW_MODE` is `1080p60`, `2160p30` or `2160p60` (the transceivers' rate; the component input is in
the 1080p60 image only). The bitstream is `<GW_OUT>/avb/impl/pnr/avb.fs`, not compressed:
openFPGALoader 1.1.1 cannot parse a compressed one. It goes into the FPGA's SRAM only.

## Parts

| | |
|---|---|
| `rtl/top.v` | the registers; the picture's path: `pattern.v` or `fbview.v` -> `hdmi_scr.v` -> `tmds.v` -> `gtx_quad.v` |
| `rtl/mon.v`, `uart.v`, `fmeter.v`, `sys_pll.v` | the monitor (1 Mbaud: `W addr data`, `R addr`), frequency meters, the 50 MHz |
| `rtl/pattern.v` | video timing and the test picture, 1, 2 or 4 pixels a clock |
| `rtl/hdmi_scr.v`, `tmds.v` | HDMI's framing and HDMI 2.0's scrambling (from public patents: not proven on a sink), TMDS coding N characters a clock |
| `rtl/gtx_quad.v` | the transceiver quad (generated: `tools/mkgtx.py`); its register file by `gowin/serdes.py`, no IDE |
| `rtl/vcap.v`, `cap_ddr.v` | the ADV7181D's pixel port decoded, its fields into the DDR3 (eight slots, a bank each) |
| `rtl/deint.v`, `lineview.v` | the motion adaptive deinterlacer (a line when the output wants it), its lines through a ring of eight as the 1080p picture |
| `rtl/ddr3/`, `ddr_arb.v` | the DDR3: our own PHY, calibration and controller (from the fpc console; `pll_init.v` is Sipeed's, Apache 2.0), its port shared by the capture, the picture and the host |
| `rtl/grab.v` | rows of the picture as sent, for the host to read: `tools/grab.py OUT.png` shows the output with no display |
| `gowin/` | the build: `avb.tcl` makes the project, `csr_result.py` hands it the transceivers' register file, `run.tcl` runs it; pins `avb.cst`, clocks `avb.sdc` |
| `tools/avb.py` | the monitor from the host: registers, the four I2C buses, the meters |
| `tools/ddr.py` | the DDR3's calibration state, a write and read test through the monitor |
| `tools/video.py`, `adv.py` | the component input: the ADV7181D's settings (and what was learnt about them), the capture's state, raw samples of the pixel port |
| `tools/hdmi.py`, `clkgen.py`, `edid.py`, `scdc.py`, `linkq.py`, `ddcci.py` | HDMI up; the MS5351M; the sink's EDID, SCDC, error counters, and its own measure of the picture rate |
| `tools/load.sh` | a bitstream into the SRAM through the XIAO's USB-JTAG bridge |
| `sim/` | testbenches (iverilog, each checks against a model in Python): `tmds_tb.py`, `scr_tb.py`, `pattern_tb.py`, `deint_tb.py [NFIELDS]` (the whole picture path with a model of the DDR3, against `model.py`) |
| `test/loop.v` | a UART loop-back, to test the XIAO's wiring |

The monitor's port: `AVB_TTY` (a serial device, or `tcp:HOST[:PORT]`), else the Wi-Fi link
(`avscaler.local`), else a XIAO's USB serial port.
