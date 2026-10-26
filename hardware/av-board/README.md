# The AV board

Revisions A and B: one board on the Tang Console 138K's two 2x20 headers, component video and
stereo audio in on J10, HDMI out on J9, the Console's outline plus a 15 mm strip for the jacks.
Revision C: the Tang Mega 138K SOM on a carrier of its own, no Console, in two variants that
differ only in their HDMI transmitter.

## Revisions

| Revision | Video in | Layers | Status |
|---|---|---|---|
| [rev-a](rev-a/) | ADV7842 (256-ball BGA) | 6 | Routed, DRC clean, fab files made (not ordered): about $400 at JLCPCB, the BGA and six layers the cost |
| [rev-b](rev-b/) | ADV7181D (64-lead LFCSP) | 4 | Reviewed against every data sheet (twice), routed, DRC clean, fab files made (not ordered): the cheaper decoder, no BGA, four layers (two ground planes), 230 parts, SMT on the top only; a variant BOM leaves the RCA jacks for hand soldering; HDMI CEC, a SCART sync input, an S/PDIF input (coax or an optical module; Dolby Digital/DTS passed to HDMI), a VGA header (RGBHV with DDC), a status LED and sockets for a Seeed XIAO (ESP32: Wi-Fi/Bluetooth) |
| [rev-ca](rev-ca/) | ADV7181D | 4 | The SOM on its own carrier (rev-c/design.md), HDMI from an ADV7511 at up to 1080p60 fed 24-bit RGB; USB-C power, the XIAO as the FPGA's programmer (JTAG) and console, an orange RCA for S/PDIF coax, a clock generator for frame-locked output, the VGA header; 280 parts. Rev B's circuits from the same code (kit/circuits.py); the new parts reviewed against their data sheets (rev-c/review.md); being routed |
| [rev-cb](rev-cb/) | ADV7181D | 4 | As rev C-A but HDMI 2.0 from the FPGA's transceivers through an SN65DP159 retimer: up to 4K60, the HDMI protocol in gateware; 291 parts. Reviewed, routed, DRC clean, fab files made (not ordered) |

