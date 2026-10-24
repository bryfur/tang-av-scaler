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
 2 RCA (L R)     -> 10k/10k, 1 uF   -> PCM1808 (I2S slave)  <- SCKI/BCK/LRCK, DOUT ->      J10
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
| Y0 = P16 | H1 | 1 (D0) | R19 |
| Y1 = P17 | J2 | 2 (D1) | P19 |
| Y2 = P18 | J1 | 3 (D2) | U21 |
| Y3 = P19 | K2 | 4 (D3) | T21 |
| Y4 = P20 | K1 | 5 (D4) | R17 |
| Y5 = P21 | L2 | 6 (D5) | P16 |
| Y6 = P22 | L1 | 7 (D6) | T18 |
| Y7 = P23 | M2 | 8 (D7) | R18 |
| C0 = P4 | B2 | 18 (D8) | N13 |
| C1 = P5 | B1 | 17 (D9) | N14 |
| C2 = P6 | C2 | 16 (D10) | N17 |
| C3 = P7 | C1 | 15 (D11) | P17 |
| C4 = P8 | D2 | 14 (D12) | W21 |
| C5 = P9 | D1 | 13 (D13) | W22 |
| C6 = P10 | E2 | 10 (D14) | V17 |
| C7 = P11 | F2 | 9 (D15) | W17 |
| LLC | N1 | 20 (CLK) | U20 (SGCLK_5) |
| HS | C4 | 19 (A12) | V20 |
| VS | C3 | 21 (A9) | Y22 |
| DE | D4 | 22 (A11) | Y21 |

The LLC goes to the header's CLK pin, the P side of the clock-capable pair V20/U20, where
Sipeed's SDRAM modules take their clock. The FPGA's assignment of each bit is free; the order
above keeps the traces from crossing.

Control [UG-214 App. C; DS; EBZ sheets 7, 9]:

| Ball | Pin | Connection |
|---|---|---|
| L3, M3 | SCL, SDA | J10 pins 27, 28 (WE, A4); 4.7 k pull-ups to 3.3 V [EBZ R54, R57] |
| N5 | RESET | J10 pin 29 (EXIO0/DM0); 4.7 k to GND, so the part is held in reset until the FPGA drives it (low while the supplies come up, at least 5 ms [UG-214 App. A; DS]) |
| M4 | INT1 | J10 pin 30 (EXIO1/DM1); 4.7 k pull-up to 3.3 V |
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
  1 nF to GND after the 10 k series resistor gives the optional anti-aliasing RC (8.2.2.4), at
  about 32 kHz.
- To J10: SCKI pin 23 (A7), BCK pin 24 (A8), LRCK pin 25 (A5), DOUT pin 26 (A6). The FPGA is the
  audio clock master (12.288 MHz = 256 x 48 kHz).

## ADV7511KSTZ (U2, LQFP-100)

Video in [HWG Table 4, Table 7]: Input ID 1 (YCbCr 4:2:2, separate syncs, up to 165 MHz), 16
bits, right-justified, style 1: CbCr[7:0] on D[23:16], Y[7:0] on D[15:8]. 1080p60 is 148.5 MHz
SDR on CLK pin 79. The DDR modes stop at 82.5 MHz, too slow for 1080p. Unused D0-D7, D24-D35 to
GND [HWG 6.1.1].

| Signal | ADV7511 pin | J9 pin | FPGA ball (bank 2) |
|---|---|---|---|
| Y0-Y7 = D8-D15 | 88 87 86 85 84 83 82 81 | 1 2 3 4 5 6 7 8 (D0-D7) | E14 E13 C15 C14 B13 C13 A14 A13 |
| C0-C7 = D16-D23 | 80 78 74 73 72 71 70 69 | 18 17 16 15 14 13 10 9 (D8-D15) | B21 A21 B20 A20 A15 A16 B15 B16 |
| CLK | 79 | 20 (CLK) | B17 |
| HSYNC | 98 | 19 (A12) | B18 |
| VSYNC | 2 | 21 (A9) | C17 |
| DE | 97 | 22 (A11) | D17 |
| MCLK | 11 | 23 (A7) | A19 |
| SCLK | 16 | 24 (A8) | A18 |
| LRCLK | 17 | 25 (A5) | D15 |
| I2S0 | 12 | 26 (A6) | D14 |
| SCL, SDA | 55, 56 | 27, 28 (WE, A4) | D16, E16 |
| INT | 45 | 29 (EXIO0/DM0) | F14 |
| PD/AD | 38 | 30 (EXIO1/DM1) | F13 |

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
  HPD (30) direct from the connector (5 V tolerant).
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
| 3V3 | TPS7A7001 from +5 V (R1 169 k, R2 30.1 k [TI Table 2]; 10 uF in/out) | DVDDIO 110 mA, TVDD (no HDMI input: leakage), VDD_SDRAM 3 mA, MVDD, PCM1808 VDD, pull-ups: about 0.2 A, 0.34 W |
| 2V5 | TLV62569 buck from +5 V (2.2 uH, 4.7 uF in, 10 uF out, R1 316 k, R2 100 k, 6.8 pF feed-forward [TI Fig. 5, Eq. 2]) | the two 1.8 V LDOs, about 0.9 A |
| 1V8A | TPS7A7001 from 2V5 (R1 78.7 k, R2 30.1 k); EN from 3V3 through 100 k, 470 nF to GND [PSU Fig. 2; EBZ] | ADV7842 VDD + AVDD + CVDD + PVDD, up to about 0.68 A |
| 1V8B | TPS7A7001 from 2V5, same | ADV7511 1.8 V, about 0.2 A |
| 5VA | ferrite from +5 V | PCM1808 VCC, 10 mA |
| HDMI_5V | 0.2 A PTC from +5 V | the sink's DDC (55 mA) |

