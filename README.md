# tang-av-scaler

A PS2-class console's component video, cleaned up on a Sipeed Tang Console 138K: deinterlaced,
anti-aliased with SMAA, scaled, and sent out as 1080p60 HDMI with the console's sound.

```
PS2 component (YPbPr) + stereo audio
  -> AV board: ADV7181D (video ADC/decoder; rev A: ADV7842)         on the Console's J10 header
               PCM1808 (audio ADC)                                on the Console's J9 header
  -> GW5AST-138 FPGA: capture -> deinterlace -> SMAA 1x -> scale
  -> AV board: ADV7511 (HDMI transmitter)                           on the Console's J9 header
  -> HDMI 1080p60 with audio
```

| Directory | What |
|---|---|
| `hardware/av-board/` | The AV board: one board on the Console's two 2x20 headers (J9, J10), the Console's size, over the 138K SOM. Generated with KiCad's Python API; every circuit taken from the parts' reference designs. Revisions in `rev-a/`, `rev-b/`, their shared generators in `kit/`. |

Status: rev A (ADV7842, six layers) is routed and ready to order but costs about $400 at
JLCPCB; rev B (ADV7181D, four layers) is in design. Nothing has been built.

## The host board

Sipeed Tang Console with the Tang Mega 138K SOM (GW5AST-LV138PG484AC1/I0, revision C), board
revision 32001C. Its two 2x20 headers (J9 "SDRAM0", J10 "SDRAM1") carry 38 FPGA I/O each,
+5 V on pin 11 and GND on pin 12, no 3.3 V. Sipeed's schematic, interactive BOM and 3D models:
`https://dl.sipeed.com/shareURL/TANG/Console`.

## Reference documents

`hardware/av-board/refs/` (not in git: the vendors' copyright) holds the datasheets and user
guides the circuits follow; the board's README lists which and where each came from.
