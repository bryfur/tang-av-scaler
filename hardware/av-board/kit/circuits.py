"""Circuit blocks the revisions share: rev B's circuits, reviewed against every data sheet
(rev-b/review.md), used as they are by rev C-A and C-B too. A revision's board.py calls them in its
own order (the reference designators R1, C1 ... follow the order of the calls). The design behind
each block is in rev-b/design.md; sources in brackets:

    [DS] ADV7181D data sheet Rev C         [HWG] ADV7511 hardware user's guide Rev D
    [PSU] ADI's PCB layout and power supply recommendations for HDMI receivers
    [TI] TLV62569, TPS7A7001               [TI-ADC] PCM1808          [TI-LDO2] TPS7A20
    [TI-ESD] TPD1E05U06, TPD4E05U06        [LVC] TI's SN74LVC1G04, SN74LVC1GU04, SN74LVC2G17
    [AN-1260] ADI's crystal design considerations for video decoders
"""

import re

from parts import C, R, block, lib_pins, nxt, part, two

AV = lib_pins("lcsc:ADV7181DBCPZ-RL")
TX = lib_pins("lcsc:ADV7511KSTZ")
# Jacks: CUI RCJ-01x, one footprint, the last digit the colour (1 black, 2 red, 3 white, 4 yellow, 7
# orange [RCJ-01 data sheet]): yellow RCJ-014 ($1.69, 200 in stock) where rev A had black RCJ-011
# ($3.82, 40), red RCJ-012 for Pr and R; the silkscreen names each input
RCA_YELLOW, RCA_RED, RCA_ORANGE = "C4991844", "C4991691", "C22359757"
# the ADV7181D's pins tied to the FPGA (through their 33 R, or straight): FPGA line -> pin name
ADV7181D_FPGA_PINS = {"IN_RESET_N": "#RESET", "IN_SDA": "SDATA", "IN_SCL": "SCLK", "IN_INT": "#INT",
                      "IN_Y7": "P19", "IN_Y6": "P18", "IN_Y5": "P17", "IN_Y4": "P16", "IN_Y3": "P15",
                      "IN_Y2": "P14", "IN_Y1": "P13", "IN_Y0": "P12", "IN_C7": "P9", "IN_C6": "P8",
                      "IN_C5": "P7", "IN_C4": "P6", "IN_C3": "P5", "IN_C2": "P4", "IN_C1": "P3", "IN_C0": "P2",
                      "IN_LLC": "LLC", "IN_HS": "HS/CS", "IN_VS": "VS", "IN_DE": "FIELD/DE"}
# the ADV7181D's pins left open on purpose: unused inputs and outputs [DS Table 7]
ADV7181D_OPEN = re.compile(r"^(AIN[1345]|SFL/SYNC_OUT|P0|P1|P10|P11)$")


def avpin(name):
    (n,) = AV[name]
    return n


def txpin(name):
    (n,) = TX[name]
    return n


# ---------------------------------------------------------------------------
# Supplies (rev-b/design.md "Power")
# ---------------------------------------------------------------------------

def supply_tree(second_rail="1V8B"):
    """+5 V -> TLV62569 buck -> 3V6 -> TPS7A7001 3V3 -> TPS7A7001 1.8 V LDOs: 1V8A (the ADV7181D)
    and second_rail (rev B's and C-A's 1V8B for the ADV7511; None: none), the 1V8A clamp, the
    ADV7181D rails' ferrites. In the caller's block."""
    # Each LDO is enabled by its own input, so a 1.8 V rail rises behind 3V3 and can never pass it,
    # and once in regulation trails it by 1.5 V: the ADV7181D's supply-to-supply limits (DVDDIO -
    # PVDD and AVDD - DVDD within -0.3..+2 V [DS Table 5]) hold at power-up by construction. Rev A
    # started 3V3 30 ms before the 1.8 V rails, a 3.3 V difference.

    # 3V6: TLV62569 buck [TI Fig. 5, 8.2.2]: R2 100 k, R1 499 k: 0.6 V x (1 + 4.99) = 3.594 V (Eq. 2);
    # 6.8 pF feed-forward for R2 = 100 k [TI 8.2.2.2]; 2.2 uH (Isat 2 A, 78 mR) with 10 uF out
    # [Table 4]; 10 uF in (TI's 4.7 uF, doubled: the 0805's 5 V DC bias leaves about 60 %). About
    # 0.6 A out
    part("U4", "TLV62569DBVR", "lcsc:TLV62569DBVR", "lcsc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR", "C141836",
         {"1": "+5V", "2": "GND", "3": "SW_3V6", "4": "+5V", "5": "FB_3V6"})
    # (placed in this order, each by its pin [TI 10.1: the capacitors and the inductor as close as
    # possible, FB away from SW]: the input capacitor at VIN (EN, pin 1, is on +5 V too, across the
    # package from it), the feedback divider at FB on the same side, then the inductor at SW and
    # the output capacitor at its far end)
    C("10u", "+5V", size="C0805", at="U4.4")
    R("499k", "3V6", "FB_3V6")
    R("100k", "FB_3V6", "GND")
    C("6.8p", "3V6", "FB_3V6")
    l = nxt("L")
    two(l, "L3015", "2.2uH", "SW_3V6", "3V6")
    C("10u", "3V6", size="C0805", at=l + ".2")

    # 3V3: TPS7A7001 from 3V6, EN tied to IN [TI 7.3.1]; R1 169 k / R2 30.1 k = 3.307 V [TI Table 2];
    # 10 uF in and out [TI 6.3]; 220 pF feed-forward across R1 [TI 8.1.2: more than 47 uF on the
    # output, here about 60 uF with the 1.8 V LDOs' inputs]. 0.3 V headroom against about 0.1 V
    # dropout at its 0.6 A [TI Fig. 3]; 0.18 W
    part("U5", "TPS7A7001DDAR", "lcsc:TPS7A7001DDAR", "lcsc:SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL-EP", "C60719",
         {"3": "3V6", "2": "3V6", "6": "3V3", "7": "FB_3V3", "8": "GND", "9": "GND", "1": "GND", "4": "GND", "5": "GND"})
    # (in this order: the input capacitor at IN, the feedback divider at FB, the output capacitor
    # at OUT, FB's neighbour: the divider's node is the one noise reaches)
    C("10u", "3V6", size="C0805", at="U5.3")
    R("169k", "3V3", "FB_3V3")
    R("30.1k", "FB_3V3", "GND")
    C("220p", "3V3", "FB_3V3")
    C("10u", "3V3", size="C0805", at="U5.6")

    # 1V8A (ADV7181D, about 0.13 A) and 1V8B (ADV7511, at most 0.18 A [HWG 6.8.2: 326 mW]): TPS7A7001
    # from 3V3, EN tied to IN; R1 78.7 k / R2 30.1 k = 1.807 V [TI Table 2]; 10 uF in and out, 220 pF
    # feed-forward as for 3V3. 0.2 and 0.27 W
    for u, out in [("U6", "1V8A")] + ([("U7", second_rail)] if second_rail else []):
        fb = "FB_" + out
        part(u, "TPS7A7001DDAR", "lcsc:TPS7A7001DDAR", "lcsc:SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL-EP", "C60719",
             {"3": "3V3", "2": "3V3", "6": out, "7": fb, "8": "GND", "9": "GND", "1": "GND", "4": "GND", "5": "GND"})
        C("10u", "3V3", size="C0805", at=u + ".3")      # (in 3V3's order)
        R("78.7k", out, fb)
        R("30.1k", fb, "GND")
        C("220p", out, fb)
        C("10u", out, size="C0805", at=u + ".6")

    # Power-down: 3V3 carries the heavier load and may fall faster than 1V8A; a Schottky from 1V8A
    # to 3V3 holds 1V8A within its forward drop (about 0.25 V at a few mA) of 3V3, inside the
    # ADV7181D's -0.3 V [DS Table 5]. Reverse-biased (1.5 V) in operation
    part("D1", "B5819W", "Device:D_Schottky", "Diode_SMD:D_SOD-123", "C8598", {"1": "3V3", "2": "1V8A"})

    # ADV7181D rails: a ferrite per supply, 10 uF after it [PSU: a ferrite per rail, 10 uF bulk; DS
    # Fig. 9 draws the rails filtered off-sheet]. BLM18PG121SN1D: 120 R at 100 MHz, 2 A, 50 mR: AVDD's
    # 0.2 A drops 10 mV (the 0.2 A / 0.45 R bead first fitted dropped 90 mV and put AVDD under its
    # 3.15 V minimum at the 3V3 LDO's low limit)
    for src, rail in (("1V8A", "AV_DVDD"), ("1V8A", "AV_PVDD"), ("3V3", "AV_AVDD"), ("3V3", "AV_DVDDIO")):
        two(nxt("FB"), "FB0603", "120R", src, rail)
        C("10u", rail)


