# AV board rev C-B

The Tang Mega 138K SOM on its own carrier, HDMI 2.0 from the FPGA's transceivers through a TI
SN65DP159 retimer, up to 4K60; S/PDIF (coax and optical) on rev B's 5-pin header instead of a
jack, so the HDMI receptacle sits by the audio jacks and the board is 100 x 100 mm, 30 mm
narrower than C-A. Everything else is shared with rev C-A:
[../rev-c/design.md](../rev-c/design.md) describes both.

![Rev C-B, 3D](img/av-board-cb-3d.png)

![Rev C-B, top](img/av-board-cb-top.png)

Status: designed, reviewed against the data sheets ([../rev-c/review.md](../rev-c/review.md) for
the parts rev C adds; rev B's circuits, shared, in [../rev-b/review.md](../rev-b/review.md)), placed
and routed; not ordered.

- `board.py`: the parts and nets (the shared circuit in ../rev-c/carrier.py and ../kit/circuits.py)
- `gen_pcb.py`: the PCB (../rev-c/layout.py, kit/)
- `fpga/av-board-cb.cst`: the FPGA pin assignment, Gowin constraints, generated from the board

## Test access

The SOM hides the FPGA's pins (rev B's sit on the Console's headers), so C-B brings out what
bring-up needs.

J17, a 2 x 8 header left of the SOM (assembled; pin 1 top left, labelled on the silkscreen):

| Pin | Signal | Pin | Signal |
|---|---|---|---|
| 1 | VREF: 3.3 V through 220 R | 2 | GND |
| 3 | IN SCL: the ADV7181D's I2C | 4 | IN SDA |
| 5 | DP SCL: the SN65DP159's | 6 | DP SDA |
| 7 | PLL SCL: the MS5351M's | 8 | PLL SDA |
| 9 | D0: FPGA AB16 | 10 | D1: FPGA L13 |
| 11 | D2: FPGA M13 | 12 | D3: FPGA AA16 |
| 13 | D4: FPGA AB17 | 14 | D5: FPGA Y17 |
| 15 | GND | 16 | GND |

D0-D5 are spare FPGA pins (`dbg0`-`dbg5` in `fpga/av-board-cb.cst`, 3.3 V LVCMOS) for whatever
the gateware brings out: syncs, PLL lock, a UART.

Every pin but ground goes through a 220 R resistor by the header, as Digilent's Pmod ports do
(200 R): a probe slipping onto VREF or ground, or a wire in the wrong place, drives at most 15 mA
into the pin behind it. A shorted I2C pin holds its bus without hurting anything that drives it; a
logic analyzer or an outside I2C master still works through the resistor (0.15 V more on a low,
against the buses' 4.7 k pull-ups). VREF is a reference for a logic analyzer's threshold or a level
shifter, not a supply: shorted to the ground pin beside it, it puts 50 mW into its resistor and
leaves the 3.3 V rail alone. D0-D5 through 220 R still carry a few tens of MHz into a probe's
10-15 pF.

Test pads, bare (nothing fitted), each by its rail's regulator and labelled with its rail: +5V,
3V6, 3V3, 1V8, 1V1, 3V0, 2V5, 5VA; two ground pads, with holes for a wire loop, by U4 and by U6.
Pads apart rather than a header: a probe slipping on a header could short 5 V onto the 1.1 V core.

## Ordering at JLCPCB

As rev B ([../rev-b/README.md](../rev-b/README.md)): `fab/` holds the Gerbers and the BOM/CPL, and a
`hand-jacks` BOM/CPL leaves the five RCA jacks for hand soldering. Settings the files do not carry:

- 4 layers, 1.6 mm, stack-up **JLC04161H-7628** (F.Cu / In1 GND / In2 GND / B.Cu), impedance
  control on.
- The four transceiver TX pairs (J21 to the SN65DP159) and the TMDS pairs: 100 R differential on
  F.Cu over In1 (the TMDS pairs 0.25/0.25 mm, as rev B; the 7 mm TX lanes 0.2 mm lines at the
  SOM connector's 0.4 mm pitch). Confirm in JLCPCB's impedance calculator. The HDMI lines follow
  TI's layout rules (SN65DP159 data sheet, SPRAAR7): rev-c/review.md's HDMI rows, checked by
  `kit/hdmi_audit.py rev-cb`; the voids under the AC capacitors' and ESD arrays' pads in In1 and
  In2 are meant.

- Minimum clearance 0.1 mm (the USB-C receptacle's own GND/VBUS pads; JLCPCB's four-layer minimum
  is 0.09 mm); 0.4/0.2 mm vias at the SOM receptacles' ground pads and the ESD arrays.
- Top-side assembly only. Fitted by hand: the SOM's four M2 x 3 mm spacers and M2 screws, the XIAO
  ESP32-S3 (in its sockets J11/J12, its USB-C towards the board's bottom edge: silkscreen
  "XIAO, USB >" beside J12; a C3 works too, JTAG over Wi-Fi only), and the jacks
  for the `hand-jacks` variant.
- Power from a 5 V / 3 A USB-C supply (the board and SOM draw up to about 2 A; a sink with only
  5.1 k on CC cannot ask a weaker source for less). J16 (JTAG) is for a cable with the XIAO out of
  its sockets.
- Check in JLCPCB's preview: the SOM receptacles J20-J22 on their pads (JLCPCB's footprint numbers
  them as a mirror of ours, so its pin 1 dot shows at the far end of the row: the DF40 has no
  polarity [Hirose DF40 drawings], either way is right; do not turn them), the
  USB-C (mouth out of the back edge), the chips' rotations, the RCA jacks' barrels over the back
  edge (the CPL turns the yellow ones 90 degrees for JLCPCB's footprint, kit/gen_fab.py JLC_TURN;
  the red RCJ-012 has no model there and is placed as drawn, as the black RCJ-011).