All carry the PCM1808 (audio ADC). Rev A, B and C-A have the ADV7511 (HDMI transmitter: the
Console's own HDMI port is rated 1080p30 / 720p60 only, so 1080p60 needs it); rev C-B drives HDMI
from the FPGA's transceivers instead. Each revision's README and design.md say what is particular
to it; rev C-A and C-B share rev-c/ (their circuit, floor plan, SOM interface and design notes).

## Pictures

Rendered by `python3 kit/render.py rev-x` (KiCad's raytracer; 3D models from `kit/fetch_lib.sh` and
`kit/fetch_3d.py`). The SOM itself (rev C) and the Console under rev A/B are not drawn.

| | 3D | Top |
|---|---|---|
| Rev A (ADV7842, 6 layers) | ![](rev-a/img/av-board-a-3d.png) | ![](rev-a/img/av-board-a-top.png) |
| Rev B (ADV7181D, a hat on the Console) | ![](rev-b/img/av-board-b-3d.png) | ![](rev-b/img/av-board-b-top.png) |
| Rev C-A (the SOM's carrier, ADV7511, 1080p60) | ![](rev-ca/img/av-board-ca-3d.png) | ![](rev-ca/img/av-board-ca-top.png) |
| Rev C-B (the SOM's carrier, SN65DP159, 4K60) | ![](rev-cb/img/av-board-cb-3d.png) | ![](rev-cb/img/av-board-cb-top.png) |

## Layout of this directory

| Path | What |
|---|---|
| `rev-x/board.py` | the revision's parts and nets: the one source its schematic and PCB are generated from |
| `rev-x/gen_pcb.py` | its outline, hand placement and chip-specific placing rules, on `kit/pcbkit.py` |
| `rev-x/design.md` | its electrical design, connection by connection, with sources |
| `rev-x/*.kicad_*`, `rev-x/fab/`, `rev-x/img/` | generated: KiCad project, schematic, board; JLCPCB Gerbers, BOM, CPL; renders |
| `rev-c/` | rev C-A's and C-B's shared circuit (carrier.py), floor plan, layout, SOM interface (som.py, som-pinout.csv, check_som_fp.py), FPGA pin assignment (pinmap.py) and design.md |
| `kit/` | the generators and tools all revisions share (below), and the circuits and layout rev B and rev C share: `circuits.py` (the supplies, the ADV7181D front end with the VGA and SCART sync inputs, the PCM1808, the S/PDIF input, the XIAO, the ADV7511, the HDMI receptacle), `adv7181d_layout.py` and `tmds_layout.py` (their placement and fanout) |
| `lib/` | LCSC symbols and footprints, all revisions' (3D models not in git) |
| `refs/` | data sheets and reference designs (not in git) |

## Making a revision

Everything is generated from `rev-x/board.py`; edit that (and `gen_pcb.py` for placement), not
the KiCad files. On a machine with KiCad 9 (here: the build host), from this directory:

| Step | Command | Makes |
|---|---|---|
| check the design | `python3 rev-b/board.py` | errors: one-pin nets, chip pins left open that should not be |
| schematic | `python3 kit/gen_sch.py rev-b` | `rev-b/av-board-b.kicad_sch`, project and library tables |
| ERC | `kicad-cli sch erc rev-b/av-board-b.kicad_sch` | (clean) |
| netlist check | `kicad-cli sch export netlist -o /tmp/av.net rev-b/av-board-b.kicad_sch && python3 kit/check_netlist.py rev-b /tmp/av.net` | schematic = board.py, pin by pin |
| PCB | `python3 rev-b/gen_pcb.py --route` | `rev-b/av-board-b.kicad_pcb`: placed, fanned out, routed, ground poured, the revision's own pass (rev B: the TMDS pairs laid again), then whatever is left unconnected finished by mazeroute.py (`--complete`). Router: Freerouting (`FREEROUTING=1.9.0` default, under a private Xvfb; `2.5.0` headless), or DeepPCB (`ROUTER=deeppcb MINUTES=60`, API key in `~/.config/deeppcb/key`), or any session (`SES=file.ses`); a session from elsewhere gets a Freerouting finishing pass with its copper fixed (`FINISH=0`: none); `PCB=path` for a trial board elsewhere; `--silk`: the silkscreen pass again on a routed board |
| finishing | `kicad-cli pcb drc ...`, then for each connection left: `python3 kit/mazeroute.py dump BOARD REF.PAD REF.PAD /tmp/m.json [PARTNER_NET] && ~/tools/eda-venv/bin/python kit/mazeroute.py route /tmp/m.json /tmp/p.json && python3 kit/mazeroute.py apply BOARD /tmp/p.json` | a grid router (A*) for what Freerouting leaves: F/In2/B (`MAZE_LAYERS`, `MAZE_WIDTH`), new vias where they fit, our clearances; with `MAZE_SOFT=1` it may cross other signal nets' unlocked copper at a cost, and apply takes up what it crossed (rip-up). `gen_pcb.py --complete` does all this for whatever DRC lists, the rip-up last; DRC after |
| a router's result for some nets | `python3 kit/sesgraft.py BOARD x.ses PREFIX` | those nets' copper from a session added to a routed board |
| placement check | `python3 kit/placecheck.py rev-b [--min 8]` | the small parts' signal pins far from the rest of their net (a part by the wrong anchor); `gen_pcb.py` itself prints the crossings left in each header bus |
| analog isolation | `python3 kit/xtalk.py rev-b` | each analog line's digital neighbours within 1 mm on its layer: the closest gap, how far they run within 1 mm and within 0.5 mm |
| renders | `python3 kit/render.py rev-b` | `rev-b/img/`: a 3D view and a top view (KiCad's raytracer; models from `fetch_lib.sh` and `kit/fetch_3d.py`) |
| picture | `python3 kit/snap.py BOARD out.png` | a PNG of the board (needs PyMuPDF in `~/tools/eda-venv`) |
| DRC | `kicad-cli pcb drc BOARD` | |
| fab files | `python3 kit/gen_fab.py rev-b` | `rev-b/fab/`: Gerbers + drill zip, JLCPCB BOM and CPL, all from the board's lower-left corner; a BOM + CPL per assembly variant (`VARIANTS` in board.py: parts left for hand soldering) |
| parts library | `./kit/fetch_lib.sh` | `lib/`: LCSC symbols/footprints (committed) and 3D models (not) |

`kit/parts.py` is what board.py is written with (parts, LCSC numbers, the Console's headers);
`kit/pcbkit.py` the PCB generator (placer, fanout, rules, planes, routing passes, silkscreen);
`kit/sexp.py` reads and writes KiCad's s-expression files; `kit/fix_lib.py` makes the LCSC
symbols' pins passive (their EasyEDA pin types are arbitrary); `kit/merge_sym.py` adds a symbol
whose EasyEDA name clashes with one already there; `kit/deeppcb.py` drives DeepPCB.

## The host's headers (Sipeed's schematic Tang_138K_Console_V32001C, sheet FPGA_EXT_CONN)

J9 ("SDRAM0") and J10 ("SDRAM1"): 2x20, 2.54 mm, SMD male headers, parallel, 49 mm apart (J9 along
the top edge at y = 30 mm, J10 along the bottom at y = 79 mm in Sipeed's PCB coordinates, both
x = 105-153 mm, pin 1 at opposite ends). Each carries 38 FPGA I/O at 3.3 V; pin 11 is +5 V,
pin 12 GND; no 3.3 V. Pins 29/30 (EXIO0/1) reach the DM0/DM1 balls through 0 R links.

- J9: all FPGA bank 2. Clock-capable balls on it: D19/E19 (SGCLK_0), C19/C18 (MGCLK_0),
  C17/D17 (MGCLK_1), B18/B17 (SGCLK_1).
- J10: all FPGA bank 4. Clock-capable: V20/U20 (SGCLK_5), Y19/Y18 (MGCLK_4); P19 is SSPI_CLK.

The full pin -> ball map is taken from the schematic's SOM connector sheets (pages 4-6).

## Reference documents

In `refs/` (not in git), shared by the revisions. Every circuit on the boards follows these.

| File | What | From |
|---|---|---|
| ADV7842_datasheet_adi.pdf | ADV7842 data sheet, Rev B: supplies, currents, crystal (28.63636 MHz), 256-ball map | analog.com data-sheets/ADV7842.pdf |
| UG-214_ADV7842_hardware.pdf | ADV7842 Hardware User Guide: analog input configuration (6.2.1), reset, pixel port, PCB layout recommendations, recommended decoupling (Fig. 168, 179), 75 R input termination (Appendix B) | analog.com user-guides/UG-214.pdf (via docs.ampnuts.ru mirror) |
| HDMI_RX_PowerSupplies_RevA_050411.pdf | ADI "PCB Layout and Power Supply Design Recommendations for HDMI RX Products", Rev A (April 2011): a ferrite per supply rail (Murata NFE61PT472C1H9), 10 nF + 100 nF per pin, 10 uF bulk on AVDD/CVDD/PVDD, LDOs not switchers, 3.3 V before 1.8 V; Fig. 2 the reference LDO supply (10 uH + 10 uF after the 1.8 V LDO, 100 nF + 1 uF on AVDD/CVDD/PVDD, 100 nF on DVDD/DVDDIO/TVDD, 1.8 V enable from 3.3 V via 100 k / 470 nF) | ADI EngineerZone, ADV7842 design support files (downloaded by hand) |
| adv7844ebz/ | ADI's ADV7844 evaluation board ("ADV7844 Input Module", Rev C, July 2010): schematic (11 sheets, image-only PDF), manufacturing BOM (.xls), IPC-356 netlist, Gerbers. The main circuit reference: see reference-notes.md | ADI EngineerZone, ADV7844 evaluation board info (downloaded by hand) |
| ADV7844-VER.5.8c.txt | ADI's recommended register scripts for the ADV7844 (v5.8c, 2012), the ADV7842's sibling: I2C write sequences per input mode, configuring the receiver (0x40 IO, 0x44 CP, 0x4C AFE ...) and the ADV7511 (0x72) together; "CP YPbPr SD/ED/HD" are the PS2's component modes. For bring-up; the ADV7842's own file (Rev 1.9) is the exact match | ADI EngineerZone, ADV7842 design support files (downloaded by hand) |
| UG-206_ADV7842_software.pdf | ADV7842 software (register) guide | analog.com user-guides/UG-206.pdf |
| UG-235_eval_ADV7842_7511.pdf | EVAL-ADV7842-7511 user guide (placement drawing, jumpers; no schematic) | farnell.com mirror of UG-235 |
| ADV7511_hardware_users_guide_RevD.pdf | ADV7511 Hardware User's Guide, Rev D: 100-lead LQFP pinout, input/output connections, HPD, DDC, PLL circuit, power domains and filtering, example schematic (Fig. 27) | analog.com user-guides/ADV7511_Hardware_Users_Guide.pdf |
| ADV7511_programming_guide.pdf | ADV7511 Programming Guide | analog.com user-guides |
| ADV7511_HDMI_designs_appnote.pdf | HDMI-enabled designs using the ADV7511 | analog.com evaluation-documentation |
| ADV7511W_hardware_users_guide_RevA.pdf | ADV7511W (64-lead) guide: cross-check only, its pinout does not apply | digikey.com |
| ADV7511_datasheet.pdf | ADV7511 short data sheet | docs.ampnuts.ru mirror |
| ADV7181D_datasheet.pdf | ADV7181D data sheet, Rev C (2024): 64-lead LFCSP pinout, supplies, component formats (525i-1080i), typical connection diagram (Fig. 9: ADC reference caps, loop filter, crystal), pixel output modes (rev B) | analog.com data-sheets/ADV7181D.pdf (downloaded by hand) |
| AN-1260.pdf | Crystal design considerations for ADI video decoders and HDMI parts | docs.ampnuts.ru mirror |
| AN-1270.pdf | ADV7511-based video generators | docs.ampnuts.ru mirror |
| AN-1143.pdf | ADV7511 HDCP 1.1 enable/disable | docs.ampnuts.ru mirror |
| PCM1808_datasheet.pdf | TI PCM1808 (Rev B): typical application circuit | ti.com |
| console138k_C.pdf | Sipeed Tang_138K_Console_V32001C schematic | dl.sipeed.com TANG/Console/02_Schematic |
| ibom_C.html | Sipeed's interactive BOM for board 32001C (part positions) | dl.sipeed.com TANG/Console/03_Designator_drawing |
| console/ | the Tang Mega 138K SOM's drawing, the NEO Console's schematic, the Retro Console's STEP model | dl.sipeed.com |
| RCJ-01.pdf | CUI RCJ-01x RCA jacks: footprint, colour codes | cuidevices.com |
| tlv62569.pdf, tps7a7001.pdf, tps7a20.pdf, tpd1e05u06.pdf, tpd4e05u06.pdf | TI: the buck, the LDOs, the ESD diodes and arrays | ti.com |
| sn65dp159.pdf | TI SN65DP159 retimer, SLLSEJ2G (rev C-B) | ti.com |
| MS5351M_datasheet_V1.4.pdf | Relmon MS5351M clock generator, V1.4 (Chinese): supplies, crystal, outputs (rev C) | LCSC (atta.szlcsc.com) |
| gowin/DS1239E.pdf | Gowin GW5AST data sheet DS1239: I/O standards, transceiver DC and reference clock characteristics (rev C) | cdn.gowinsemi.com.cn |

Still wanted, for cross-checking: the ADV7842 recommended settings (Rev 1.9) and the ADV7511
evaluation schematic (ADI's design support files).

What these documents say, circuit by circuit: [rev-a/reference-notes.md](rev-a/reference-notes.md) (ADV7842, ADV7511) and each revision's design.md.

Fetching: analog.com serves its PDFs to `wget` (HTTP/1.1); curl over HTTP/2 stalls. EngineerZone
(ez.analog.com) refuses automated clients ("Access Denied"): its files are downloaded by hand.
Sipeed's file server lists folders with a POST to `https://dl.sipeed.com/fileList/<path>`.
