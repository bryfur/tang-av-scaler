# Gateware: the scaler

The FPGA design for the AV board rev C-B (Tang Mega 138K SOM, GW5AST-LV138PG484AC1/I0 version C):
the picture's path from the component input to HDMI out of the FPGA's transceivers, the SOM's hard
CPU that runs it, and a register monitor on the XIAO's UART for development. `rtl/top.v` lists the
registers. What it all adds up to: [../README.md](../README.md).

State on the board (2026-11-12):

| | |
|---|---|
| Component in, HDMI out | 480i YPbPr -> 1080p60 (59.94 Hz), in colour: the fields kept in the SOM's DDR3, deinterlaced motion adaptive to 720 x 480 from the last four (weave where nothing moves, the lines' mean where something does), made quieter where the picture is still (a sample's mean with the same one a frame before), anti-aliased (SMAA 1x, the orthogonal and the diagonal patterns, corners kept, the edges held from frame to frame against the picture's noise: `rtl/smaa_hist.v`; a view of what it finds in the picture's place), scaled to 1440 x 1080 (4:3) by FSR 1: its edge adaptive upsampling (EASU), table driven, and its sharpening (RCAS, on luma; less where a pixel is noise: its denoise term). The part scaled is all of the 720 x 480 or less: the black round a game's picture is measured (`rtl/border.v`) and left out, so the picture fills the 4:3. No tear: a frame is made of one field's lines and the ones before it. The output is kept in step with the input (the CPU trims the clock chip: no field repeated or dropped), and a frame can be made from the field still coming in: 2 ms from a line captured to it shown (16.8 ms with whole fields). 480p, 720p, 1080i: decoder settings not found yet. |
| HDMI out | 1080p60 and 2160p30 clean on the sink's own counters (SN65DP159 as a redriver: as a retimer it corrupts 2.97 Gb/s). 2160p60: the link is clean and the sink sees scrambling, no picture yet. |
| Audio | the PCM1808's clocks and samples (`rtl/audio_in.v`: alive on the board, `tools/audio.py`), and HDMI's data islands for them (`rtl/hdmi_audio.v`: samples, N/CTS, audio and AVI InfoFrames; decoded and checked in simulation, `sim/audio_tb.py`). On a display and a capture dongle: the sound is there (HDMI register bit 2, the web page's "sound over HDMI"). fs is 48 kHz (the clock chip's third output, 512 fs: `sw/board.c`). With the web page's "Surround 5.1" the CPU makes six channels of the two (`sw/surround.c`) and they go out as 5.1 PCM: running on the board, not yet heard through a receiver. |

## Build, load, run

    (cd sw && make)                          # the hard CPU's program (the bitstream takes sw/build/cpu.hex)
    GW_MODE=1080p60 GW_OUT=$PWD/gowin/build/vid gowin/build.sh    # Gowin 1.9.12 in fpc's fpga-tools container
    tools/video.py --load                    # load it (USB JTAG), HDMI up, the decoder set, the input shown
    tools/hdmi.py --load gowin/build/hdmi/avb/impl/pnr/avb.fs     # the test picture alone

    tools/flash.sh <GW_OUT>/avb/impl/pnr/avb.fs     # into the SOM's flash: the board starts by itself

A build is the same build every time: its number (register 01) is not the time it was made but
`gowin/build.stamp`'s, which belongs to the logic's sources by their checksum, with the place and
route options that close the timing for them. (The number is a constant in the logic: with
another one the synthesis gives another netlist and the place and route another result. With the
build's time for it, a design that had closed missed its clocks a minute later; with the same
number the result is the same to the last digit, on either build machine.) A new CPU program
alone changes nothing. After a change to the logic: build the pairs GW_PLACE, GW_ROUTE = (2, 1),
(2, 2), (3, 1), (3, 2) (four at once on each machine), with GW_BUILD a second on for more tries
if none closes, and copy the closing build's `build.stamp` (in its GW_OUT) to `gowin/`.

With the bitstream in the flash and the Wi-Fi link's firmware in the XIAO (`firmware/xiao-wifi`),
the board needs power, a source and a display, and nothing else: the FPGA loads from the flash
(some 20 s), its CPU brings the clock chip, the HDMI redriver, the decoder and the lanes up (under
a second) and the link gives it the settings. The scripts below are for development; the CPU
leaves the scaler alone while one of them is on the link's console port.

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
| `rtl/audio_in.v`, `hdmi_audio.v` | the audio converter's clocks and I2S words; HDMI's data islands: a packet in each line's back porch (two channels, or six: 5.1) |
| `rtl/audio_fifo.v`, `sw/audio.c`, `sw/surround.c` | the sound through the CPU: the converter's pairs wait for it, it makes each six channels (a matrix decoder for Pro Logic II mixes, our own: `sim/surround_test.py` measures it), they wait for their sample time |
| `rtl/gtx_quad.v` | the transceiver quad (generated: `tools/mkgtx.py`); its register file by `gowin/serdes.py`, no IDE |
| `rtl/vcap.v`, `cap_ddr.v` | the ADV7181D's pixel port decoded, its fields into the DDR3 (eight slots, a bank each) |
| `rtl/cpu.v`, `sw/` | the SOM's hard CPU (an Andes A25, Gowin's RiscV_AE350_SOC from the IDE's own files) and its program, which runs the scaler: the bring-up, the settings, each second's looking after, the on-screen text ([docs/hard-cpu.md](docs/hard-cpu.md)); it reaches the registers at 0xE8000000 + 4 x the register. `cd sw && make` (on fpga) before a bitstream; the link's firmware carries a copy and gives the CPU the newer; `tools/cpu.py load` puts one in from a host |
| `rtl/spis.v` | the XIAO's SPI port: the registers (no program needed: the CPU's program is loaded through it), and requests and answers between the link and the CPU's program (`sw/link.h`) |
| `rtl/osd.v` | the on-screen text: 8 lines of 48 characters over the picture (the CPU's program writes them: what comes in and goes out, what is done to the picture, the delay, the chip's temperature); its font `rtl/osd_font.hex` (`tools/mkfont.py`) |
| `rtl/border.v` | where the fields have picture (the first and last lit pixel pair and line since asked): for the part shown |
| `rtl/focus.v` | how sharp a field is across its lines: for the decoder's sampling phase (`tools/video.py phase sweep`) |
| `rtl/deint.v`, `lstream.v` | the deinterlacer (a line when the output wants it): the fields' rows read from the DDR3 into line buffers, then passes through them a pixel pair a clock: motion adaptive; along edges (`edi`); motion compensated (`mc`: a vector for each block of 8 pixels, estimated line by line: `sim/model.py` `me_line()` is the same bit for bit); the lines above the part shown are not made (`skip`). Its lines made a 4:4:4 stream, each pixel with its part of the scaler's edge analysis A view of the vectors (`mvdbg`, DEINT bit 20): the picture grey, each block's chroma its vector (Cb 128 + 4 dx, Cr 128 + 16 dyr). |
| `rtl/deint_edi.v` | the deinterlacer's edge search: 16 directions a pixel, four lines, its guards (`sim/model.py` `edge_line()`; `sim/edi_tb.py` tests the source and, with `synth`, what the synthesis makes of it) |
| `rtl/sflash.v`, `sw/store.c`, `tools/sflash.py` | the SOM's configuration flash as the board's own storage, from 0x800000: the settings, the tables and the network's weights kept there by the CPU's program; the port makes the flash's commands itself and writes nowhere below 0x800000 ([docs/storage.md](docs/storage.md)); registers 68-6A |
| `rtl/bram.v` | memories put into block RAM by hand: 512 x 32 in one block (the tools would use two), and one read at two places at once |
| `sw/pan.c` | the picture's pan, from six rows of two fields read through the CPU's port to the DDR3: a candidate for the blocks' vectors and what a frame begins with; and where a frame's lines begin |
| `rtl/smaa.v` | the anti-aliasing: SMAA's edges, searches (15 pixels each way, 8 along the diagonals), area tables and mixing on the 480-line stream (`sim/smaa.py`) |
| `rtl/easu.v` | the scaler: FSR 1's EASU with the kernel from a table by the pixel's place between source pixels (8 x 8 places), the edge's direction (32 bins) and strength (8 levels); the part of the source shown set by a start and a step each way (registers 3A-3D): 55 dB from the shader on a real frame (`sim/fsr.py`). The table is a RAM: built with FSR's kernel, and another can be put there while the picture runs (registers 58, 59, 5C-5F) |
| `rtl/cnn.v`, `rtl/bicu.v`, `tools/net.py` | a small network as the scaler's first stage, in `easu.v`'s place when the setting says so: the luma made twice the size by three layers of 3 x 3 (192 multipliers, six products each a source pixel; the weights in LUT RAM, changeable while the picture runs), then a bicubic stretch to the output; the chroma straight from the source ([docs/cnn-upscaler.md](docs/cnn-upscaler.md); what is on the board now, the weights and the checks: [docs/neural-pipeline.md](docs/neural-pipeline.md)); registers 44-47 |
| `sw/table.c`, `tables/`, `tools/table.py` | the scaler's tables: the CPU keeps several in the DDR3 and puts the one the setting asks for into the scaler (0.2 s, the picture running; read back and compared); two learnt ones come with the link's firmware, more can be sent to the board ([tables/README.md](tables/README.md)) |
| `rtl/ddr3/`, `ddr_arb.v` | the DDR3: our own PHY, calibration and controller (from the fpc console; `pll_init.v` is Sipeed's, Apache 2.0), its port shared by the capture, the picture, the host and the CPU; a register each way at the pins' side (`ddr3_dp.v`: the pins are at the chip's edge, what uses the memory is not); `sim/ddr3_tb.py` runs it on a model of the chips that checks protocol and timing (`sim/ddr3/`) |
| `rtl/cpu_ddr.v` | the CPU's data memory port on the DDR3: all 1 GB at address 0, a line kept for reads, writes gathered (`sim/cpu_ddr_tb.py`); `sw/mem.c` tests it at start |
| `rtl/grab.v` | rows of the picture as sent, for the host to read: `tools/grab.py OUT.png` shows the output with no display |
| `tools/still.py` | stills of one frozen frame for comparing: the 480i fields as the console sent them (out of the DDR3), woven; that stretched to 1080p the plain way; the scaler's 1080p, every pixel as sent; and parts of the two side by side |
| `gowin/` | the build: `avb.tcl` makes the project, `csr_result.py` hands it the transceivers' register file, `run.tcl` runs it; pins `avb.cst`, clocks `avb.sdc` |
| `tools/avb.py` | the monitor from the host: registers, the four I2C buses, the meters |
| `tools/audio.py` | the audio converter's words and peaks |
| `tools/ddr.py` | the DDR3's calibration state, a write and read test through the monitor |
| `tools/video.py`, `adv.py` | the component input: the ADV7181D's settings (and what was learnt about them), the capture's state, raw samples of the pixel port |
| `tools/hdmi.py`, `clkgen.py`, `edid.py`, `scdc.py`, `linkq.py`, `ddcci.py` | HDMI up; the MS5351M; the sink's EDID, SCDC, error counters, and its own measure of the picture rate |
| `tools/load.sh`, `flash.sh` | a bitstream into the SRAM, or into the SOM's flash, through the XIAO's USB-JTAG bridge |
| `sim/` | testbenches (iverilog, each checks against a model in Python): `tmds_tb.py`, `scr_tb.py`, `pattern_tb.py`, `audio_tb.py` (the data islands decoded), `osd_tb.py` (the on-screen text), `cpu_tb.py` (the CPU's turn on the register bus beside the monitor's), `cpu_ddr_tb.py` (its data memory port), `ddr3_tb.py` (the DDR3 controller on a model of the chips), `audio_fifo_tb.py`, `surround_test.py` (the surround decoder on a PC: what comes out of each channel), `deint_tb.py [NFIELDS]` (Verilator: the whole picture path with a model of the DDR3, against `model.py`, `smaa.py` and `fsr.py`, pixel for pixel; `aa=T` with the anti-aliasing, `diag` its diagonal patterns, `aadbg` its view of what it finds, `sharp=N` the sharpening, `pic=FILE` a still picture in, `crop=X0,CW,Y0,CH` a part of it shown, `nr=N` the noise reduction, `dn` the sharpening's, `noise=A` noise added to the fields) |
| `test/loop.v` | a UART loop-back, to test the XIAO's wiring |

The monitor's port: `AVB_TTY` (a serial device, or `tcp:HOST[:PORT]`), else the Wi-Fi link
(`avscaler.local`), else a XIAO's USB serial port.

What the SOM's hard RISC-V core could take over from this logic: [docs/hard-cpu.md](docs/hard-cpu.md).
