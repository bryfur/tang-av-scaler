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
 2 RCA (L R)     -> 10k/10k, 1 uF   -> PCM1808 (I2S slave)  <- SCKI/BCK/LRCK, DOUT ->              J9
 J9 (bank 2) -> 16-bit 4:2:2 + CLK/HS/VS/DE, I2S -> ADV7511 -> HDMI type A                          (as rev A)
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
inputs (rev A's 24 R / 51 R divider was the ADV7842's front end). Unused: AIN1-5, AIN7, AIN9,
SOG float (the data sheet gives them no connection).

Crystal [DS Table 1, pins 21/22, Fig. 9]: 28.63636 MHz fundamental between XTAL (22) and XTAL1
(21), 1 M across. The load caps follow rev A's sum for the same 20 pF crystal (TXM, LCSC C362486,
+-20 ppm against the decoder's +-50 ppm): C = 2 (CL - Cstray) - Cpg = 31 pF [AN-1260]; 33 pF C0G,
the nearest JLCPCB basic part, pulls the crystal about 12 ppm low, still inside +-50 ppm. Fig.
9's 47 pF suit the 30 pF-class crystal on ADI's board.

ADC references [DS Fig. 9]: CAPY2 (40) to GND through two 0.1 uF; between CAPY1 (39) and CAPY2,
and between CAPC2 (44) and CAPY2, 10 uF + 0.1 uF + 10 nF each; REFOUT (42) and CML (43) each
10 uF + 0.1 uF to GND.

PLL loop filter at ELPF (30) [DS Fig. 8]: 1.69 k in series with 82 nF to PVDD, 10 nF from ELPF
to PVDD; placed at the pin.

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
+5 V -> ferrite -> PCM1808 VCC;  +5 V -> 0.2 A PTC -> HDMI +5 V
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
- A TPD4E05U06 protects the three video inputs (review.md).
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
- One-sided assembly: every SMT part is on the top (only the J9/J10 sockets, through-hole, sit
  underneath), so JLCPCB assembles one side. The ADV7181D's decoupling therefore sits on the
  top too, by its supply pins' escape vias, outside the lines' band: each pin's 100 nF placed
  first, 2.7-4.3 mm from its pin (2.2-2.7 mm when they were underneath).
- Part count: 163 (rev A 230).
- Cost: the jacks are CUI RCJ-014 (yellow, $1.69) for Y, Pb and L and RCJ-012 (red) for Pr and R,
  where rev A had the black RCJ-011 ($3.82, 40 in stock): one footprint for the series, the
  silkscreen names each input. A second BOM/CPL (`hand-jacks`) leaves the five jacks to be soldered
  by hand. The ADV7511's audio series resistors are 49.9 R (JLCPCB basic) for
  [HWG 7.3]'s 51 R, the crystal's caps 33 pF (above). The regulators' dividers keep TI's E96
  values: the TPS7A7001 wants R2 at 27-33 k [TI 8.1.3], and no basic pair gives 3.3 V or 1.8 V
  from there.

## Routing (2026-10-25)

`gen_pcb.py --route` does all of it:

1. Before routing (fanout): the ADV7181D's exposed-pad and escape vias, the ADV7511's inward
   escapes, the ESD arrays' GND vias, the TMDS pairs (laid, see above), the plane vias of every
   ground and decoupling pad. All locked.
2. Freerouting 1.9 (100 passes) on F.Cu and B.Cu, about 20 minutes.
3. What is still unconnected (Freerouting leaves a few, a different few each run), by
   mazeroute.py (pcbkit finish_unconnected).

| Pair | P | N | skew | vias |
|---|---|---|---|---|
| D2 | 12.67 mm | 13.50 mm | 0.83 mm | 0 |
| D1 | 15.16 mm | 15.99 mm | 0.83 mm | 0 |
| D0 | 18.06 mm | 18.89 mm | 0.83 mm | 0 |
| CK | 20.54 mm | 21.37 mm | 0.83 mm | 0 |

All on F.Cu over In1, coupled from pin to connector; the 0.83 mm is the outer line's longer path
through the one bend (6 ps). Pixel clock to the ADV7511 18.9 mm with no via; R_EXT 2.2 mm. DRC: no
errors, no unconnected items. review.md has the checks.