# ---------------------------------------------------------------------------
# ADV7181D (rev-b/design.md "ADV7181DBCPZ", "VGA")
# ---------------------------------------------------------------------------

def adv7181d():
    """The ADV7181D (U1): component and SCART RGB in, its sync inputs, the crystal, the ADC
    references, the PLL filter, the pixel port's series resistors, the control lines, the VGA input,
    the supply pins' decoupling."""
    block("adv7181d")
    u1 = {}
    for name, nums in AV.items():
        net = {"GND": "GND", "EP": "GND", "DVDD": "AV_DVDD", "PVDD": "AV_PVDD", "AVDD": "AV_AVDD",
               "DVDDIO": "AV_DVDDIO"}.get(name)
        if net:
            for n in nums:
                u1[n] = net

    # Component in: 75 R to GND at the jack, 0.1 uF to the input; Y on AIN10, Pb on AIN8, Pr on AIN6
    # [DS Fig. 9, Table 8 "Component YUV": Y = AIN10, U = AIN8, V = AIN6]; Y also through 1 nF to SOY,
    # sync on Y [DS Fig. 9]
    for jack, sig, ain, lc, colour in (("J1", "Y", "AIN10", RCA_YELLOW, "yellow"), ("J2", "PB", "AIN8", RCA_YELLOW, "yellow"),
                                       ("J3", "PR", "AIN6", RCA_RED, "red")):
        part(jack, "RCA " + {"Y": "Y", "PB": "Pb", "PR": "Pr"}[sig], "lcsc:RCJ-014", "lcsc:CONN-TH_RCJ-011", lc,
             {"2": "RCA_" + sig, "1": "GND"}, note=colour + " RCJ-01x")
        two(nxt("R"), "R0603", "75", "RCA_" + sig, "GND")
        C("100n", "RCA_" + sig, "AIN_" + sig)
        u1[avpin(ain)] = "AIN_" + sig
    C("1n", "RCA_Y", "SYNC_Y")
    u1[avpin("SOY")] = "SYNC_Y"
    # SCART RGB: R/G/B on the three jacks above (CP RGB, manual muxing [DS Table 9]); its sync (sync on
    # composite video, or CSYNC) on J7 into the second sync slicer, SOG: 75 R termination, 1 nF [DS
    # Fig. 9, as SOY]. A 2-pin header (SYNC, GND): no room for a sixth jack on rev B's edge
    part("J7", "SYNC", "lcsc:PZ254V-11-02P", "lcsc:HDR-TH_2P-P2.54-V-M", "C492401", {"1": "RCA_SYNC", "2": "GND"})
    two(nxt("R"), "R0603", "75", "RCA_SYNC", "GND")
    C("1n", "RCA_SYNC", "SYNC_G")
    u1[avpin("SOG")] = "SYNC_G"
    # ESD on the four video inputs (DS Fig. 9 has none; the connectors are where a charged cable
    # lands): a TPD1E05U06 each, the single-line part of the TMDS lines' family (0.42-0.5 pF, 5.5 V
    # stand-off, 6.5 V breakdown minimum, unidirectional [TI-ESD]), at its connector's pin as TI asks
    # [TI-ESD Pin Functions note 2] (kit/pcbkit.py places ESD parts first, at their connectors). One
    # four-line array for all four left Y 18 mm and the sync 25 mm from theirs (the jacks are 13 mm
    # apart, J7 a header elsewhere)
    for ref, sig in (("D8", "RCA_Y"), ("D9", "RCA_PB"), ("D10", "RCA_PR"), ("D11", "RCA_SYNC")):
        part(ref, "TPD1E05U06DPYR", "lcsc:TPD1E05U06DPYR", "lcsc:X1SON-2_L1.0-W0.6-P0.65-RD-1", "C436349",
             {"1": sig, "2": "GND"})

    # Crystal: 28.63636 MHz fundamental [DS Table 1, pin 21], 1 M across [DS Fig. 9]. YXC
    # X50322863636MSB2GI: 20 pF load, +-10 ppm at 25 C, +-20 ppm over temperature, 40 R ESR, 5032
    # two-pad (476 in stock; rev A's TXM part had 68). Load caps C = 2 (CL - Cstray) - Cpg = 31 pF
    # [AN-1260], 33 pF C0G the nearest JLCPCB basic part: about 1 pF over the load, about -9 ppm;
    # worst case -39 ppm against the decoder's +-50 ppm [DS Table 1]. Fig. 9's 47 pF suit its own
    # crystal
    part("Y1", "28.63636MHz 20pF", "lcsc:SMD-5032_2P28.63636M20pF", "lcsc:CRYSTAL-SMD_L5.0-W3.2", "C112564",
         {"1": "XTAL", "2": "XTAL1"})
    R("1M", "XTAL", "XTAL1")
    C("33p", "XTAL")
    C("33p", "XTAL1")
    u1[avpin("XTAL")] = "XTAL"
    u1[avpin("XTAL1")] = "XTAL1"

    # ADC references [DS Fig. 9]: CAPY2 to GND through 0.1 uF (twice); 10 uF + 0.1 uF + 10 nF from
    # CAPY1 to CAPY2 and from CAPC2 to CAPY2; REFOUT and CML 10 uF + 0.1 uF each to GND. The 10 uF in
    # 0402 (6.3 V X5R; the references sit near 1-2 V, where it keeps about 7 uF): the network is laid
    # as a block above its pins, top side only (kit/adv7181d_layout.py band)
    for name in ("CAPY1", "CAPY2", "CAPC2", "REFOUT", "CML"):
        u1[avpin(name)] = name
    C("100n", "CAPY2")
    C("100n", "CAPY2")
    for a in ("CAPY1", "CAPC2"):
        C("10u", a, "CAPY2", size="C0402")
        C("100n", a, "CAPY2")
        C("10n", a, "CAPY2")
    for a in ("REFOUT", "CML"):
        C("10u", a, size="C0402")
        C("100n", a)

    # PLL loop filter at ELPF: 1.69 k + 82 nF in series and 10 nF across, to PVDD [DS Fig. 8]
    u1[avpin("ELPF")] = "ELPF"
    R("1.69k", "ELPF", "ELPF_RC")
    C("82n", "ELPF_RC", "AV_PVDD")
    C("10n", "ELPF", "AV_PVDD")

    # Pixel port: 16-bit SDR 4:2:2, Y on P19-P12, CbCr on P9-P2 [DS Table 11, CP 16-bit SDR]; 33 R in
    # series next to the chip on every output [DS Fig. 9]. Where four used pins sit side by side
    # (P19-P16, P15-P12, P6-P4 + LLC) a 4 x 0402 array at the pins' own 0.5 mm pitch, in line with
    # them (kit/adv7181d_layout.py); a single 0402 on each of the others
    arrays = [[("P19", "Y7"), ("P18", "Y6"), ("P17", "Y5"), ("P16", "Y4")],
              [("P15", "Y3"), ("P14", "Y2"), ("P13", "Y1"), ("P12", "Y0")],
              [("P6", "C4"), ("P5", "C3"), ("P4", "C2"), ("LLC", "LLC")]]
    single = [("P9", "C7"), ("P8", "C6"), ("P7", "C5"), ("P3", "C1"), ("P2", "C0"), ("HS/CS", "HS"),
              ("VS", "VS"), ("FIELD/DE", "DE")]
    for group in arrays:
        pins = {}
        for j, (pname, sig) in enumerate(group):
            u1[avpin(pname)] = "AV_" + sig
            pins[str(1 + j)] = "AV_" + sig
            pins[str(8 - j)] = "IN_" + sig
        part(nxt("RN"), "33", "lcsc:4D02WGJ0750TCE", "lcsc:RES-ARRAY-SMD_0402-8P-L2.0-W1.0-BL", "C25501", pins)
    for pname, sig in single:
        u1[avpin(pname)] = "AV_" + sig
        R("33", "AV_" + sig, "IN_" + sig)

    # Control [DS Fig. 9, Table 7]: I2C to the FPGA with 4.7 k pull-ups (rev A's), ALSB high (write
    # address 0x42), PWRDWN high through 4.7 k, INT 4.7 k to DVDDIO (open drain by default)
    u1[avpin("SCLK")] = "IN_SCL"
    u1[avpin("SDATA")] = "IN_SDA"
    R("4.7k", "3V3", "IN_SCL")
    R("4.7k", "3V3", "IN_SDA")
    u1[avpin("#RESET")] = "IN_RESET_N"
    R("4.7k", "IN_RESET_N", "GND", note="held in reset until the FPGA drives it (5 ms low minimum [DS pin 51])")
    u1[avpin("#INT")] = "IN_INT"
    R("4.7k", "AV_DVDDIO", "IN_INT")
    u1[avpin("ALSB")] = "ALSB"
    R("4.7k", "AV_DVDDIO", "ALSB")
    u1[avpin("#PWRDWN")] = "PWRDWN"
    R("4.7k", "AV_DVDDIO", "PWRDWN")
    # Unused input held low: fast blank (SCART only)
    u1[avpin("FB")] = "PD_FB"
    R("10k", "PD_FB", "GND")

    _vga(u1)
    part("U1", "ADV7181DBCPZ-RL", "lcsc:ADV7181DBCPZ-RL", "lcsc:LFCSP-64_L9.0-W9.0-P0.50-BL-EP7.1", "C514378", u1)

    # Decoupling, per supply pin as DS Fig. 9: DVDDIO and DVDD 2 x (0.1 uF + 10 nF), PVDD and AVDD
    # 0.1 uF + 10 nF
    for rail, n in (("AV_DVDDIO", 2), ("AV_DVDD", 2), ("AV_PVDD", 1), ("AV_AVDD", 1)):
        for _ in range(n):
            C("100n", rail)
            C("10n", rail)


