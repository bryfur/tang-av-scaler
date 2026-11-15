# One recurrent stage: field in, x 2 frame out

Handed to the gateware side on 2026-11-15 by the picture-research session. Measured offline on emulator data
and on two real still grabs from this board; nothing of it is in the RTL. What is here is ready to build
against: the arithmetic in whole numbers, the weights, a plain-Python reference and test vectors. Whether and
when to build it is the user's call; it is a bigger change than `cnn.v` was.

The design: one small recurrent network that replaces, for luma, both the deinterlacer and the x 2 network. It
is given one field at a time, plus its own previous output moved to lie on the new field, and makes the x 2
frame. The history fills in the lines the field lacks (exactly, for the second field of a 30 fps game's frame;
moved by the motion otherwise) and gathers detail over the frames.

## Why this one

Two ways to add a history were built and measured the same way: **A**, this one; **B**, the history network behind
the board's existing deinterlacer (sim/model.py `deinterlace()`, mode 0, threshold 6, noise reduction 2, motion
compensation). Games never trained on (Tales of the Abyss, Final Fantasy XII, God of War, Killzone, Silent Hill 2
and Gran Turismo 4's real 60 fps fields; trained on eight others), luma PSNR against the 8 x render, frames with
a history.

Mean over 16 held-out sets (floating point):

| | board-sized | larger (about 4.4 x) | flicker |
|---|---|---|---|
| perfect weave, then the network with history (a reference no hardware has) | | 32.01 dB | 3.50 |
| **A: this design** | **31.58** | **31.72** | **2.68 - 2.79** |
| B: the board's deinterlacer, then the network with history | 30.92 | 31.10 | 3.46 - 3.60 |
| the board's deinterlacer, then a single-frame network (today's chain) | 30.52 | 30.63 | 3.85 - 3.92 |

