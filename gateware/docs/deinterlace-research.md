# Research: what would suit 480i better than the current chain (2026-11-12)

A reading of the literature and of what other scalers do, for the question "is there an
anti-aliasing or upscaling method better suited to 480i/480p from a PS2". Nothing here has been
built or measured on this board; where a number is an estimate it says so.

## Where the picture is today (rtl/deint.v)

Motion adaptive over four fields: where nothing moves the missing line is the previous field's
(weave), where something moves it is the mean of the lines above and below (bob). No cadence
detection; no direction in the interpolation.

## Findings

**1. Edge-directed interpolation of the moving parts is the established next step.** The scalers
this board competes with added exactly that, late: the RetroTINK 4K in firmware 1.4.2 (2024-04-27),
"Edge-adaptive interpolation to minimize 'jaggies' when Bob is used", with a "next generation Motion
Adaptive Deinterlacer"; the RetroTINK 5X in 3.98 (2026-06-01) as "MA Smoother" [RT4K, RT5X].

**2. Inverse 2:2 (weaving 30 fps games) may be worth more than it, for the games it applies to.**
A PS2 game either draws a new half-height picture every field (field rendering, 60 fps: every field
a new moment) or a full frame (640 x 448 or 512 x 448) that goes out as two fields (frame rendering,
commonly 30 fps) [LIBRETRO, PCSX2]. In the second kind both fields of a pair come from one frame:
weaving the right pair gives the frame back exactly, moving or not. Our motion detector sees the
motion between frames and interpolates lines that the other field already holds. RetroTINK's 2:2
mode is for this: "2:2 is useful for interlaced games that run at reliable/stable 30 fps. Under
these conditions, the deinterlacing is perfect" [RT5X 3.7]; 3.98 "weave[s] 30 fps games output as
480i". It needs the cadence found (which field pairs belong together) and a fast way out when a
game drops a frame. docs/hard-cpu.md already lists this as a job for the CPU.
For the first field of a new frame there is a choice: interpolate it (no added delay, half the
output frames soft), or show the previous frame's weave again (every frame whole, one field later).

**3. Which edge-directed method.** In rising cost:

| Method | What it does | Known weakness |
|---|---|---|
| ELA, 3 directions | the pair of pixels (above-left/below-right, above/below, above-right/below-left) that differ least; their mean | 45, 90, 135 degrees only; "sensitive to small variations", picks wrong directions on thin lines, texture, noise [KOR1, KOR2] |
| yadif's spatial predictor | 5 directions (offsets 0, +-1, +-2), each scored by the sum of three neighbouring column differences; the result held within the temporal difference of the previous/next fields' value [YADIF] | nothing flatter than about 27 degrees |
| Lin, Chang, Chen 2003 | 5 directions; used only where one direction clearly wins ("dominant edge"), else the vertical mean; then the median of (result, pixel above, pixel below) against "bursting pixels"; with a same-parity 4-field motion detector like ours | the median costs thin horizontal detail [LIN, PAT] |
| Wider searches (wide-range ELA, DCDi-like, EEDI2/3) | offsets to +-4...+-8 and more, for nearly horizontal edges: the ones with the longest stair steps under bob | false matches grow with the range: need longer scores, agreement with the neighbours' directions [UCI, PAT] |
| NNEDI3 | a small neural network per missing pixel | cost: see 5 |