def _vga(u1):
    # VGA in (rev-b/design.md "VGA"): RGB with separate (or composite) sync on J8, a 2 x 8 header whose
    # pin n is the DE-15's pin n (16 unused), for a bracket cable. R, G, B as the component inputs (75 R,
    # 100 nF) on the inputs Table 9 routes to the three ADCs besides the component ones: G on AIN2
    # (ADC0), B on AIN9 (ADC1), R on AIN7 (ADC2) [DS Table 9], R and B among the component inputs (pins
    # 45-49), G past the reference pins (39-44) on the other side, none against them; the CP digitizes
    # RGB graphics up to XGA at 70 Hz [DS p. 1]. H and V sync (TTL, up to 5 V) through an SN74LVC2G17
    # (Schmitt, inputs 5.5 V tolerant at a 3.3 V supply [LVC]) into HS_IN/CS_IN and VS_IN, 5-wire (or
    # 4-wire, composite sync on H) [DS pins 55, 56]; 10 k holds an empty input low. DDC (EDID for a PC)
    # to the FPGA through two 2N7002 in the level-shifter arrangement (gate at 3.3 V; a board that is
    # off leaves the source's bus alone); 47 k to the source's 5 V (pin 9) keeps the lines high with no
    # FPGA. ESD: two TPD4E05U06, one for R/G/B, one for the syncs and DDC (a sync on the video
    # array ran its line beside R's)
    part("J8", "VGA", "lcsc:Header-Male-2.54_2x8", "lcsc:HDR-TH_16P-P2.54-V-M-R2-C8-S2.54", "C68234",
         {"1": "VGA_R", "2": "VGA_G", "3": "VGA_B", "5": "GND", "6": "GND", "7": "GND", "8": "GND", "9": "VGA_5V",
          "10": "GND", "12": "VGA_SDA", "13": "VGA_HS", "14": "VGA_VS", "15": "VGA_SCL"},
         note="pin n = the DE-15's pin n")
    for sig, ain in (("R", "AIN7"), ("G", "AIN2"), ("B", "AIN9")):
        two(nxt("R"), "R0603", "75", "VGA_" + sig, "GND")
        C("100n", "VGA_" + sig, "AIN_V" + sig)
        u1[avpin(ain)] = "AIN_V" + sig
    # (its channels in the header's order: G, the even row's, on the ground pads' one side, R and B,
    # the odd row's, on the other, so no line crosses another between the header and the array; R on
    # the outermost channel crossed G's line there and did not route on rev B)
    part("U19", "TPD4E05U06DQAR", "lcsc:TPD4E05U06DQAR_C138714", "lcsc:USON-10_L2.5-W1.0-P0.50-BL", "C138714",
         {"2": "VGA_G", "9": "VGA_G", "4": "VGA_R", "7": "VGA_R", "5": "VGA_B", "6": "VGA_B", "3": "GND", "8": "GND"})
    part("U20", "TPD4E05U06DQAR", "lcsc:TPD4E05U06DQAR_C138714", "lcsc:USON-10_L2.5-W1.0-P0.50-BL", "C138714",
         {"1": "VGA_HS", "10": "VGA_HS", "2": "VGA_VS", "9": "VGA_VS", "4": "VGA_SDA", "7": "VGA_SDA",
          "5": "VGA_SCL", "6": "VGA_SCL", "3": "GND", "8": "GND"})
    part("U21", "SN74LVC2G17DBVR", "lcsc:SN74LVC2G17DBVR", "lcsc:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL", "C10429",
         {"1": "VGA_HS", "2": "GND", "3": "VGA_VS", "4": "VGA_VSB", "5": "3V3", "6": "VGA_HSB"})
    C("100n", "3V3", at="U21.5")
    R("10k", "VGA_HS", "GND")
    R("10k", "VGA_VS", "GND")
    R("33", "VGA_HSB", "VGA_HSIN")
    R("33", "VGA_VSB", "VGA_VSIN")
    u1[avpin("HS_IN/CS_IN")] = "VGA_HSIN"
    u1[avpin("VS_IN")] = "VGA_VSIN"
    for sig in ("SDA", "SCL"):
        part(nxt("Q"), "2N7002", "lcsc:2N7002", "lcsc:SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR", "C8545",
             {"1": "3V3", "2": "VGA_%s_F" % sig, "3": "VGA_" + sig})
        R("4.7k", "3V3", "VGA_%s_F" % sig)
        R("47k", "VGA_5V", "VGA_" + sig)


