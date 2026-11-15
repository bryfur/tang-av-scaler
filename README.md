# tang-av-scaler

An FPGA video scaler for the sixth generation of game consoles (PlayStation 2, Xbox, GameCube):
480i component video and stereo sound in, 1080p60 HDMI out, about 2 ms behind the console. A Sipeed
Tang Mega 138K SOM (Gowin GW5AST-138) on a carrier board of its own, with a Seeed XIAO ESP32-C5 for
Wi-Fi. The board, the FPGA design, the software for the FPGA's CPU and the ESP32's firmware are all
here.

```
console: component video (YPbPr, 480i) + stereo audio
  -> ADV7181D decoder, PCM1808 audio converter
  -> GW5AST-138 FPGA
       fields into DDR3 -> motion adaptive / compensated deinterlace + noise reduction -> SMAA
       -> upscale: a small neural network (x 2) + bicubic, or FSR 1's EASU from a table
       -> FSR 1 sharpen (RCAS) -> on-screen text -> HDMI coding
       its hard RISC-V CPU: bring-up, settings, frame lock, on-screen text
  -> the FPGA's transceivers -> SN65DP159 -> HDMI 1080p60 with sound
  XIAO ESP32-C5: Wi-Fi, web page, updates, JTAG; talks to the CPU over SPI
```

Status (2026-11-14): the board (rev C-B) is built and runs a console's picture and sound to a
display and a capture device. The table below is what it does now, on the board. New since
2026-11-12: motion compensated deinterlacing with vectors found in the FPGA, a small neural network as the upscaler's first stage, scaler tables learnt from games and
changeable while the picture runs, and SMAA that holds its edges from frame to frame
([the path with the network, as deployed](gateware/docs/neural-pipeline.md)). The console it
has been run with is a PlayStation 2; an Xbox or a GameCube with its component cable puts out the
same signal (480i, YPbPr, 59.94 Hz) and has not been tried yet.

<p>
<img src="hardware/av-board/rev-cb/img/av-board-cb-3d.png" width="49%" alt="The board, rev C-B, rendered from its design">
<img src="hardware/av-board/rev-cb/img/av-board-cb-top.png" width="49%" alt="The same from above">
</p>

![The board, rev C-B](hardware/av-board/rev-cb/img/av-board-cb-photo.jpg)

The board, rev C-B ([hardware/av-board/](hardware/av-board/README.md)), as designed (rendered, and from above) and as built:
the SOM under its heat sink, the XIAO and its antenna at the right; along the back edge the HDMI
output, the two audio jacks, power (USB-C) and the three component video jacks.

