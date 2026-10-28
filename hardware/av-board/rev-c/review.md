# Rev C: review against the data sheets (2026-10-25)

Rev C-A and C-B share rev B's circuits (kit/circuits.py: the supplies, the ADV7181D front end, the
PCM1808, the S/PDIF input, the XIAO block, the ADV7511, the HDMI receptacle), reviewed in
[../rev-b/review.md](../rev-b/review.md); this covers what rev C adds, checked against each part's
own document for being inside its limits with margin. Sources: [MS] MS5351M data sheet V1.4
(Relmon), [DS1239] Gowin GW5AST data sheet, [TI-DP159] SN65DP159 (SLLSEJ2G), [TI-BUCK] TLV62569, [TI-LDO] TPS7A7001,
[TI-XLAT] SN74LVC8T245 and SN74AVC4T245, [HWG] ADV7511 hardware user's guide Rev D, the Tang
Console's schematic and iBOM (refs/console138k_C.pdf, refs/ibom_C.html), Hirose's and JLCPCB's part
data; for the HDMI layout [TI-AR7] TI SPRAAR7J High-Speed Interface Layout Guidelines (HDMI among
its signals), [TI-HDMI] TI's HDMI Design Guide (the HDMI specification's skew budgets) and [AN837]
Intel AN 837, HDMI board design tips (the HDMI specification itself and its compliance tests are
for HDMI Adopters only). **Fixed** marks what this review changed.

## The SOM and the 5 V input

| Check | Requirement | Board | Verdict |
|---|---|---|---|
| Receptacle footprints | the Console's pads and numbering (pin 2k-1 facing 2k) | DF40HC-*-SOM made from EasyEDA's outline with the Console's pads (EasyEDA's own number the rows 1-50 / 51-100); check_som_fp.py: 280 of 280 pads at the Console's place and number | OK |
| SOM supply | 5 V on six contacts (J22 89-99), 0.3 A each [Hirose DF40HC(3.0)]: 1.8 A | the Console's arrangement; 1.2 mm track from the fuse, then along the pads; 2 x 47 uF + 4 x 22 uF | OK: the SOM's budget is the Console's |
| USB-C sink | Rd 5.1 k on each CC [USB Type-C 4.11]; a sink with Rd alone draws no more than the source advertises | 5.1 k 1 % each; the board draws up to about 2 A and cannot read the advertisement | OK with a 5 V / 3 A USB-C supply (README, design.md); not a computer's port |
| Input protection | VBUS 5 V +-5 %; the SOM's input; the TVS at the receptacle [TI-ESD] | SMF5.0A (5 V standoff, 6.4 V breakdown, 9.2 V clamp at 21.7 A), then a 3 A hold / 5 A trip PTC (16 V, 10-50 mR: 0.1 V at 2 A worst case); the TVS had landed 10 mm away (the jacks either side of the USB-C left the placer no nearer room) | **Fixed**: laid in order under the receptacle, TVS (4.3 mm from the VBUS pins) then fuse |
| 5 V input copper | the board's about 2 A from the USB-C to the fuse | was left to the router at 0.25 mm: about 1 A at a 10 C rise [IPC-2221], 27 mR and 0.1 W at 2 A in its 14 mm (second review, 2026-10-26) | **Fixed**: laid before routing (layout.py vbus_in): 0.7 mm from each VBUS pad (each carries half), 1.2 mm from the TVS into the fuse, as the spine beyond it; the CC lines cross on B.Cu |
| Buck layout | the input and output capacitors and the inductor as close to the IC as possible [TI-BUCK 10.1] | the input capacitor was placed by EN (pin 1, on +5 V too), across the package from VIN: 5.5-6.5 mm (second review) | **Fixed**: each regulator capacitor names its pin (board.py `at=`, placed before the rest): at VIN, 2.9 mm (C-B's 1V1 buck too); the feedback divider next, 3.7-4.5 mm (was 2.6: VIN's capacitor first, FB being its neighbour); the output capacitor at the inductor's output. C-B's 1V1 buck (U7) places its inductor and output capacitor before the divider: in the 3V6 bucks' order the divider's 6.8 pF took the inductor's place beside SW, and the inductor went above the chip with its SW pad turned away (10.7 mm of SW track, FB's copper 0.2 mm from it, in this review's first route). Routed: 4.0-4.1 mm of SW track, FB's copper 2.5-3.0 mm from it, every buck |
| LDO capacitors | input and output capacitors at the device, as its layout example [TI-LDO 10.1, Fig. 8] | 3.3-6.5 mm | **Fixed** (`at=`): 2.6-3.5 mm |
| Configuration straps | MODE[2:0] = 001 (MSPI), as the Console | MODE0 1 k up, MODE1/2 5.1 k down; PUDC_B, CFGBVS as the Console | OK |
| RECONFIG_N | open drain, pulled up | 10 k up, a button to GND; was also on the XIAO's D4: an ESP32's pin glitching at its boot could reload the FPGA | **Fixed**: the button's alone (JTAG reloads the FPGA too) |
| DONE, READY | open drain | 10 k up, each gating a 2N7002 for its LED (the LED does not load the line) | OK |
| Standoffs | M2, 3 mm (the receptacles' stack) | plated 2.2 mm holes, 3.8 mm ring to GND; spacers and screws by hand (JLCPCB's M2 x 3 mm SMD nut has a 5.6 mm flange, which would sit on the receptacles) | OK |