The order is 3.3 V first, then 1.8 V through the EN delay (about 50 ms), as [UG-214 App. A] asks.
There is one ground plane [UG-214 App. A; HWG; PSU].

## The two headers

On the bottom of the AV board: two 2x20 2.54 mm female sockets, mating with the Console's J9 and J10.

| Pin | J9 (bank 2) | J10 (bank 4) |
|---|---|---|
| 1-10, 13-18 | ADV7511 D8-D23 | ADV7842 P16-P23, P4-P11 |
| 11 | +5 V | +5 V |
| 12 | GND | GND |
| 19, 20, 21, 22 | HSYNC, CLK, VSYNC, DE | HS, LLC, VS, DE |
| 23-26 | MCLK, SCLK, LRCLK, I2S0 | SCKI, BCK, LRCK, DOUT |
| 27, 28 | SCL, SDA | SCL, SDA |
| 29, 30 | INT, PD | RESET, INT1 |
| 31, 32 | GND | KEY1, KEY2 (buttons SW1/SW2 to GND, 10 k pull-ups: low = pressed) |
| 33-40 | GND | GND |

J9 pins 31-40 and J10 pins 33-40 (CAS, RAS, CS, BA0, BA1, A10, A0-A3) are tied to the AV board's
ground. They add returns next to the only real GND pin (12). **The FPGA design must drive them
low or leave them as inputs, never high.**

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
- J10 pin 2 (FPGA P19) is also the FPGA's SSPI_CLK configuration pin; it carries Y1, an input to
  the FPGA, which is harmless while the FPGA configures from flash.

## Mechanics

Coordinates are Sipeed's Console PCB coordinates in mm, top view, from the 32001C ibom and the
SOM drawing (`refs/console/`, dl.sipeed.com TANG/Mega_138K_60K/04_Mechanical_drawing).

- Console board: x 89.2-168.8, y 20.6-90.0. J9: pins on y 28.73 (odd) and 31.27 (even), pin n
  at x = 153.13 - 2.54 (n - 1) // 2 (pin 1 at the right end). J10: odd pins on y 80.27, even on
  77.73, pin n at x = 104.87 + 2.54 (n - 1) // 2 (pin 1 at the left end). (ibom pad centres sit
  1.055 mm further out: SMD pads.)
- SOM: 45 x 35 mm on the four holes H1-H4 at x 106/147, y 39/70, so x 104-149, y 37-72. Its
  fan and heat sink sit on it. The AV board has a window over it (x 102-151, y 35-74): the SOM's
  height does not matter.
- What the AV board's area covers on the Console's top side: buttons S1 (98.9, 38.0) and S2
  (98.9, 71.0), 7 mm tall, and SW2 (160.5, 54.5), 6 mm; the LCD FPC J4 at the left edge; PMOD
  sockets J6/J7 and the 2 mm fan socket J5 at the right edge. They all fit under the board (11
  mm above the Console). SW2 gets a 7 mm hole; S1 and S2 sit right where the input bus runs
  from J10 to the ADV7842, so they are covered, and the AV board has two buttons of its own
  (SW1, SW2 at its bottom right edge, on J10 pins 31/32) for the scaler's menu. The Console's
  HDMI, USB and USB-C are on its bottom side and stay usable.
- Stack: the Console's SMD male headers (2.5 mm plastic) into 8.5 mm female sockets on the AV
  board's bottom: the AV board's bottom is 11 mm above the Console's top. Two M2.5
  standoffs, 11 mm, diagonally on two of the Console's four holes beside the headers (H7_*:
  (100, 30) and (158, 79)); the other two, (100, 79) and (158, 30), sit where the video buses
  enter J10 and J9.
- Wings: the input side (ADV7842, PCM1808, five RCA jacks facing left) sits left of the SOM,
  over the end of J10 where its data pins are (pins 1-18 at x 105-115). The ADV7842 sits at
  J10's height, so its pixel balls (its right edge, y 71-82), the series resistors beside
  them and J10's pins line up and the bus runs straight across; the output side
  (ADV7511, HDMI facing right) right of the SOM, over the end of J9 where its data pins are
  (x 142-153). Both wings reach past the Console's edges: board x 60-190, y 20.6-90.0
  (130 x 69.4 mm). It does not fit Sipeed's retail case.

## Stack-up and rules

Six layers, 1.6 mm (JLCPCB's standard 6-layer stack):

| Layer | Use |
|---|---|
| F.Cu | parts, signals (pixel buses, TMDS), ground pour |
| In1 | ground, solid |
| In2 | signals |
| In3 | the ADV7842's rail planes (AVDD, VDD, CVDD, DVDDIO, each from its filter to its balls), signals elsewhere |
| In4 | ground, solid |
| B.Cu | decoupling, signals, ground pour |

Four layers were tried first: with one plane layer for ground and one shared by the rail planes
and signals, Freerouting left about 100 connections unrouted around the 256-ball BGA and
diverged in later passes (it also cut the ground plane up while it could route on it). Six
layers give four signal layers, each next to a ground plane: the 148.5 MHz output bus and the
TMDS lines run over solid ground.

Rules: 0.127 mm tracks and clearance by default (JLCPCB's minimum is 0.09); power nets 0.25 mm
with 0.15 mm clearance (they must reach 0.5 mm-pitch supply pins; the large currents run in planes); TMDS 0.2 mm; vias 0.3 mm drill, 0.5 mm pad. The ADV7842's balls are
1.0 mm apart with 0.4 mm pads: a dogbone via sits on the diagonal between four balls.
