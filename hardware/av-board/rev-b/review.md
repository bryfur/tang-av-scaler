# Rev B: review against the data sheets (2026-10-25)

Every part checked against its own document, for being inside the limits with margin, not just
inside them. Sources as in design.md: [DS] ADV7181D data sheet Rev C, [HWG] ADV7511 hardware
user's guide Rev D, [TI-LDO] TPS7A7001 (SBVS134F), [TI-BUCK] TLV62569 (SLVSD87), [TI-ESD]
TPD4E05U06, [TI-ADC] PCM1808 (SLES177), [AN-1260], [PSU] ADI's HDMI RX supply note, and JLCPCB's
part data (rated current, DCR, voltage, dielectric). **Fixed** marks what this review changed.

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

## ADV7181D

| Check | Requirement | Board | Verdict |
|---|---|---|---|
| Component inputs | Y AIN10, Pb AIN8, Pr AIN6 (manual mux) [DS Table 8, 9]; 75 R + 0.1 uF, Y 1 nF to SOY [Fig. 9] | as required; 75 R 1 % 0603 at the jack side of the coupling cap | OK |
| ESD at the jacks | none in Fig. 9 | was none | **Fixed**: a TPD4E05U06 (0.5 pF/line, 5.5 V) on Y/Pb/Pr between the jacks and the terminations |
| Crystal | 28.63636 MHz fundamental, +-50 ppm [DS Table 1] | was TXM (68 in stock); now YXC X50322863636MSB2GI: +-10 ppm, +-20 ppm over temperature, 40 R ESR; 33 pF loads (31 pF computed [AN-1260]), about -9 ppm: worst -39 ppm | **Fixed** (stock) |
| PLL loop filter | 1.69 k + 82 nF, 10 nF to PVDD, close to ELPF [DS Fig. 8] | as required, placed first, at pin 30 | OK |
| ADC references | CAPY1/CAPY2/CAPC2 network, REFOUT/CML 10 uF + 0.1 uF [Fig. 9] | as required, placed before decoupling, at pins 39-44 | OK |
| Output port | 16-bit SDR, 33 R series at the chip [Table 11, Fig. 9] | 3 arrays in line with their pins + 8 singles; LLC on the FPGA's clock pin | OK |
| LLC | 12.825-75 MHz [DS pin 20] | 1080i at 74.25 MHz | OK (1.0 % margin, ADI's own limit) |
| Control | ALSB, PWRDWN, INT pull-ups; RESET low >= 5 ms [DS Table 7] | ALSB/PWRDWN/INT 4.7 k to DVDDIO; RESET held low by 4.7 k until the FPGA drives it (FPGA configuration takes far longer than 5 ms after the supplies) | OK |
| I2C | 400 kHz max [DS pin 54] | 4.7 k to 3V3, a few cm: rise about 0.1 us | OK |
| Unused pins | FB, HS_IN, VS_IN inputs; AIN1-5/7/9, SOG | FB/HS_IN/VS_IN 10 k to GND; analog inputs float | OK |
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
| HPD | 10 k +-10 % to GND [HWG 6.1.4] | 10 k 1 % | OK |
| HDMI +5 V | >= 55 mA; 4.8-5.3 V at the source | 200 mA PTC (0.5-1.5 R: 30-80 mV at 55 mA) from the Console's 5 V | OK if the Console's 5 V is >= 4.9 V; note |
| Supply filters | 10 uH + 10 uF per group, 0.1 uF per pin [HWG 7.1, Fig. 23] | NRS4018 10 uH (1.2 A, 150 mR): < 15 mV drop | OK |

## PCM1808

| Check | Requirement | Board | Verdict |
|---|---|---|---|
| Full scale | 3 Vp-p at VCC = 5 V [TI-ADC 6.3] | 2 Vrms source through 10 k into 10 k // 60 k: 2.6 Vp-p (1.2 dB headroom); at VCC = 4.75 V, 2.85 Vp-p | OK |
| Inputs | 1 uF coupling, 60 k input [TI-ADC] | 1 uF X5R 50 V: 2.4 Hz | OK |
| VREF, VCC, VDD | 0.1 uF + 10 uF each | as required | OK |
| Clock / mode | SCKI 256/384/512 fs, slave I2S: MD0 = MD1 = FMT = 0 | 10 k pull-downs; SCKI from the FPGA | OK |

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
| DRC | no errors, no unconnected items (warnings: silkscreen over the board edge and copper, one copper sliver in a pour) |
| ERC, netlist | clean; schematic = board.py, 652 pins |
| ADV7181D to J10 | LLC 19.0 mm (one via); data 12.3-26.4 mm (74.25 MHz at most: 95 ps spread in 13.5 ns) |
| Small vias | 0.4/0.2 mm at the ESD arrays' GND pads only (JLCPCB's four-layer minimum is 0.3/0.15 mm); everything else 0.5/0.3 |
| Assembly | 161 parts on the top, J9/J10 (through-hole) underneath |

Tooling found on the way: KiCad's session import gives every via the default size (the 0.4 mm
vias came back 0.5 mm and broke clearance to the TMDS lines); pcbkit's session() now restores
each locked via's size.