# ---------------------------------------------------------------------------
# PCM1808 [TI-ADC Fig. 26, 8.2.2] and the S/PDIF input (rev-b/design.md "Audio", "Additions")
# ---------------------------------------------------------------------------

def pcm1808():
    """The PCM1808 (U3) stereo input: its own 4.5 V LDO, the line inputs' dividers and filters, the
    L and R jacks (J4, J5)."""
    block("pcm1808")
    part("U3", "PCM1808PWR", "lcsc:PCM1808PWR", "lcsc:TSSOP-14_L5.0-W4.4-P0.65-LS6.4-BL", "C55513",
         {"1": "VREF", "2": "GND", "3": "5VA", "4": "3V3", "5": "GND", "6": "IN_SCKI", "7": "IN_LRCK", "8": "IN_BCK",
          "9": "IN_DOUT", "10": "MD0", "11": "MD1", "12": "FMT", "13": "AUD_VINL", "14": "AUD_VINR"})
    for pin in ("MD0", "MD1", "FMT"):
        R("10k", pin, "GND")                         # slave mode, I2S [TI-ADC 8.2.2.1]
    # VCC: its own low-noise LDO from +5 V, at the PCM1808. VREF (the ADC's reference and the inputs'
    # bias) is VCC / 2 [TI-ADC 7], so audio-band noise on VCC lands in the conversion; a 5 V supply
    # from elsewhere (the Console's, a USB adapter's) carries its own regulators' noise and this
    # board's buck input current, and a ferrite passes all of it below a few MHz. TPS7A2045: 4.5 V,
    # 10 uVrms, 92 dB PSRR at 1 kHz, about 5 mV dropout at the PCM1808's 9 mA; EN tied to IN (internal
    # pull-down); >= 1 uF in, 1-200 uF ceramic out [TI-LDO2 Pin Functions, 6.3]. VCC 4.5 V is inside
    # 4.0-5.5 V
    part("U12", "TPS7A2045PDBVR", "lcsc:TPS7A2045PDBVR", "lcsc:SOT-23-5_L2.9-W1.6-P0.95-LS2.8-BR", "C2873627",
         {"1": "+5V", "2": "GND", "3": "+5V", "5": "5VA"}, at="U3.3")
    C("1u", "+5V", at="U12.1")
    # VREF, VCC (5VA) and VDD (3V3): 100 nF and 10 uF at each pin [TI-ADC 10.1.1: "as close to the
    # pins as possible"]; the 5VA pair is the LDO's output capacitor as well, a few mm off
    for rail, pin in (("VREF", "1"), ("5VA", "3"), ("3V3", "4")):
        C("100n", rail, at="U3." + pin)
        C("10u", rail, at="U3." + pin)
    for jack, ch, lc, colour in (("J4", "L", RCA_YELLOW, "yellow"), ("J5", "R", RCA_RED, "red")):
        part(jack, "RCA " + ch, "lcsc:RCJ-014", "lcsc:CONN-TH_RCJ-011", lc,
             {"2": "RCA_" + ch, "1": "GND"}, note=colour + " RCJ-01x")
        # 12 k over 10 k // 60 k (the input): 0.42, a 2 Vrms line in to 2.36 Vp-p, 1.2 dB under the
        # full scale at VCC = 4.5 V (0.6 VCC = 2.7 Vp-p [TI-ADC 6.3])
        R("12k", "RCA_" + ch, "AUD_DIV_" + ch)
        R("10k", "AUD_DIV_" + ch, "GND")
        C("220p", "AUD_DIV_" + ch)                   # anti-alias RC: 5.5 k x 220 pF, 133 kHz [TI-ADC 10.1.3]
        C("1u", "AUD_DIV_" + ch, "AUD_VIN" + ch)


