# The AV board

One board on the Tang Console 138K's two 2x20 headers: component video and stereo audio in
(ADV7842, PCM1808) on J10, HDMI out (ADV7511) on J9. A frame around the 138K SOM, which sits
between the headers. Status: design in progress.

## The host's headers (Sipeed's schematic Tang_138K_Console_V32001C, sheet FPGA_EXT_CONN)

J9 ("SDRAM0") and J10 ("SDRAM1"): 2x20, 2.54 mm, SMD male headers, parallel, 49 mm apart (J9 along
the top edge at y = 30 mm, J10 along the bottom at y = 79 mm in Sipeed's PCB coordinates, both
x = 105-153 mm, pin 1 at opposite ends). Each carries 38 FPGA I/O at 3.3 V; pin 11 is +5 V,
pin 12 GND; no 3.3 V. Pins 29/30 (EXIO0/1) reach the DM0/DM1 balls through 0 R links.

- J9: all FPGA bank 2. Clock-capable balls on it: D19/E19 (SGCLK_0), C19/C18 (MGCLK_0),
  C17/D17 (MGCLK_1), B18/B17 (SGCLK_1).
- J10: all FPGA bank 4. Clock-capable: V20/U20 (SGCLK_5), Y19/Y18 (MGCLK_4); P19 is SSPI_CLK.

The full pin -> ball map is taken from the schematic's SOM connector sheets (pages 4-6).

## Reference documents

In `refs/` (not in git). Every circuit on the board follows these.

| File | What | From |
|---|---|---|
| ADV7842_datasheet_adi.pdf | ADV7842 data sheet, Rev B: supplies, currents, crystal (28.63636 MHz), 256-ball map | analog.com data-sheets/ADV7842.pdf |
| UG-214_ADV7842_hardware.pdf | ADV7842 Hardware User Guide: analog input configuration (6.2.1), reset, pixel port, PCB layout recommendations, recommended decoupling (Fig. 168, 179), 75 R input termination (Appendix B) | analog.com user-guides/UG-214.pdf (via docs.ampnuts.ru mirror) |
| HDMI_RX_PowerSupplies_RevA_050411.pdf | ADI "PCB Layout and Power Supply Design Recommendations for HDMI RX Products", Rev A (April 2011): a ferrite per supply rail (Murata NFE61PT472C1H9), 10 nF + 100 nF per pin, 10 uF bulk on AVDD/CVDD/PVDD, LDOs not switchers, 3.3 V before 1.8 V; Fig. 2 the reference LDO supply (10 uH + 10 uF after the 1.8 V LDO, 100 nF + 1 uF on AVDD/CVDD/PVDD, 100 nF on DVDD/DVDDIO/TVDD, 1.8 V enable from 3.3 V via 100 k / 470 nF) | ADI EngineerZone, ADV7842 design support files (downloaded by hand) |
| UG-206_ADV7842_software.pdf | ADV7842 software (register) guide | analog.com user-guides/UG-206.pdf |
| UG-235_eval_ADV7842_7511.pdf | EVAL-ADV7842-7511 user guide (placement drawing, jumpers; no schematic) | farnell.com mirror of UG-235 |
| ADV7511_hardware_users_guide_RevD.pdf | ADV7511 Hardware User's Guide, Rev D: 100-lead LQFP pinout, input/output connections, HPD, DDC, PLL circuit, power domains and filtering, example schematic (Fig. 27) | analog.com user-guides/ADV7511_Hardware_Users_Guide.pdf |
| ADV7511_programming_guide.pdf | ADV7511 Programming Guide | analog.com user-guides |
| ADV7511_HDMI_designs_appnote.pdf | HDMI-enabled designs using the ADV7511 | analog.com evaluation-documentation |
| ADV7511W_hardware_users_guide_RevA.pdf | ADV7511W (64-lead) guide: cross-check only, its pinout does not apply | digikey.com |
| ADV7511_datasheet.pdf | ADV7511 short data sheet | docs.ampnuts.ru mirror |
| AN-1260.pdf | Crystal design considerations for ADI video decoders and HDMI parts | docs.ampnuts.ru mirror |
| AN-1270.pdf | ADV7511-based video generators | docs.ampnuts.ru mirror |
| AN-1143.pdf | ADV7511 HDCP 1.1 enable/disable | docs.ampnuts.ru mirror |
| PCM1808_datasheet.pdf | TI PCM1808 (Rev B): typical application circuit | ti.com |
| console138k_C.pdf | Sipeed Tang_138K_Console_V32001C schematic | dl.sipeed.com TANG/Console/02_Schematic |
| ibom_C.html | Sipeed's interactive BOM for board 32001C (part positions) | dl.sipeed.com TANG/Console/03_Designator_drawing |

Still wanted, for cross-checking: the EVAL-ADV7842-7511 / ADV7844 evaluation board schematics and
the ADV7511 evaluation schematic (ADI's design support files).

Fetching: analog.com serves its PDFs to `wget` (HTTP/1.1); curl over HTTP/2 stalls. EngineerZone
(ez.analog.com) refuses automated clients ("Access Denied"): its files are downloaded by hand.
Sipeed's file server lists folders with a POST to `https://dl.sipeed.com/fileList/<path>`.