A guard is not optional: every source that goes past plain ELA adds one (a dominant-direction test,
a median, a clamp by the other fields, or the neighbours' majority direction) [LIN, PAT, YADIF].
Our noise reduction ahead of the interpolation helps the direction search.

Lin's architecture is ours with the mean replaced: the paper reports about a tenth of a motion
compensated design's hardware [LIN]. A commercial FPGA core rates ELA "medium" between bob and a
5 x 5 method [ZIP]. The search works on the two lines the deinterlacer already holds.

**4. The first proposal to try:** yadif's 5-direction search with Lin's dominant-edge test, luma
picks the direction and chroma follows it, mixed by the motion value as the mean is today. Then
measure whether a +-4 or +-8 search with a consistency check earns its keep on near-horizontal edges.

**5. On ruling out neural methods.** The 148.5 Mpixel/s argument applies to the scaler. The
deinterlacer makes 720 x 240 x 60 = 10.4 million pixels a second. NNEDI3's smallest predictor is,
from memory, about a thousand multiply-adds a missing pixel: some 70 multipliers running flat out
at 148.5 MHz, of the 298 the FPGA has (43.5 in use). That is an estimate, and the fixed-point work
and the timing would be weeks: not ruled out by size, but well behind 1, 2 and 4.

**6. Not found:** a list of which PS2 games are field or frame rendered; how RetroTINK's edge
interpolation or its cadence detector work inside; a like-for-like PSNR table for the ELA family.

## Neural methods that could fit (the scaler's side)

What decides it here: the weights are fixed at build time, the logic is 87 % free, the block RAM
68 % used, and a network that works at the input's resolution sees 720 x 480 x 60 = 20.7 million
pixels a second (7 clocks of 148.5 MHz each), not the output's 148.5.

| Kind | Fit | What the papers show |
|---|---|---|
| A network baked into lookup tables (SR-LUT, MuLUT, RC-LUT, HKLUT) | the best: no multipliers, table reads and a small interpolation, as easu.v's kernel table already is | at x4 on Set5: RC-LUT 30.72 dB, FSRCNN's figure; HKLUT-S 30.35 dB in 100 KB of tables (about 45 block RAMs; easu.v's table has 55) [RCLUT, HKLUT, SRLUT]. Figures at x2 not found |
| A small CNN at the input's resolution, then a pixel shuffle (FSRCNN-s size) | by arithmetic: about 2,500 multiply-adds an input pixel (my count), weights as shift-and-add logic | real-time on an FPGA at far higher rates: 2K to 4K at 60 fps with 1-D convolutions to save line memories, on a larger device [KAIST] |
| One-layer networks (edge-SR) | trivially | not worth it: the fast eSR-MAX is below bicubic at x2 (33.15 against 33.73 dB on Set5) [ESR] |
| NNEDI3 for the deinterlacer's lines | see 5 above | a prescreener sends most pixels to cubic interpolation, the rest to the network [NNEDI] |
| Deep, temporal or game-engine methods (DLSS, FSR 2+, Arm NSS) | no | they need motion vectors and depth from the engine |

The published weights are trained on photographs shrunk with a bicubic filter. Our input is aliased
3-D rendering through an analogue path, so the gain would come from training on our own pairs: the
same frames rendered at the console's resolution and supersampled (an emulator can render both),
the first put through a model of the analogue path. The network then learns anti-aliasing and
scaling together, in place of smaa.v and easu.v. Paired low-resolution and supersampled renders are
how game upscalers are trained [QRISP, NSS]; no emulator data set was found. Qualcomm's QRISP set
(rendered game frames, 270p to 1080p, native and supersampled) would do for a first trial.

**Google's RAISR (2016) is the nearest of all to what easu.v already is.** Each pixel's
neighbourhood is put in a bucket by its edge's angle (24 bins), strength and coherence (3 each),
and the bucket's filter is applied: an 11 x 11 filter learnt from pairs of pictures by least
squares (10,000 pairs, about an hour, no GPU) [RAISR]. easu.v picks 12 weights from a table by
place, direction (32 bins) and strength (8 levels): the same machine with a computed table. So:
(a) learn easu.v's own table from our pairs: a new ROM file, no new logic; (b) more taps (RAISR's
filter on the scaled picture comes to about 6 x 6 source pixels): more multipliers and line
buffers; (c) coherence as a third index: a larger table. Learnt on pairs with the analogue path
modelled, the filters can undo some of its blur by edge type, which a fixed kernel cannot. Of the
learnt methods this is the cheapest to try and the surest to fit.

Unknown until tried: whether any of these beats the present chain visibly on this source.

## How to measure before building

A Python model beside sim/model.py: take progressive frames (a PS2 game in 480p once that input
works, or an emulator's native frames), drop alternate lines, interpolate with each method, compare
with the truth (PSNR and by eye on near-horizontal edges). For 2:2: fields captured from a 30 fps
game, the pairing's comb measure field by field.

## Emulator truth: first results (2026-11-13)

A harness drives PCSX2 with a virtual controller, records the game's drawing commands
(GS dumps) and replays the same frames twice: by the software renderer at the console's own
resolution and by the GPU at 8 x. The native frame goes through a model of the board's input
(the console's flicker filter: a line is the mean of two frame buffer lines; 512 pixels sampled as
640; a blur of 0.55 samples along the line; noise 0.7 levels), set against real captures by the
widths of their sharpest edges (real 1.63 / 2.04 / 2.67 samples along a line and 1.93 / 2.03 / 2.22
lines across at the 10th / 25th / 50th percentile; the model 1.70 / 2.00 / 2.44 and 1.97 / 2.07 /
2.29). The 8 x render reduced to 1440 x 1080 is the truth; it sits on the scaler's output within
0.03 pixels. Tales of the Abyss, 12 still scenes in three places and two walking sequences. Scores
are luma PSNR; fitted things are scored on a place they were not fitted on. The scripts are
scratch work outside the repository so far; the game's pictures stay out of it.

**The deinterlacer: follow the 30 frames a second cadence.** The game renders 30 frames a second
and each frame goes out as two fields. sim/model.py deinterlace() on the walking sequences (the
camera pans, the picture changes 16 levels mean between frames), against the frame each field came
from:

| | first field of a frame | second field |
|---|---|---|
| bob | 33.6 to 33.9 dB | 33.2 to 33.5 |
| weave with the field before | 21.0 to 21.5 | 49.2 |
| motion adaptive, threshold 6, nr 2 | 33.7 to 33.9 | 34.3 to 34.6 |
| + edi | 33.8 to 33.9 | 34.3 to 34.6 |
| + edi + mc (no pan given) | 33.0 to 33.5 | 33.8 to 34.3 |
| weave with the other field of the same frame | 49.2 | 49.2 |

The motion test compares fields two apart, which here are always of different frames: so all of a
moving picture is bobbed, though its other half is in the memory, one field before or one after.
49.2 dB is the noise alone. The motion compensation loses a little: it takes the field before to
be half a vector away, and here it is none or all of it. What it needs: which field begins a frame
(the comb measure of the newest field against the one before, field by field: it alternates), then
either weave the pair when its second field is in (the first field's lines wait one field), or for
no wait give the first field the field before moved by the whole vector. To confirm on the console:
four fields in a row grabbed in motion (tools/fields.py). A still sequence scores 49.0 weave, 47.4
to 50.5 adaptive, 33 bob.

**The upscaler: the loss is the game's aliasing, not our filter.** A bicubic stretch to 1440 x 1080
of: an ideal anti-aliased 640 x 448 picture 35.2 dB; the game's own frame 32.0; that through the
flicker filter, the blur and the noise 31.55. The path costs under half a dB; three are the stair
steps and shimmer of a picture drawn with one sample a pixel.

| after the deinterlacer | dB |
|---|---|
| bicubic | 31.07 |
| FSR's table (easu.v as it is) | 31.18 |
| the same table refitted to truth (same 12 pixels, same index) | 31.55 |
| RAISR's index (structure tensor: direction 24, strength 3, coherence 3), 12 pixels | 31.65 |
| ... 6 x 4 pixels 31.69, 6 x 6 pixels 31.78, 8 x 6 pixels 31.77 | |
| FSR's index + coherence | 31.52 (nothing) |
| SMAA 12 + FSR's table + RCAS 8 (the board's default) | 30.91 |
| SMAA 12 + refitted table | 31.30 |

Refitting the table's contents is worth 0.4 dB and costs nothing (the same ROM); RAISR's index and
more pixels add 0.1 to 0.2 more for a new analysis and more line buffers: not worth building. SMAA
loses 0.26 dB, all of it away from the geometry's edges (33.16 to 32.81 dB there; at the edges 19.9
to 19.8): it softens texture. Against a reference with no stair steps (the same frame anti-aliased
by the emulator, through the same path) it takes 7 % off the error at the edges (14.1 to 13.2
levels rms). PSNR does not weigh stair steps as the eye does, so this does not say SMAA should go;
it says a guard that keeps it off texture is worth trying, and this harness can score it. Threshold
20 loses less than 12 (30.97). RCAS at 0 to 8 changes nothing measurable, 12 loses 0.07.

## Sources

- [RT4K] RetroTINK 4K firmware notes: https://retrotink-llc.github.io/firmware/4k.html
- [RT5X] RetroTINK 5X firmware notes: https://retrotink-llc.github.io/firmware/5x.html
- [YADIF] FFmpeg libavfilter/vf_yadif.c (CHECK, FILTER): https://ffmpeg.org/doxygen/trunk/vf__yadif_8c_source.html
- [BWDIF] FFmpeg vf_bwdif.c (yadif's frame with the BBC's Weston 3-field coefficients): https://ffmpeg.org/doxygen/trunk/vf__bwdif_8c_source.html
- [LIN] S.-F. Lin, Y.-L. Chang, L.-G. Chen, "Motion adaptive interpolation with horizontal motion detection for deinterlacing", IEEE Trans. Consumer Electronics, 2003: https://homepage.ntu.edu.tw/~lgchen/publication/paper/[J][2003][TCE][Shyh-Feng.Lin][1].pdf
- [KOR1] https://koreascience.kr/article/CFKO201131748034180.pdf  [KOR2] https://koreascience.kr/article/CFKO201131748034182.pdf
- [UCI] wide-range edge interpolation, ICME 2006: https://www.cecs.uci.edu/~papers/icme06/pdfs/0000837.pdf
- [PAT] US 8081256 (edge directed deinterlacing), US 6798422 (filtering edge directions): https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8081256
- [ZIP] Zipcores deinterlacer core (bob, ELA, LCI): https://www.mouser.com/datasheet/2/1026/deinterlacer-1660055.pdf
- [LIBRETRO] field and frame rendering on the PS2: https://www.libretro.com/?p=50686
- [PCSX2] https://forums.pcsx2.net/archive/index.php/thread-68073.html
- [EEDI] forum comparisons of EEDI2/EEDI3/NNEDI3: https://forum.videohelp.com/threads/394380-QTGMC-EdiMode
- [SRLUT] Jo, Kim, "Practical Single-Image Super-Resolution Using Look-Up Table", CVPR 2021: https://openaccess.thecvf.com/content/CVPR2021/papers/Jo_Practical_Single-Image_Super-Resolution_Using_Look-Up_Table_CVPR_2021_paper.pdf
- [RCLUT] Liu et al., "Reconstructed Convolution Module Based Look-Up Tables", ICCV 2023: https://openaccess.thecvf.com/content/ICCV2023/papers/Liu_Reconstructed_Convolution_Module_Based_Look-Up_Tables_for_Efficient_Image_Super-Resolution_ICCV_2023_paper.pdf
- [HKLUT] "Hundred-Kilobyte Lookup Tables for Efficient Single-Image Super-Resolution", IJCAI 2024: https://arxiv.org/html/2312.06101v2
- [ESR] Michelini, Lu, Jiang, "edge-SR: Super-Resolution For The Masses", WACV 2022: https://arxiv.org/pdf/2108.10335
- [KAIST] Kim, Choi, Kim, "A Real-Time Convolutional Neural Network for Super-Resolution on FPGA With Applications to 4K UHD 60 fps Video Services", IEEE TCSVT 2019: https://koasas.kaist.ac.kr/handle/10203/265537
- [NNEDI] FFmpeg's nnedi filter (prescreener, predictor): https://ayosec.github.io/ffmpeg-filters-docs/5.1/Filters/Video/nnedi.html
- [QRISP] Mercier et al., "Efficient Neural Supersampling on a Novel Gaming Dataset", ICCV 2023: https://arxiv.org/pdf/2308.01483.pdf
- [NSS] Arm Neural Super Sampling: https://semiengineering.com/how-neural-super-sampling-works-architecture-training-and-inference/
- [RAISR] Romano, Isidoro, Milanfar, "RAISR: Rapid and Accurate Image Super Resolution" (arXiv 1606.01299); Google: https://research.google/blog/enhance-raisr-sharp-images-with-machine-learning/