def spdif(connectors):
    """The S/PDIF input, coax and optical, to the FPGA (SPDIF_RX, SPDIF_ORX), which decodes the
    biphase code itself (no receiver chip) and can send it on, delayed for lip sync, to the HDMI
    transmitter: Dolby Digital / DTS pass to the TV untouched. connectors: "header" (rev B: J13, five
    pins: 1 COAX, 2 GND, 3 OPT, 4 GND, 5 +5 V; coax on an orange RCA pigtail, a TOSLINK receiver
    module on 3-5; rev B, and rev C-B, whose narrower board has no room for the jack), "jack" (rev
    C-A: an orange RCA, J14, on the back edge; the module on J13, three pins: 1 OUT, 2 GND, 3 +5 V)
    or "optical" (the module's J13 alone, no coax: the PS2 has an optical output only; no board
    uses it now). Module pin order: a PLR135's (OUT, GND, VCC)."""
    block("spdif")
    coax = connectors != "optical"
    if connectors == "header":
        part("J13", "SPDIF", "lcsc:PZ254V-11-05P", "lcsc:HDR-TH_5P-P2.54-V-M", "C492404",
             {"1": "SPDIF_COAX", "2": "GND", "3": "SPDIF_OPT", "4": "GND", "5": "SPDIF_5V"})
    else:
        if coax:
            part("J14", "RCA S/PDIF", "lcsc:RCJ-017", "lcsc:CONN-TH_RCJ-011", RCA_ORANGE, {"2": "SPDIF_COAX", "1": "GND"},
                 note="orange RCJ-01x")
        part("J13", "OPTICAL", "lcsc:PZ254V-11-03P_C2937625", "lcsc:HDR-TH_3P-P2.54-V-M_PZ254V-11-03P", "C2937625",
             {"1": "SPDIF_OPT", "2": "GND", "3": "SPDIF_5V"})
    # ESD on each input, a TPD1E05U06 at its connector's pin (5.5 V working: a 5 V module's output
    # is inside it [TI-ESD]): rev C-A's two connectors are 25 mm apart, too far for one array
    for ref, sig in ((("D12", "SPDIF_COAX"),) if coax else ()) + (("D13", "SPDIF_OPT"),):
        part(ref, "TPD1E05U06DPYR", "lcsc:TPD1E05U06DPYR", "lcsc:X1SON-2_L1.0-W0.6-P0.65-RD-1", "C436349",
             {"1": sig, "2": "GND"})
    # The module's supply: +5 V through the HDMI 5 V's 0.2 A PTC part (a short at the header trips it
    # instead of pulling down the board's 5 V), 100 nF at the pin. Most modules take 5 V (TORX
    # 4.75-5.25 V, PLR135 2.7-5.5 V)
    two(nxt("F"), "PTC0805", "0.2A", "+5V", "SPDIF_5V")
    C("100n", "SPDIF_5V", at="J13.5" if connectors == "header" else "J13.3")
    if coax:
        # Coax [IEC 60958-3: 0.5 Vp-p into 75 R]: 75 R termination, 100 nF, then an unbuffered inverter
        # biased at its threshold by 1 M (a linear amplifier: 0.5 Vp-p swings it rail to rail) and a
        # buffered one to square the edges; 33 R at the source towards the FPGA
        two(nxt("R"), "R0603", "75", "SPDIF_COAX", "GND")
        C("100n", "SPDIF_COAX", "SPDIF_AC")
        part("U13", "SN74LVC1GU04DBVR", "lcsc:SN74LVC1GU04DBVR", "lcsc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR", "C81934",
             {"2": "SPDIF_AC", "3": "GND", "4": "SPDIF_AMP", "5": "3V3"})
        R("1M", "SPDIF_AMP", "SPDIF_AC")
        part("U14", "SN74LVC1G04DBVR", "lcsc:SN74LVC1G04DBVR", "lcsc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR", "C7827",
             {"2": "SPDIF_AMP", "3": "GND", "4": "SPDIF_SQ", "5": "3V3"})
        R("33", "SPDIF_SQ", "SPDIF_RX")
    # Optical: the module's logic output through a buffer whose input takes 5.5 V at any supply [LVC]:
    # the FPGA sees 3.3 V whatever the module runs from; 100 k holds an empty input low
    part("U15", "SN74LVC1G04DBVR", "lcsc:SN74LVC1G04DBVR", "lcsc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR", "C7827",
         {"2": "SPDIF_OPT", "3": "GND", "4": "SPDIF_OSQ", "5": "3V3"})
    R("100k", "SPDIF_OPT", "GND")
    R("33", "SPDIF_OSQ", "SPDIF_ORX")
    for u in (("U13", "U14") if coax else ()) + ("U15",):        # (one at each inverter's VCC)
        C("100n", "3V3", at=u + ".5")


