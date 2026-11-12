# AV board rev B: electrical design

Rev A ([../rev-a/design.md](../rev-a/design.md)) with its video decoder changed: the ADV7842
(256-ball BGA, about $13) becomes the ADV7181D (64-lead LFCSP, 9 x 9 mm, 0.5 mm pitch, about
$5.60). The BGA was what made rev A cost about $400 at JLCPCB: its escape needed six layers (four
did not route), and BGA assembly. The ADV7181D's pins are all on its edge, so the board is four
layers. Everything else (PCM1808, ADV7511, HDMI, power, headers, mechanics) is rev A's, described
there; this file lists what changed and the ADV7181D's circuit.

Sources: [DS] the ADV7181D data sheet Rev C (2024), with its Fig. 8 (loop filter) and Fig. 9
(typical connection); [AN-1260] crystal design for ADI's video parts; [PSU] ADI's HDMI RX power
supply note; the others as in rev A.

Why not drive the Console's own HDMI port and drop the ADV7511 too: the Console's HDMI output is
rated 1080p30 / 720p60, and the scaler's output is 1080p60.

## Blocks

```
 3 RCA (Y Pb Pr) -> 75R to GND, 0.1 uF -> ADV7181D AIN10/8/6 -> 16-bit 4:2:2 + LLC/HS/VS/DE -> 33R -> J10 (bank 4)
 J7 (SCART sync) -> 75R to GND, 1 nF   -> ADV7181D SOG
 2 RCA (L R)     -> 12k/10k, 1 uF   -> PCM1808 (I2S slave)  <- SCKI/BCK/LRCK, DOUT ->              J9
 J9 (bank 2) -> 16-bit 4:2:2 + CLK/HS/VS/DE, I2S, CEC_CLK -> ADV7511 -> HDMI type A (with CEC)
 J9 (bank 2) <- SPI + IRQ, level translators -> Seeed XIAO (ESP32) sockets;  J10 -> status LED, two buttons
 J13 S/PDIF: coax -> 75R, 100 nF, LVC1GU04 + LVC1G04 slicer -> J10 27;  optical module -> LVC1G04 -> J10 29
 J10 28 (S/PDIF from the FPGA) -> ADV7511 SPDIF: Dolby Digital / DTS passed through to HDMI
 J8 VGA: R/G/B -> 75R, 100 nF -> AIN7/2/9; H/V sync -> LVC2G17 -> HS_IN/VS_IN; DDC <-> 2N7002 <-> J10 30/34
```

## ADV7181DBCPZ-RL (U1, LFCSP-64, LCSC C514378)

Analog inputs [DS Fig. 9, Table 8 "Component YUV", Table 9]:

| Input | Path | Pin |
|---|---|---|
| Y (RCA J1) | 75 R to GND at the input, 0.1 uF in series | AIN10 (49) |
| Y, for sync | 1 nF from the same node | SOY (50) |
| Pb (RCA J2) | 75 R, 0.1 uF | AIN8 (47) |
| Pr (RCA J3) | 75 R, 0.1 uF | AIN6 (45) |

Table 8 maps component video to these inputs (Y on ADC0, U on ADC2, V on ADC1, by manual muxing:
IO map 0xC3/0xC4/0xF3, ADC_SW_MAN_EN). The figure draws no series resistor on the component
inputs (rev A's 24 R / 51 R divider was the ADV7842's front end). Unused: AIN1-5, AIN7, AIN9
float (the data sheet gives them no connection). SOG takes the SCART sync input (below).

Crystal [DS Table 1, pins 21/22, Fig. 9]: 28.63636 MHz fundamental between XTAL (22) and XTAL1
(21), 1 M across. YXC X50322863636MSB2GI (LCSC C112564: 20 pF load, +-10 ppm, +-20 ppm over
temperature, 40 R ESR). Load caps C = 2 (CL - Cstray) - Cpg = 31 pF [AN-1260]; 33 pF C0G, the
nearest JLCPCB basic part, pulls the crystal about 9 ppm low: worst case -39 ppm against the
decoder's +-50 ppm. Fig. 9's 47 pF suit the 30 pF-class crystal on ADI's board.

