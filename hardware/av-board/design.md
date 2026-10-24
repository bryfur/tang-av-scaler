# AV board: electrical design

Every connection below comes from a document in `refs/` (see the README); the source is given in
brackets. [EBZ] is ADI's ADV7844 evaluation board, Rev C; [UG-214] the ADV7842 hardware user
guide, with its Appendix B (the ADV7842 evaluation schematic), C (unused pins) and D (pixel
formats); [DS] the ADV7842 data sheet Rev B; [HWG] the ADV7511 hardware user's guide Rev D;
[PSU] ADI's HDMI RX power-supply note; [TI] the TI data sheet of that part. Where the board does
something the references do not, the reason is listed under "Deviations" at the end.

## Blocks

```
                         +5 V (J9.11, J10.11)
                                 |
        +-------------------+----+-----------------+------------------+
        |                   |                      |                  |
   TPS7A7001 3.3 V     TLV62569 buck 2.5 V     ferrite: PCM1808 VCC   PTC: HDMI +5V
        |                   |
   ferrites:          +-----+-----------------+
   DVDDIO, TVDD,      |                       |
   3V3 (ADV7511 MVDD, TPS7A7001 1.8 V A       TPS7A7001 1.8 V B
   PCM1808 VDD,       (EN from 3.3 V, RC)     (EN from 3.3 V, RC)
   pull-ups)          |                       |
                      NFE61PT filters:        10 uH + 10 uF filters:
                      ADV7842 VDD, AVDD,      ADV7511 DVDD, AVDD+PVDD,
                      CVDD, PVDD              PLVDD+BGVDD

 3 RCA (Y Pb Pr) -> 24R/51R, 0.1 uF -> ADV7842 AIN4/5/6 -> 16-bit 4:2:2 + LLC/HS/VS/DE -> J10 (bank 4)
 2 RCA (L R)     -> 10k/10k, 1 uF   -> PCM1808 (I2S slave)  <- SCKI/BCK/LRCK, DOUT ->      J9
 J9 (bank 2) -> 16-bit 4:2:2 + CLK/HS/VS/DE, I2S -> ADV7511 -> HDMI type A
```

## ADV7842KBCZ-5 (U1, CSPBGA-256, 17 x 17 mm, 1.0 mm pitch)

Analog inputs [EBZ sheet 1; UG-214 App. A, B Fig. 171]:

| Input | Path | Ball |
|---|---|---|
| Y (green RCA) | 24 R series, 51 R to GND, 0.1 uF | AIN4 J14 |
| Y, for sync | 1 nF from the same node | SYNC2 J15 |
| Pr (red RCA) | 24 R, 51 R, 0.1 uF | AIN5 K13 |
| Pb (blue RCA) | 24 R, 51 R, 0.1 uF | AIN6 J13 |

UG-214 App. A asks for component on AIN4-6 and termination close to the chip. The traces are
75 R, short and far from digital lines.

Crystal [UG-214 App. A Fig. 170; AN-1260; DS Table 5]: 28.63636 MHz between XTALP B16 and XTALN
C16, 390 k across it. The load caps are C = 2 (CL - Cstray) - Cpg with Cpg = 4 pF and Cstray
2.5 pF. With the 20 pF crystal that is 31 pF, so 30 pF C0G. ADI's crystal is 30 pF CL
(+-30 ppm, ESR <= 30 R): no such part is stocked, and the TXM 5032 part is 20 pF, +-20 ppm,
ESR 30 R.

References [EBZ sheet 7; UG-214 Fig. 176]: REFP E15 and REFN E16 each 0.1 uF to GND, 10 uF between.

RTERM D11: 499 R 1 % to GND [UG-214 Fig. 177 R3; App. C "500 R"].

