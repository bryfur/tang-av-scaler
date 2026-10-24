# What the reference designs say

Circuit details taken from ADI's documents (in `refs/`, see the README), circuit by circuit. The
board follows these; anything it does differently is listed at the end with the reason.

The main reference is ADI's ADV7844 evaluation board, "ADV7844 Input Module", Revision C, July 2010
(`refs/adv7844ebz/`: schematic adv7844ebz-sch_c.pdf, 11 sheets; BOM adv7844ebz-mfg_c.xls; IPC-356
netlist adv7844ebz_c.ipc; Gerbers). The ADV7844 is the ADV7842's larger sibling (425-ball BGA, four
HDMI ports, DDR memory): the ball numbers differ, the circuits around the analog front end, crystal,
references and supplies are the same parts. Where UG-214 (the ADV7842's own hardware guide) gives a
value, it agrees with the evaluation board.

## ADV7842: component inputs (EBZ sheet 1 "D-Type and Component Connectors"; UG-214 App. A, B)

Per channel (Y, Pb, Pr), from the RCA jack:

```
RCA ---- 24 R (R96/R104/R106, 0402 1 %) --+-- 0.1 uF (C96/C95/C97) ---- AINx
                                          |
                                        51 R (R132/R134/R136, 0402 1 %)
                                          |
                                         GND
```

- 24 R + 51 R make the 75 R termination (UG-214 Appendix B), placed as close as possible to the
  ADV7842 (UG-214 App. A; the EBZ notes say "as close as possible to end of line").
- Sync on Y: Y also goes through 1 nF (C98) to a SYNC input (SYNC2 on the EBZ).
- Analog input traces 75 R, short, far apart, similar lengths, no digital traces near them
  (EBZ sheet notes; UG-214 App. A).
- UG-214 App. A, strongly recommended routing: component on AIN4, AIN5, AIN6 (EBZ: Y on AIN4,
  Pr on AIN5, Pb on AIN6).

## ADV7842: crystal (EBZ sheet 7; UG-214 App. A "XTAL and load cap value selection", Fig. 170; AN-1260)

- 28.63636 MHz, +-50 ppm or better (datasheet Table 5; UG-214).
- 390 k across the crystal (R44 on the EBZ, "place resistor as close as possible").
- C1 = C2 = 2 (Cload - Cstray) - Cpg, Cstray 2-3 pF, Cpg 4 pF. The EBZ uses a CL = 30 pF crystal
  (Golledge MA08380, HC49) with 47 pF C0G 0603 caps (C60, C64).
- XTALP/XTALN swing is PVDD (1.8 V); an external 1.8 V oscillator can drive XTALP instead.

## ADV7842: reference pins (EBZ sheet 7)

REFP and REFN: 0.1 uF from each to GND (C105, C2) and 10 uF X5R 0603 between them (C150).

## ADV7842: pixel port (EBZ sheet 6; UG-214 App. A "Digital outputs")

- A series resistor at every output (P0-P35, LLC, HS, VS/FIELD, DE, SYNC_OUT, AP0-5, SCLK,
  MCLK), as close as possible to the ADV7842: the EBZ uses 75 R (Panasonic EXB-28V750JX arrays,
  0402 singles for LLC and MCLK), traces matched to 75 R. UG-214 gives the range 50-200 R and asks
  for less than 15 pF load per output, one receiver per output.

## ADV7842: reset, I2C, INT (EBZ sheets 7, 9)

- RESET low while the supplies come up (UG-214 power-up sequence). EBZ: 4.7 k pull-up, 4.7 uF and
  a push button into an AND gate (NC7S08) with the board-level V_RESET; R46 4.7 k on the
  RESET/TEST14 net to GND.
- I2C: 4.7 k pull-ups to 3.3 V (R54, R57). INT1 to the host.

## ADV7842: supplies (EBZ sheet 10; ADI "HDMI RX power supplies" Fig. 2; UG-214 App. A)

The EBZ:
- 1.8 V: NCP5662DS18 LDO (2 A), 150 uF on its input; its EN from the 3.3 V LDO's output through
  100 k with 470 nF to GND ("1V8_EN > 1.3 V = enabled"): 3.3 V first, 1.8 V after.
- 3.3 V: NCP5662DS33 LDO, 150 uF on its input.
- Each rail from its LDO through its own NFE61PT472C1H9 3-terminal EMI filter: 220 uF before the
  filter, 33 uF tantalum after it. Rails: VDD 1.8, AVDD 1.8, CVDD 1.8, PVDD 1.8, DVDDIO 3.3,
  TVDD 3.3, VCC 3.3 (EEPROM, pull-ups, logic), DVDD_RAM.
- Per-pin decoupling (sheet 11; UG-214: a 10 nF and a 0.1 uF per pin "where possible", within
  about 5 mm, via under the 0.1 uF pad):

  | Rail | 10 nF | 0.1 uF | 220 pF (plane caps) |
  |---|---|---|---|
  | TVDD 3.3 | 8 | 3 | 10 |
  | AVDD 1.8 | 5 | 3 | 9 |
  | CVDD 1.8 | 5 | 0 | 0 |
  | VDD 1.8 | 8 | 3 | 2 |
  | DVDDIO 3.3 | 5 | 2 | 3 |
  | PVDD 1.8 | 1 | 1 | 0 |
  | VDD_SDRAM | 5 | 2 | 2 |

- One ground plane for the whole board; PVDD (the sampling clock's supply) kept especially clean
  (UG-214 App. A).
- Power-up order 3.3 V, (2.5 V), 1.8 V, or all together as long as a lower supply never rises
  above a higher one (UG-214 App. A).

ADI's power-supply note (Fig. 2) is the smaller version of the same: 1.8 V LDO -> 10 uH -> 10 uF,
a ferrite per rail, 100 nF + 1 uF on AVDD, CVDD, PVDD, 100 nF on DVDD, DVDDIO, TVDD.