ADC references [DS Fig. 9]: CAPY2 (40) to GND through two 0.1 uF; between CAPY1 (39) and CAPY2,
and between CAPC2 (44) and CAPY2, 10 uF + 0.1 uF + 10 nF each; REFOUT (42) and CML (43) each
10 uF + 0.1 uF to GND. The 10 uF in 0402 (6.3 V X5R, a JLCPCB basic part: the references sit near
1-2 V, where it keeps about 7 uF), so the network fits above its pins (below, "Layout").

PLL loop filter at ELPF (30) [DS Fig. 8]: 1.69 k in series with 82 nF to PVDD, 10 nF from ELPF
to PVDD; "as close to the pin as possible": laid out beside pins 30/31 (below, "Layout").

Pixel port [DS Table 11, CP 16-bit SDR 4:2:2]: Y on P19-P12, CbCr on P9-P2; P11/P10/P1/P0 unused
(high-Z in this mode). Every output (the 16 data lines, LLC, HS, VS, FIELD/DE) has 33 R in series
at the chip [DS Fig. 9]: where four used pins sit side by side (P19-P16, P15-P12, P6-P4 + LLC) a
4 x 0402 array (LCSC C25501) at their own 0.5 mm pitch, in line with them; one 0402 on each of the
eight others. The FPGA can take
any bit on any pin, so J10's pins follow the order the lines leave the chip, seen from J10 below
it: up its left side (control, Y7-Y4, DE, VS), along its bottom (INT, HS, Y3-Y0, C7-C5) and up its
right (C4-C0); LLC keeps the clock-capable CLK pin (20) as on rev A.

| Signal | ADV7181D pin | J10 pin | FPGA ball (bank 4) |
|---|---|---|---|
| RESET_N | 51 RESET | 1 (D0) | R19 |
| SDA | 53 SDATA | 2 (D1) | P19 |
| SCL | 54 SCLK | 3 (D2) | U21 |
| Y7 | 59 P19 | 4 (D3) | T21 |
| Y6 | 60 P18 | 5 (D4) | R17 |
| Y5 | 61 P17 | 6 (D5) | P16 |
| Y4 | 62 P16 | 7 (D6) | T18 |
| DE | 63 FIELD/DE | 8 (D7) | R18 |
| VS | 64 VS | 9 (D15) | W17 |
| INT | 1 INT | 10 (D14) | V17 |
| HS | 2 HS/CS | 13 (D13) | W22 |
| Y3 | 5 P15 | 14 (D12) | W21 |
| Y2 | 6 P14 | 15 (D11) | P17 |
| Y1 | 7 P13 | 16 (D10) | N17 |
| Y0 | 8 P12 | 17 (D9) | N14 |
| C7 | 14 P9 | 18 (D8) | N13 |
| C6 | 15 P8 | 19 (A12) | V20 |
| LLC | 20 LLC | 20 (CLK) | U20 (SGCLK_5) |
| C5 | 16 P7 | 21 (A9) | Y22 |
| C4 | 17 P6 | 22 (A11) | Y21 |
| C3 | 18 P5 | 23 (A7) | AB22 |
| C2 | 19 P4 | 24 (A8) | AB21 |
| C1 | 25 P3 | 25 (A5) | AA21 |
| C0 | 26 P2 | 26 (A6) | AA20 |
| KEY1, KEY2 | (SW1, SW2) | 31, 32 | Y19, Y18 |
| LED | (D2 through 470 R) | 33 | |
| VGA DDC SDA, SCL | (Q1, Q2) | 36, 34 | |
| SPDIF_RX (coax, sliced) | (U14) | 27 | |
| OUT_SPDIF (to the ADV7511) | (49.9 R) | 28 | |
| SPDIF_ORX (optical module) | (U15) | 35 | |
| (open) | | 29, 30 | |