Pixel port [UG-214 App. D Table 104 (8-bit PAR mode 0: main Y on P[23:16], main CbCr on P[11:4]);
OP_FORMAT_SEL 0x80 16-bit ITU-656 SDR]: 16 data lines plus LLC N1, HS/CS C4, VS/FIELD C3, FIELD/DE
D4. All of these go through a series resistor next to the ADV7842: 75 R in 4x0402 arrays, as on
[EBZ sheet 6, UG-214 Fig. 175] (UG-214 App. A: 50-200 R, <15 pF load, one receiver each).

| Signal | Ball | J10 pin | FPGA ball (bank 4) |
|---|---|---|---|
| C0 = P4 | B2 | 1 (D0) | R19 |
| C1 = P5 | B1 | 2 (D1) | P19 |
| C2 = P6 | C2 | 3 (D2) | U21 |
| C3 = P7 | C1 | 4 (D3) | T21 |
| VS | C3 | 5 (D4) | R17 |
| HS | C4 | 6 (D5) | P16 |
| C4 = P8 | D2 | 7 (D6) | T18 |
| C5 = P9 | D1 | 8 (D7) | R18 |
| DE | D4 | 9 (D15) | W17 |
| C6 = P10 | E2 | 10 (D14) | V17 |
| C7 = P11 | F2 | 13 (D13) | W22 |
| Y0 = P16 | H1 | 14 (D12) | W21 |
| Y1 = P17 | J2 | 15 (D11) | P17 |
| Y2 = P18 | J1 | 16 (D10) | N17 |
| Y3 = P19 | K2 | 17 (D9) | N14 |
| Y4 = P20 | K1 | 18 (D8) | N13 |
| Y5 = P21 | L2 | 19 (A12) | V20 |
| LLC | N1 | 20 (CLK) | U20 (SGCLK_5) |
| Y6 = P22 | L1 | 21 (A9) | Y22 |
| Y7 = P23 | M2 | 22 (A11) | Y21 |

The LLC goes to the header's CLK pin, the P side of the clock-capable pair V20/U20, where
Sipeed's SDRAM modules take their clock. The FPGA's assignment of each bit is free, so the pins
follow the order in which the lines leave the 75 R arrays under the ADV7842 (left to right, as
the arrays sit in ball order): the bus to J10 is then flat, except LLC, which has to be on the CLK
pin and crosses Y6/Y7 (pins 21, 22) at the header, where the through-hole pins give it the other
layer.

Control [UG-214 App. C; DS; EBZ sheets 7, 9]:

| Ball | Pin | Connection |
|---|---|---|
| L3, M3 | SCL, SDA | J10 pins 23, 25 (A7, A5); 4.7 k pull-ups to 3.3 V [EBZ R54, R57] |
| N5 | RESET | J10 pin 26 (A6); 4.7 k to GND, so the part is held in reset until the FPGA drives it (low while the supplies come up, at least 5 ms [UG-214 App. A; DS]) |
| M4 | INT1 | J10 pin 24 (A8); 4.7 k pull-up to 3.3 V |
| C10 | PWRDN1 | 4.7 k to 3.3 V [App. C] |
| C11 | TEST8 | 4.7 k to 3.3 V [UG-214 Table 1, App. C, Fig. 176]; a DNP 4.7 k to GND beside it ([DS] Rev B says to GND) |
| N4, P3 | TEST4, TEST5 | GND [DS; Fig. 176] |
| N6, P5 | TEST6, TEST7 | float [DS] |
| D8, D10, D13, F4 | DDCB_SCL, DDCA_SCL, VGA_SCL, TTX_SCL | 10 k to GND [App. C] |
| C8, C9 | RXB_5V, RXA_5V | +5 V [App. C] |
| G14, H16 | SYNC4, SYNC3 | GND [Fig. 176] |
| F15 | TRI4 | GND [Fig. 176] |
| P13 | SDRAM_VREF | GND [App. C] |
| N11-14, P11, P12, P14, P15, R11-R16, T11, T13-T15 | SDRAM DQ, LDQS, UDQS | 4.7 k to GND each [App. C] |
| M6-M10 | VDD_SDRAM | DVDDIO 3.3 V [App. C] |
| everything else unused | HDMI, other AIN, SYNC1, TRI1-3, HS/VS_IN, AOUT, AP, SCLK, MCLK, EP_*, CEC, other P, SDRAM A/BA/CS/RAS/CAS/WE/CK/CKE, INT2, SYNC_OUT, HPA | float [App. C] |

