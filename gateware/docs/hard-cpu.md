# What the SOM's hard CPU could do instead of FPGA logic

The GW5AST-138 has a hard RISC-V core beside the fabric (Andes A25 "AE350", run at 800 MHz in the
fpc console's design). Since 2026-11-12 the scaler has it (`rtl/cpu.v`, its program in `sw/`): it
runs at 400 MHz beside the picture's path, reaches every register the monitor does, and writes the
on-screen text. The rest is still logic, and what is slow and rare is still done by the ESP32
through a UART (`firmware/xiao-wifi/main/scaler.c`). This note sorts the design's parts by whether
the CPU would do them better; "Where it stands" at the end says what is done.

What it does not change: the paths that are hard to close are every pixel's (the scaler, the
sharpening, the deinterlacer), and those stay logic. The CPU makes the rest quicker to write and to
change (a program is loaded in a second, `tools/cpu.py load`; a bitstream takes 25 minutes).

## The measure

The output is 148.5 million pixels a second. At 800 MHz that is 5.4 CPU clocks a pixel: nothing
that touches every output pixel can be software. The input is 13.5 million pixels a second
(480i/480p): 59 clocks a pixel, still far too few for the deinterlacer (4 fields read, 6
differences, a blend) or SMAA (4 searches). So the picture's path stays logic. What the CPU is good
for is whatever happens once a line, once a field, or once in a while.

## Better on the CPU

| What | Now | On the CPU |
|---|---|---|
| Bring-up and control: MS5351M, SN65DP159, SCDC, ADV7181D, lanes | the ESP32, bit by bit through the monitor's UART (2 s; the board needs the ESP to make a picture) | a few I2C masters in logic or bit-banged GPIO: up in milliseconds, and the board runs without the XIAO. The ESP becomes what it is good at: Wi-Fi and the web page, talking to the CPU. |
| The scaler's kernel table (`rtl/easu.v`: 4608 entries, 55 block RAMs of ROM, fixed for 720x480 to 1440x1080) | made by `sim/fsr.py` at build time | computed by the CPU when the input or output format changes (floating point, a few milliseconds) into a RAM: any ratio (480p, 576i, 720p, 1080i in; 720p, 1440p, 4K out) from one bitstream. The same for SMAA's area table and its reach. |
| Input format detection | none: 480i assumed | read the decoder's STDI measurement and the capture's counters each field, pick the decoder's register set, the capture geometry and the scaler's table; follow a console that switches 480i/480p in a game |
| Film and cadence detection (3:2, 2:2) for the deinterlacer | none: motion adaptive always | the logic gives one number a field (the sum of the field's motion); the CPU looks at the last ten, finds the cadence and tells the deinterlacer to weave the right pair: film material at full resolution without motion artefacts |
| Adaptive settings: motion threshold from the measured noise, sharpening from the picture | fixed numbers from the web page | per-field statistics from the logic (a histogram of the still parts' differences), thresholds set by the CPU |
| HDMI packets: AVI and audio InfoFrames, audio clock regeneration values, later HDR or VRR data | not sent (DVI framing) | the CPU writes each packet's bytes into a small RAM; logic adds the error correction and sends it in the blanking. Packets change with every format: tedious in logic, trivial in C. |
| On-screen display: a menu, the input's format, a setup picture | none (the web page) | the CPU draws into a small overlay (e.g. 480x270, 4 bits a pixel, 65 kbit) that the output stage mixes over the picture; buttons or a controller read by the CPU |
| DDR3 calibration (`rtl/ddr3/ddr3_cal.v`, 600 lines of state machine) | logic, once at start | software stepping the same delays and reading the same compare results: easier to extend (per-lane write levelling, a retry, a report) |
| The debug monitor (`rtl/mon.v`, `rtl/grab.v`) | a register bus on the UART | the same registers on the CPU's bus; the picture read back, statistics, a self test, all in C |

## Not on the CPU

- The deinterlacer, SMAA, the scaler, colour conversion, TMDS coding: every pixel, fixed work, and
  they fit (a tenth of the logic, a tenth of the DSP blocks, 60 % of the block RAM).
- The capture and the DDR3 traffic: every pixel.
- Audio samples: 48,000 a second would be easy for the CPU, but they must go into packets on a
  line's timing; a small state machine does that with no jitter. The CPU sets it up.

## What it costs

- The core needs Gowin's AE350 SoC wrapper, a boot path (the SOM's SPI flash, or the DDR3 loaded
  by a ROM loader) and the Andes/RISC-V toolchain: the fpc console design already has all three
  (`fpc/console`: `riscv_ae350_config.v`, its boot ROM and software build), so this is a port, not
  new ground.
- The CPU and the picture's path would share the DDR3: one more user on `rtl/ddr_arb.v`.
- A second thing to build and version (firmware in the bitstream or the flash).

## Suggested order

1. Control on the CPU (bring-up, format detection, settings): the board stands alone, and every
   later feature has somewhere to live.
2. The scaler's table in RAM, written by the CPU: all the input formats and other output sizes.
3. HDMI packets: InfoFrames, then audio.
4. Cadence detection and adaptive thresholds.
5. The on-screen display.

## Where it stands (2026-11-12)

- The core runs (`rtl/cpu.v`): the fpc console's configuration, the core clock 400 MHz from
  PLL_R[0]'s CLKOUT1 (the system clock's PLL, placed there), the buses on the system's 50 MHz. Its
  program is 32 KB of block RAM at 0x80000000, the bitstream's `sw/build/cpu.hex` in it; the
  register bus can write it. Its data is the core's own DLM. No operating system: a loop
  (`sw/main.c`), and waits that keep answering the link.