J10 pins 29 and 30 are the Console's SDRAM1_EXIO0/1: FPGA pins through 0 R (its R29/R31), but its
schematic has places for 0 R to 3.3 V and GND instead (R30/R32, not fitted; MiSTer's SDRAM modules
take their supply there). They stay open here, so a Console fitted that way meets no driver. J9's
pins 29/30 (the same on SDRAM0) carry I2S clocks into the ADV7511 (through 49.9 R): harmless either
way.

Control [DS Table 7, Fig. 9]:

| Pin | Connection |
|---|---|
| 53, 54 SDATA, SCLK | J10 pins 2, 3; 4.7 k pull-ups to 3.3 V (rev A's) |
| 52 ALSB | 4.7 k to DVDDIO: I2C write address 0x42 (VBI readback 0x23) |
| 51 RESET | J10 pin 1; 4.7 k to GND, so the part is held in reset until the FPGA drives it (5 ms low minimum) |
| 1 INT | J10 pin 10; 4.7 k to DVDDIO [Fig. 9] |
| 29 PWRDWN | 4.7 k to DVDDIO [Fig. 9] |
| 32 FB | 10 k to GND (fast blank: SCART only) |
| 55 VS_IN, 56 HS_IN/CS_IN | 10 k to GND each (5-wire graphics sync: unused) |
| 9 SFL/SYNC_OUT | float (output) |
| 3, 10, 24, 57 GND; exposed pad | GND [DS: the exposed pad must be connected to GND] |

Bring-up: the 720p and 1080i component modes need ADI's recommended register scripts [DS
"Package thermal performance"]; they are with the ADV7181D design support files on EngineerZone.

