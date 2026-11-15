# The picture's path with the network, as it runs on the board

What is in the board's flash and running on 2026-11-15: the build, the stages a pixel goes through
with the network as the scaler's first stage, the weights and where they live, how to change them,
and how all of it is checked. The research behind the network (what was tried, what it gains, the
arithmetic in full) is in [cnn-upscaler.md](cnn-upscaler.md); this note is the deployed state.

## What is deployed

| | |
|---|---|
| Bitstream | build 1794698353 (`gowin/build.stamp`: place 3, route 1), in the SOM's flash since 2026-11-15: the FPGA starts with it by itself, and with what the board keeps beside it in the same flash |
| Timing | system clock 65.3 MHz (wanted 50), output clock 157.5 MHz (148.5), memory's user clock 101.4 MHz (100); ten of ten builds of these sources meet their timing |
| Size | logic 34 %, registers 35 %, block RAM 258 of 340 (76 %), multiplier blocks 159 of 298 (54 %) of the GW5AST-138 |
| Network | `t8s` shape: three layers of 3 x 3, 1 -> 8 -> 8 -> 4 channels, luma only, 720 x 480 to 1440 x 960 |
| Weights at power-on | the ones the board keeps in its flash ([storage.md](storage.md)): `t8s-s10k3` (refitted for the anti-aliasing with its edges kept), given once by `tools/net.py load`. A board that keeps none has the bitstream's own, `sim/cnn/t8s.json` |
| Scaler tables | kept by the board in its flash: `learnt-11games` and `learnt-11games-aa12` (the pair the link's firmware carries) and `learnt-11games-aa10k3` in slot 3. Not used while the network is on |
| Settings it runs with | network on, SMAA on (diagonals, corners, edges kept: keep 3), noise reduction 2, sharpening 8, low latency and frame lock on |

## The path

```
console, 480i YPbPr
  -> ADV7181D, 13.5 MHz line-locked                                   [decoder's clock]
  -> vcap.v, cap_ddr.v: fields into the DDR3 (eight kept)
  -> deint.v: 720 x 480 progressive from the last four fields         [memory's clock, 100 MHz]
       motion adaptive; motion compensated by a vector a block
       noise reduction where the picture is still
  -> lstream.v: whole lines in order
  -> smaa.v + smaa_hist.v: SMAA 1x, the edges of the frame before kept in the DDR3
  -> 4:4:4, into a ring of eight lines                                [crossing to the output's clock]
  -> cnn.v: luma x 2 by the network (1440 x 960)                      [output's clock, 148.5 MHz]
     bicu.v: bicubic stretch to 1440 x 1080 (or 1920 x 1080); chroma from the source
       (network off: easu.v, the table's kernel, does this step alone)
  -> rcas.v: sharpening on luma, then R'G'B'
  -> osd.v, HDMI coding, the transceivers -> SN65DP159 -> HDMI 1080p60
```

Everything before the ring works on the 720 x 480 picture at the source's size. The network sits
after SMAA because that is what it was trained on: SMAA takes the stair steps out, the network puts
detail back at twice the size.

The delay with the network on and the picture made from the field still coming in: 2.4 ms from a
line captured to it sent (the board's own measure; 2.0 ms with the kernel).

## The network stage

`rtl/cnn.v`, on the output's clock, a source line at a time (a pass):

- **A pass** makes two lines of the picture at twice the size from five source lines, read from the
  same ring `easu.v` uses. A source pixel takes six clocks, so a pass is (720 + 12) x 6 = 4,392
  clocks; a full 480-line picture wants a pass every 4,950 (1080 rows of 2,200 clocks).
- **Multipliers.** 192 of 9 x 8 bits, each doing six products a source pixel: 1,080 multiply-adds a
  pixel. The network itself is 936; the rest is layer 1 computed three times over (for the three
  lines layer 2 looks at) rather than kept in block RAM.
- **Lines kept.** Layer 2's last two lines, eight channels each: eight block RAMs. The source's
  lines are the ring's; layer 1 keeps none.
- **The arithmetic** is whole numbers throughout and is `sim/cnn_ref.py`'s: a layer's sum is the
  products plus a bias, shifted and limited to 0 to 255; the last layer's four channels are the
  2 x 2 output pixels of a source pixel in sixteenths of a level, added to a plain two-tap stretch
  of the source.

`rtl/bicu.v` takes the picture at twice the size from its own ring of eight lines to the output: a
bicubic kernel (a = -0.75, 32 places a pixel), down first and then across. Chroma does not go
through the network: it is taken from the source by its four nearest. The crop and the widescreen
setting work as with the kernel.

A frame's first rows want their lines sooner than `easu.v` does, so the lines' side begins the next
frame before the one shown is over. Register 47 counts output rows begun before their lines were
made, while the network is shown: none in steady running (it counts a few hundred while the board
starts or a setting is changed).

## The weights

| | |
|---|---|
| Parameters | 959: 936 weights, 20 biases, 3 shifts |
| A weight | 8 bits signed (the largest in `t8s` is 109, in `t8s-s10k3` 122) |
| A bias | 22 bits signed, with half of what the shift drops added in |
| Size | 936 bytes of weights and 55 of biases: just under 1 kB. The model file is 8 to 10 kB of JSON |
| In the FPGA | LUT RAM beside each multiplier (its six weights, a byte each); 983 values through the register port (24 are the unused phases of layer 1's second multipliers) |
| Trained on | eleven PlayStation 2 games: a frame as the capture path would deliver it, after SMAA, against the same frame rendered at 8 x |
| Gain | +0.54 dB luma PSNR over a bicubic stretch of the same input, on four games never trained on |

Two sets exist, of the same shape:

- `t8s.json`: trained on SMAA at threshold 12 without the edges kept. In the bitstream.
- `t8s-s10k3.json`: trained on SMAA at threshold 10 with the edges kept (keep 3), the games'
  frames run through it in order. It scores the same +0.54 dB on its own input; it keeps the
  weights matched to what the board now feeds the network.

To put another set of this shape in while the picture runs:

    tools/net.py load sim/cnn/t8s-s10k3.json      # or t8s.json, t8.json
    tools/net.py status

With a design that has the board's own storage ([storage.md](storage.md)) `net.py load` gives the
weights to the board's CPU, which puts them in and keeps them in the SOM's flash: they are there at
every start (`net.py try`: not kept; `net.py drop`: back to the bitstream's own). Another shape
(`f16s`: 16 channels, 5 x 5 first) is another build.

## The settings that matter to it

| Setting (web page) | |
|---|---|
| `net` (Upscaler: Kernel / Network) | 1: the network and the bicubic stretch; 0: `easu.v` and its table |
| `aa`, `aa_thr`, `aa_diag`, `aa_corner` | SMAA before the network: the weights were trained with it on, diagonals and corners on |
| `aa_keep` (Steady edges) | how firmly the edges of the frame before are kept (0 off, to 7; 3 as deployed): stops a still picture's edges changing with its noise |
| `sharp` | the sharpening after it still follows its setting; it was not part of the training, so it is a matter of taste (0 turns it off) |
| `table` | the kernel's table: only with the network off |

## How it is checked

- **The network alone**: `sim/cnn_tb.py` runs `cnn.v` on the four test pictures of a model
  (`sim/cnn/vec/`) and compares every pixel with the trainer's own output; `cnn_tb.py synth` does
  the same with the synthesized netlist.
- **The whole path**: `sim/deint_tb.py ... net[=MODEL.json] [keep=N]` puts fields through the
  capture, the deinterlacer, SMAA, the network, the stretch and the sharpening and compares the
  frame with `sim/model.py`: the same on every pixel, with crops, widescreen, 480p, low latency,
  motion compensation, and the edges kept.
- **The board**: `tools/boardcheck.py` freezes the picture, reads the fields and SMAA's kept edges
  out of the board's memory, reads rows of the output back, and compares them with the model's
  frame from those fields and the board's settings (`NET=MODEL.json` for loaded weights). The
  build passes in the deinterlacing modes 0 and 8 with the network (the board's kept weights) and
  with the kernel, the frame's first rows among those compared.
- **A new build** is screened on the board before it is kept: the memory's calibration and test
  (`tools/ddr.py test`), frames still coming once the tables are in, then `boardcheck.py`. Two
  earlier builds of the network that met timing failed there, so this is not skipped.

## What is not done

- One shape only. `f16s` (+0.05 dB) is not built.
- How the network's picture does in motion has not been measured: the scores are on single frames.
- With the kernel in the network's place, low latency, a part of the picture shown and motion
  compensation together, a frame's first lines have no time to spare (the kernel's path does not
  begin a frame's lines early as `bicu.v` does): to be given the same.
