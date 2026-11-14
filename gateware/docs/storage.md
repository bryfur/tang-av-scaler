# What the board keeps: its own storage

The board keeps its settings, the scaler's tables and the network's weights itself, in the SOM's
configuration flash. The Wi-Fi link (the XIAO) gives it things to keep and shows them on its page;
it need not be there when the board starts.

## Where

The SOM carries one 16 MB SPI NOR flash. The FPGA configures itself from its first 5.1 MB. Once it
is configured the flash's pins are plain pins of the design (`gowin/avb.tcl`: `use_mspi_as_gpio`;
`gowin/avb.cst`: chip select T19, clock L12, data P22 and R22, write protect P21, hold R21), and the
upper half, from 0x800000, is the board's.

| From | What |
|---|---|
| 0x000000 | the bitstream (never written by the design) |
| 0x801000 | the settings: 1024 records of 64 bytes, written one after the other and round again |
| 0x820000 | the network's weights: a head, then the values as `cnn.v`'s port takes them |
| 0x840000 | the tables, slots 1 to 7, 0x40000 each: a head, then the 32768 words |
| 0xA00000 on | free |

Writing a new bitstream (`tools/flash.sh`) erases and writes only as far as the bitstream reaches,
so what the board keeps comes through a new image.

## The port: `rtl/sflash.v`

Not a plain SPI port. The flash's commands are made in the logic, a fixed six (read, page program,
write enable, sector erase, status, identity); the CPU's program gives an address and data through
three registers (68 to 6A). A program or an erase is done only with the address at 0x800000 or
above and a key in the command; anything else is refused and nothing goes to the flash. A page
program cannot leave its 256-byte page nor a sector erase its 4096 bytes, so no value written to
those registers, by a fault or by design, can reach the bitstream, the flash's status register or
the whole chip. The clock is 12.5 MHz: a table is read in about 0.2 s.

`sim/sflash_tb.py` runs it against a model of the flash: the commands, the refusals, and 20000
register writes of anything at all, after which the model must have seen no other command and no
write below 0x800000.

## The keeping: `sw/store.c`

- **The settings.** Two seconds after the settings last changed a record is written at the next
  place: "SET1", a number one greater than the last, the settings, the words' sum. At a start the
  record with the greatest number and a right sum is taken, before the board is brought up. A sector
  is erased as the writing comes to it, so the newest record is never in the sector being erased.
  1024 records round sixteen sectors: a sector is erased once in 1024 changes.
- **The tables.** A table the link gives (`LINK_TABLE`, `LINK_TABLE_END`, with a name) is kept in its
  slot unless the one kept has the same sum. At a start from cold each slot's table is read from the
  flash into the memory, where `sw/table.c` has always had them.
- **The network's weights.** Given by the link (`LINK_NET`, `LINK_NET_END`: `tools/net.py load`),
  put into the network through its port and kept; at a start the kept ones are put in once the
  memory and the output run. With none kept the network has the bitstream's own.
- **A write cut short** leaves nothing rather than something wrong: a head is erased first and
  written last, after its data has been read back and summed; a settings record is one page with
  its own sum.
- **Writing is slow** (a sector's erase 50 ms and more, a table some seconds), so it is done a step
  each time round the program's loop, and the picture and the sound go on.

`make test` in `sw/` builds `store.c` for the host against a model of the port and the flash
(`sw/test/store_test.c`): 3000 changes of the settings, the power cut at any moment of some
hundreds of writes (what is found after is the settings before the change or after it, and the
next change is kept), tables and weights kept, found, replaced and dropped, and no write below
0x800000.

## The link's part

- **Settings.** A board that keeps its own says so in its status; the link then takes the board's
  settings as the ones that count and keeps only a copy. A board whose flash holds none yet (the
  first start with this design) is given the link's, and keeps them from then on.
- **Tables.** The link still carries the two learnt tables in its firmware and the ones sent to it.
  At a start it asks the board what it keeps in each slot (`LINK_STORE`: a sum and a name) and
  gives only what the board lacks or keeps another version of. A table the board keeps and the link
  does not is left alone, and shown on the page under the board's name for it.
- **Weights.** `POST /api/net` passes them on; the link keeps none.
- **An older bitstream** (no port) answers that it keeps nothing: the link then does all of this
  itself, as before.

## Looking at it

    tools/sflash.py id            the flash's identity
    tools/sflash.py store         the newest settings record, the tables' and the weights' heads
    tools/sflash.py test          a sector away from the store erased, written, read back; refusals
    tools/net.py load MODEL.json  weights put in and kept;  net.py try: not kept;  net.py drop

The page's status has a row "Kept in the board", and the upscaler's line says whose weights the
network has.

## What is not done

- The CPU's program is still the bitstream's own, or a newer one from the link: it is not kept in
  the flash.
- Without the link there is no way to change a setting: the board has no buttons of its own in use.
- The flash's block protection is not set: the bitstream's half is safe from this design by the
  port's own rule, not by the flash's.
