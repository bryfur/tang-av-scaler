# AV board rev C: the SOM on its own carrier

Rev B is a hat on the Tang Console 138K, reaching the FPGA through two 2x20 headers (68 I/O, J9
full) and leaving HDMI 1.4 to an ADV7511. Rev C drops the Console: the Tang Mega 138K SOM plugs
straight into this board. Two carriers share everything but the HDMI transmitter:

| | rev C-A ([../rev-ca](../rev-ca)) | rev C-B ([../rev-cb](../rev-cb)) |
|---|---|---|
| HDMI | ADV7511, as rev B, fed 24-bit RGB 4:4:4 | the FPGA's transceivers through a TI SN65DP159 retimer |
| Output | up to 1080p60 (HDMI 1.4) | up to 4K60 (HDMI 2.0, 5.94 Gb/s a lane) |
| HDMI in gateware | video timing only (the ADV7511 does TMDS, audio packets, CEC, EDID) | TMDS coding, HDMI 2.0 scrambling and SCDC, audio data islands, InfoFrames, CEC |
| Parts | 280 | 291 |

What both have that rev B has (rev B's circuits, reviewed in rev-b/review.md, from the same code:
kit/circuits.py): the ADV7181D component/RGB front end with the SCART sync and VGA inputs, the
PCM1808 stereo input on its own 4.5 V LDO, the S/PDIF input (coax slicer, optical module), the
supply tree for the ADV7181D, the HDMI receptacle with its ESD arrays and DDC/HPD/CEC parts, the
XIAO ESP32's sockets and level translators, the buttons and status LED. New in rev C: the SOM
interface, USB-C power, an orange RCA for S/PDIF coax on the back edge, the MS5351M clock
generator, the XIAO as the FPGA's programmer and console, a JTAG header, configuration LEDs and
the RECONFIG button. The circuits are in rev-c/carrier.py (shared by C-A and C-B) and each
board.py.

## The SOM interface

The Tang Mega 138K SOM (45 x 35 mm) plugs in through three Hirose DF40 board-to-board connectors
(0.4 mm pitch, 3.0 mm stack): two 100-pin (J21, J22) and one 80-pin (J20); the Console calls them
J1, J2, J0. Everything about them is copied from the Console:

- **Placement**: from the Console's interactive BOM (refs/ibom_C.html), relative to the SOM's four
  M2 holes (rev-c/som.py). rev-c/check_som_fp.py places our footprints the same way and compares
  every pad with the Console's: 280 of 280 at the same place, numbered the same.
- **Pin numbering**: the Console's (and Hirose's): pin 2k-1 faces pin 2k across the rows.
  EasyEDA's DF40 footprints number one row 1-50 and the other 51-100, which would have put almost
  every SOM signal on the wrong pin; som.py writes DF40HC-*-SOM footprints with the Console's pads.
- **Pinout**: read from the Console's schematic (refs/console138k_C.pdf, sheets SOM_BTB0-2) by
  rev-c/som_pinout.py into rev-c/som-pinout.csv: each pin's net (bank, ball, I/O name), what the
  Console uses it for, and the ball's clock functions.
- **Supplies**: the SOM makes its own core, DDR and I/O supplies from 5 V (its VBUS_SOM, six pins
  of J22). Banks 2-5 and 10 are 3.3 V from the SOM's own regulator [Console sheet POWER_TREE]; the
  VCCO pins on the connectors are taps, left open here. Bank 8 shares the DDR banks' supply: its
  two pins are not used.
- **Configuration**: MODE[2:0] = 001 (from the SOM's SPI flash), as the Console's default: MODE0
  1 k up, MODE1/MODE2 5.1 k down. PUDC_B (J20 pin 10) and CFGBVS (J22 pin 75) left as the Console
  leaves them. RECONFIG_N 10 k up, with a button (JTAG reloads the FPGA too; no XIAO pin on it,
  so an ESP32 booting cannot pulse it). DONE and READY (10 k up) each switch a red LED through a
  2N7002.
- **Current**: the receptacles' contacts are rated 0.3 A each [Hirose DF40HC(3.0), LCSC C424649];
  the 5 V input's six give the SOM 1.8 A, the Console's arrangement.
- **Fixing**: the SOM's four M2 holes (2.2 mm plated, 3.8 mm ring, GND), for M2 x 3 mm brass
  spacers and screws fitted by hand: JLCPCB's only M2 x 3 mm SMD nut (SMTSO2030CTJ) has a 5.6 mm
  flange, which would sit on the receptacles' ends; the Console's 4 mm one is not stocked.

## Floor plan (rev-c/floor.py)

130 x 100 mm, the same four layers as rev B (JLC04161H-7628: F.Cu / GND / GND / B.Cu).

- The back edge carries every cable: the Y, Pb, Pr jacks, the USB-C power input, the L, R and
  S/PDIF jacks, then HDMI. USB-C sits between the video and audio jacks, straight above the SOM's
  5 V pins, its 5 V running between the two analog front ends, not through them.
- The SOM below, turned 270 degrees from its place on the Console: J22 (banks 4/5, the 5 V input)
  faces left, towards the ADV7181D, PCM1808 and S/PDIF under the jacks; J21 (banks 2/3 and the
  transceivers) faces right, towards the HDMI transmitter; J20 (JTAG, RECONFIG_N, DONE, READY)
  faces the front.
- The VGA header (J8) upright left of the ADV7181D.
- The ADV7181D under the video jacks in rev B's rotation (analog side up), with rev B's whole
  layout round it (kit/adv7181d_layout.py: escape vias, the ADC references' and AVDD's the small
  0.4/0.2 mm ones; series rows and arrays; the crystal block; the band above the analog pins; the
  PLL filter and the inputs' last stretch laid before routing; the I2C and reset pull-ups at the
  FPGA's end, so those lines keep out of the references' corner).
- The HDMI transmitter right beside J21, level with its upper end: C-A's ADV7511 7 mm from the
  receptacle's I/O pins (its 24-bit bus crosses that gap; nothing digital passes the audio block
  above), C-B's retimer 7 mm from the transceivers' TX pins. The TMDS lines leave its right side and
  run up the right edge to rev B's ESD arrays and receptacle on the back edge, laid by the
  generator (kit/tmds_layout.py) as on rev B.
