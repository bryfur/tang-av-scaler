# Rev C: review against the data sheets (2026-10-25)

Rev C-A and C-B share rev B's circuits (kit/circuits.py: the supplies, the ADV7181D front end, the
PCM1808, the S/PDIF input, the XIAO block, the ADV7511, the HDMI receptacle), reviewed in
[../rev-b/review.md](../rev-b/review.md); this covers what rev C adds, checked against each part's
own document for being inside its limits with margin. Sources: [MS] MS5351M data sheet V1.4
(Relmon), [DS1239] Gowin GW5AST data sheet, [TI-DP159] SN65DP159 (SLLSEJ2G), [TI-BUCK] TLV62569,
[TI-XLAT] SN74LVC8T245 and SN74AVC4T245, [HWG] ADV7511 hardware user's guide Rev D, the Tang
Console's schematic and iBOM (refs/console138k_C.pdf, refs/ibom_C.html), Hirose's and JLCPCB's part
data. **Fixed** marks what this review changed.

## The SOM and the 5 V input

| Check | Requirement | Board | Verdict |
|---|---|---|---|
| Receptacle footprints | the Console's pads and numbering (pin 2k-1 facing 2k) | DF40HC-*-SOM made from EasyEDA's outline with the Console's pads (EasyEDA's own number the rows 1-50 / 51-100); check_som_fp.py: 280 of 280 pads at the Console's place and number | OK |
| SOM supply | 5 V on six contacts (J22 89-99), 0.3 A each [Hirose DF40HC(3.0)]: 1.8 A | the Console's arrangement; 1.2 mm track from the fuse, then along the pads; 2 x 47 uF + 4 x 22 uF | OK: the SOM's budget is the Console's |
| USB-C sink | Rd 5.1 k on each CC [USB Type-C 4.11]; a sink with Rd alone draws no more than the source advertises | 5.1 k 1 % each; the board draws up to about 2 A and cannot read the advertisement | OK with a 5 V / 3 A USB-C supply (README, design.md); not a computer's port |
| Input protection | VBUS 5 V +-5 %; the SOM's input; the TVS at the receptacle [TI-ESD] | SMF5.0A (5 V standoff, 6.4 V breakdown, 9.2 V clamp at 21.7 A), then a 3 A hold / 5 A trip PTC (16 V, 10-50 mR: 0.1 V at 2 A worst case); the TVS had landed 10 mm away (the jacks either side of the USB-C left the placer no nearer room) | **Fixed**: laid in order under the receptacle, TVS (4.3 mm from the VBUS pins) then fuse |
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
| Reference clock (C-B) | 20-800 MHz, 40-60 % duty [DS1239 Table 3-22]; AC coupled | CLK0 and CLK1 (programmed as its inverse) through 2.2 R and 100 nF each into REFCLK0, the Console's network (its REFCLK1) | OK |
| Decoupling | 100 nF at VDD and VDDO; LDOs >= 1 uF in and out | 100 nF at each; 1 uF in, 10 uF out at each LDO | OK |

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
| DP159 decoupling | VCC 10 uF + 0.1 uF + 0.01 uF, VDD 10 uF and 0.1 uF per pin [Fig. 33] | as listed | OK |
| Main link in | AC coupled, 75-200 nF, 100 nF recommended [TI-DP159 10.2.1] | 100 nF 0402 per line, 7 mm of 0.2/0.2 mm line (about 105 R differential) | OK |
| Swing | Vsadj 7.06 k [TI-DP159 10.2.1] | 7.06 k 0.5 % | OK |
| OE | a 0.1 uF capacitor to GND; changes state after the supplies [10.2.1] | 100 nF, driven by the FPGA | OK |
| Control | I2C mode: I2C_EN/PIN high; A0 (EQ_SEL), A1 (HDMI_SEL, weak internal pull-down) address bits [Pin Functions] | I2C_EN 10 k up, A0 10 k down, A1 open; 4.7 k pull-ups on SCL_CTL/SDA_CTL | OK |
| HPD | HPD_SNK in (fail-safe), HPD_SRC out [Pin Functions] | the receptacle's HPD (10 k down) in; HPD_SRC to the FPGA | OK |
| DDC | passed through, both sides pulled up [Fig. 33] | 2 k to HDMI 5 V on the receptacle's side, 2 k to 3V3 on the FPGA's | OK |
| CEC (C-B) | a powered-off device must not load the bus (leakage < 1.8 uA [HWG Fig. 26]) | the FPGA's pin through a 2N7002 (gate at 3V3): with the board off the gate is at 0 V and the body diode reversed | OK |
| TMDS output run (C-B) | the driver is made for 2 to 3 inches of board trace and connector [TI-DP159 10.2.2] | was about 79 mm (the receptacle at the board's right) | **Fixed**: C-B's receptacle 15.5 mm left: 59.6-67.9 mm |
| TMDS skew (C-B) | intra-pair 0.15 Tbit (25 ps), inter-pair 0.2 Tchar (337 ps) at 5.94 Gb/s (HDMI 2.0 source) | under 1 mm (5 ps) within a pair, 8 mm (50 ps) between pairs | OK |
| TMDS ESD | < 0.6 pF a line [HWG 6.3.2.1], 6 Gb/s | TPD4E05U06, 0.5 pF, flow-through, rev B's | OK |
| DDC/HPD/CEC ESD (U8) | as close to the connector as possible [TI-ESD] | was 48-59 mm from the receptacle, by the ADV7511 or the DP159 (the placer put parts by the IC on their signal nets) | **Fixed**: ESD parts placed first, at their connectors (kit/pcbkit.py): 2.5-3.7 mm |
| S/PDIF ESD | at each connector [TI-ESD] | one TPD4E05U06 for the coax RCA (J14) and the optical header (J13), 25 mm apart | **Fixed**: a TPD1E05U06 at each |

## Layout (after routing)

Routed as rev B (rev-b/design.md "Routing"): the analog lines and references kept 0.5 mm from
digital and clock lines by the router, the ESD parts at their connectors, rip-up for the last gaps.

| Check | C-B | C-A |
|---|---|---|
| DRC | no errors, no unconnected items (warnings: silkscreen, which JLCPCB clips; footprints changed from the library on purpose) | follows |
| ERC, netlist | clean; schematic = board.py, 1006 pins | clean; 1063 pins |
| SOM receptacles | 280 of 280 pads at the Console's place and number (check_som_fp.py) | the same footprints |
| ADV7181D to the SOM | LLC 25.4 mm (two vias); data 23.3-72.3 mm (74.25 MHz at most: about 0.3 ns spread in 13.5 ns; the FPGA's input delays can trim it) | follows |
| TMDS | DP159 to the receptacle 59.6-67.9 mm, no vias (TI: 2-3 inches); the FPGA's lanes to the DP159 3-22 mm, AC coupled | follows |
| Video inputs | Y 34.2, Pb 22.6, Pr 31.1, SCART sync 49.7 mm; VGA R 56.9, G 103.2 (AIN2, past the references), B 53.1 mm | follows |
| Interference | nothing digital within 0.5 mm of an analog line but XTAL1 beside LLC along the pins' own pitch (0.36 mm, 2.2 + 1.7 mm); the VGA port's DDC lines (static while video runs) 0.47-0.70 mm from some inputs | follows |
| Vias | 90 at 0.4/0.2 mm (SOM ground pads, ESD arrays, references), 1411 at 0.5/0.3 | follows |
| Assembly | every part on the top | the same |