Supplies [EBZ sheet 10; UG-214 Fig. 178; PSU]: one 1.8 V LDO for VDD, AVDD, CVDD and PVDD, each
through its own NFE61PT472C1H9L filter with 33 uF tantalum + 10 uF after it; 3.3 V for DVDDIO
(with VDD_SDRAM) and TVDD, each through its own NFE61PT472C1H9L. Per-ball decoupling exactly as
[UG-214 Fig. 179]:

| Rail | Balls | 10 nF | 0.1 uF | 220 pF |
|---|---|---|---|---|
| TVDD 3.3 | A5 A15 B5 B15 | 2 | 2 | 9 |
| AVDD 1.8 | F12 G12 H12 J12 K12 L12 | 5 | 0 | 9 |
| CVDD 1.8 | C12 C13 C14 D12 E11 E12 | 3 | 1 | 0 |
| VDD 1.8 | J7 K6-K9 L6-L9 | 5 | 0 | 2 |
| DVDDIO 3.3 | F5 G5 H5 J5 K5 L5 M5 | 6 | 0 | 8 |
| PVDD 1.8 | D15 D16 | 1 | 1 | 0 |
| VDD_SDRAM | M6-M10 | 4 | 0 | 5 |

Typical currents [DS Table 2, 1080p sampling]: VDD 155-220 mA, AVDD 279-295 mA, PVDD 28-30 mA,
CVDD (HDMI only) up to 130 mA, DVDDIO 51-109 mA.

## PCM1808PWR (U3, TSSOP-14) [TI Fig. 26, 8.2.2]

- Slave mode, I2S: FMT, MD0, MD1 each 10 k to GND (8.2.2.1).
- VCC (analog, 5 V): ferrite from +5 V, 0.1 uF + 10 uF. VDD (3.3 V): 0.1 uF + 10 uF.
  VREF: 0.1 uF + 10 uF.
- Inputs: 1 uF in series (2.7 Hz with the 60 k input). In front of it, 10 k series and 10 k to
  GND: a 2 Vrms line output comes down to 1 Vrms, under the 3 Vp-p (1.06 Vrms) full scale. A
  220 pF to GND after the 10 k series resistor gives the optional anti-aliasing RC: 5 k (the
  divider) x 220 pF, 145 kHz, in TI's range (100 R x 10 nF to 1 k x 1 nF, about 160 kHz
  [10.1.3]), flat to 20 kHz.
- To J9 (bank 2), its left end, next to the PCM1808: SCKI pin 37 (A0, D19), LRCK pin 38 (A1, E19),
  DOUT pin 39 (A2, C19), BCK pin 40 (A3, C18). The FPGA is the
  audio clock master (12.288 MHz = 256 x 48 kHz).

## ADV7511KSTZ (U2, LQFP-100)

Video in [HWG Table 4, Table 7]: Input ID 1 (YCbCr 4:2:2, separate syncs, up to 165 MHz), 16
bits, right-justified, style 1: CbCr[7:0] on D[23:16], Y[7:0] on D[15:8]. 1080p60 is 148.5 MHz
SDR on CLK pin 79. The DDR modes stop at 82.5 MHz, too slow for 1080p. Unused D0-D7, D24-D35 to
GND [HWG 6.1.1].