- The front edge: the XIAO (its USB-C out of the front), the JTAG header, the buttons.
- The 3V6 buck and the 3V3 LDO at the right front, away from both analog front ends and clear of
  the TMDS lines; the 1V8A LDO by the ADV7181D; the clock generator above J21's top end.
- Nothing under the SOM (its own parts hang 3 mm above the board): only copper there.

## Power

- USB-C (TYPE-C-31-M-12), a 5 V sink: 5.1 k on each CC. With Rd alone the board cannot see how
  much the source offers, and the SOM and board draw up to about 2 A: a 5 V / 3 A USB-C supply,
  not a computer's port. A 5 V TVS (SMF5.0A) at the receptacle, then a 3 A resettable fuse (1812,
  16 V) into +5 V.
- +5 V to the SOM: a 1.2 mm track (about 2 A) laid by the generator from the fuse straight down to
  J22's six VBUS pins (layout.py spine()), 2 x 47 uF + 4 x 22 uF at the SOM.
- rev B's tree for the board's own parts: TLV62569 buck to 3V6, TPS7A7001 to 3V3 and 1V8A, the
  1V8A clamp; rev C-A adds rev B's 1V8B LDO for the ADV7511.
- The clock generator's: below.
- rev C-B: 1V1 for the SN65DP159's core (1.0-1.27 V, about 0.25 A) from a second TLV62569 (R1
  82.5 k / R2 100 k: 1.095 V; 6.8 pF; 2.2 uH, 10 uF [TI-BUCK 8.2.2]).

## Clock generator

MS5351M (Si5351A-compatible), a 25 MHz 10 pF crystal (the Console's load; the chip's internal load
capacitance set to 10 pF over I2C), I2C from the FPGA (4.7 k to 3.3 V). CLK2 to a clock pin of the
FPGA through 33 R: a pixel clock that can be trimmed in fine steps, so the output can lock to the
console's 59.94 Hz instead of dropping or repeating a frame every 17 s. rev C-B: CLK0 and CLK1 (its
inverse) to the transceivers' REFCLK0 through 2.2 R and 100 nF each, as the Console's.