## Clock generator (MS5351M)

| Check | Requirement | Board | Verdict |
|---|---|---|---|
| Core supply | VDD 2.7-3.3 V [MS: recommended operating conditions] | was 2.5 V, as the Console runs it | **Fixed**: an ME6211C30 (3.0 V) of its own from 3V3 (3V3 itself, 3.31 V nominal, would pass 3.3 V at its LDO's tolerance) |
| Output supply | VDDO 1.71-1.89, 2.25-2.75 or 3.0-3.6 V, independent of VDD [MS] | C-A 3V3; C-B 2V5 (ME6211C25), the Console's reference-clock drive | OK |
| CLK2 into the FPGA | VOH >= VDDO - 0.6 V [MS]; LVCMOS33 VIH 2.0 V [DS1239] | C-A: 2.7 V min; C-B: 1.9 V min at the data sheet's floor, about 2.45 V typical | OK on C-A; C-B: typically, or the input as LVCMOS18UD33 (VIH 1.17 V) [DS1239 2.3]; C-B's output timing comes from the transceivers |
| Crystal | 25 or 27 MHz, load 6-12 pF, ESR <= 150 R [MS]; internal load capacitance set over I2C | was a 12 pF crystal against the chip's 10 pF setting (about 10 ppm high) | **Fixed**: 25 MHz 10 pF (HY25MSMD2016EA1R30, +-10 ppm, 45 R), the Console's load |
| I2C | pull-ups >= 1 k; VIH 0.7 x the bus supply, inputs to 3.6 V [MS] | was 4.7 k to 2V5 | **Fixed**: 4.7 k to 3V3, the FPGA's bus level |
| Reference clock (C-B) | 20-800 MHz, 40-60 % duty [DS1239 Table 3-22]; AC coupled | CLK0 and CLK1 (programmed as its inverse) through 2.2 R and 100 nF each into REFCLK0, the Console's network (its REFCLK1). Laid by the generator as a pair, 0.2 mm lines 0.2 mm apart, no vias: 24.4 and 26.5 mm from the MS5351M's pins (13 ps apart), 20.8 and 22.1 mm of that from the capacitors to J21; the resistors at the pins and the capacitors after them side by side; the router keeps other lines 30 mil and other clocks 50 mil off (were: autorouted as two lines, 33-39 mm with two vias each, 0.15 mm from the PCM1808's bit clock: the placer had put its parts 20-30 mm off) | OK |
| Decoupling | 100 nF at VDD and VDDO; LDOs >= 1 uF in and out | 100 nF at each; 1 uF in, 10 uF out at each LDO | OK |
| Its LDOs' place | by the chip they feed (their own LDOs: rails short and quiet) | were 73-80 mm off, by the XIAO's translators (the placer's rule for a part on supplies only: by the chip before it in board.py), their 3V0 and 2V5 90-113 mm of track (second review, 2026-10-26) | **Fixed**: each LDO by the MS5351M pin it feeds (`at=`, placed after that pin's 100 nF), 4-5 mm |

## The XIAO and JTAG

| Check | Requirement | Board | Verdict |
|---|---|---|---|
| Back-powering | an unpowered FPGA's pins must not be driven (a XIAO on its own USB with the board off) | was 470 R in each line: 6 mA a pin, 11 lines | **Fixed**: SN74LVC8T245 (the XIAO's seven outputs) and SN74AVC4T245 (the FPGA's four), A sides on the XIAO's 3V3 pin, B sides on the board's: either supply off puts both ports at high impedance, inputs 5.5 V tolerant unpowered [TI-XLAT: VCC isolation, Ioff] |
| JTAG header coexistence | a cable on J16 must not fight the XIAO's drivers | with the XIAO out its 3V3 is 0 V (100 k down): the translators release the lines | OK; with the XIAO in, J16 is not to be used (README) |
| Translator control | DIR and OE referenced to VCCA [TI-XLAT] | U22 DIR to the XIAO's 3V3 (A to B), U23 1DIR/2DIR to GND (B to A), OE low; an unused input to GND | OK |
| Floating inputs | none [TI-XLAT] | 10 k: the XIAO's side (its pins are inputs while it boots) TCK low, TMS/TDI high (the TAP held in reset), chip select, TX and SCK high, MOSI low; the FPGA's side TDO, MISO, RX and the interrupt high, chip select and the JTAG inputs again (empty socket) | OK |
| SPI framing | a chip select | was SCK/MISO/MOSI only | **Fixed**: D4 is the chip select (from RECONFIG_N), D5 the interrupt (active low) |
| Edge rates | JTAG, SPI up to about 20 MHz | 470 R x 10-15 pF (5-7 ns) was; now the translators' 2-4 ns edges, the four lines to the XIAO through 470 R (about 4 ns) | OK |
| Strapping pins | the XIAO's straps must read right at boot: on a C3 GPIO2 (D0) pulled up, GPIO8 (D8) high for its download boot, GPIO9 (D9) high, or low with BOOT held [ESP32-C3 DS Table 3-3] | the S3's straps are not on D0-D10; a C3's were held wrong: TCK's pull-down on D0, SCK's on D8, and its BOOT button shorted U23's output on D9 | **Fixed**: TMS (pulled up) on D0 and TCK on D1, SCK pulled up, 470 R between U23 and the XIAO's pins |

## HDMI

| Check | Requirement | Board | Verdict |
|---|---|---|---|
| ADV7511 input (C-A) | input ID 0, 24-bit RGB 4:4:4: R D35-D28, G D23-D16, B D11-D4, the rest to GND [HWG Table 5, 6.1.1] | as required | OK |
| ADV7511 place (C-A) | short pixel bus; nothing digital by the analog inputs | was 45 mm from J21, its bus climbing past the PCM1808's inputs (0.3 mm from RCA_R for 14 mm) | **Fixed**: beside J21, the bus 7 mm across; the FPGA pins matched to the chip's pins round its body, each receptacle row's lines in order (pinmap.py) |
| DP159 supplies (C-B) | VCC 3.0-3.6 V; VDD 1.0-1.27 V, about 0.25 A [TI-DP159 7.3] | 3V3; 1V1 from a TLV62569: 0.6 V x (1 + 82.5/100) = 1.095 V [TI-BUCK Eq. 2], 6.8 pF, 2.2 uH, 10 uF | OK |
| DP159 decoupling | VCC 10 uF + 0.1 uF + 0.01 uF, VDD 10 uF and 0.1 uF per pin [Fig. 33], "as close to VCC and VDD pins as possible" [12.2, Fig. 36] | the values as listed; placed every capacitor of a rail by its first pin: 6.4-14.5 mm from five of its seven pins (second review, 2026-10-26) | **Fixed**: each capacitor names its pin (board.py `at=`), placed before the rest: 0.1 uF at 2.2-4.7 mm |
| ADV7511 decoupling (C-A) | 0.1 uF at each supply pin "as close to the supply pin as possible", adjacent pins sharing; the 10 uH + 10 uF filters "as close to the ADV7511 as possible" [HWG 7.1, Fig. 23] | every 0.1 uF of a rail by its first pin, 3.4-18.0 mm from the pins; the filters by the 1V8B LDO (second review) | **Fixed** (`at=`): 2.0-6.0 mm (AVDD 34 and 41, between the TMDS pairs, beside the pairs: decoupling stays on the top); the filters 3-9 mm from the chip |
| Main link in | AC coupled, 75-200 nF, 100 nF recommended [TI-DP159 10.2.1] | 100 nF 0402 per line, 7 mm of 0.2/0.2 mm line (about 105 R differential) | OK |
| Swing | Vsadj 7.06 k [TI-DP159 10.2.1] | 7.06 k 0.5 % | OK |
| OE | a 0.1 uF capacitor to GND; changes state after the supplies [10.2.1] | 100 nF, driven by the FPGA | OK |
| Control | I2C mode: I2C_EN/PIN high; A0 (EQ_SEL), A1 (HDMI_SEL, weak internal pull-down) address bits [Pin Functions] | I2C_EN 10 k up, A0 10 k down, A1 open; 4.7 k pull-ups on SCL_CTL/SDA_CTL | OK |
| HPD | HPD_SNK in (fail-safe), HPD_SRC out [Pin Functions] | the receptacle's HPD (10 k down) in; HPD_SRC to the FPGA | OK |
| DDC | passed through, both sides pulled up [Fig. 33] | 2 k to HDMI 5 V on the receptacle's side, 2 k to 3V3 on the FPGA's | OK |
| CEC (C-B) | a powered-off device must not load the bus (leakage < 1.8 uA [HWG Fig. 26]) | the FPGA's pin through a 2N7002 (gate at 3V3): with the board off the gate is at 0 V and the body diode reversed | OK |
| TMDS output run (C-B) | the driver is made for 2 to 3 inches of board trace and connector [TI-DP159 10.2.2] | was about 79 mm (the receptacle at the board's right) | **Fixed**: C-B's receptacle in the coax jack's place, 25.5 mm left of C-A's (both S/PDIF inputs on rev B's header): 49.3-59.0 mm of trace, 1.9-2.3 inches, and the connector |
| TMDS skew (C-B) | intra-pair 0.15 Tbit (25 ps), inter-pair 0.2 Tchar (337 ps) at 5.94 Gb/s (HDMI 2.0 source) [TI-HDMI] | 0.83 mm (5 ps) within a pair, 8.8 mm (55 ps) between pairs | OK |
| TMDS layout (C-B) | on the top layer, no vias, a solid ground plane next to them [TI-DP159 12.1]; pairs 5 W apart, other lines 30 mil off, clocks 50 mil; 1.5 W from plane voids; one width; turns of 135 degrees or wider [TI-AR7 3.1-3.4, 3.11]; at most two vias a line [AN837] | were 3 W apart (0.75 mm: the ESD arrays' pins held the pairs together all the way); 3V3, 2V5, +5V and DP_OE vias beside the outer lines, their antipads in In1 0.01-0.21 mm from them | **Fixed**: the pairs 1.27 mm apart along their run, closing to the arrays' 0.75 mm within the receptacle's break-out (kit/tmds_layout.py TMDS_SPREAD); rule areas beside and between them keep out other tracks, vias and the ground pour (rev-cb/gen_pcb.py hdmi_keepouts); F.Cu, no vias, 0.25 mm, 135-degree turns. kit/hdmi_audit.py leaves DP_OE (static) 0.74 mm from the outermost line outside its corner and two other vias' antipads (HPD by the DP159, the PCM1808's bit clock by J21) within packages' break-outs, where pins put other nets beside a pair [TI-AR7 3.3] |
| Parts on the lines (C-B) | 0402 or smaller, symmetric, the plane voided under their pads two layers deep [TI-AR7 3.10]; ESD at the connector, flow-through, 60 % voids under its pads [3.14] | 0402 AC capacitors side by side, the arrays flow-through at the receptacle; no voids | **Fixed**: In1 and In2 voided under every AC capacitor pad and under 60 % of the arrays' TMDS pads |
| Near the lines (C-B) | not near crystals, clock generators, switchers or mounting holes [TI-AR7 3.2] | the MS5351M's crystal 1.6 mm from DP_D2_P | **Fixed**: the crystal held up against the MS5351M, 3.1 mm off; the switchers 8.8 mm and more. **Open**: H2's hole edge 2.1 mm from the TMDS clock pair (the spread brought them 0.85 mm nearer; moving the hole changes the board's mounting) |
| Impedance (C-B) | 100 R +-10 % [AN837] | 0.25 mm lines 0.25 mm apart on F.Cu over In1 (JLC04161H-7628, 0.21 mm of 7628): about 103 R by IPC-2141 | to confirm in JLCPCB's impedance calculator at ordering |
| TMDS ESD | < 0.6 pF a line [HWG 6.3.2.1], 6 Gb/s | TPD4E05U06, 0.5 pF, flow-through, rev B's | OK |
| DDC/HPD/CEC ESD (U8) | as close to the connector as possible [TI-ESD] | was 48-59 mm from the receptacle, by the ADV7511 or the DP159 (the placer put parts by the IC on their signal nets) | **Fixed**: ESD parts placed first, at their connectors (kit/pcbkit.py): 2.5-3.7 mm |
| S/PDIF ESD | at each connector [TI-ESD] | one TPD4E05U06 for C-A's coax RCA (J14) and optical header (J13), 25 mm apart | **Fixed**: a TPD1E05U06 at each input's pin (C-B: both on rev B's header, J13) |

## Layout (after routing)

Routed as rev B (rev-b/design.md "Routing"): the analog lines and references kept 0.5 mm from
digital and clock lines by the router, the ESD parts at their connectors, rip-up for the last gaps.

| Check | C-B | C-A |
|---|---|---|
| DRC | no errors, no unconnected items (warnings: only footprints that differ from the library, on purpose: their silkscreen cut back for JLCPCB (below), local clearances) | the same |
| Silkscreen | every label on the board and in sight once the parts are fitted (kit/pcbkit.py silkscreen). Were: the jacks', HDMI's and USB-C's labels past the back edge (not printed), the S/PDIF header's pin labels printed over one another, the JTAG pins' run together and under the board's name. **Fixed**: each label clear of pads, other texts, the parts' bodies and the SOM; a header's pin labels beside its pins (a column) or alternately above and below (a crowded row), their room kept free of parts at placement. **Fixed** too, to JLCPCB's limits (lines and strokes 0.15 mm, text 1 mm high with a 1:6 stroke, 0.15 mm from pads): designators 1 mm (were 0.8), the pin labels too (were 0.9), every line 0.15 mm wide (the library outlines were 0.06-0.12 mm); the parts' outlines cut back at pads, the board's edge, texts and one another, EasyEDA's 0.12 mm pin 1 dots (too small to print) taken out (kit/pcbkit.py silk_tidy): no silkscreen warnings left in DRC; 41 designators shown, none on another part's body. The XIAO's way in printed beside J12 ("XIAO, USB >", reading down to the USB-C's end: that of D0 and 5V, the sockets' pin 1); J17's pin labels beside both its columns and its name ("DEBUG") above it, room kept at placement (rev-cb/gen_pcb.py reserved()); each test pad labelled with its rail | the same (the optical header's labels clear of parts by the placement itself); 51 designators |
| ERC, netlist | clean; schematic = board.py, 1064 pins | clean; 1063 pins |
| SOM receptacles | 280 of 280 pads at the Console's place and number (check_som_fp.py) | the same footprints |
| ADV7181D to the SOM | LLC 22.9 mm (two vias); data 20.9-48.8 mm (74.25 MHz at most: about 0.2 ns spread in 13.5 ns; the FPGA's input delays can trim it) | LLC 22.9 mm (two vias); data 20.6-56.1 mm (about 0.25 ns spread) |
| TMDS | DP159 to the receptacle 49.3-59.0 mm, no vias, laid on F.Cu (TI: 2-3 inches with the connector); 0.83 mm (5 ps) within a pair, 8.8 mm (55 ps) between pairs, against HDMI 2.0's 25 and 337 ps at 5.94 Gb/s; the pairs 1.27 mm apart along their run (5 W), other lines, vias and the ground pour kept off beside and between them; the FPGA's lanes to the DP159 5.8-6.8 mm and their capacitors, no vias, 0.46 mm (3 ps) within a pair; REFCLK0 laid as a pair, 20.8 and 22.1 mm (8 ps), no vias (the HDMI layout rows above: TI's rules, kit/hdmi_audit.py) | ADV7511 to the receptacle 74.9-83.6 mm, no vias, laid on F.Cu; 0.8-0.9 mm (6 ps) within a pair, 8.7 mm (55 ps) between pairs, against 101 ps and 1.35 ns at 1080p60 (1.485 Gb/s); about 1 dB of loss |
| SOM to the ADV7511 | | pixel clock 11.4 mm, two vias; RGB 10.3-49.3 mm (about 0.25 ns spread in 6.7 ns at 148.5 MHz; the FPGA's output delays can trim it) |
| Video inputs | Y 27.5, Pb 22.6, Pr 34.0, SCART sync 42.1 mm; VGA R 39.6, G 80.9 (AIN2, past the references), B 46.5 mm | Y 32.5, Pb 27.6, Pr 35.4, SCART sync 43.5 mm; VGA R 37.4, G 75.1, B 37.3 mm |
| Interference | nothing digital within 0.5 mm of an analog line but XTAL1 beside LLC along the pins' own pitch (0.36 mm, 2.2 + 2.0 mm) and two of RCA_SYNC's vias 0.27 mm from the VGA DDC clock (the DDC static while video runs; Freerouting places them so in most routes: it does not hold its class rule against vias); within 1 mm: the DDC clock 0.53 mm from RCA_SYNC's track for 0.8 mm and 0.71 mm from VGA G for 5.1 mm, the ADV7181D's PLL filter (ELPF_RC) 0.69 mm from IN_C0 for 0.9 mm and its PVDD 0.58 mm from IN_C1 for 0.5 mm (both decoupled or filtered at the chip), the PCM1808's 4.5 V supply 0.94 mm from its 12 MHz system clock for 0.7 mm; nothing digital within 1 mm of the audio inputs. Vias counted too (KiCad's DRC with the 0.5 mm rule: kit/xtalk.py measures tracks only) | nothing digital within 0.5 mm of an analog line but XTAL1 beside LLC along the pins' own pitch (0.36 mm, 2.2 + 1.8 mm), the crystal's XTAL 0.50 mm from IN_C1 for 0.2 mm, and two of RCA_SYNC's vias 0.27 mm from the VGA DDC clock (found later, by KiCad's DRC with the rule: kit/xtalk.py does not measure vias; the DDC static while video runs); within 1 mm: the PCM1808's right input 0.69 mm from its data output for 1.6 mm, its 4.5 V supply 0.85 mm from its 12 MHz system clock |
| Doubled routes | none: the prune pass takes up copper laid twice, on another track or beside one (an earlier route had VGA_G's run from R31 to U19 laid twice, a via each: KiCad's copper sliver warning, no position given); kit/doubled.py's 0.5 mm of HDMI_HPD is its two branches side by side at the ESD array's flow-through pads | none: the prune pass takes up copper laid twice (here 218 segments lying on another track) |
| Vias | 89 at 0.4/0.2 mm (SOM ground pads, ESD arrays, references), 983 at 0.5/0.3 | 78 at 0.4/0.2 mm, 1446 at 0.5/0.3 |
| Assembly | every part on the top | the same |
| Test access | the SOM hides the FPGA's pins: J17, a 2 x 8 header left of the SOM, with the ADV7181D's, the DP159's and the clock generator's I2C, six spare FPGA pins (dbg0-dbg5, J22's nearest), a 3.3 V reference and ground (rev-cb/README.md), every pin but ground through 220 R by the header (a slipped probe or a wrong wire: at most 15 mA into a pin; VREF shorted to ground beside it: 50 mW in its 62.5 mW resistor, the rail untouched); a bare test pad on each rail by its regulator, labelled, two for ground | none (C-A not changed) |