| Signal | ADV7511 pin | J9 pin | FPGA ball (bank 2) |
|---|---|---|---|
| Y0-Y7 = D8-D15 | 88 87 86 85 84 83 82 81 | 23 22 21 20 19 18 17 16 (A7 A11 A9 CLK A12 D8 D9 D10) | A19 D17 C17 B17 B18 B21 A21 B20 |
| C0-C7 = D16-D23 | 80 78 74 73 72 71 70 69 | 15 13 10 9 8 7 6 5 (D11 D13 D14 D15 D7 D6 D5 D4) | A20 A16 B15 B16 A13 A14 C13 B13 |
| CLK | 79 | 14 (D12) | A15 |
| HSYNC | 98 | 25 (A5) | D15 |
| VSYNC | 2 | 26 (A6) | D14 |
| DE | 97 | 24 (A8) | A18 |
| MCLK | 11 | 27 (WE) | D16 |
| SCLK | 16 | 29 (EXIO0/DM0) | F14 |
| LRCLK | 17 | 30 (EXIO1/DM1) | F13 |
| I2S0 | 12 | 28 (A4) | E16 |
| SCL, SDA | 55, 56 | 3, 4 (D2, D3) | C15, C14 |
| INT | 45 | 2 (D1) | E13 |
| PD/AD | 38 | 1 (D0) | E14 |

The pins follow the order in which the lines leave the ADV7511, seen from J9 above it: up its left
side (the audio, VSYNC), along its top (HSYNC, DE, D8-D23, CLK) and down its right side (D19-D23,
SDA, SCL), then INT and PD from its bottom, round the right. The bus is then flat. CLK is an
output, forwarded by an ODDR, which any pin can do, so it does not need the header's CLK pin.

- Audio inputs: series 50 R (51 R) next to the source, the FPGA side [HWG 7.3]. I2S1-3, SPDIF,
  DSD0-5, DSD_CLK to GND [6.1.1].
- SDA, SCL: 2 k pull-ups to 3.3 V [HWG 7.4, Fig. 27]. INT: 2 k pull-up to 3.3 V [6.3.4].
- PD/AD: 2 k to GND, so the I2C address is 0x72 and power-down is active high [6.1.5]; the FPGA
  can drive it.
- R_EXT pin 28: 887 R 1 % to GND, short trace, no switching lines near it [7.6].
- CEC and CEC_CLK to GND (CEC not used) [6.4.1]. HEAC+/HEAC- (51, 52) to GND (ARC not used)
  [6.2.1].
- TMDS to the HDMI connector: 100 R differential pairs, matched, short [6.3.2]. ESD: two TI
  TPD4E05U06 (0.5 pF per line, made for HDMI 1.4b, flow-through) at the connector; the HWG asks
  for < 0.6 pF and names Panasonic's EZAEG2A50AX varistors, one per line [6.3.2.1].
- DDCSDA/DDCSCL (54, 53) direct to the connector with 2 k pull-ups to the HDMI +5 V [6.3.3, Fig. 27].
  HPD (30) direct from the connector (5 V tolerant), 10 k to GND so it reads 0 V with no sink
  [6.1.4].
- Supplies [HWG 6.8 Fig. 23, 7.1]: one 1.8 V LDO, then three 10 uH + 10 uF LC filters: DVDD
  (1, 19, 49, 76, 77); AVDD (29, 34, 41) with PVDD (24, 25); PLVDD (21) with BGVDD (26).
  0.1 uF at every supply pin (adjacent pins share one). MVDD (47) 3.3 V. No sequencing needed
  [6.8.1].

HDMI connector (type A): pin 18 +5 V through a resettable fuse from the board's 5 V (HDMI
requires the source to supply at least 55 mA). DDC, HPD and +5 V get a TPD4E05U06 ESD array.
Pin 13 (CEC) and 14 (utility) are not connected; pins 2, 5, 8, 11 and 17 (shields and DDC/CEC
ground) and the shell go to GND.

## Power [PSU; EBZ sheet 10; UG-214 App. A, Fig. 178; TI data sheets]