By game, the board-sized networks in whole numbers (each game's main set; its other sets agree):

| | Tales of the Abyss | FF XII | God of War | Killzone | Silent Hill 2 | GT4 (real fields) |
|---|---|---|---|---|---|---|
| A | 31.41 | 30.23 | 31.35 | 34.48 | 34.87 | 28.11 |
| B | 30.43 | 29.39 | 31.65 | 33.30 | 34.16 | 27.22 |

- A beats B on five of six games by 0.6 to 1.4 dB and is steadier; it is about 1 dB over today's chain.
- At board size A does as well as the larger network: the history, not the size, carries it.
- Flicker is the frame-to-frame temporal error against the truth (levels): lower is steadier. A is the
  steadiest of everything measured, including a bicubic stretch of the perfectly woven frame (3.95).

**On real captures from this board** (two still scenes, no truth exists; `~/devel/rvwork/fsrcmp/real_check.py`):
A shows no combing or artefacts. Its output changes a little more from field to field than the board's
deinterlacer (mean |out(n) - out(n-1)|: 0.89 against 0.50 levels on a Xenosaga III grab, 0.71 against 0.53 on
Tales of the Abyss; today's chain 0.60 and 0.70). That is capture noise it averages less than weave does; spread
evenly, no field-to-field pattern. A fine-tune with still scenes did not change it. Moving real fields have not
been tried: that needs someone playing (below).

## What the hardware does, for each field

All whole numbers. `sim/cnn_ref_hist.py` is the reference (plain Python; it uses `sim/cnn_ref.py` for the
network), `sim/cnn/histA.json` the weights, `sim/cnn/vec/histA/<name>/` test vectors.

1. **The picture p:** the field's 224 lines at the frame's rows of its parity; the rows between, the mean of the
   lines above and below, rounded half up (640 x 448, 8 bits).
2. **The motion:** a vector for each block of 8 x 8 source pixels (80 x 56 blocks), in eighths of an output
   pixel. See "The estimator".
3. **The moved history hm** (the previous output, 8 bits, 1280 x 896): each output pixel's vector from the four
   nearest blocks' (block b's middle at output 16 b + 7.5; rows b0 = (2 y - 15) >> 5 and b0 + 1, clamped;
   ty = 2 y - 15 - 32 b0; the same across; v = ((32 - ty)((32 - tx) a + tx b) + ty((32 - tx) c + tx d) + 512) >> 10),
   then bilinear from the four nearest history pixels in eighths:
   ((8 - fy)((8 - fx) a + fx b) + fy((8 - fx) c + fx d) + 32) >> 6, the picture's edge pixels repeated.
4. **The agreement d:** |p - ((the sum of hm's 2 x 2) + 2) >> 2| for each source pixel; 255 for the first field.
5. **The network:** inputs, in order: p, the real-lines plane (255 on the field's rows, else 0), hm's 2 x 2 of each
   source pixel (top left, top right, bottom left, bottom right), d. Layers 3 x 3 7 -> 8, 3 x 3 8 -> 8,
   3 x 3 8 -> 4; shifts 8, 5, 6; weights at most 110 in size; bias plus rounding half between -3446 and 3630;
   every sum under 2^19: within `cnn.v`'s limits, only the first layer wider (1,368 multiply-adds a source
   pixel; t8's 936).
6. **The output:** (skip16(p) + r + 8) >> 4 as in `cnn.v`: x 2 (1280 x 896). It is what is shown (then the bicubic
   stretch to 1080, as now) and the next field's history.

Check: `cd sim && python3 cnn_ref_hist.py cnn/histA.json check cnn/vec/histA/shapes` (and diag, edge, menu)
prints "equal" for each of the five pictures. Each vector sequence is a test picture panned by known sub-pixel
amounts, with one step whose vectors vary from block to block (the spreading) and one still step (no vectors).

## The estimator

The history must be moved from the previous output to the new field. Estimating between consecutive fields needs
the game's cadence (a 30 fps frame's second field has not moved; a 60 fps game's has), and the deinterlacer's
estimator compares a field with the one two before. **Estimating between the new field and the history itself**
(its 2 x 2 means) gives exactly the move the history needs, whatever the cadence. Measured with the weights here:
the same as estimating between frames on every game but Killzone, which loses about 1 dB (fast motion: 13 % of
its pixels move more than 8 lines a frame).

The estimator measured: a whole-pixel block search (8 x 8 blocks, 16 x 16 windows, +-16 x +-12), the fraction of
a pixel from the costs either side of the best (where the two lines through them cross), each block weighted by
its texture (the smaller eigenvalue of its slopes' sums) and its match, smoothed over about three blocks with the
far-off ones weighted down and kept as their own, 3 x 3 medians. Reference: `~/devel/rvwork/fsrcmp/flow_est.py`
`bmq_blocks()` (floating point; the vectors are then rounded to eighths). The search is the FPGA's job: the
deinterlacer's search could serve, also reporting the four neighbour costs and the window's slope sums. The rest
is arithmetic on 4,480 blocks a field, which the CPU can do. A learned correction of the vectors was tried and
did not help the picture.

With the deinterlacer's own six-candidate search as the front end instead of an exhaustive one, about 0.1 dB was
lost (measured on frames).

## Sizes and choices

- **History in the DDR3:** 1280 x 896 x 8 bits = 1.15 MB, written and read once a field (about 70 MB/s each way at
  60 fields a second, plus the read window's overlap).
- **Read window:** true vertical motion between frames is within 8 source lines (16 output rows) for 96.5 % of
  pixels, 12 for 98.2 %, 16 for 99 % (all games). A window of +-16 output rows (33 rows of 1280 bytes) covers
  96.5 %; beyond it the vector could be clamped and d left to say the history does not fit.
- **Latency:** the smoothing wants the vectors of blocks below a block. Limited to two block rows ahead (16 source
  lines) it lost about 0.1 pixel of accuracy in fast scenes and little in slow ones. Prediction from the previous
  field did not help.
- **Chroma:** the network is luma only. Simplest: chroma as today's deinterlacer path makes it.
- **The edge search is gone** (removed 2026-11-14); A needs none.

## Open

- **Real moving fields** (step 6 of the plan): `real_check.py` takes `tools/fields.py OUT.json 8` of a game in
  motion and runs A, B and today's chain on it. It needs someone playing and the monitor free.
- **Killzone-like fast motion** with the history-based estimator (about 1 dB lost there).
- **More 60 fps field data:** Gran Turismo 4 is the only held-out field game (40 fields), Ace Combat 5 the only
  training one.

## Where the numbers come from

Emulator pairs (PCSX2: software-rendered native frames through a model of the capture path, the 8 x render as the
truth), 4,800 frames from 13 games, plus the board's two real still grabs. Scripts in `~/devel/rvwork/fsrcmp`:
`cnn_hwr.py` (this design, whole numbers: trains, sets the formats, writes the json), `cnn_o.py` (the floating-
point comparisons), `deint_pairs.py` (B's data through `sim/model.py`), `field_pairs.py` (60 fps field pairs),
`flow_est.py` / `flow_truth.py` (the motion), `cnn_vec_hist.py` (the vectors), `real_check.py` (real captures). The
game data stays out of every repository.