# ---------------------------------------------------------------------------
# The XIAO (rev-b/design.md "XIAO", rev-c/design.md)
# ---------------------------------------------------------------------------

# Pull resistors (10 k) on the lines between a XIAO and the FPGA, so that no translator input ever
# floats and nothing happens while the XIAO boots (its pins are inputs then) or while the socket is
# empty. On the XIAO's side of a line it drives: JTAG's TCK low and TMS/TDI high (the TAP held in
# reset), SPI's chip select high, the UART's TX high (idle), MOSI low, and SCK high: on an ESP32-C3
# D8 is GPIO8, a strapping pin that must read high for its download boot [ESP32-C3 DS Table 3-3]
# (chip select is high meanwhile, so the FPGA ignores SCK). On the FPGA's side: every line the FPGA
# drives (TDO, MISO: driven only while selected; RX; IRQ, active low), high; and chip select and
# JTAG's inputs again (for an empty socket, or rev C's JTAG header)
XIAO_SIDE_PULL = {"JTAG_TCK": "down", "JTAG_TMS": "up", "JTAG_TDI": "up", "ESP_CS": "up", "ESP_TX": "up",
                  "ESP_SCK": "up", "ESP_MOSI": "down"}
FPGA_SIDE_PULL = {"JTAG_TCK": "down", "JTAG_TMS": "up", "JTAG_TDI": "up", "JTAG_TDO": "up", "ESP_CS": "up",
                  "ESP_MISO": "up", "ESP_RX": "up", "ESP_IRQ": "up"}


def xiao(lines):
    """A Seeed XIAO ESP32 (21 x 17.8 mm) on two 1x7 sockets: J12 its pins 1-7 (D0-D6), J11 its pins
    14-8 (5V, GND, 3V3, D10, D9, D8, D7), rows 15.24 mm apart, the XIAO's own pitch. lines: {XIAO
    pin ("D0".."D10"): (the FPGA's net, "out" from the XIAO or "in" to it)}.

    Each line passes a level translator powered from both sides: the A side from the XIAO's own
    3.3 V (its 3V3 pin), the B side from the board's. If either supply is off, both sides of every
    channel go to high impedance, and the inputs take any voltage up to 5.5 V unpowered [TI
    SN74LVC8T245 and SN74AVC4T245: VCC isolation, Ioff]: a XIAO running from its own USB with the
    board off cannot feed the FPGA's I/O (or the board's 3V3 through them), an empty socket leaves
    the FPGA's lines to whatever else drives them (rev C's JTAG header). U22 (SN74LVC8T245, DIR
    high: A to B) carries up to eight lines from the XIAO, U23 (SN74AVC4T245, both halves B to A) up
    to four to it, each through 470 R: on an ESP32-C3 D9 is GPIO9, which its BOOT button shorts to
    GND, and U23 drives it (high, from MISO's pull-up): 7 mA then, not the output's short-circuit
    current; 470 R x about 8 pF of pin and socket is 4 ns on edges for SPI and JTAG of 20 MHz and
    less. DIR and OE are referenced to VCCA. 100 k holds the XIAO's 3V3 at 0 V with the socket
    empty. The XIAO's 5 V pin from +5 V through a Schottky (D3), so a USB cable in the XIAO cannot
    feed the board's 5 V; 10 uF there for its Wi-Fi bursts."""
    j12 = {str(1 + k): "XIAO_D%d" % k for k in range(7) if "D%d" % k in lines}
    j11 = {"1": "XIAO_5V", "2": "GND", "3": "XIAO_3V3"}
    j11.update({str(4 + k): "XIAO_D%d" % (10 - k) for k in range(4) if "D%d" % (10 - k) in lines})
    part("J12", "XIAO D0..D6", "lcsc:HXPM2.54-1X7PZC-Y", "lcsc:HDR-TH_7P-P2.54-V-F", "C22438157", j12,
         note="XIAO pins 1..7: D0..D6")
    part("J11", "XIAO 5V..D7", "lcsc:HXPM2.54-1X7PZC-Y", "lcsc:HDR-TH_7P-P2.54-V-F", "C22438157", j11,
         note="XIAO pins 14..8: 5V GND 3V3 D10 D9 D8 D7")
    part("D3", "B5819W", "Device:D_Schottky", "Diode_SMD:D_SOD-123", "C8598", {"1": "XIAO_5V", "2": "+5V"})
    C("10u", "XIAO_5V", size="C0805", at="J11.1")
    R("100k", "XIAO_3V3", "GND")
    outs = [(d, n) for d, (n, way) in lines.items() if way == "out"]
    ins = [(d, n) for d, (n, way) in lines.items() if way == "in"]
    assert len(outs) <= 8 and len(ins) <= 4, lines
    # U22: A1-A8 (pins 3-10) to B1-B8 (pins 21-14); an unused input held low
    u = {"1": "XIAO_3V3", "2": "XIAO_3V3", "11": "GND", "12": "GND", "13": "GND", "22": "GND", "23": "3V3", "24": "3V3"}
    for k in range(8):
        if k < len(outs):
            u[str(3 + k)] = "XIAO_" + outs[k][0]
            u[str(21 - k)] = outs[k][1]
        else:
            u[str(3 + k)] = "GND"
    part("U22", "SN74LVC8T245PWR", "lcsc:SN74LVC8T245PWR", "lcsc:TSSOP-24_L7.8-W4.4-P0.65-LS6.4-BL", "C27643", u)
    C("100n", "XIAO_3V3", at="U22.1")             # (at VCCA and VCCB)
    C("100n", "3V3", at="U22.24")
    # U23: 1B1, 1B2, 2B1, 2B2 (pins 13, 12, 11, 10) to 1A1 ... 2A2 (pins 4-7), 1DIR/2DIR low (B to A),
    # both OE low; an unused input held low; each output through 470 R to its XIAO pin
    v = {"1": "XIAO_3V3", "2": "GND", "3": "GND", "8": "GND", "9": "GND", "14": "GND", "15": "GND", "16": "3V3"}
    for k, (a, b) in enumerate((("4", "13"), ("5", "12"), ("6", "11"), ("7", "10"))):
        if k < len(ins):
            v[a] = "XIAO_%s_A" % ins[k][0]
            v[b] = ins[k][1]
        else:
            v[b] = "GND"
    part("U23", "SN74AVC4T245PWR", "lcsc:SN74AVC4T245PWR", "lcsc:TSSOP-16_L5.0-W4.4-P0.65-LS6.4-BL", "C81461", v)
    C("100n", "XIAO_3V3", at="U23.1")
    C("100n", "3V3", at="U23.16")
    for d, n in ins:
        R("470", "XIAO_%s_A" % d, "XIAO_" + d)
    for d, n in outs:
        if n in XIAO_SIDE_PULL:
            R("10k", "XIAO_" + d, "XIAO_3V3" if XIAO_SIDE_PULL[n] == "up" else "GND")
    for d, n in outs + ins:
        if n in FPGA_SIDE_PULL:
            R("10k", n, "3V3" if FPGA_SIDE_PULL[n] == "up" else "GND")