| Rail | Source | Load (max) |
|---|---|---|
| +5 V | J9 pin 11 + J10 pin 11 (the Console's 5 V), 22 uF + 0.1 uF | everything, about 0.7 A |
| 3V3 | TPS7A7001 from +5 V (R1 169 k, R2 30.1 k [TI Table 2]; 10 uF in/out; 220 pF feed-forward, required with over 47 uF on the output [TI 6.3, 8.1.2]) | DVDDIO 110 mA, TVDD (no HDMI input: leakage), VDD_SDRAM 3 mA, MVDD, PCM1808 VDD, pull-ups: about 0.2 A, 0.34 W |
| 2V5 | TLV62569 buck from +5 V (2.2 uH, 4.7 uF in, 10 uF out, R1 316 k, R2 100 k, 6.8 pF feed-forward [TI Fig. 5, Eq. 2]) | the two 1.8 V LDOs, about 0.9 A |
| 1V8A | TPS7A7001 from 2V5 (R1 78.7 k, R2 30.1 k; 10 uF out, about 185 uF with its filters' caps, under the 200 uF limit; 220 pF feed-forward); EN from 2V5 (its VIN: EN must not exceed VIN [TI 6.3]) through 100 k, 470 nF to GND [PSU Fig. 2; EBZ] | ADV7842 VDD + AVDD + CVDD + PVDD, up to about 0.68 A |
| 1V8B | TPS7A7001 from 2V5, same | ADV7511 1.8 V, about 0.2 A |
| 5VA | ferrite from +5 V | PCM1808 VCC, 10 mA |
| HDMI_5V | 0.2 A PTC from +5 V | the sink's DDC (55 mA) |

The order is 3.3 V first, then 1.8 V through the EN delay (about 30 ms after 2V5), as
[UG-214 App. A] asks.
There is one ground plane [UG-214 App. A; HWG; PSU].

## The two headers

On the bottom of the AV board: two 2x20 2.54 mm female sockets, mating with the Console's J9 and J10.

| Pin | J9 (bank 2) | J10 (bank 4) |
|---|---|---|
| 1, 2, 3, 4 | PD, INT, SCL, SDA | C0, C1, C2, C3 |
| 5-10 | C7, C6, C5, C4, C3, C2 | VS, HS, C4, C5, DE, C6 |
| 11 | +5 V | +5 V |
| 12 | GND | GND |
| 13-18 | C1, CLK, C0, Y7, Y6, Y5 | C7, Y0, Y1, Y2, Y3, Y4 |
| 19-22 | Y4, Y3, Y2, Y1 | Y5, LLC (CLK pin), Y6, Y7 |
| 23-26 | Y0, DE, HSYNC, VSYNC | SCL, INT1, SDA, RESET |
| 27-30 | MCLK, I2S0, SCLK, LRCLK | GND |
| 31, 32 | GND | KEY1, KEY2 (buttons SW1/SW2 to GND, 10 k pull-ups: low = pressed) |
| 33-36 | GND | GND |
| 37-40 | PCM1808 SCKI, LRCK, DOUT, BCK | GND |

Each bus is in the order its lines leave its chip, so the traces do not cross (the tables above).
J9 pins 31-36 and J10 pins 27-30 and 33-40 are tied to the AV board's ground. They add returns
next to the only real GND pin (12). **The FPGA design must drive them low or leave them as
inputs, never high.**

## Deviations from the references

- 1.8 V comes from a buck converter (2.5 V) followed by LDOs, instead of LDOs straight from the
  supply. From 5 V, the 1.8 V LDOs would burn about 2.9 W at 0.9 A. The LDOs and the per-rail
  filters after the buck stay as ADI shows them.
- ADI's crystal is 30 pF CL; the board uses a 20 pF part, with load caps from UG-214's formula.
- No HDMI input, CVBS, S-video, SCART, VGA, EDID EEPROMs, external SDRAM or teletext. Those pins
  are terminated per UG-214 Appendix C.
- ADV7511: no CEC oscillator (CEC unused), no ARC. TMDS ESD with TPD4E05U06 arrays instead of
  one varistor per line (same capacitance class, easier to route).
- TEST8: UG-214 says pull it up, the data sheet says pull it down. The board fits the pull-up and
  has the pull-down's pads (DNP).
- TEST5: UG-214 Appendix C says float, but the data sheet and both evaluation schematics tie it
  to GND. The board ties it to GND.
- J10 pin 2 (FPGA P19) is also the FPGA's SSPI_CLK configuration pin; it carries C1, an input to
  the FPGA, which is harmless while the FPGA configures from flash.

## Review against the data sheets (2026-10-24)

Every IC's connections checked pin by pin against its document:

- ADV7842: every ball against UG-214 App. C (unused interfaces float, PWRDN1 4.7 k up, the four
  SCL 10 k down, SDRAM DQ/DQS 4.7 k down, VDD_SDRAM to DVDDIO, SDRAM_VREF and TEST4 to GND,
  RTERM 500 R, RXA/RXB_5V to 5 V); the only differences are the deviations above (TEST5) and
  SYNC3/SYNC4/TRI4 to GND as in UG-214 Fig. 176. AIN4/5/6 = Y/Pr/Pb with SYNC2 as UG-214 Fig. 13
  and the AIN_SEL = 001 table show. Firmware note: 480i component needs the manual ADC routing
  (ADC_SWITCH_MAN, UG-214 6.4).
- ADV7511 (HWG Rev D): supply domains and filters (Fig. 23), R_EXT 887 R 1 %, PD/AD, INT, SDA/SCL,
  DDC pull-ups, CEC and ARC pins to GND, unused data inputs to GND, audio series resistors at the
  source. Fixed: the HPD pull-down is 10 k as 6.1.4 asks (was 100 k). Layout: the CLK net gets
  extra clearance (7.2); no switching line or via near R_EXT (7.6) is checked after routing.
- PCM1808: pinout, slave I2S straps, VREF/VCC/VDD bypass, 1 uF inputs. Fixed: the anti-alias cap
  (220 pF, was 1 nF, which cut 1.4 dB at 20 kHz).
- TPS7A7001: pinout (EN 2, IN 3, OUT 6, FB 7, GND 8), R2 in 27-33 k, Table 2 values, >= 4.7 uF out.
  Fixed: the 220 pF feed-forward the outputs need above 47 uF; 1V8A kept under the 200 uF output
  limit (10 uF at the LDOs); EN of the 1.8 V LDOs from their own 2V5 input (it went to 3.3 V
  with 2.5 V on VIN).
- TLV62569: pinout, Eq. 2 (2.50 V), R2 <= 200 k, 6.8 pF for R2 = 100 k, 2.2 uH with 10-47 uF
  out (30 uF), 4.7 uF in; inductor Isat 2 A against about 1.4 A needed.
- TPD4E05U06: pinout (flow-through, NC pads opposite), 5.5 V stand-off for HDMI 5 V.

## Mechanics

Coordinates are Sipeed's Console PCB coordinates in mm, top view, from the 32001C ibom and the
SOM drawing (`refs/console/`, dl.sipeed.com TANG/Mega_138K_60K/04_Mechanical_drawing).

- Console board: x 89.2-168.8, y 20.6-90.0. J9: pins on y 28.73 (odd) and 31.27 (even), pin n
  at x = 153.13 - 2.54 (n - 1) // 2 (pin 1 at the right end). J10: odd pins on y 80.27, even on
  77.73, pin n at x = 104.87 + 2.54 (n - 1) // 2 (pin 1 at the left end). (ibom pad centres sit
  1.055 mm further out: SMD pads.)
- SOM: 45 x 35 mm on the four holes H1-H4 at x 106/147, y 39/70, so x 104-149, y 37-72. Nothing
  sits on it (no fan, no heat sink; the Console has a fan connector, J24, switched by FAN_EN):
  its top is about 7 mm above the Console (3.0 mm DF40HC connectors, the SOM board, the PG484
  package), under the AV board's underside at 11 mm. Only flat parts (0402-0805 passives,
  tantalums, filters: under 2 mm) sit on the AV board's underside.
