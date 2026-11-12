# Gateware: rev C-B's bring-up image

For the AV board rev C-B (Tang Mega 138K SOM, GW5AST-LV138PG484AC1/I0 version C): a monitor on the
XIAO's UART that reaches every chip on the board, HDMI out of the FPGA's transceivers, and the
component input shown on the HDMI output. `rtl/top.v` lists the registers.

State on the board (2026-11-12):

| | |
|---|---|
| Component in, HDMI out | 480i YPbPr -> 1080p60 (59.94 Hz), in colour: the fields kept in the SOM's DDR3, deinterlaced motion adaptive to 720 x 480 from the last four (weave where nothing moves, the lines' mean where something does), anti-aliased (SMAA 1x, the orthogonal and the diagonal patterns, corners kept; a view of what it finds in the picture's place), scaled to 1440 x 1080 (4:3) by FSR 1: its edge adaptive upsampling (EASU), table driven, and its sharpening (RCAS, on luma). The part scaled is all of the 720 x 480 or less: the black round a game's picture is measured (`rtl/border.v`) and left out, so the picture fills the 4:3. No tear: a frame is made of whole fields (one repeated or dropped as the rates drift). 480p, 720p, 1080i: decoder settings not found yet. |
| HDMI out | 1080p60 and 2160p30 clean on the sink's own counters (SN65DP159 as a redriver: as a retimer it corrupts 2.97 Gb/s). 2160p60: the link is clean and the sink sees scrambling, no picture yet. |
| Audio | the PCM1808's clocks and samples (`rtl/audio_in.v`: alive on the board, `tools/audio.py`), and HDMI's data islands for them (`rtl/hdmi_audio.v`: samples, N/CTS, audio and AVI InfoFrames; decoded and checked in simulation, `sim/audio_tb.py`). Off by default (HDMI register bit 2, the web page's "sound over HDMI"): not yet tried on a display. fs is the pixel clock / 3072 = 48.34 kHz. |

## Build, load, run

    GW_MODE=1080p60 GW_OUT=$PWD/gowin/build/vid gowin/build.sh    # Gowin 1.9.12 in fpc's fpga-tools container
    tools/video.py --load                    # load it (USB JTAG), HDMI up, the decoder set, the input shown
    tools/hdmi.py --load gowin/build/hdmi/avb/impl/pnr/avb.fs     # the test picture alone

    tools/flash.sh <GW_OUT>/avb/impl/pnr/avb.fs     # into the SOM's flash: the board starts by itself

With the bitstream in the flash and the Wi-Fi link's firmware in the XIAO (`firmware/xiao-wifi`:
it brings the clock chip, the HDMI redriver, the decoder and the picture's settings up through
the monitor), the board needs power, a source and a display, and nothing else: the FPGA loads from the flash,
the link brings the rest up: a picture some 20 s after power-on. The scripts below are for development; the link stands
back while one of them is on its console port.

`GW_MODE` is `1080p60`, `2160p30` or `2160p60` (the transceivers' rate; the component input is in
the 1080p60 image only). The bitstream is `<GW_OUT>/avb/impl/pnr/avb.fs`, not compressed:
openFPGALoader 1.1.1 cannot parse a compressed one. `tools/load.sh` puts it in the FPGA's SRAM only
(until the next power-on or reload).

## Parts

| | |
|---|---|
| `rtl/top.v` | the registers; the picture's path: `pattern.v` or `fbview.v` -> `hdmi_scr.v` -> `tmds.v` -> `gtx_quad.v` |
| `rtl/mon.v`, `uart.v`, `fmeter.v`, `sys_pll.v` | the monitor (1 Mbaud: `W addr data`, `R addr`), frequency meters, the 50 MHz |
| `rtl/pattern.v` | video timing and the test picture, 1, 2 or 4 pixels a clock |
| `rtl/hdmi_scr.v`, `tmds.v` | HDMI's framing and HDMI 2.0's scrambling (from public patents: not proven on a sink), TMDS coding N characters a clock |
| `rtl/rcas.v`, `dline.v` | FSR 1's sharpening on the scaled picture's luma (a row of delay: the timing waits in a block RAM), then R'G'B' |
| `rtl/audio_in.v`, `hdmi_audio.v` | the audio converter's clocks and I2S words; HDMI's data islands: a packet in each line's back porch |
| `rtl/gtx_quad.v` | the transceiver quad (generated: `tools/mkgtx.py`); its register file by `gowin/serdes.py`, no IDE |
| `rtl/vcap.v`, `cap_ddr.v` | the ADV7181D's pixel port decoded, its fields into the DDR3 (eight slots, a bank each) |
| `rtl/border.v` | where the fields have picture (the first and last lit pixel pair and line since asked): for the part shown |
| `rtl/deint.v`, `lstream.v` | the motion adaptive deinterlacer (a line when the output wants it); its lines made a 4:4:4 stream, each pixel with its part of the scaler's edge analysis |
| `rtl/smaa.v` | the anti-aliasing: SMAA's edges, searches (15 pixels each way, 8 along the diagonals), area tables and mixing on the 480-line stream (`sim/smaa.py`) |
| `rtl/easu.v` | the scaler: FSR 1's EASU with the kernel from a table by the pixel's place between source pixels (8 x 8 places), the edge's direction (32 bins) and strength (8 levels); the part of the source shown set by a start and a step each way (registers 3A-3D): 55 dB from the shader on a real frame (`sim/fsr.py`) |
| `rtl/ddr3/`, `ddr_arb.v` | the DDR3: our own PHY, calibration and controller (from the fpc console; `pll_init.v` is Sipeed's, Apache 2.0), its port shared by the capture, the picture and the host |
| `rtl/grab.v` | rows of the picture as sent, for the host to read: `tools/grab.py OUT.png` shows the output with no display |
| `gowin/` | the build: `avb.tcl` makes the project, `csr_result.py` hands it the transceivers' register file, `run.tcl` runs it; pins `avb.cst`, clocks `avb.sdc` |
| `tools/avb.py` | the monitor from the host: registers, the four I2C buses, the meters |
| `tools/audio.py` | the audio converter's words and peaks |
| `tools/ddr.py` | the DDR3's calibration state, a write and read test through the monitor |
| `tools/video.py`, `adv.py` | the component input: the ADV7181D's settings (and what was learnt about them), the capture's state, raw samples of the pixel port |
| `tools/hdmi.py`, `clkgen.py`, `edid.py`, `scdc.py`, `linkq.py`, `ddcci.py` | HDMI up; the MS5351M; the sink's EDID, SCDC, error counters, and its own measure of the picture rate |
| `tools/load.sh`, `flash.sh` | a bitstream into the SRAM, or into the SOM's flash, through the XIAO's USB-JTAG bridge |
| `sim/` | testbenches (iverilog, each checks against a model in Python): `tmds_tb.py`, `scr_tb.py`, `pattern_tb.py`, `audio_tb.py` (the data islands decoded), `deint_tb.py [NFIELDS]` (Verilator: the whole picture path with a model of the DDR3, against `model.py`, `smaa.py` and `fsr.py`, pixel for pixel; `aa=T` with the anti-aliasing, `diag` its diagonal patterns, `aadbg` its view of what it finds, `sharp=N` the sharpening, `pic=FILE` a still picture in, `crop=X0,CW,Y0,CH` a part of it shown) |
| `test/loop.v` | a UART loop-back, to test the XIAO's wiring |

The monitor's port: `AVB_TTY` (a serial device, or `tcp:HOST[:PORT]`), else the Wi-Fi link
(`avscaler.local`), else a XIAO's USB serial port.

What the SOM's hard RISC-V core could take over from this logic: [docs/hard-cpu.md](docs/hard-cpu.md).