def buttons_led():
    """The scaler's two menu buttons (SW1, SW2: to the FPGA, 10 k pull-ups; wired across a diagonal,
    pins 1 and 4, which is open/closed whichever way the switch pairs its pins inside) and its
    status LED (power, signal lock): red KT-0603R (1.8-2.4 V) through 470 R from the FPGA's 3.3 V
    I/O, about 2.8 mA."""
    for k in (1, 2):
        part("SW%d" % k, "TS-1187A-B-A-B", "lcsc:TS-1187A-B-A-B", "lcsc:SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5",
             "C318884", {"1": "IN_KEY%d" % k, "4": "GND"})
        R("10k", "3V3", "IN_KEY%d" % k)
    R("470", "IN_LED", "LED_A")
    part("D2", "KT-0603R", "lcsc:KT-0603R", "lcsc:LED-SMD_L1.6-W0.8-R-RD", "C2286", {"1": "LED_A", "2": "GND"})


# ---------------------------------------------------------------------------
# ADV7511 (rev-b/design.md "ADV7511KSTZ") and the HDMI receptacle
# ---------------------------------------------------------------------------

def adv7511(pixel):
    """The ADV7511 (U2) on 1V8B: pixel: {data pin name ("D0".."D35"): net} for the input format the
    revision uses (the other data inputs to GND [HWG 6.1.1]); CLK/HSYNC/VSYNC/DE, I2C, INT, PD, the
    audio inputs (I2S0, SPDIF) through 49.9 R at the source, CEC and its clock, R_EXT, decoupling.
    The FPGA lines are OUT_*."""
    block("adv7511")
    # Rails: 10 uH + 10 uF per domain group [HWG Fig. 23, 7.1], each filter by the chip [7.1: "as
    # close to the ADV7511 as possible"; it sat by the 1V8B LDO, 13-20 mm off], its 10 uF at the
    # inductor's output
    for rail, pin in (("TX_DVDD", "1"), ("TX_AVDD", "24"), ("TX_PLVDD", "21")):
        l = nxt("L")
        two(l, "L4018", "10uH", "1V8B", rail, at="U2." + pin)
        C("10u", rail, at=l + ".2")
    u2 = {}
    for name, nums in TX.items():
        net = {"GND": "GND", "DVDD": "TX_DVDD", "AVDD": "TX_AVDD", "PVDD": "TX_AVDD", "PLVDD": "TX_PLVDD",
               "BGVDD": "TX_PLVDD", "MVDD": "3V3"}.get(name)
        if net:
            for n in nums:
                u2[n] = net
    for i in range(36):
        u2[txpin("D%d" % i)] = pixel.get("D%d" % i, "GND")
    for name, net in (("CLK", "OUT_CLK"), ("HSYNC", "OUT_HSYNC"), ("VSYNC", "OUT_VSYNC"), ("DE", "OUT_DE"),
                      ("SCL", "OUT_SCL"), ("SDA", "OUT_SDA"), ("INT", "OUT_INT"), ("PD", "OUT_PD"),
                      ("R_EXT", "R_EXT"), ("HPD", "HDMI_HPD"), ("DDCSDA", "HDMI_SDA"), ("DDCSCL", "HDMI_SCL"),
                      ("TX2+", "TMDS_D2_P"), ("TX2-", "TMDS_D2_N"), ("TX1+", "TMDS_D1_P"), ("TX1-", "TMDS_D1_N"),
                      ("TX0+", "TMDS_D0_P"), ("TX0-", "TMDS_D0_N"), ("TXC+", "TMDS_CK_P"), ("TXC-", "TMDS_CK_N")):
        u2[txpin(name)] = net
    for name in ("I2S1", "I2S2", "I2S3", "DSD0", "DSD1", "DSD2", "DSD3", "DSD4", "DSD5", "DSDCLK",
                 "HEAC+", "HEAC-"):
        u2[txpin(name)] = "GND"                         # [HWG 6.1.1, 6.2.1]
    # CEC [HWG 7.7, Fig. 26]: the ADV7511's CEC engine on the receptacle's CEC line (pin 13; its
    # pull-up with the receptacle, hdmi_receptacle()); CEC_CLK 12 MHz (3-100 MHz, +-2 %) from the
    # FPGA. Lets the scaler wake the TV, switch it to its input and put it to standby
    u2[txpin("CEC")] = "HDMI_CEC"
    u2[txpin("CEC_CLK")] = "OUT_CECCLK"
    # Audio: series resistors at the source (the FPGA's side) [HWG 7.3: 51 R]; 49.9 R, the nearest
    # JLCPCB basic part. SPDIF: the S/PDIF input passed on by the FPGA
    for name, sig in (("MCLK", "MCLK"), ("SCLK", "SCLK"), ("LRCLK", "LRCLK"), ("I2S0", "I2S0"), ("SPDIF", "SPDIF")):
        u2[txpin(name)] = "TX_" + sig
        R("49.9", "OUT_" + sig, "TX_" + sig)
    part("U2", "ADV7511KSTZ", "lcsc:ADV7511KSTZ", "lcsc:LQFP-100_L14.0-W14.0-P0.50-LS16.0-BL", "C179459", u2)
    R("887", "R_EXT", "GND")                            # 1 % [HWG 7.6]
    R("2k", "3V3", "OUT_SCL")                           # [HWG 7.4]
    R("2k", "3V3", "OUT_SDA")
    R("2k", "3V3", "OUT_INT")                           # [HWG 6.3.4]
    R("2k", "OUT_PD", "GND")                            # address 0x72, PD active high [HWG 6.1.5]
    # 0.1 uF at every supply pin, adjacent pins sharing [HWG 7.1, Fig. 23: "as close to the supply
    # pin as possible"]: DVDD 1, 19, 49, 76+77; AVDD 29, 34, 41; PVDD 24+25; PLVDD 21; BGVDD 26;
    # MVDD 47. (Top side only: 34 and 41 lie between TMDS pairs, their capacitors beside the pairs)
    for rail, pins in (("TX_DVDD", ("1", "19", "49", "76")), ("TX_AVDD", ("24", "29", "34", "41")),
                       ("TX_PLVDD", ("21", "26")), ("3V3", ("47",))):
        for n in pins:
            C("100n", rail, at="U2." + n)
    return u2