Supplies [DS Table 1; PSU]: DVDD and PVDD 1.8 V from 1V8A, AVDD and DVDDIO 3.3 V from 3V3, each
through its own ferrite (BLM18PG121SN1D: 120 R at 100 MHz, 2 A, 50 mR) with 10 uF after it (rev A's
NFE61PT filters were for the ADV7842's larger currents); per pin as [DS Fig. 9]:

| Rail | Pins | 0.1 uF | 10 nF | Typical current [DS Table 1] |
|---|---|---|---|---|
| DVDDIO 3.3 | 4, 11 | 2 | 2 | 4-38 mA |
| DVDD 1.8 | 23, 58 | 2 | 2 | 90-106 mA |
| PVDD 1.8 | 31 | 1 | 1 | 11-12 mA |
| AVDD 3.3 | 41 | 1 | 1 | 99-200 mA |

DVDDIO and AVDD may lead DVDD and PVDD by at most 2 V, and trail them by at most 0.3 V [DS Table
5]. Rev A's sequencing (3.3 V first, the 1.8 V LDOs enabled 30 ms later) broke the first limit;
see "Power" below.

## Power

```
+5 V (J9.11, J10.11) -> TLV62569 buck -> 3V6 -> TPS7A7001 -> 3V3 -> TPS7A7001 -> 1V8A (ADV7181D)
                                                               \-> TPS7A7001 -> 1V8B (ADV7511)
+5 V -> TPS7A2045 -> 4.5 V PCM1808 VCC (its own low-noise LDO);  +5 V -> 0.2 A PTC -> HDMI +5 V
```

- The buck makes 3.6 V (R1 499 k / R2 100 k, 6.8 pF, 2.2 uH, 10 uF in and out [TI-BUCK]); the 3V3
  LDO runs from it with 0.3 V headroom (0.17 W instead of 0.94 W from 5 V); the 1.8 V LDOs run
  from 3V3 (0.2 and 0.27 W).
- Each LDO's EN is tied to its own input. A 1.8 V rail therefore follows 3V3 up, never above it,
  and once in regulation sits 1.5 V under it: the ADV7181D's supply-to-supply limits hold at
  power-up by construction. At power-down a B5819W Schottky from 1V8A to 3V3 keeps 1V8A within
  about 0.25 V of a falling 3V3 (3V3 has the heavier load).
- Loads: 3V3 about 0.55 A (AVDD 0.2, DVDDIO 0.04, the 1.8 V LDOs 0.31, the rest small); 1V8A
  0.13 A; 1V8B at most 0.18 A [HWG 6.8.2].
- review.md has every check with its source.

## What else changed from rev A

- Power: the six NFE61PT filters and their 33 uF tantalums and 220 pF plane caps are gone (the
  four ferrites above take their place); the supply tree above.
- J10's pin map (above): the new chip's pin order.
- The board: four layers (JLC04161H-7628): F.Cu signal / In1 ground / In2 ground / B.Cu
  signal. Each signal layer sits 0.21 mm over its own solid plane (the 7628 prepreg), so a track
  on either side has the same controlled impedance and a return path under it [HWG 7.2]; power
  runs as tracks. (A first route used In2 for signals: B.Cu then had no plane closer than In1,
  1.3 mm away.)
- The TMDS pairs are laid by gen_pcb.py before routing, locked, on F.Cu: at the ADV7511's own
  0.5 mm pin pitch, 0.25 mm lines with a 0.25 mm gap, 103 R differential (IPC-2141 over 0.21 mm
  of 7628; confirm in JLCPCB's calculator). Straight out of the pins, one 45-degree corner each
  (cut so the spacing to the line inside stays the same through the bend), straight to the ESD
  arrays, across their flow-through pads, on to the connector. A corridor from the pins to the
  connector is kept free of other parts. The four ADV7511 pins between the pairs (AVDD 34 and
  41, GND 37, PD 38) leave inwards, under the package, to a via each; the ESD arrays' GND pads
  take a 0.4/0.2 mm via beside them, between the pairs.
- R_EXT's 887 R sits at pin 28 [HWG 7.6].
- Each video input (Y, Pb, Pr and the SCART sync) has its own TPD1E05U06 at its connector's
  signal pin, about 3 mm from it, its 75 R termination beside it (kit/adv7181d_layout.py
  u1_anchor; review.md). One four-line array for all of them sat by the Pb jack and left Y's
  18 mm and the sync's 25 mm from their connectors, the lines running to it and back.
- The crystal is a laid block (gen_pcb.py crystal()): in the lane straight out of pins 21/22
  between the series rows, the 1 M, the crystal and its 33 pF caps in line, about 7 mm of line
  in a 0.25 mm clearance class, so no pixel line runs beside it.
- The PCM1808's VCC has its own TPS7A2045 LDO (4.5 V, 92 dB PSRR at 1 kHz) instead of a ferrite
  from the Console's 5 V (VREF, the ADC's reference, is VCC / 2); the inputs' divider is 12 k over
  10 k for the lower full scale (2 Vrms in: 2.36 Vp-p of 2.7).
- The exposed pad: a 3 x 3 grid of 1.6 mm paste windows (about half the pad; a full 7.1 mm
  aperture lifts the part) and 12 ground vias in the lanes between them; the four GND pins join
  the pad on F.Cu.
- The ADV7181D's escape: every supply pin and every tied-off pin (ALSB, PWRDWN, FB, HS_IN,
  VS_IN) has its own via just past its neighbours' tips, laid before routing, like rev A's BGA
  fanout. Without them the router boxed these pins in between their neighbours' escapes (the
  first routes left 11, 3 and 4 connections, all at such pins). Each via sits in front of its
  pin, or of a GND or unused neighbour, or past the corner, never in front of a pin with a line
  of its own, and on the spot that leaves the series resistors most room. The arrays sit just
  outside the vias (6.7 mm from the chip's centre); each single resistor stays between the lines
  on either side of its pin (7.6 mm out), and the band between the chip and the resistors is
  kept for the lines.
- The band above the analog pins, laid out by the generator (kit/adv7181d_layout.py band()), not
  left to the placer: with 14 reference and AVDD capacitors, 6 input capacitors and the inputs'
  lines in a 10 x 6 mm band the placer scattered them (one CAPY1 capacitor 3.7 mm from its pin,
  on the far side of CAPC2) and the routers never closed the band (6-10 connections open on
  every board). Of the reference network only CAPY2 is shared, so REFOUT, CML and AVDD leave
  through small escape vias to their capacitors at the band's sides on the bottom layer (laid
  too), and the top layer above the pins is a ladder: CAPC2, CAPY2 and CAPY1 run straight up as
  three lanes, the CAPC2-CAPY2 capacitors between the first two and the CAPY1-CAPY2 ones between
  the last two (10 nF nearest the pins, 0.1 uF, then 10 uF, 2.1-4.1 mm out), CAPY2's two to GND
  above. The inputs leave sideways under the band, the outermost pin lowest (nested, no
  crossings), to their coupling capacitors at its sides.
