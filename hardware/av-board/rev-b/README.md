# AV board rev B

Rev A with the ADV7842 (256-ball BGA) replaced by the ADV7181D (64-lead LFCSP): component video
into the ADV7181D, stereo audio into a PCM1808, HDMI out of an ADV7511. Four layers, no BGA.

Status: routed, DRC clean (no errors, no unconnected items; silkscreen warnings only, the
jacks' outlines over the board edge as on rev A), fab files made; not ordered.

- [design.md](design.md): what changed from rev A, and the ADV7181D's circuit with its sources
- `board.py`, `gen_pcb.py`: the sources; made as in [../README.md](../README.md)

## Ordering at JLCPCB

`fab/av-board-b-gerbers.zip` for the board, `fab/av-board-b-bom.csv` and `fab/av-board-b-cpl.csv`
for assembly. Settings the files do not carry:

- 4 layers, 1.6 mm, stack-up **JLC04161H-7628** (the TMDS geometry assumes its 7628 prepreg
  under the outer layers); impedance control on: the TMDS pairs are 0.2 mm with 0.15 mm gap on
  the outer layers, about 100 R differential. Confirm in JLCPCB's impedance calculator.
- Via 0.3 mm drill / 0.5 mm pad, minimum track and space 0.127 mm.
- Assembly: 158 parts on the top, 14 on the bottom (12 decoupling caps under the ADV7181D's
  supply vias, and the J9/J10 sockets). Through-hole: the five RCA jacks, the two sockets, HDMI.
- Check every part's rotation in JLCPCB's placement preview, mainly U1 (the ADV7181D: pin 1 at
  the dot, AIN10 at its top left), U2, U3 and the regulators.
