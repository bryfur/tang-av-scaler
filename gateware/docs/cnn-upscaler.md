# A small network as the scaler's first stage

Research handed to the gateware side on 2026-11-14 (the picture-research session; the work and its data are
outside this repository). What is here is ready to build against: the arithmetic in whole numbers, the
weights, a reference model and test vectors. Nothing of it is in the RTL yet.

## What to build, in two steps

1. **A refitted table for the scaler that is there (free).** `easu.v`'s table can be changed while the
   picture runs. A table fitted to eleven games' emulator pairs is in
   `~/devel/rvwork/fsrcmp/tables/learnt-11games{0..3}.hex` and `.json` (the format `mk_tables.py` writes; one
   entry of 8192 had a weight outside the 10 bits and was limited). Measured on games it was not fitted
   on: about +0.2 to +0.5 dB over a bicubic stretch, where FSR's own table gives +0.05. Try it on the
   board first: it costs nothing. `learnt-11games` was fitted on the picture as captured (SMAA off);
   `learnt-11games-aa12{0..3}.hex` beside it on the picture after SMAA (threshold 12, diagonals and corners
   on: the board's setting): +0.38 dB on filtered frames and +0.28 mean, where FSR's own gives 0.00.
2. **The network `t8s`, after SMAA, before the scaler.** Luma only, at the source's resolution, making
   the picture at x 2 (720 x 480 -> 1440 x 960); the scaler then has only the small stretch left to
   1440 x 1080. 936 multiply-adds for each source pixel, three layers. `f16s` is the larger choice
   (3,280), for +0.05 dB more.

Not to build: giving the network earlier frames (its own previous output moved by the deinterlacer's
vectors). On games it had not seen it gained under 0.1 dB.

## What it gains, plainly

Tested on four games the networks never saw in training (Tales of the Abyss, Killzone, Final Fantasy XII,
God of War; trained on seven others), luma PSNR against an 8 x render of the same frame, in the
whole-number arithmetic below. "Filtered" is a console frame through the flicker filter (most games; real
captures of Tales of the Abyss and Killzone match it), "unfiltered" a frame sent line for line.

| | multiply-adds a source pixel | filtered | unfiltered | mean |
|---|---|---|---|---|
| FSR's own table (the board today) | | +0.05 dB | | |
| the refitted table | | +0.34 | +0.12 | +0.23 |
| `t8` | 936 | +0.62 | +0.27 | +0.45 |
| `f16` | 3,280 | +0.72 | +0.29 | +0.50 |
| the table refitted after SMAA (against a bicubic stretch of the same input) | | +0.38 | +0.19 | +0.28 |
| `t8s` (after SMAA; the same) | 936 | +0.71 | +0.36 | +0.54 |
| `f16s` (the same) | 3,280 | +0.84 | +0.35 | +0.59 |

So the network is 0.2 to 0.3 dB over the free table: a modest step, not a new picture. Twelve shapes from
936 to 16,600 multiply-adds were tried: past about 3,000 nothing is gained. The limit is what one
448-line frame holds.

By eye, on real captures from this board (Killzone, Tales of the Abyss): the network alone is crisper than
a bicubic stretch but keeps the stair steps; **SMAA first, then the network** has the smooth edges of
today's SMAA + FSR + sharpening with crisper texture and fine lines. That is why it sits after SMAA, and
why `t8s` and `f16s` were trained on SMAA's output (threshold 12, diagonals and corners on: if the
board's SMAA settings change much, `t8` and `f16`, trained without SMAA, are the neutral ones).

What is not known: how it looks in motion on the board; games whose picture is not like the eleven
(the networks lost 0.1 to 0.2 dB on Dragon Quest VIII, whose 8 x render holds texture detail the console's
frame never had, so that number may say more about the test than the picture).

## The arithmetic

All whole numbers; `sim/cnn_ref.py` is this, in plain Python, and is the reference.

Source luma `p` = 0..255. At the picture's edges the edge pixels are repeated, for every layer's input.

    a0 = p
    layer l = 1 .. L-1:   acc = sum over the kernel and the input channels of W * a(l-1), + B
                          a(l) = clamp((acc + 2^(shift-1)) >> shift, 0, 255)
    layer L (4 channels): r = (acc + 2^(shift-1)) >> shift          signed; >> floors
    out[2y + j][2x + i] = clamp((skip16 + r[2j + i] + 8) >> 4, 0, 255)

    skip16 = 9 a + 3 b + 3 c + d     a: the source pixel; b: the one above (j = 0) or below (j = 1);
                                     c: the one to the left (i = 0) or right (i = 1); d: the diagonal one

`W` is 8 bits signed (-127..127), `a` 8 bits unsigned, `B` a whole number in `acc`'s units. The last
layer's four channels are the 2 x 2 output pixels of a source pixel, in sixteenths of a level, added to
the plain two-tap stretch (`skip16`, also sixteenths).

| | layer 1 | layer 2 | layer 3 |
|---|---|---|---|
| `t8`, `t8s` | 3 x 3, 1 -> 8, shift 6, acc under 2^17 | 3 x 3, 8 -> 8, shift 7, under 2^19 | 3 x 3, 8 -> 4, shift 5, under 2^19 |
| `f16`, `f16s` | 5 x 5, 1 -> 16, shift 6, under 2^18 | 3 x 3, 16 -> 16, shift 6, under 2^19 | 3 x 3, 16 -> 4, shift 5, under 2^20 |

(The bounds are the worst case of each model's own weights: 21 bits signed holds every sum.)

A model file (`sim/cnn/<name>.json`): `layers[l]` = `{kh, kw, cin, cout, shift, w[cout][cin][kh][kw], b[cout]}`;
`in` 1; `scale` 2. (`in` 5 is the history variant, not built; `cnn_ref.py` still computes it.)

## What it needs

- **Lines.** `t8s`: two lines of the source (1 channel), two of layer 1's output (8 channels), two of layer
  2's (8 channels): 34 line-channels of 720 x 8 bits, about 196 kbit. `f16s`: four of the source, two of
  16 channels twice: 68 line-channels, about 392 kbit. (A RAM wider than 18 bits takes two sites on this
  part: count from the P&R report.)
- **Multiplies.** 8 x 8 bits (signed by unsigned). At 13.5 MHz of source pixels and the pixel pair a clock the
  stream runs at, `t8s` is 936 for each source pixel. The weights are fixed for a model: as constants they
  are shifts and adds; as a RAM they can be changed while the picture runs, like the scaler's table (956
  weights and biases for `t8s`). That choice is the gateware's.
- **Delay.** The network looks 3 source lines down (`t8s`) or 4 (`f16s`): that many more lines of the
  source before a line comes out.
- **Around it.** Chroma is not touched by the network: stretch it x 2 by the same two-tap filter (or any
  plain one) to go with the new luma. The scaler after it gets 1440 x 960 and the edge analysis it takes
  from the deinterlacer's stream would be of the wrong picture: a plain kernel for that last stretch is
  what the networks were trained with (bicubic, the pictures' centres in line; 1.125 down for a full
  480 lines, 1440/1280 x 1080/896 for a game's 640 x 448). Sharpening after it was not part of the
  training: it is a matter of taste on the board.

## Checking the RTL

    cd sim && python3 cnn_ref.py cnn/t8s.json check cnn/vec/t8s

`sim/cnn/vec/<name>/<picture>-in.png` are parts of `sim/ref`'s test pictures (96 x 64 and one 64 x 48 at the
picture's corner, for the edges), `-out.png` what the model must make of each (192 x 128), written by the
trainer's own integer path; `cnn_ref.py` gives the same on every pixel for all four models. A testbench
can feed the `-in` pictures as the stream and compare with `-out`, or call `cnn_ref.upscale(model, rows)`
on any picture.

## Where the numbers come from

Pairs from PCSX2: a frame at the console's resolution from the software renderer, put through a model of
the capture path (flicker filter or not, 640 samples a line, the analogue blur and noise set against real
captures), and the same frame drawn at 8 x as the truth. Eleven games (Tales of the Abyss, Xenosaga III,
San Andreas, Killzone, God of War, Shadow of the Colossus, Metal Gear Solid 3, Final Fantasy XII, Dragon
Quest VIII, Burnout 3, Odin Sphere), about 1,800 frames, both capture models. Every score above is on
games left out of the training; the weights here are then trained on all eleven. The scripts are in
`~/devel/rvwork/fsrcmp` (`cnn_hw.py` trains and writes a model, `cnn_vec.py` the vectors, `table_lo.py` the
table by the same test); the game data stays out of every repository.

Two things learnt on the way that matter to anyone repeating it: a test on sequences from the same place
as the training ones flatters every network, the large ones most (the history variant looked worth +0.3
to +0.5 dB that way and was worth under 0.1 on new games); and training on through the rounding made the
networks worse: the weights here are the floating-point ones rounded, which loses 0.01 dB.

## In the design

Built on 2026-11-14 (gateware side): `rtl/cnn.v` is the network, `rtl/bicu.v` the stretch after it; the
setting `net` (the web page's "Upscaler": Kernel or Network) puts them in `easu.v`'s place.

- **Where.** After SMAA, as the note says: the network reads the same eight-line ring `lstream.v` fills
  for `easu.v` (five of its lines at once), on the output's clock, a source line at a time (a pass). A
  source pixel takes six clocks, so each of the 192 multipliers (9 x 8 bits) does six products a pixel:
  1,080 a pixel in all, because layer 1 is computed three times over rather than kept (it is small; its
  two lines of eight channels would have cost eight more block RAMs). Layer 2's two lines are kept
  (eight block RAMs).
- **The last stretch.** The picture at twice the size goes to a ring of eight lines; `bicu.v` reads four
  of them by the bicubic kernel torch uses (a = -0.75), a place to the nearest 32nd of a pixel, down
  first and then across, to 1440 x 1080 or whatever the crop and the wide setting ask. The chroma is not
  stretched twice: it goes from the source to the output directly, the four nearest by sixteenths. The
  sharpening after it is still there and still follows its setting (0 turns it off).
- **The weights** are in LUT RAM, the design's own `sim/cnn/t8s.json` (`sim/model.py net_init()` at build
  time); another network of the same shape (3 x 3, 1 -> 8 -> 8 -> 4: `t8.json` is one) can be put in while
  the picture runs: registers 45, 46 (`tools/net.py load MODEL.json`, through the monitor; it lasts until
  the FPGA is loaded again). `f16s` is another shape and would be another build.
- **A frame's start** was the hard part: the network wants the first lines some ten rows before
  `easu.v` does. Its passes begin two lines above the first line shown, and the lines' side is told to
  begin the next frame before the frame now shown is over (it reads ahead; nothing reaches the ring
  until the last row is done). Register 47 counts rows begun before their lines were made.
- **Checked.** `sim/cnn_tb.py`: `cnn.v` against the four test pictures here, every pixel (and its
  synthesized netlist: `cnn_tb.py synth`). `sim/deint_tb.py ... net`: a whole frame through the
  deinterlacer, SMAA, the network, the stretch and the sharpening against `sim/model.py scale_net()`:
  the same on every pixel, with crops, widescreen, 480p, the low latency mode, motion compensation and
  the edges on. `tools/boardcheck.py` compares the board's output with the model the same way.