- The PLL block (pll()): the loop filter beside ELPF (30) and PVDD (31), the 10 nF straight across
  the two pins, the 1.69 k and 82 nF beside it, PVDD's 0.1 uF and 10 nF next, one PVDD line over
  them: all within 1-6 mm of the pins (the placer had put the filter 6-10 mm away, above the
  corner, in every board so far).
- One-sided assembly: every SMT part is on the top (only the J9/J10 sockets, through-hole, sit
  underneath), so JLCPCB assembles one side. The ADV7181D's decoupling therefore sits on the
  top too, by its supply pins' escape vias, outside the lines' band: each pin's 100 nF placed
  first, 2.7-4.3 mm from its pin (2.2-2.7 mm when they were underneath). Every other chip's
  capacitors name the pin they serve in board.py (`at=`) and go there first, after the ESD parts
  (second review, 2026-10-26: they had each gone to their rail's first pin, the ADV7511's 0.1 uF
  3.6-20 mm from its pins [HWG 7.1], the buck's input capacitor 13.5 mm from VIN).
- Part count: 230 with the additions below (rev A 230).
- Cost: the jacks are CUI RCJ-014 (yellow, $1.69) for Y, Pb and L and RCJ-012 (red) for Pr and R,
  where rev A had the black RCJ-011 ($3.82, 40 in stock): one footprint for the series, the
  silkscreen names each input. A second BOM/CPL (`hand-jacks`) leaves the five jacks to be soldered
  by hand. The ADV7511's audio series resistors are 49.9 R (JLCPCB basic) for
  [HWG 7.3]'s 51 R, the crystal's caps 33 pF (above). The regulators' dividers keep TI's E96
  values: the TPS7A7001 wants R2 at 27-33 k [TI 8.1.3], and no basic pair gives 3.3 V or 1.8 V
  from there.

## Additions (2026-10-25)

- **CEC** [HWG 7.7, Fig. 26]: the ADV7511's CEC pin on the connector's pin 13, 27 k to 3.3 V through a 1N4148WS (so a powered-off board leaves the TV's bus alone),
  through the fourth channel of the DDC/HPD ESD array (the HDMI 5 V pin gave it up: a supply behind
  its PTC and 100 nF, it needs none). CEC_CLK (3-100 MHz, 12 MHz suggested) from the FPGA on J9
  pin 31. The scaler can wake the TV, switch it to its input and put it to standby.
- **SCART RGB sync** on J7, a 2-pin header (SYNC, GND; no room for a sixth jack on the edge): 75 R
  termination, 1 nF to SOG, the ADV7181D's second sync slicer [DS Fig. 9, as SOY], and a
  TPD1E05U06 at the header's pin. R, G and B go to the Y/Pb/Pr jacks (CP RGB by manual muxing [DS
  Table 9]); composite sync or sync-on-composite comes in here. Composite and S-Video can use the
  same jacks with firmware only.
