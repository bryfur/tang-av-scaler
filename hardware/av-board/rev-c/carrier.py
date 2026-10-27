"""Rev C's shared circuit: everything but the HDMI transmitter, for both carriers (rev-ca: ADV7511,
1080p60; rev-cb: the FPGA's transceivers through an SN65DP159, 4K60). Each board.py does

    from carrier import *          # (after kit/parts)
    common(second_rail=...)        # the parts below
    ... its transmitter ...
    som(groups)                    # the SOM's receptacles, the FPGA pins assigned last

Rev B's circuits (reviewed against their data sheets, rev-b/review.md) are taken as they are, from
kit/circuits.py: the supply tree, the ADV7181D front end, the PCM1808, the S/PDIF input, the XIAO's
sockets and translators, the buttons and LED, the HDMI receptacle's ESD and DDC/HPD/CEC parts. New
here (rev-c/design.md): the SOM and its standoffs, USB-C power, the MS5351M clock generator, the
XIAO as the FPGA's JTAG and UART, the JTAG header, configuration LEDs and the RECONFIG button.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "kit"))
sys.path.insert(0, HERE)
from parts import PARTS, block, part, two, nxt, R, C, lib_pins, nets, common_errors, unconnected, summary  # noqa: E402,F401
from circuits import (AV, ADV7181D_FPGA_PINS, ADV7181D_OPEN, avpin, supply_tree, adv7181d, pcm1808, spdif,  # noqa: E402
                      xiao, buttons_led, hdmi_receptacle)
import floor  # noqa: E402
import pinmap  # noqa: E402
import som as _som  # noqa: E402

# ---------------------------------------------------------------------------
# Power
# ---------------------------------------------------------------------------

def power(second_rail):
    """USB-C 5 V in -> +5 V (the SOM's and everything's); rev B's tree: buck 3V6 -> 3V3 LDO -> 1V8A
    (ADV7181D); second_rail: "1V8B" (the ADV7511's LDO, as rev B) or None (rev-cb makes its own
    1V1). The clock generator's supplies are clocks()'."""
    block("power")
    # USB-C, a sink at 5 V: 5.1 k on each CC [USB Type-C 4.11: Rd], 5 V up to 3 A from a 3 A
    # source. The SOM (FPGA, DDR3) and this board draw about 2 A at most [the Console's input:
    # 6.5 V / 3.1 A OCP for the SOM and all its peripherals]. D+/D- unused
    part("J15", "USB-C 5V", "lcsc:TYPE-C-31-M-12", "lcsc:USB-C_SMD-TYPE-C-31-M-12_1", "C165948",
         {"A4B9": "VBUS_IN", "B4A9": "VBUS_IN", "A1B12": "GND", "B1A12": "GND", "A5": "CC1", "B5": "CC2",
          "1": "GND", "2": "GND", "3": "GND", "4": "GND"})
    R("5.1k", "CC1", "GND")
    R("5.1k", "CC2", "GND")
    # Protection: a 5 V TVS at the receptacle, a 3 A resettable fuse (16 V, 10 mR) into +5 V. The
    # SMF5.0A is unidirectional (cathode, pad 1, on VBUS): drawn as KiCad's Zener, which shows it;
    # its D_TVS symbol is the bidirectional one
    part("D6", "SMF5.0A", "Device:D_Zener", "Diode_SMD:D_SMF", "C2857263", {"1": "VBUS_IN", "2": "GND"})
    f = nxt("F")
    two(f, "PTC1812", "3A", "VBUS_IN", "+5V")
    for _ in range(2):                          # (at the fuse's output, where the 5 V comes in)
        C("47u", "+5V", size="C1206", at=f + ".2")
    C("100n", "+5V", at=f + ".2")

    # the supply tree for the board's own parts: rev B's (kit/circuits.py)
    supply_tree(second_rail)


# The ADV7181D's FPGA lines -> the pin each comes from (through its 33 R, or straight)
FRONTEND_PINS = ADV7181D_FPGA_PINS


def chip_pins(footprint, at, angle, pad_of):
    """({signal: (x, y)}, body) of a chip's pads on the board, the chip at its floor-plan place: what
    the FPGA pin assignment matches the SOM's pins against (pinmap.assign), and the box its pads
    span, which the lines go round."""
    import pcbkit
    from pcbnew import VECTOR2I, FromMM
    fp = pcbkit.load(footprint)
    fp.SetPosition(VECTOR2I(FromMM(at[0]), FromMM(at[1])))
    fp.SetOrientationDegrees(angle)
    xy = [pcbkit.pad_pos(fp, p.GetNumber()) for p in fp.Pads() if p.GetNumber()]
    body = (min(x for x, _ in xy), min(y for _, y in xy), max(x for x, _ in xy), max(y for _, y in xy))
    return {sig: pcbkit.pad_pos(fp, num) for sig, num in pad_of.items()}, body


def point(signals, at):
    return {s: at for s in signals}


# ---------------------------------------------------------------------------
# Clock generator
# ---------------------------------------------------------------------------

def clocks(refclk):
    """MS5351M (Si5351A-compatible) from a 25 MHz crystal, I2C from the FPGA, as the Console's
    [Console sheet SYS_CLOCK] but for its supplies. CLK2 to a clock pin of the FPGA: an output clock
    that can be trimmed in fine steps, so the output frame rate can lock to the console's (59.94 Hz)
    instead of dropping or repeating a frame every 17 s. refclk: CLK0 and CLK1 (programmed as its
    inverse) to the transceivers' REFCLK0 through 2.2 R and 100 nF each (rev-cb), as the Console's.

    Supplies [MS5351M data sheet V1.4 (Relmon), recommended operating conditions]: the core (VDD)
    2.7-3.3 V, the outputs (VDDO) 1.71-1.89, 2.25-2.75 or 3.0-3.6 V, independent of each other. The
    Console runs both at 2.5 V, the core below its range; here the core has a 3.0 V LDO of its own
    (ME6211C30: the board's 3V3, up to 3.37 V at its LDO's tolerance, would pass 3.3 V). VDDO: 3.3 V
    on rev C-A, so CLK2 (VOH >= VDDO - 0.6 V) meets the FPGA's LVCMOS33 input (VIH 2.0 V); 2.5 V on
    rev C-B, the Console's drive into the transceivers' reference input (an ME6211C25), CLK2 then
    within LVCMOS33 typically (the data sheet's VOH floor is 1.9 V). ME6211: >= 1 uF in and out."""
    block("clock")
    # (each LDO by the MS5351M pin it feeds: by the placer's rules for a part on supplies only they
    # went 73-80 mm off, by the XIAO's level translators, their rails as long)
    part("U24", "ME6211C30M5G-N", "lcsc:ME6211C30M5G-N", "lcsc:SOT-23-5_L2.9-W1.6-P0.95-LS2.8-BL", "C403651",
         {"1": "3V3", "2": "GND", "3": "3V3", "5": "3V0"}, at="U17.1")
    C("1u", "3V3", at="U24.1")                  # (at VIN and VOUT)
    C("10u", "3V0", at="U24.5")
    vddo = "3V3"
    if refclk:
        vddo = "2V5"
        part("U18", "ME6211C25M5G-N", "lcsc:ME6211C25M5G-N", "lcsc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR", "C194395",
             {"1": "3V3", "2": "GND", "3": "3V3", "5": "2V5"}, at="U17.7")
        C("1u", "3V3", at="U18.1")
        C("10u", "2V5", at="U18.5")
    pins = {"1": "3V0", "2": "PLL_XA", "3": "PLL_XB", "4": "PLL_SCL", "5": "PLL_SDA", "6": "PLL_CLK2_S",
            "7": vddo, "8": "GND"}
    if refclk:
        pins.update({"10": "PLL_CLK0", "9": "PLL_CLK1"})
    part("U17", "MS5351M", "lcsc:MS5351M", "lcsc:MSOP-10_L3.0-W3.0-P0.50-LS5.0-BL", "C1509083", pins)
    # 25 MHz, 10 pF load (the Console's): the MS5351M's internal load capacitance, set over I2C to
    # 10 pF, matches it [data sheet: crystal CL 6-12 pF, ESR <= 150 R]. HY25MSMD2016EA1R30: +-10 ppm,
    # +-10 ppm over -20..70 C, 45 R, 2016 four-pad (pads 2, 4 the case). Placed before the 100 nF
    # (VDD, pin 1, is XA's neighbour): its lines the shortest
    part("Y2", "25MHz 10pF", "lcsc:HY25MSMD2016EA1R30", "lcsc:CRYSTAL-SMD_4P-L2.0-W1.6-BL", "C5265839",
         {"1": "PLL_XA", "3": "PLL_XB", "2": "GND", "4": "GND"})
    C("100n", "3V0", at="U17.1")                # (at VDD and VDDO)
    C("100n", vddo, at="U17.7")
    # I2C: 4.7 k to 3.3 V (the FPGA's bus level; the MS5351M's inputs take up to 3.6 V at VIH 0.7 x
    # the bus supply, and want 1 k or more)
    R("4.7k", "3V3", "PLL_SCL")
    R("4.7k", "3V3", "PLL_SDA")
    R("33", "PLL_CLK2_S", "PLL_CLK2")
    if refclk:
        R("2.2", "PLL_CLK0", "PLL_CLK0_S")
        R("2.2", "PLL_CLK1", "PLL_CLK1_S")
        C("100n", "PLL_CLK0_S", "SER_REFCLK_P")
        C("100n", "PLL_CLK1_S", "SER_REFCLK_N")


# ---------------------------------------------------------------------------
# The XIAO (JTAG, UART, SPI), the JTAG header, buttons, LEDs
# ---------------------------------------------------------------------------

# The XIAO's lines (kit/circuits.py xiao()): JTAG on D0-D3 (TMS on D0: an ESP32-C3's D0 is GPIO2, a
# strapping pin Espressif asks to be pulled up [ESP32-C3 DS Table 3-3 note 2], and TMS's pull is up;
# TCK's is down), SPI (the XIAO the master: D4 chip select, D8 SCK, D9 MISO, D10 MOSI), an interrupt
# from the FPGA (D5, active low), the FPGA's UART (D6 the XIAO's TX, D7 its RX)
XIAO_LINES = {"D0": ("JTAG_TMS", "out"), "D1": ("JTAG_TCK", "out"), "D2": ("JTAG_TDI", "out"), "D3": ("JTAG_TDO", "in"),
              "D4": ("ESP_CS", "out"), "D5": ("ESP_IRQ", "in"), "D6": ("ESP_TX", "out"), "D7": ("ESP_RX", "in"),
              "D8": ("ESP_SCK", "out"), "D9": ("ESP_MISO", "in"), "D10": ("ESP_MOSI", "out")}


def control():
    block("control")
    # A Seeed XIAO ESP32-S3 on two 1x7 sockets, USB-C to the front edge: the FPGA's programmer
    # (JTAG: openFPGALoader over Wi-Fi to an XVC server on it, or over USB), its console (UART), and
    # Wi-Fi/Bluetooth (SPI), through level translators that isolate either side when the other is
    # off (kit/circuits.py xiao()). The S3 for its USB (a JTAG bridge); a C3 boots right too (its
    # strapping pins on D0, D8 and D9 read high, XIAO_LINES), for JTAG over Wi-Fi. (JTAG reloads the
    # FPGA too: RECONFIG_N is the button's alone, so an ESP32 booting cannot pulse it)
    xiao(XIAO_LINES)
    # JTAG header for a cable (FT2232 or the like) with the XIAO out of its sockets (the translators
    # then leave the lines alone): 3V3 GND TCK TDO TDI TMS
    part("J16", "JTAG", "lcsc:PZ254V-11-06P", "lcsc:HDR-TH_6P-P2.54-V-M", "C492405",
         {"1": "3V3", "2": "GND", "3": "JTAG_TCK", "4": "JTAG_TDO", "5": "JTAG_TDI", "6": "JTAG_TMS"})
    # RECONFIG_N: 10 k up, the button to GND (as the Console's RECFG key)
    R("10k", "3V3", "RECONFIG_N")
    part("SW3", "TS-1187A-B-A-B", "lcsc:TS-1187A-B-A-B", "lcsc:SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5",
         "C318884", {"1": "RECONFIG_N", "4": "GND"})
    # Configuration status: DONE and READY (open drain at the SOM, 10 k up here) each switch a red
    # LED through a 2N7002, so the LED does not load the line
    for sig, ref in (("FPGA_DONE", "D4"), ("FPGA_READY", "D5")):
        R("10k", "3V3", sig)
        part(nxt("Q"), "2N7002", "lcsc:2N7002", "lcsc:SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR", "C8545",
             {"1": sig, "2": "GND", "3": ref + "_K"})
        R("470", "3V3", ref + "_A")
        part(ref, "KT-0603R", "lcsc:KT-0603R", "lcsc:LED-SMD_L1.6-W0.8-R-RD", "C2286", {"1": ref + "_A", "2": ref + "_K"})
    # The scaler's buttons and status LED (rev B's)
    buttons_led()


def common(second_rail, spdif_connectors="jack"):
    """Everything but the HDMI transmitter: rev B's shared circuits (kit/circuits.py) and rev C's own.
    spdif_connectors: kit/circuits.py spdif()'s (C-A "jack": coax and optical; C-B "optical")."""
    power(second_rail)
    adv7181d()
    pcm1808()
    spdif(spdif_connectors)
    control()
    hdmi_receptacle()


# ---------------------------------------------------------------------------
# The SOM
# ---------------------------------------------------------------------------

# Groups of FPGA signals and where their chip sits (floor.py), in the order they are given pins
def common_groups(spdif_at=floor.SPDIF_AT, ui_at=floor.UI_AT):
    """The chips' places are floor.py's (the ADV7181D under the video jacks, its pins as placed;
    the PCM1808 under the audio jacks, the S/PDIF input under its jack, the clock generator by J21's
    top, the XIAO's translators at the front left, the buttons and LEDs along the front); a
    revision's own S/PDIF and button places if it moves them (C-B)."""
    u1, body = chip_pins("lcsc:LFCSP-64_L9.0-W9.0-P0.50-BL-EP7.1", floor.U1_AT, 0,
                         {sig: avpin(name) for sig, name in FRONTEND_PINS.items()})
    present = {n for p in PARTS for n in p.pins.values()}       # (C-B has no coax input)
    return [
        ("adv7181d", u1, {"IN_LLC": "clock"}, body),
        ("pcm1808", point(["IN_SCKI", "IN_BCK", "IN_LRCK", "IN_DOUT"], floor.PCM1808_AT), {}),
        ("spdif", point([n for n in ("SPDIF_RX", "SPDIF_ORX") if n in present], spdif_at), {}),
        ("vga", point(["VGA_SDA_F", "VGA_SCL_F"], floor.VGA_AT), {}),
        ("clock", point(["PLL_CLK2", "PLL_SCL", "PLL_SDA"], floor.CLOCK_AT), {"PLL_CLK2": "clock"}),
        ("xiao", point([n for n, _ in XIAO_LINES.values() if n.startswith("ESP_")], floor.XIAO_AT), {}),
        ("ui", point(["IN_KEY1", "IN_KEY2", "IN_LED"], ui_at), {}),
    ]


def som(groups, transceiver_lanes=None, rev=None):
    """The SOM's three receptacles with every used pin's net; the standoffs; the MODE straps; the
    pin assignment written to fpga/<rev>.cst as well."""
    block("som")
    pin_nets = pinmap.fixed()
    if transceiver_lanes:
        pin_nets.update(pinmap.transceivers(transceiver_lanes))
    assigned = pinmap.assign(groups, pin_nets)
    pin_nets.update(assigned)
    for ref, (console, count, _, _) in _som.CONNECTORS.items():
        pins = {str(p): n for (r, p), n in pin_nets.items() if r == ref}
        part(ref, "DF40HC(3.0)-%dDS" % count, _som.SYMBOL[count], "lcsc:" + _som.FOOTPRINT[count], _som.LCSC[count],
             pins, note="SOM %s (the Console's %s)" % (ref, console))
    # MODE[2:0] = 001: configuration from the SOM's SPI flash (MSPI), as the Console's default
    R("1k", "3V3", "MODE0")
    R("5.1k", "MODE1", "GND")
    R("5.1k", "MODE2", "GND")
    # The SOM's four M2 holes (som.py: M2 x 3 mm spacers and screws, fitted by hand), to GND
    for k in range(1, 5):
        part("SO%d" % k, "M2 spacer 3mm", "Mechanical:MountingHole_Pad", "lcsc:" + _som.HOLE_FOOTPRINT, "",
             {"1": "GND"}, note="M2 x 3 mm spacer, fitted by hand")
    for _ in range(4):
        C("22u", "+5V", size="C0805")
    if rev:
        pinmap.write_cst(os.path.join(os.path.dirname(HERE), "rev-" + rev.lower().replace("-", ""), "fpga",
                                      "av-board-%s.cst" % rev.lower().replace("-", "")), assigned)
    return pin_nets


def check(extra=()):
    errors = common_errors()
    errors += unconnected("U1", AV, ADV7181D_OPEN.match)
    for e in extra:
        errors += e()
    return errors
