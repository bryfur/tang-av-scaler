# Rev B: review against the data sheets (2026-10-25)

Every part checked against its own document, for being inside the limits with margin, not just
inside them. Sources as in design.md: [DS] ADV7181D data sheet Rev C, [HWG] ADV7511 hardware
user's guide Rev D, [TI-LDO] TPS7A7001 (SBVS134F), [TI-BUCK] TLV62569 (SLVSD87), [TI-ESD]
TPD1E05U06/TPD4E05U06 (SLVSBO7O), [TI-ADC] PCM1808 (SLES177), [AN-1260], [PSU] ADI's HDMI RX supply note, and JLCPCB's
part data (rated current, DCR, voltage, dielectric). **Fixed** marks what this review changed.

**Status (2026-10-27):** the routed board, its schematic and its fab files are the route before the
placement fixes of 2026-10-26 (capacitors at their pins, ESD parts first), with the silkscreen
pass: DRC clean, no unconnected items, the board = its schematic part for part. The fixes in the
Buck layout, LDO capacitors, U8 and Supply filters rows are in the generator (board.py, gen_pcb.py,
kit/pcbkit.py) but not routed yet (the routes on the new placement left 1 and 3 connections). board.py now also numbers eight capacitors the other way round (C10/C11, C13/C14,
C16/C17, C19/C20: each regulator's feedback and output capacitor), so the schematic stays the one
the board was routed from until rev B is routed again.

## Supplies and sequencing

| Check | Requirement | Board | Verdict |
|---|---|---|---|
| ADV7181D supply-to-supply limits | DVDDIO - PVDD, DVDDIO - DVDD, AVDD - PVDD, AVDD - DVDD: -0.3 V to +2 V; DVDDIO - AVDD and PVDD - DVDD within 0.3 V [DS Table 5] | Was: 3V3 up 30 ms before the 1.8 V rails (rev A's RC enable, made for the ADV7842): 3.3 V apart, outside +2 V | **Fixed**: 1.8 V LDOs fed from 3V3 and enabled by it: a 1.8 V rail stays under 3V3 and once regulating trails it by 1.5 V; a B5819W Schottky 1V8A -> 3V3 holds the -0.3 V side while the rails decay at power-down (3V3 carries the heavier load). DVDDIO/AVDD both from 3V3, PVDD/DVDD both from 1V8A |
| ADV7511 sequencing | none; all domains within 1 s of each other [HWG 6.8.1] | 1V8B from 3V3 with the rest | OK |
| PCM1808 | VINL/VINR <= VCC + 0.3 V, +-10 mA input current [TI-ADC 6.1] | inputs through 10 k: an unpowered board with 2 Vrms in sees 0.14 mA | OK |
| PVDD range | 1.71-1.89 V [DS Table 1] | TPS7A7001 +-3 % at light load [TI-LDO 6.5] + 1 % resistors: 1.73-1.88 V; ferrite drop 0.6 mV | OK, inside by 20 mV at worst |
| DVDD range | 1.65-2.0 V | as above, 5 mV ferrite drop at 0.1 A | OK |
| AVDD range | 3.15-3.45 V | 3V3 3.17-3.44 V worst case; was a 0.2 A / 0.45 R bead at 0.2 A: -90 mV, 3.08 V | **Fixed**: BLM18PG121SN1D (2 A, 50 mR): -10 mV, 3.16 V worst case |
| Ferrite current ratings | | DVDD 0.1 A, AVDD 0.2 A, DVDDIO 0.04 A, PVDD 0.01 A, PCM1808 VCC 0.01 A against 2 A | OK (all five beads the same basic part) |
| 3V3 LDO | VIN >= VOUT + VDO; Cout >= 4.7 uF any type; R2 27-33 k; Cff above 47 uF of load [TI-LDO 6.5, 8.1] | was fed from 5 V (0.94 W at 0.55 A); now from the 3.6 V buck: 0.3 V headroom, VDO about 0.1 V at 0.55 A [Fig. 3], 0.17 W | **Fixed** (heat: 47 C rise to 8 C) |
| 1.8 V LDOs | as above | 1.5 V headroom, 0.2 and 0.27 W | OK |
| Buck | Eq. 2 with R2 <= 200 k; 6.8 pF Cff for R2 = 100 k; 2.2 uH and 10-47 uF per Table 4 [TI-BUCK 8.2.2] | R2 100 k, R1 499 k: 3.594 V; 6.8 pF; 2.2 uH (Isat 2 A) for 0.6 A + ripple; 10 uF out; input 10 uF (TI's 4.7 uF doubled for DC bias) | OK |
| Sequencing of the buck | soft start 0.9 ms [TI-BUCK 7.3.3] | the LDOs follow its ramp | OK |
| Buck layout | the input and output capacitors and the inductor as close to the IC as possible [TI-BUCK 10.1] | the input capacitor was placed by EN (pin 1, on +5 V too), across the package from VIN: 13.5 mm (second review, 2026-10-26) | **Fixed**: each regulator capacitor names its pin (board.py `at=`, placed before the rest): at VIN, 2.6 mm; the feedback divider next (FB is VIN's neighbour), 4.4 mm as before; then the inductor and the output capacitor at its output |
| LDO capacitors | input and output capacitors at the device, as its layout example [TI-LDO 10.1, Fig. 8] | 5-19 mm (placed by the rail's first pin of whatever chip came before them in board.py) | **Fixed** (`at=`): 2.6-4.1 mm; but the 3V3 LDO's output capacitor 8.9 mm, its OUT pin facing the TMDS lines 1.2 mm off (about 3 nH of track: nothing to its stability). The feedback dividers, placed before the output capacitors: 3.4, 7.5 and 8.1 mm (1V8A, 1V8B, 3V3; were 3.4, 5.9, 7.5): FB is OUT's neighbour on the side facing the corridor (turned over, the row came out worse) |

## ADV7181D

| Check | Requirement | Board | Verdict |
|---|---|---|---|
| Component inputs | Y AIN10, Pb AIN8, Pr AIN6 (manual mux) [DS Table 8, 9]; 75 R + 0.1 uF, Y 1 nF to SOY [Fig. 9] | as required; 75 R 1 % 0603 at the jack side of the coupling cap | OK |
| ESD at the jacks | none in Fig. 9; "as close to the connector as possible" [TI-ESD] | was none; then one TPD4E05U06 for Y, Pb, Pr and the SCART sync, which sat by the Pb jack: Y's line ran 18 mm to it and back, the sync's 25 mm | **Fixed**: a TPD1E05U06 (the same family's single line: 0.42-0.5 pF, 5.5 V, unidirectional) at each connector's signal pin, about 3 mm from it, the 75 R termination beside it |
| Crystal | 28.63636 MHz fundamental, +-50 ppm [DS Table 1] | was TXM (68 in stock); now YXC X50322863636MSB2GI: +-10 ppm, +-20 ppm over temperature, 40 R ESR; 33 pF loads (31 pF computed [AN-1260]), about -9 ppm: worst -39 ppm | **Fixed** (stock) |
| PLL loop filter | 1.69 k + 82 nF, 10 nF to PVDD, "as close to the pin as possible" [DS Fig. 8] | was placed first by anchor but landed 6-10 mm away, above the corner | **Fixed**: laid out beside pins 30/31, the 10 nF across them, all within 1-6 mm (kit/adv7181d_layout.py pll()) |
| ADC references | CAPY1/CAPY2/CAPC2 network, REFOUT/CML 10 uF + 0.1 uF [Fig. 9] | as required, placed before decoupling, at pins 39-44 | OK |
| Output port | 16-bit SDR, 33 R series at the chip [Table 11, Fig. 9] | 3 arrays in line with their pins + 8 singles; LLC on the FPGA's clock pin | OK |
| LLC | 12.825-75 MHz [DS pin 20] | 1080i at 74.25 MHz | OK (1.0 % margin, ADI's own limit) |
| Control | ALSB, PWRDWN, INT pull-ups; RESET low >= 5 ms [DS Table 7] | ALSB/PWRDWN/INT 4.7 k to DVDDIO; RESET held low by 4.7 k until the FPGA drives it (FPGA configuration takes far longer than 5 ms after the supplies) | OK |
| I2C | 400 kHz max [DS pin 54] | 4.7 k to 3V3, a few cm: rise about 0.1 us | OK |
| Unused pins | FB input; AIN1, 3, 4, 5 [DS Table 7] | FB 10 k to GND; the unused analog inputs float; HS_IN/VS_IN driven by the VGA sync buffer (10 k at its inputs) | OK |
| SOG (SCART sync on J7) | as SOY: 75 R termination, 1 nF [DS Fig. 9] | as required; its own TPD1E05U06 at J7 | OK |
| Exposed pad | must be GND [DS] | 12 vias to both ground planes, paste grid | OK |
| Thermal | TJ = 85 C + 20.3 C/W x P [DS] | about 0.9 W in component mode: +18 C | OK |
| Decoupling | 0.1 uF + 10 nF per pin group [Fig. 9] | all on the top, 2.7-4.3 mm (100 nF) from the pins through the supply-pin vias | Acceptable: closer needs the bottom side (two-sided assembly) |
| Firmware | 720p/1080i need ADI's scripts; XTAL VIH: register 0x13 = 0x04 [DS notes 4, 5] | | note for bring-up |

## ADV7511 and HDMI

| Check | Requirement | Board | Verdict |
|---|---|---|---|
| Pin connections | as rev A's review (HWG 6.1-6.4) | unchanged from rev A | OK |
| TMDS impedance | 100 R differential [HWG 6.3.2] | was Freerouting's: a third of each line on B.Cu over an In2 signal layer (no plane), 8-28 % coupled | **Fixed**: pairs laid by the generator on F.Cu over In1, 0.25/0.25 mm at the pins' 0.5 mm pitch: 103 R (IPC-2141), coupled from pin to connector, corners keeping the spacing |
| TMDS skew | match intra- and inter-pair [HWG 6.3.2] | measured: 0.83 mm (6 ps) inside every pair, no vias, F.Cu only; between pairs 12.7-20.5 mm (53 ps, against HDMI's 0.2 Tpixel = 1.35 ns at 148.5 MHz) | OK |
| TMDS ESD | < 0.6 pF, close to the lines [HWG 6.3.2.1] | TPD4E05U06 0.42-0.5 pF, flow-through, at the connector [TI-ESD] | OK |
| Pins between the pairs | | AVDD 34/41, GND 37, PD 38 leave inwards to vias under the package; the ESD arrays' GND pads to 0.4/0.2 mm vias between the pairs | OK |
| Pixel clock | controlled impedance, solid reference, short, nothing beside it [HWG 7.2] | stack-up changed: In2 a ground plane, every signal on F or B over its own plane; CLOCK class 0.19 mm clearance; CLK 18.9 mm, no via | **Fixed** (stack-up) |
| Video data | match lengths [HWG 7.2] | J9 to the ADV7511: 18.1-28.7 mm (70 ps spread in a 6.7 ns period, SDR); the FPGA's output delays can trim it | OK |
| R_EXT | 887 R 1 %, short, nothing switching near [HWG 7.6] | 887 R 1 %, 2.2 mm of trace (was 5.2 mm) | OK |
| DDC | 1.5-2 k to HDMI 5 V; < 50 pF [HWG 6.3.3] | 2 k 1 %; TPD4E05U06 0.5 pF | OK |
| DDC/HPD/CEC ESD (U8) | as close to the connector as possible [TI-ESD] | was 14-18 mm from J6: the placer put parts by the IC on their signal nets, the ADV7511; then 5.4-9.1 mm (placed after the ADV7181D's decoupling, which took the room) | **Fixed**: 2.6-3.8 mm (ESD parts now first of all, second review); every ESD part is placed first, at its connector, 2.5 mm towards where its lines go (kit/pcbkit.py): U8 5.5-8.3 mm from J6's pins 13-19, the TMDS corridor and the buck holding the nearer room |
| HPD | 10 k +-10 % to GND [HWG 6.1.4] | 10 k 1 % | OK |
| HDMI +5 V | >= 55 mA; 4.8-5.3 V at the source | 200 mA PTC (0.5-1.5 R: 30-80 mV at 55 mA) from the Console's 5 V; no ESD channel (it gave it to CEC): a supply behind its PTC and 100 nF | OK if the Console's 5 V is >= 4.9 V; note |
| CEC | 27 k to 3.3 V through a diode with < 1.8 uA leakage; CEC_CLK 3-100 MHz +-2 % [HWG 7.7, Fig. 26] | was 27 k straight to 3V3: with the board off, 3V3 sits near 0 V and the 27 k pulled the TV's CEC bus down (about 60 uA) | **Fixed**: 27 k 1 % through a 1N4148WS (nA reverse leakage; high level 3.3 V less 0.6 V = 2.7 V, over CEC's 2.5 V); ESD on the DDC array's fourth channel; CEC_CLK from the FPGA (J9 pin 31) |
| Supply filters | 10 uH + 10 uF per group, "as close to the ADV7511 as possible"; 0.1 uF at each supply pin, "as close to the supply pin as possible", adjacent pins sharing [HWG 7.1, Fig. 23] | NRS4018 10 uH (1.2 A, 150 mR): < 15 mV drop. Placed (second review, 2026-10-26): every 0.1 uF of a rail by its first pin, 3.6-20.2 mm from the pins; the filters by the 1V8B LDO | **Fixed**: each 0.1 uF names its pin (board.py `at=`), placed before everything but the ESD parts: 2.1-7.1 mm (AVDD 41 and MVDD 47 open onto the TMDS lines' corridor, their capacitors beside it: decoupling stays on the top); the filters by the chip, 3-7 mm from its edge |

## Interference (analog against everything else)

Measured on the routed board (every analog net's segments against every digital net's, same
layer, closer than 1 mm; tracks on the other outer layer are shielded by both ground planes).

| Check | Result | Verdict |
|---|---|---|
| Router spacing | the analog lines and ADC references kept from digital and clock lines | was the classes' 0.25 mm alone: one route ran the VGA syncs 0.25 mm beside the Y and SCART sync inputs for 10-12 mm | **Fixed**: 0.5 mm for the router (Freerouting class-to-class rules, kit/pcbkit.py CLASS_CLASS); the classes keep 0.25 mm for the chip's pins |
| Video path (RCA_Y/PB/PR, AIN_*, SYNC_Y) | nothing digital within 0.5 mm; within 1 mm only the VGA port's own DDC lines (0.50-0.73 mm, static while video runs) and 1.1 mm of its V sync at 0.89 mm | OK |
| Audio path (RCA_L/R, AUD_*, VREF, 5VA) | nothing digital within 1 mm | OK |
| ADC references, PLL filter (CAPY*, CAPC2, REFOUT, CML, ELPF) | nothing digital within 1 mm; AVDD's supply line 0.34 mm from the VGA DDC clock for 0.8 mm (static in operation) | OK |
| Crystal | was 15 and 24 mm of line running 0.27-0.4 mm beside LLC and pixel lines for up to 12.6 mm (the crystal had landed behind the series row) | **Fixed**: a laid block in the lane straight out of pins 21/22: 1 M, crystal and load caps in line, about 7 mm of line, a 0.25 mm clearance class; LLC beside XTAL1 only along the pins' own 0.5 mm pitch to the array (0.36 mm, 2.2 mm before the array and 1.7 mm after it), everything else 0.86 mm or more |
| Buck (switching node, inductor) | 40 mm from the ADV7181D, 70 mm from the jacks and the PCM1808 | OK |
| PCM1808 supply | VCC was the Console's 5 V through a ferrite (transparent in the audio band); VREF = VCC / 2 is the ADC's reference | **Fixed**: TPS7A2045 LDO for VCC alone (4.5 V, 92 dB PSRR at 1 kHz, 10 uVrms); the input divider's top resistor 12 k so a 2 Vrms line still has 1.2 dB headroom at the lower full scale |
| ADV7181D supplies | AVDD: LDO, then its own 2 A ferrite and 10 uF; DVDDIO (the output drivers) on a separate ferrite | OK |
| Reference / decoupling caps | scattered by the placer (a CAPY1 cap on the far side of CAPC2), 2-7 mm from their pins; the band never routed closed | **Fixed**: laid out (band()): a ladder of CAPC2/CAPY2/CAPY1 lanes on the top with their caps between (10 nF at 2.1 mm, 0.1 uF at 3.1, 10 uF at 4.1), REFOUT/CML/AVDD to their caps at the band's sides by small vias and the bottom layer; the 10 uF in 0402; the bottom side would put them at 1-2 mm |

## PCM1808

| Check | Requirement | Board | Verdict |
|---|---|---|---|
| Full scale | 0.6 VCC [TI-ADC 6.3]: 2.7 Vp-p at the 4.5 V LDO | 2 Vrms source through 12 k into 10 k // 60 k: 2.36 Vp-p (1.2 dB headroom), independent of the Console's 5 V | OK |
| Inputs | 1 uF coupling, 60 k input [TI-ADC] | 1 uF X5R 50 V: 2.4 Hz | OK |
| VREF, VCC, VDD | 0.1 uF + 10 uF each | as required | OK |
| Clock / mode | SCKI 256/384/512 fs, slave I2S: MD0 = MD1 = FMT = 0 | 10 k pull-downs; SCKI from the FPGA | OK |

## XIAO sockets, LED, S/PDIF

| Check | Requirement | Board | Verdict |
|---|---|---|---|
| XIAO supply | 5 V pin: 5 V in (the module's own LDO makes 3.3 V); ESP32-S3 Wi-Fi bursts up to about 0.5 A | +5 V through a B5819W (1 A, about 0.4 V at 0.5 A: 4.6 V at the pin), 10 uF there; the Schottky stops a USB cable in the XIAO from feeding the Console's 5 V | OK; the Console's 5 V budget takes the XIAO's 0.1-0.5 A on top |
| XIAO I/O | 3.3 V, like the FPGA's bank 2 | through SN74LVC8T245 (the XIAO's three outputs) and SN74AVC4T245 (the FPGA's two, each through 470 R to its XIAO pin), A sides on the XIAO's 3.3 V, B sides on the board's; DIR and OE tied (referenced to VCCA [TI]); unused inputs to GND | OK |
| Back-powering | an unpowered FPGA bank's pins must not be driven | XIAO on USB, board off: VCCB = 0 puts both ports at high impedance [TI: VCC isolation]; the XIAO's lines reach no FPGA pin (the 470 R first fitted only limited it to 6 mA a pin) | OK |
| Floating inputs | translator inputs must not float [TI] | 10 k on each: XIAO side (it boots with its pins as inputs) CS and SCK up, MOSI down; FPGA side (unconfigured; MISO undriven between transfers) MISO/IRQ up, CS up for an empty socket | OK |
| SPI framing | a chip select | D4 to J9 32 (was the UART's: the Console's USB carries the FPGA's UART); D5 an interrupt from the FPGA, J9 33 | OK |
| ESP32-C3 straps | GPIO9 (D9) high at reset, or the C3 boots to download; GPIO8 (D8) high for its download boot (BOOT held: GPIO9 low); GPIO2 (D0) pulled up [ESP32-C3 DS Table 3-3] | D9: MISO undriven with CS high, 10 k up on the FPGA side, U23 drives the XIAO's side high; but its BOOT button grounds D9, which shorted U23's output, and SCK's pull held D8 low | **Fixed**: 470 R between U23 and each XIAO pin (7 mA into the button); SCK pulled up at the XIAO (CS is high meanwhile, the FPGA ignores it); D0 unused here |
| Mechanics | module 21 x 17.8 mm, 8.5 mm up; USB-C plug about 11 mm up | only SMT parts under it; USB-C pointing right, 44 mm of low parts to the edge, 3 mm clear of the HDMI plug's outline; J7 3 mm past its other end | OK |
| LED | KT-0603R, 20 mA max, Vf 1.8-2.4 V | 470 R from 3.3 V I/O: 1.9-3.2 mA | OK |
| S/PDIF coax level | 0.2-0.6 Vp-p into 75 R [IEC 60958-3] | 75 R 1 %; LVC1GU04 self-biased by 1 M (open-loop gain about 10-20 at 3.3 V): 0.2 Vp-p swings it past both thresholds; LVC1G04 squares it | OK |
| S/PDIF timing | 48 kHz: 6.144 Mb/s, shortest cell 81 ns; 96 kHz 40 ns | LVC stages 3-4 ns each; 33 R into the FPGA pin | OK to 96 kHz |
| S/PDIF optical module | TTL/CMOS out at 3.3-5 V | LVC1G04 input 5.5 V tolerant at VCC 3.3 V; 100 k pull-down | OK |
| S/PDIF ESD | at the connector [TI-ESD] | was one TPD4E05U06 for both inputs, 11-16 mm from J13 (by the slicer) | **Fixed**: a TPD1E05U06 at each input's pin (rev C's two connectors are 25 mm apart: one array cannot be at both) |
| Module supply | 5 V, a few mA (receivers 3-10 mA) | +5 V through a 0.2 A PTC, 100 nF | OK |
| ADV7511 SPDIF input | 3.3 V logic, no MCLK [HWG] | from the FPGA through 49.9 R (as the I2S lines) | OK |

## VGA

| Check | Requirement | Board | Verdict |
|---|---|---|---|
| RGB inputs | 0.7 Vp-p into 75 R; the ADC's nominal range 1.6 V [DS Table 1] | 75 R 1 %, 100 nF, as the component inputs; AIN7/2/9 reach ADC2/0/1 by manual muxing [DS Table 9], away from the reference pins | OK |
| Resolution | CP graphics up to XGA at 70 Hz, 75 MHz sampling [DS p. 1, 4]; LLC up to 75 MHz | VGA to XGA; 720p at 74.25 MHz | OK |
| Sync levels | HS_IN/VS_IN: VIH 2 V, 3.3 V inputs [DS Table 1]; VGA sync TTL up to 5 V | SN74LVC2G17 at 3.3 V, inputs 5.5 V tolerant, Schmitt; 10 k pull-downs | OK |
| DDC | 5 V open-drain I2C from the source (its pull-ups); a powered-off sink must not hold it | 2N7002 shifters, gate at 3.3 V: off with the board off; 47 k to the source's 5 V | OK |
| ESD | at the connector, the video lines kept from the digital ones | TPD4E05U06 on R, G, B (U19) and on H, V, SDA, SCL (U20); was H sync on R/G/B's array, its line 0.27 mm beside R's for 10 mm | **Fixed** |
| ESD placement | lines straight into the array [TI-ESD] | U19 sat right under J8's pins 1-2 with R on its outer channel: R crossed G there and one of the three never routed | **Fixed**: its channels in the header's order (G on one side of the ground pads, R and B on the other) and placed beside the pins, turned so the lines pass straight through it |

## The Console's headers

| Check | Requirement | Board | Verdict |
|---|---|---|---|
| Pins | +5 V on 11, GND on 12, FPGA I/O on the rest (SDRAM0 and SDRAM1 connectors) [Console schematic p. 8] | as modelled (kit/parts.py header()); LLC on SDRAM1_CLK (J10 20, a clock pin) | OK |
| Pins 29/30 (SDRAMx_EXIO0/1) | FPGA pins through 0 R (R25/R27, R29/R31); places for 0 R to 3.3 V and GND instead (R26/R28, R30/R32, not fitted: MiSTer's SDRAM modules take their supply there) | J10's carried the optical S/PDIF (U15's output) and VGA DDC data: a Console fitted for MiSTer would put 3.3 V on U15's output | **Fixed**: J10 29/30 open, those lines on 35/36. J9's carry I2S clocks into the ADV7511 through 49.9 R (inputs): harmless either way |
| Grounded FPGA pins | | J10 37-40 tied to GND as extra returns beside pin 12 | Note: a bitstream must drive them low or leave them inputs (design.md); another core that drives them high fights the ground |

## Passives

| Check | Board | Verdict |
|---|---|---|
| Capacitor voltage ratings | everything on +5 V 16-25 V; 10 uF 0603 (10 V X5R) only on <= 3.3 V rails and VREF (2.5 V); 5VA's 10 uF 0603 10 V at 5 V: about 40 % capacitance left, enough for a bypass | OK |
| Dielectrics | C0G on the crystal; X7R/X5R elsewhere | OK |
| Resistor power | all signal-level | OK |
| Inductors | L1 2 A Isat for 0.75 A peak; L2-L4 1.3 A for < 0.1 A | OK |

## Layout (after routing)

| Check | Result |
|---|---|
| Signal layers | F.Cu and B.Cu only; In1 and In2 solid ground |
| DRC | no errors, no unconnected items (warnings: silkscreen overlapping, over copper and by the edge, which JLCPCB clips; footprints changed from the library on purpose: local clearances, the sockets renumbered) |
| Silkscreen | the inputs' names were under the jacks' bodies (out of sight once fitted) and HDMI's over two parts: **fixed**, each name inboard of its jack (within 3.2 mm of its middle, the jacks 13 mm apart) and HDMI's by the receptacle, clear (kit/pcbkit.py silkscreen; the silkscreen layer alone changed). "XIAO, USB >" still crosses three small parts' outlines: no clear place by the sockets |
| ERC, netlist | clean; schematic = board.py, 858 pins |
| ADV7181D to J10 | LLC 16.7 mm (one via); data 9.8-23.8 mm, at most two vias (74.25 MHz at most: about 90 ps spread in 13.5 ns) |
| J9 to the ADV7511 | pixel clock 22.5 mm (three vias, each beside the ground planes' stitching); data 16.9-28.7 mm |
| TMDS | 12.7-21.4 mm, no vias, laid (above) |
| Video inputs | Y 38.2, Pb 40.4, Pr 64.3, SCART sync 39.8 mm, one via each; VGA R 61.8, G 79.7 (five vias: AIN2 is past the references), B 25.0 mm |
| Small vias | 22 at 0.4/0.2 mm (the ESD arrays' GND, REFOUT, CML, AVDD; JLCPCB's four-layer minimum is 0.3/0.15 mm); 605 at 0.5/0.3 |
| Assembly | 228 parts on the top, J9/J10 (through-hole) underneath |

Tooling found on the way: KiCad's session import gives every via the default size (the 0.4 mm
vias came back 0.5 mm and broke clearance to the TMDS lines); pcbkit's session() now restores
each locked via's size.