- **Status LED**: a red KT-0603R through 470 R from J10 pin 33 (about 2.8 mA), by the buttons.
- **Seeed XIAO (ESP32-C3/S3/C6)** on two 1x7 female sockets (C22438157, rows 15.24 mm apart),
  between J9 and the ADV7181D, its USB-C pointing right: the plug (about 11 mm up) runs over low SMT
  parts only, 44 mm to the edge, clear of the HDMI plug (to the left the jacks' 12 mm backs would
  leave it 16 mm). The module stands 8.5 mm up; only SMT parts are under it, J7 3 mm past its end.

  | XIAO pin | Net | J9 pin |
  |---|---|---|
  | 5V | +5 V through a B5819W (a USB cable in the XIAO cannot feed the Console), 10 uF | |
  | GND | GND | |
  | 3V3 | the translators' XIAO side (100 k to GND: 0 V with the socket empty) | |
  | D4 | ESP_CS: SPI chip select (the XIAO the master) | 32 |
  | D5 | ESP_IRQ: an interrupt from the FPGA, active low | 33 |
  | D8 (SCK) | ESP_SCK | 34 |
  | D9 (MISO) | ESP_MISO | 35 |
  | D10 (MOSI) | ESP_MOSI | 36 |

  The lines pass two level translators powered from both sides (kit/circuits.py xiao()): U22
  (SN74LVC8T245) the XIAO's outputs, U23 (SN74AVC4T245) the FPGA's; their A sides from the XIAO's
  own 3.3 V pin, their B sides from the board's. If either supply is off both sides go to high
  impedance, and the inputs take up to 5.5 V unpowered [TI: VCC isolation, Ioff]: a XIAO on its own
  USB with the board off cannot feed the FPGA's unpowered I/O. 10 k pulls hold every translator
  input while the XIAO boots or is out: chip select high on both sides, SCK and MOSI low, MISO and
  the interrupt high on the FPGA's side. With a chip select the FPGA leaves MISO undriven between
  transfers, so an ESP32-C3's strapping pin D9 (GPIO9) reads high at its reset. (The Console's own
  USB carries the FPGA's UART: the XIAO needs none.) Wi-Fi/Bluetooth for settings, a web page,
  firmware updates or controllers.

- **S/PDIF in** on J13, a 5-pin header in the strip under J10 (no edge room for a sixth jack):
  1 COAX, 2 GND, 3 OPT, 4 GND, 5 +5 V; pins 3-5 in a PLR135's own order (OUT, GND, VCC). The PS2
  has only an optical output, and JLCPCB stocks no TOSLINK receiver, so a receiver module (or a
  PLR135 on wires) plugs into 3-5; an orange RCA (CUI RCJ-017) on a pigtail takes coax on 1-2.
  - Coax [IEC 60958-3: 0.5 Vp-p into 75 R]: 75 R termination, 100 nF, an SN74LVC1GU04
    (unbuffered) biased at its threshold by 1 M, a linear amplifier that swings rail to rail on
    0.5 Vp-p, then an SN74LVC1G04 to square the edges; 33 R to J10 pin 27.
  - Optical: the module's output through an SN74LVC1G04, whose input takes 5.5 V at any supply,
    so a module run from 5 V still gives the FPGA 3.3 V; 100 k holds an empty input low; 33 R to
    J10 pin 35.
  - The module's supply: +5 V through a 0.2 A PTC (the HDMI 5 V's part), so a short at the header
    trips it instead of pulling down the Console's 5 V. Each input a TPD1E05U06 at its pin.
  - No receiver chip: the FPGA decodes the biphase code (48 kHz: 6.1 Mb/s, 81 ns cells) and can
    send the stream on, delayed for lip sync, from J10 pin 28 (J9 is full) through 49.9 R to the
    ADV7511's SPDIF input [HWG: SPDIF input, no MCLK needed]: compressed Dolby Digital / DTS
    reaches the TV or receiver untouched; PCM can join the I2S path instead.
  - A motherboard "S/PDIF out" bracket (TTL in, optical LED and coax driver out) is the other
    direction and does not work here.