def hdmi_receptacle():
    """The HDMI receptacle (J6, type A) [HWG Fig. 27, 6.3], whatever drives it: the TMDS lines' ESD
    arrays (U9, U10), DDC, HPD and CEC's (U8), the DDC pull-ups, HPD's pull-down, the 5 V pin's
    supply, CEC's pull-up."""
    block("hdmi")
    part("J6", "HDMI-001", "lcsc:HDMI-001", "lcsc:HDMI-SMD_19P-P0.50-H-F", "C138388",
         {"1": "TMDS_D2_P", "2": "GND", "3": "TMDS_D2_N", "4": "TMDS_D1_P", "5": "GND", "6": "TMDS_D1_N",
          "7": "TMDS_D0_P", "8": "GND", "9": "TMDS_D0_N", "10": "TMDS_CK_P", "11": "GND", "12": "TMDS_CK_N",
          "13": "HDMI_CEC", "15": "HDMI_SCL", "16": "HDMI_SDA", "17": "GND", "18": "HDMI_5V", "19": "HDMI_HPD",
          "20": "GND", "21": "GND", "22": "GND", "23": "GND"})
    # ESD on the TMDS lines: TI TPD4E05U06, 0.5 pF per line (HWG 6.3.2.1 asks for < 0.6 pF; its example,
    # Panasonic EZAEG2A50AX, needs one part per line), flow-through: each line crosses pad n and the
    # NC pad opposite it (10, 9, 7, 6)
    for ref, (a, b_, c, d) in (("U9", ("TMDS_D2_P", "TMDS_D2_N", "TMDS_D1_P", "TMDS_D1_N")),
                               ("U10", ("TMDS_D0_P", "TMDS_D0_N", "TMDS_CK_P", "TMDS_CK_N"))):
        part(ref, "TPD4E05U06DQAR", "lcsc:TPD4E05U06DQAR_C138714", "lcsc:USON-10_L2.5-W1.0-P0.50-BL", "C138714",
             {"1": a, "10": a, "2": b_, "9": b_, "4": c, "7": c, "5": d, "6": d, "3": "GND", "8": "GND"})
    # DDC, HPD and CEC through the fourth array (the HDMI 5 V pin, a supply behind its PTC and 100 nF,
    # gave its channel to CEC)
    part("U8", "TPD4E05U06DQAR", "lcsc:TPD4E05U06DQAR_C138714", "lcsc:USON-10_L2.5-W1.0-P0.50-BL", "C138714",
         {"1": "HDMI_SCL", "10": "HDMI_SCL", "2": "HDMI_SDA", "9": "HDMI_SDA", "4": "HDMI_HPD", "7": "HDMI_HPD",
          "5": "HDMI_CEC", "6": "HDMI_CEC", "3": "GND", "8": "GND"})
    R("2k", "HDMI_5V", "HDMI_SCL")                      # [HWG 6.3.3: 1.5-2 k to the HDMI 5 V]
    R("2k", "HDMI_5V", "HDMI_SDA")
    R("10k", "HDMI_HPD", "GND", note="0 V on HPD with no sink [HWG 6.1.4: 10 k +-10 %]")
    two(nxt("F"), "PTC0805", "0.2A", "+5V", "HDMI_5V")
    C("100n", "HDMI_5V", at="J6.18")
    # CEC: 27 k to 3.3 V through a diode [HWG Fig. 26, "leakage < 1.8 uA"]: with the board off its 3V3
    # is near 0 V, and the 27 k alone would pull the TV's CEC bus down (60 uA). 1N4148WS: nA leakage
    # reversed; the line's high level 3.3 V less its drop, 2.7 V, over CEC's 2.5 V minimum
    R("27k", "3V3", "CEC_PU")
    part("D7", "1N4148WS", "Device:D", "Diode_SMD:D_SOD-323", "C2128", {"1": "HDMI_CEC", "2": "CEC_PU"})
