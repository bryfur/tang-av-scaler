# The scaler's tables

The scaler (`rtl/easu.v`) makes each output pixel from the twelve source pixels round it, weighed by a
table's entry. The entry is chosen by where the pixel lies between source pixels (4 places below
the row above, the lower half mirrored; 8 places to the right), the direction of the edge there (32
bins) and how strong it is (8 levels): 8192 entries of twelve weights.

The design is built with FSR 1's kernel in that table (`sim/fsr.py table`). The table is a RAM, and
the CPU's program can put another one there while the picture runs (`sw/table.c`): a setting
chooses it.

| Setting `table` | The scaler has |
|---|---|
| 0 | FSR's (the design's own) |
| 1 | a learnt pair: `learnt-11games` with the anti-aliasing off, `learnt-11games-aa12` with it on (it follows the switch) |
| 2 to 6 | a table sent to the board (slots 3 to 7) |

A change takes about 0.2 s. Entries are written whole and only in the picture's blanking, so the
picture goes on, made with one table's entries or the other's, never a mixed entry. After it the
CPU reads the RAM back and compares (the status says how many entries differ: none).

## The files here

`learnt-11games.tab`, `learnt-11games-aa12.tab`: FSR's table refitted to the truth by least squares, on
pairs of pictures from eleven games (the console's frame through a model of the capture path, and the
same frame rendered by an emulator at 8 x), for the path with the anti-aliasing off and with SMAA at
threshold 12. On games they were not fitted on they score about +0.2 to +0.4 dB over a plain bicubic
stretch, where FSR's own table gives 0 to +0.05 ([docs/cnn-upscaler.md](../docs/cnn-upscaler.md)).
Options to look at, not the default. The link's firmware carries both and gives them to the CPU at
each start.

## A table file (.tab)

131072 bytes: the 8192 entries in the order {place below 0-3, place right 0-7, direction 0-31,
strength 0-7} (the last fastest), each four 32-bit words, little-endian; a word holds three weights,
10 bits each, signed, in 256ths, the first lowest: the twelve weights in `sim/fsr.py`'s order of the
twelve pixels (TAPS). An entry's weights should sum to 256.

    tools/table.py make IN OUT.tab      # from IN.json ({"py,px,ang,len": [12 weights]}) or IN0.hex .. IN3.hex
    tools/table.py hex IN OUT           # ... as the four files the block RAMs are built with
    tools/table.py fsr OUT.tab          # FSR's own
    tools/table.py send mine.tab        # to the board: slot 3 (or: send mine.tab 4 name)
    tools/table.py use 2                # the setting: slot 3's table
    tools/table.py list
    tools/table.py drop 3

The web page has the same: "Scaling kernel" under Picture, and a file chooser for a table of your
own. A table sent to the board is kept in the link's flash (five places) and survives the power
going off; the CPU's copy is in the DDR3 and the link gives it again at each start.

In the model: `model.table_load(file)` and `model.frame_1080(..., tab=...)`; `fsr.scale_hw()` takes
any table. In simulation: `sim/deint_tb.py 5 tab=FILE` puts the table in through the register port
and compares every pixel of a frame. On the board: `tools/boardcheck.py table=1` compares the
output with the model's, with the table the board says it has.