- **VGA in** on J8, a 2 x 8 2.54 mm header (C68234) whose pin n is the DE-15's pin n (16 unused;
  odd pins one row, even the other, as an IDC cable counts), for a bracket cable to a DE-15:
  - R, G, B: 75 R terminations and 100 nF, as the component inputs, on the inputs [DS Table 9]
    routes to the three ADCs besides the component ones: G on AIN2 (ADC0), B on AIN9 (ADC1), R
    on AIN7 (ADC2): R and B among the component inputs, G past the reference pins, none against
    them. Both connectors stay wired; the firmware's manual muxing picks one. The CP
    digitizes RGB graphics up to XGA at 70 Hz, sampling at up to 75 MHz [DS p. 1, 4].
  - H and V sync (TTL, up to 5 V) through an SN74LVC2G17 (Schmitt buffers, inputs 5.5 V tolerant
    at 3.3 V) and 33 R into HS_IN/CS_IN and VS_IN (pins 56, 55): separate sync (5-wire) or
    composite sync on H (4-wire) [DS pins 55, 56]. 10 k holds an empty input low. Each sync pin
    takes an escape via at the chip (kit/adv7181d_layout.py).
  - DDC, for a PC's EDID read: the FPGA (J10 pins 36, 34) serves the EDID through two 2N7002 in
    the level-shifter arrangement (gate at 3.3 V; 4.7 k on the FPGA side, 47 k to the source's
    5 V on pin 9): with the board off the source's bus sees only the FETs' leakage.
  - ESD on all seven lines: two more TPD4E05U06, one for R, G and B, one for the syncs and DDC
    (with H sync on the video array its line ran 0.27 mm beside R's for 10 mm).
  - Sync on green (the PS2's RGsB cable) needs none of this: G on the Y jack uses the SOY slicer.
- Part count: 230 with VGA, the XIAO's translators and an ESD diode per input.

## Frame lock (no part on this board)

The output can lock to the console's frame rate (59.94 Hz) instead of dropping or repeating a frame
every 17 s, with the Console's own clock generator: its MS5351M's CLK2 reaches the FPGA's
USR_CLK_IN (ball V10, through 2.2 R and 100 nF: an AC-coupled input), and its I2C bus (2.5 V
pull-ups) is wired through 22 R to the FPGA's DVI_DDC pins (M13 clock, L13 data) [Console sheet
SYS_CLOCK]. The gateware trims CLK2 in ppm steps as the pixel clock's reference. The same bus goes
to the Console's BL616 (DBG_TWI) and its own HDMI port's DDC: unused here (HDMI is the ADV7511's);
if the BL616's firmware sets the generator at power-up, the FPGA takes over after. To be tried on
the board. Without it: the vertical blanking adjusted frame by frame (1125/1126 lines at 1080p),
which most TVs accept. (Rev C has its own MS5351M, rev-c/design.md.)

## Routing (2026-10-25)

`gen_pcb.py --route` does all of it:

1. Before routing (fanout): the ADV7181D's exposed-pad and escape vias, the ADV7511's inward
   escapes, the ESD arrays' GND vias, the TMDS pairs (laid, see above), the plane vias of every
   ground and decoupling pad. All locked. (The ESD parts are placed first, at their connectors;
   an array's two GND pads are joined through the package to one via on the side away from its
   connector, TI's layout, so the lines come in straight. No via sits in a pad.)
2. Freerouting 1.9 (100 passes) on F.Cu and B.Cu, about 20 minutes, told to keep the analog
   lines and ADC references 0.5 mm from digital and clock lines (class-to-class rules written
   into its input; the classes themselves stay at 0.25 mm for the chip's 0.5 mm pins).
3. What is still unconnected (Freerouting leaves a few, a different few each run), by
   mazeroute.py (pcbkit finish_unconnected): over a wider window if need be, then by rip-up
   (through other signal nets' unlocked copper, which is taken up and joined again), kept only if
   fewer gaps are left.

| Pair | P | N | skew | vias |
|---|---|---|---|---|
| D2 | 12.67 mm | 13.50 mm | 0.83 mm | 0 |
| D1 | 15.16 mm | 15.99 mm | 0.83 mm | 0 |
| D0 | 18.06 mm | 18.89 mm | 0.83 mm | 0 |
| CK | 20.54 mm | 21.37 mm | 0.83 mm | 0 |

All on F.Cu over In1, coupled from pin to connector; the 0.83 mm is the outer line's longer path
through the one bend (6 ps). Pixel clock to the ADV7511 18.9 mm with no via; R_EXT 2.2 mm. DRC: no
errors, no unconnected items. review.md has the checks.