Supplies [MS5351M data sheet V1.4 (Relmon): recommended operating conditions]: the core (VDD)
2.7-3.3 V; the outputs (VDDO) 1.71-1.89, 2.25-2.75 or 3.0-3.6 V, independent of the core. The
Console runs both from 2.5 V, its core below that range; here the core has a 3.0 V LDO of its own
(ME6211C30; the board's 3V3, 3.31 V nominal, would pass 3.3 V at its LDO's tolerance). VDDO: 3.3 V
on C-A, so CLK2 (VOH at least VDDO - 0.6 V) meets the FPGA's LVCMOS33 input (VIH 2.0 V); 2.5 V on
C-B (an ME6211C25), the Console's drive into the transceivers' reference input, CLK2 then inside
LVCMOS33 at its typical swing (the data sheet's floor, 1.9 V, is not: C-B's gateware times its
output from the transceivers' clock, and can take CLK2 with a 1.8 V input standard in the 3.3 V
bank instead, LVCMOS18UD33 in Gowin's table [DS1239 2.3]).

## The XIAO as programmer and console

A Seeed XIAO ESP32-S3 on two 1x7 sockets at the front left, USB-C out of the front edge:

| XIAO | Net | FPGA |
|---|---|---|
| D0, D1, D2, D3 | JTAG TMS, TCK, TDI, TDO | the SOM's JTAG pins (J20 3, 7, 9, 5) |
| D4 | ESP_CS: SPI chip select (the XIAO the master) | an I/O pin |
| D5 | ESP_IRQ: an interrupt from the FPGA, active low | an I/O pin |
| D6, D7 | UART: the XIAO's TX, RX | I/O pins |
| D8, D9, D10 | SPI SCK, MISO, MOSI | I/O pins |

Every line passes a level translator powered from both sides (kit/circuits.py xiao(), as rev B):
U22 (SN74LVC8T245) carries the XIAO's seven outputs, U23 (SN74AVC4T245) the FPGA's four; their A
sides run from the XIAO's own 3.3 V pin, their B sides from the board's. If either supply is off
both sides go to high impedance [TI: VCC isolation, Ioff]: a XIAO on its own USB with the board off
cannot feed the FPGA's I/O, and the empty sockets leave the JTAG lines to J16. The four lines to
the XIAO each pass 470 R (4 ns edges with the pin's capacitance; an ESP32-C3's BOOT button shorts
D9, which U23 drives). 10 k pulls hold every translator input while the XIAO boots or is out: the
TAP in reset (TCK low, TMS and TDI high), chip select, TX and SCK high, TDO, MISO, RX and the
interrupt high on the FPGA's side. An ESP32-C3 then boots as it should too: its strapping pins are
D0 (GPIO2, TMS: high, as Espressif asks), D8 (GPIO8, SCK: high, as its download boot needs) and
D9 (GPIO9: high through U23 from MISO's pull-up, or its BOOT button low) [ESP32-C3 DS Table 3-3].
JTAG over Wi-Fi (openFPGALoader's xvc-client, an XVC server on the ESP32) or over USB (the S3's USB
with a JTAG-bridge firmware); the FPGA's UART
over USB or Wi-Fi. The ESP32-S3 for its USB; a C3 boots right too (above), for JTAG over Wi-Fi. J16, a
1x6 header (3V3 GND TCK TDO TDI TMS) on the same JTAG lines, takes a cable (FT2232 and the like)
with the XIAO out of its sockets.

## HDMI

**C-A**: rev B's ADV7511 circuit, its input now 24-bit RGB 4:4:4 (input ID 0: R on D35-D28, G on
D23-D16, B on D11-D4 [HWG Table 5]), every pixel at full colour. CEC by its own engine. The chip
beside J21: the bus crosses 7 mm (the receptacle's two rows fan out on the two layers), the TMDS
lines leave its right side and run up the right edge (1080p60: 1.485 Gb/s a lane).

**C-B**: the FPGA's four transceiver TX lanes (J21) through 100 nF each into an SN65DP159 (RGZ)
[TI-DP159 Fig. 33]: lanes 0, 3, 2, 1 to its D2, D1, D0 and CLK inputs (the order they leave J21,
so no pair crosses; the gateware maps channels to lanes). The retimer beside J21: the lanes run
7 mm, straight out of J21's pads, through their capacitors, into its pins (gen_pcb.py serdes();
0.2 mm lines 0.2 mm apart over ground 0.21 mm down: about 105 R differential, at the pairs' 100 R
whatever their length). Its TMDS outputs to the ESD arrays and the receptacle: 59.6-67.9 mm, inside
the 2 to 3 inches of board trace its driver is made for [10.2.2] (the receptacle 15.5 mm left of
rev C-A's for it); intra-pair skew under 1 mm (5 ps), between pairs 8 mm (50 ps, of HDMI's 337 ps
at 5.94 Gb/s); its pre-emphasis and swing are set over I2C. Vsadj 7.06 k 0.5 % [10.3.1]; I2C
control (I2C_EN high, A0/A1 low); OE from the FPGA with 100 nF; DDC passed through (2 k each
side); HPD out to the FPGA. CEC from the FPGA: one open-drain pin through a 2N7002 in the
bidirectional level-shifter arrangement (gate at 3.3 V): with the board off the TV's bus sees only
the FET's leakage.

**Both**: CEC's 27 k pull-up through a 1N4148WS (HDMI: a powered-off device must not load CEC
[HWG Fig. 26]; rev B had the 27 k straight to 3V3, corrected there too).

## FPGA pins

The FPGA takes any signal on any I/O, so rev-c/pinmap.py assigns them from the geometry: each
chip's signals take the free 3.3 V I/O pins nearest it, matched to the chip's pins for the least
total length (a matching that short has no crossing lines), clock inputs on clock-capable pins (the
ADV7181D's LLC, the clock generator's CLK2), clock-capable pins kept for clocks otherwise. Each
board writes its assignment as Gowin constraints: rev-ca/fpga/av-board-ca.cst, rev-cb/fpga/av-board-cb.cst.

## Sources

[TI-DP159] SN65DP159 data sheet SLLSEJ2G (refs/sn65dp159.pdf); [HWG] ADV7511 hardware user's guide
Rev D; [TI-BUCK] TLV62569; the MS5351M data sheet V1.4, Relmon (refs/MS5351M_datasheet_V1.4.pdf);
[DS1239] Gowin's GW5AST data sheet (refs/gowin/DS1239E.pdf: I/O standards, the transceivers' DC and
reference clock characteristics); TI's SN74LVC8T245 and SN74AVC4T245 data sheets (VCC isolation,
Ioff); the Tang Console's schematic and interactive BOM (refs/console138k_C.pdf, refs/ibom_C.html)
and the SOM's drawing (refs/console/Tang_Mega_138K_60K_SOM.pdf); rev B's sources for the shared
circuits.