- The register bus at 0xE8000000 + 4 x the register: the CPU takes a turn between the monitor's
  words (`sim/cpu_tb.py`).
- **The CPU runs the scaler** (`sw/board.c`: item 1 above): the bring-up (the clock chip, the
  redriver, the display's SCDC, the lanes, the decoder: 0.8 s, the link took 2), the settings into
  the registers, each second's looking after (the part shown, the sampling phase and its tuning,
  what comes in and goes out). The settings are the CPU's; the link keeps a copy for when the
  power is off and gives it to a CPU that has just begun.
- **The link talks to it over SPI** (`rtl/spis.v`, `sw/link.h`, `firmware/xiao-wifi/main/link.c`):
  a request, an answer: what the scaler does, the settings (all, or one), a command (again, find
  the border, tune, a host tool has it), pixels of the picture as it goes out (a screen capture:
  480 x 270 in 2 s; it was 7 through the monitor). The same port reaches the registers with no
  program on the other side: so the link loads the CPU's program (its own copy, built into the
  firmware, if the one that runs is older or does not answer): a new CPU program is a firmware
  update, no bitstream.
- The on-screen text (`rtl/osd.v`, `sw/osd.c`).
- With an FPGA image that has no CPU (the SOM's flash, until it is written again) the link does
  it all itself as before (`scaler.c`: it asks the SPI port for the ID register first).
- A host tool on the monitor (`tools/*.py`): the link tells the CPU, which leaves the scaler alone
  meanwhile; `tools/cpu.py load` puts a program in from the host.
- Cost: 25 block RAMs (75 % used now), some 800 LUTs, the system clock's Fmax 75 -> 58 MHz (50
  needed).
- **The frame lock** (`sw/board.c` board_lock()): ten times a second the clock chip's frequency
  trimmed (0.028 ppm a step, 300 ppm at most) so that a frame is begun a set time after a field's
  end (the scaler's LAT register). On the board: in step within 10 us, the clock at -57 ppm, the
  delay 16.8 ms all the time.
- **The picture begun before the field is all in** (`rtl/deint.v` ll, `rtl/cap_ddr.v` prog): a
  frame is made from the field coming in when enough of its lines are in the memory; the lock then
  holds the frame's start 21 lines into the field (half the part shown's first line, and 14).
  On the board: 2.0 ms from a line captured to it shown.
- Not yet: the CPU's own UART has no pins; the settings are not kept on the FPGA's side (no
  flash of its own: with no XIAO the CPU starts with its defaults).