- The AV board is the Console's outline plus 15 mm past its left edge: x 74.2-168.8, y
  20.6-90.0 (94.6 x 69.4 mm), over the SOM. The extra strip holds the RCA jacks, so the analog
  front end, crystal and PCM1808 have room between them and the ADV7842 (the Console's USB-C,
  under that edge, is on its bottom side: unaffected). It covers the Console's buttons S1 (98.9, 38.0), S2 (98.9, 71.0) (7 mm tall) and SW2
  (160.5, 54.5), the LCD FPC J4, the PMOD sockets J6/J7 and the fan socket; all fit under it.
  The AV board has two buttons of its own (SW1, SW2 at its bottom right, on J10 pins 31/32) for
  the scaler's menu. The Console's HDMI, USB and USB-C are on its bottom side and stay usable.
- Stack: the Console's SMD male headers (2.5 mm plastic) into 8.5 mm female sockets on the AV
  board's bottom: the AV board's bottom is 11 mm above the Console's top. Four M2.5 standoffs,
  11 mm, on the Console's four holes beside the headers (H7_*: x 100/158, y 30/79).
- Layout: the five RCA jacks along the left edge, facing left (audio at the top). The ADV7842
  sits right above J10's data end (pins 1-22 at x 105-130), pixel side down: its 75 R arrays in
  a row under it, then J10's pins, about 6 mm of bus. The ADV7511 sits under J9's right half,
  data side up, TMDS side down; its bus fans out along the band between it and J9, which is kept
  clear. The HDMI connector is on the right edge, facing right, with the TMDS ESD arrays in line
  before it. The PCM1808 is next to the audio jacks and J9's left end; the regulators sit
  together under the ADV7511, right of the ADV7842's planes. Each small part sits by the pin it
  serves; the video terminations and coupling caps at the ADV7842's analog edge [UG-214 App.
  A], the ADV7511's audio series resistors at J9 [HWG 7.3]; bias resistors, the reference caps
  and the regulators' feedback dividers are placed first, nearest their pins.