![A frame of the scaler's 1080p output, its on-screen display on](docs/compare/game-osd.png)

A frame as it leaves for the display, the on-screen display on (read back from the FPGA: no camera,
no capture device).

![Tales of the Abyss, one frozen frame: the plain way and the scaler's, two seconds each](docs/compare/abyss-swap.png)

Tales of the Abyss, one frozen frame, shown two ways in turn (two seconds each): the console's 480i
stretched the plain way, then the scaler's output; the corner says which.
[Drag a line between them yourself](https://bryfur.github.io/tang-av-scaler/compare/?frame=abyss).

## What it does

| | |
|---|---|
| Input | 480i component (YPbPr) through an ADV7181D, sampled line-locked at 13.5 MHz; stereo analogue audio through a PCM1808. The decoder's sampling phase can be set, or tuned to the console's pixels (every phase tried on a still picture, the sharpest kept). |
| Deinterlacing | Motion adaptive from the last four fields, kept in the SOM's DDR3: a field's lines as they are, the lines between from the field before where nothing moves and from their neighbours where something does. One more step can be switched on. Motion compensated: each block of 8 pixels of each line has its own motion vector, found in the FPGA line by line (six candidates a block, scored against the field two before); where the picture moves that way the line between is the field before's, moved, so a pan or a moving object keeps its full detail. Bob and weave can be chosen instead. The vectors can be shown in the picture's place (each block tinted by how it moves) to see what the motion compensation found. |
| Noise | Where the picture is still, each sample is averaged with the same one a frame earlier (off, or three strengths). |
| Anti-aliasing | SMAA 1x on the 480-line picture: luma edges, the orthogonal and the diagonal patterns, corners kept; the edges of the frame before are kept in memory and held to, so a still picture's edges do not shimmer with its noise. A view that paints what it finds (edges, blends) in the picture's place, for tuning. |
| Scaling | FSR 1's edge adaptive upsampling (EASU) to 1440 x 1080 (4:3) or 1920 x 1080 (16:9, for a game's widescreen mode). Any part of the source can be shown: the black border round a game's picture is measured and left out, so the picture fills the screen (or the part is set by hand). In its place a small neural network can make the picture twice the size first, with a plain bicubic stretch after it: three layers, under 1 kB of weights, 192 multipliers, trained on eleven games against the same frames rendered at 8 x; +0.54 dB over a bicubic stretch on games it never saw ([as deployed](gateware/docs/neural-pipeline.md), [the research](gateware/docs/cnn-upscaler.md)). Its weights can be changed while the picture runs. The kernel comes from a table that can be changed while the picture runs: FSR's own, a pair learnt from a game's pictures, or one you send to the board ([gateware/tables](gateware/tables/README.md)). |
| Sharpening | FSR 1's RCAS on luma, in 16 steps, with its noise term (less where a pixel is noise rather than detail). |
| Timing | The output's frames are kept in step with the input's fields (the CPU trims the clock generator: within 10 us, no field shown twice or left out). A frame is made from the field that is still coming in: about 2 ms from a line captured to it sent (2.4 ms with the network; 16.8 ms with whole fields). |
| Output | 1080p60 (59.94 Hz) HDMI from the FPGA's own transceivers; the console's sound as HDMI audio (two channels of L-PCM at 48 kHz, its clock from the PLL the pixel clock comes from); AVI and audio InfoFrames. Runs a display, a capture device and an AV receiver (picture and sound). |
| On screen | An on-screen display: what comes in and goes out, what is done to the picture, the delay, the lock, the FPGA's temperature. |
| Storage | The board keeps its own settings, scaler tables and network weights, in the upper half of the SOM's configuration flash: it starts as it was left, with or without the XIAO ([gateware/docs/storage.md](gateware/docs/storage.md)). The design can write only above the bitstream. |
| Standby | The board's first button held a second, or the page: the FPGA is halted (its configuration taken away over JTAG by the XIAO and the chip left waiting), so nothing in it runs. The RECONFIG button or the page loads it again: a picture some 25 s later, as it was left. There is no switch in the board's supply: the SOM's and the other chips' standing current stays. |
| Control | A web page on the XIAO: every setting (applied as it is changed, kept across power cycles), status, a screen capture of the output read back from the FPGA, firmware update over Wi-Fi. |

## What it looks like

Two frozen frames, each in and out: Killzone (PS2, its widescreen mode) and Tales of the Abyss
(PS2, 4:3). "The plain way" is the
two 480i fields as the console sent them, woven into a frame and stretched to 1080p (bilinear),
which is about what a simple scaler or a display does. "The scaler" is its 1080p output (motion
adaptive deinterlacing, noise reduction medium, SMAA with diagonals and corners at edge threshold
12, FSR 1 with sharpening 8/16). Nothing went through a camera or a capture device: the fields are
read out of the FPGA's memory and the output is read back from its last stage, pixel for pixel
(`gateware/tools/still.py`).

![The gun: the plain way and the scaler's, three times the size](docs/compare/gun.png)

**[Drag to compare](https://bryfur.github.io/tang-av-scaler/compare/)**: both frames on a page with a
line to drag between the plain picture and the scaler's, at any size up to four screen pixels a
pixel (`docs/compare/index.html`).

The pictures themselves, in [`docs/compare/`](docs/compare/):

- Whole frames, 1920 x 1080. Killzone: [the plain way](docs/compare/game-plain.png),
  [the scaler](docs/compare/game-scaler.png), [a half of each](docs/compare/game-split.png).
  Tales of the Abyss: [the plain way](docs/compare/abyss-plain.png),
  [the scaler](docs/compare/abyss-scaler.png), [a half of each](docs/compare/abyss-split.png).
- The frames as they came, the fields woven and nothing else (720 x 480):
  [Killzone](docs/compare/game-480i.png), [Tales of the Abyss](docs/compare/abyss-480i.png).
- Parts of Killzone side by side, three times the size: [the tower and its guy wires](docs/compare/tower.png),
  [palms](docs/compare/palms.png), [hanging foliage](docs/compare/foliage.png),
  [HUD text](docs/compare/hud-text.png), [the ammunition counter](docs/compare/ammo.png).

## How it is put together

- **The picture's path is logic** (`gateware/rtl/`): every pixel, at 148.5 MHz out. Each block has a
  model in Python (`gateware/sim/`) and the whole path is simulated against them pixel for pixel:
  the deinterlacer, SMAA, the scaler and the sharpening give exactly the models' pictures.
- **Everything else runs on the FPGA's hard CPU** (an Andes A25 RISC-V in the GW5AST, `gateware/sw/`,
  no operating system): it brings the board's chips up, holds the settings, finds the picture's
  border, tunes the sampling phase, keeps the output in step with the input, writes the on-screen
  text. A new program is loaded in a second, with no new bitstream. It runs at 800 MHz and has the
  SOM's 1 GB of DDR3 as its memory, beside the picture's fields.
- **The sound** goes out over HDMI as it comes in, 48 kHz stereo; or, when switched on, through
  the CPU: a matrix decoder of our own (`gateware/sw/surround.c`) makes five channels of a game's
  Pro Logic II mix, sent as 5.1 PCM.
- **The XIAO ESP32-C5** (`firmware/xiao-wifi/`) is the way in: Wi-Fi, the web page, updates, and
  JTAG to load bitstreams. It talks to the CPU over SPI in small messages and carries the CPU's
  program. What must outlast the power (settings, tables, weights) the board keeps itself, in the
  SOM's flash; the XIAO passes changes on and holds a copy.

The design uses 34 % of the FPGA's logic, 76 % of its block RAM and 54 % of its multipliers (the
network's 192 are most of those).

## Measured on the board

| | |
|---|---|
| Delay | 2.0 ms at the top of the picture (some 2.5 ms at the bottom, by the two scan rates) with the picture made from the field coming in; 2.4 ms with the network as the upscaler; 16.8 ms with whole fields. From the FPGA's own timing of a frame's start against the field; not yet measured from outside, and a display adds its own. |
| Frame lock | within 10 us of its mark, the clock trimmed by some -57 ppm (this console against this board); in step some 20 s after starting 5 ms off |
| Still edges | on a still picture SMAA's edge decisions changed on 4.4 % of edge pixels from frame to frame (143 pixels a frame moved by 6 levels or more); with the edges kept, none (about 10 pixels a frame, the noise's own). The model on the board's own fields; the board's output is the model's pixel for pixel. |
| Noise | the spread in a frozen frame's flat areas: 2.32 as it comes, 1.98 with the noise reduction; sharpened fully 3.94, with the sharpening's noise term 3.12, with both 2.61 |
| Sampling phase | 4.5 % between the sharpest and the least sharp phase on Killzone (its picture is soft to begin with) |
| Screen capture | 480 x 270 in 2 s, 960 x 540 in 6 s over the web page |

## What is not done

- Consoles other than the PlayStation 2 have not been tried. The Xbox and the GameCube put out the
  same 480i over their component cables; the Dreamcast has no component output (its VGA and RGB
  would come in at the board's inputs that are not used yet).
- Inputs: 480i is the one in use; 720p goes out as it came, 720p; 480p is taken as the progressive
  picture it is and scaled like the rest, but only in simulation so far (not yet tried from a
  console); 576i and 1080i need the decoder's settings and the capture's timing for each.
- The network: one shape is built; how it does in motion is not measured.
- With the kernel scaler (not the network), low latency, a part of the picture shown and motion
  compensation all at once, a frame's first lines are made with no time to spare: in simulation its
  first one or two rows can come from lines not yet there. The network's path begins a frame's
  lines early and has the room; the kernel's wants the same. The
  edges SMAA keeps are held by screen position, so they steady a still picture, not edges that
  move across it.
- The surround decoding runs on the board (the CPU keeps up, nothing lost), but has not been
  heard through a receiver yet: off unless switched on.
- 4K output: a 2160p30 test picture is clean on a display; at 2160p60 the link runs and the display
  sees scrambling but shows nothing; the scaler's own path ends at 1080p.
- The board's other inputs (S/PDIF, VGA, RGB with SCART sync) are wired but not used.
- Without the XIAO the board starts as it was left (its settings, tables and weights are in its own
  flash), but nothing can be changed: the page is the only control in use.
- At power-on the FPGA loads its image twice, some 20 s more before there is a picture: configured
  before the clock generator runs, one transceiver lane's clock comes up wrong and the lanes'
  resets do not clear it; the XIAO sees that and has the FPGA load again. The right reset is not
  found yet.
- A bitstream into the FPGA's SRAM over Wi-Fi (`avx.py load`) goes in, and the XIAO then restarts
  with the FPGA left unloaded; over USB it works (`gateware/tools/load.sh`).
- The delay has not been measured through a display with a camera or a light sensor.

## The repository

| Directory | What |
|---|---|
| [`hardware/av-board/`](hardware/av-board/README.md) | The board, rev C-B: generated with KiCad's Python API from `rev-cb/board.py`, every circuit from its part's reference design and reviewed against the data sheets; fab files for JLCPCB. Earlier designs that were not built are in `older/`. |
| [`gateware/`](gateware/README.md) | The FPGA design: `rtl/` the logic, `sw/` the CPU's program, `sim/` the models and testbenches, `gowin/` the build, `tools/` the host's scripts (registers, loading, stills), `docs/` notes. |
| [`firmware/xiao-wifi/`](firmware/xiao-wifi/README.md) | The XIAO ESP32-C5's firmware: Wi-Fi, the web page, updates, a JTAG server, the link to the FPGA's CPU. (`firmware/xiao/` is an earlier USB-only bridge for an ESP32-S3.) |

Building and loading: [gateware/README.md](gateware/README.md) (the bitstream and the CPU's
program: Gowin's tools, a RISC-V GCC) and [firmware/xiao-wifi/README.md](firmware/xiao-wifi/README.md)
(ESP-IDF). With the bitstream in the SOM's flash and the firmware in the XIAO, the board needs
power, a console and a display.

## Reference documents

`hardware/av-board/refs/` (not in git: the vendors' copyright) holds the data sheets and user
guides the circuits follow; [hardware/av-board/README.md](hardware/av-board/README.md) lists which
and where each came from. The scaler's algorithms: SMAA (Jimenez et al.) and AMD's FidelityFX Super
Resolution 1 (EASU and RCAS, MIT licence), both written again for this hardware
(`gateware/sim/smaa.py`, `gateware/sim/fsr.py` say how they differ).