- Rail planes (inner layer): each ADV7842 rail's balls are inside its plane, which widens past
  the BGA to hold its filter and all its decoupling on the underside (68 of 69 caps fully over
  their plane, the last a 10 uF bulk cap beside it): AVDD over the top right, PVDD and TVDD over
  the top left (TVDD also under the jack strip), VDD and DVDDIO to the right, DVDDIO (25 caps)
  taking the larger lower part. CVDD has no plane: its filter is left of the BGA, four rows from
  its balls.
- Sipeed's retail case: not checked.

## Stack-up and rules

Four layers, 1.6 mm (JLCPCB's standard 4-layer stack); gen_pcb.py can make six (LAYERS=6) if
routing needs them:

| Layer | 4 layers | 6 layers |
|---|---|---|
| F.Cu | parts, signals (pixel buses, TMDS), ground pour | same |
| In1 | ground, solid | ground, solid |
| In2 | the ADV7842's rail planes (AVDD, VDD, DVDDIO, PVDD, TVDD, each from its filter to its balls), signals elsewhere | signals |
| In3 | - | the rail planes, signals elsewhere |
| In4 | - | ground, solid |
| B.Cu | decoupling, signals, ground pour | same |

(The first layout, with a window over the SOM, needed six layers and still did not route; the
window is gone, see Mechanics.)

Rules: 0.127 mm tracks and clearance by default (JLCPCB's minimum is 0.09); power nets 0.25 mm
with 0.15 mm clearance (they must reach 0.5 mm-pitch supply pins; the large currents run in planes); TMDS 0.2 mm; vias 0.3 mm drill, 0.5 mm pad. The ADV7842's balls are
1.0 mm apart with 0.4 mm pads: a dogbone via sits on the diagonal between four balls.
