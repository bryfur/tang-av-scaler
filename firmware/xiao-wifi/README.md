# The Wi-Fi debug link

Firmware for a Seeed XIAO ESP32-C5 (or ESP32-S3) in the AV board's XIAO sockets (rev C-A, C-B):
the FPGA loaded and debugged over Wi-Fi, with no cable to a PC. `../xiao` is the wired firmware
(an ESP32-S3 on its USB); this one does the same work over the network, and over the XIAO's USB
serial port too when a cable is in.

| What | Where | With |
|---|---|---|
| JTAG (D0-D3) | TCP 2542, a Xilinx Virtual Cable server | `openFPGALoader -c xvc-client --ip ...`: load the FPGA, write the SOM's flash |
| The FPGA's UART (D6, D7, 1 Mbaud) | TCP 2323, raw bytes; the USB serial port | `tools/avx.py console`, `tools/avx.py pty` |
| Status, settings, updates | http://avscaler.local/ | a browser, or `tools/avx.py` |

## State on the board (2026-11-12, an ESP32-C5 in rev C-B)

Works: joining a network, the FPGA's UART on TCP 2323, the status page, updates over Wi-Fi; and with
a USB cable in, the chip's own USB-JTAG bridge on the JTAG pads (`openFPGALoader -c esp32s3`,
`gateware/tools/load.sh`: 30 s a bitstream), which is how the FPGA is loaded now.

Does not work: loading a bitstream over Wi-Fi. The scan chain reads right (the ID code, an 8 Mbit
BYPASS loop-back), but an SRAM load ends in the FPGA's "Bad Command" or "Timeout", through the XVC
port and through the link's own loader (`main/gowin.c`, `/api/load`) alike; the cause is not found.
The loader's SPI path (`jtag_bulk_*`) hangs and is off by default.

Beside the board: each answer the link sends is a radio transmission, and the MS5351M's I2C bus
took those for clock edges in the middle of a transaction. `gateware/tools/avb.py` reads nothing
back until a transaction's stop.

## Build and first flash

    ssh fpga firmware/xiao-wifi/build.sh          # ESP-IDF 6.x; build-esp32c5/avwifi.bin
    firmware/xiao-wifi/flash.sh                   # on the PC the XIAO's USB is in, once

After that the XIAO needs power only (the board's, through its sockets), and a new firmware goes
over Wi-Fi: `tools/avx.py ota`. An update is on trial until it has been reached over the network
(the tool does that); one that cannot be reached goes back to the firmware before it, by itself,
3 minutes after its start.

## Wi-Fi

With no network saved, or when the saved one cannot be joined for 25 s, the link opens its own
access point: **avscaler-XXXX**, password **avscaler**. Join it (a phone will do), open
http://192.168.4.1/, give the network's name and password. The access point closes 10 s after the
network is joined. From a PC on the access point: `AVX_HOST=192.168.4.1 tools/avx.py wifi NAME`.

The user LED: lit on a network; one flash a second with the access point open; fast while it looks
for the network.

## Use

    tools/avx.py status                 # firmware, Wi-Fi, who is on the JTAG and console ports
    tools/avx.py fpga                   # the FPGA's ID code and status register, read by the link
    tools/avx.py load avb.fs            # into the FPGA's SRAM
    tools/avx.py flash avb.fs           # into the SOM's flash
    tools/avx.py console                # the FPGA's UART on the terminal (Ctrl-] ends it)
    tools/avx.py pty &                  # the UART as /tmp/avb-tty, for tools that want a serial port:
    AVB_TTY=/tmp/avb-tty gateware/tools/avb.py id

The link is found as `avscaler.local` (mDNS); `AVX_HOST` names another host or address.

There are no passwords on its ports: whoever is on the local network can load the FPGA and update
the link.

## Test

`test/run.sh [FS]` runs the XVC server's code and the link's own JTAG scans on a PC against a model
of the FPGA's TAP, with openFPGALoader as the client: its detect, and with a bitstream a whole SRAM
load (437 shifts, 36 Mbit for the 138K's 35 Mbit). `MODEL_HOST=fpga test/run.sh` builds and runs the
model on fpga (gcc), openFPGALoader here.

## Parts

| File | |
|---|---|
| `main/board.h` | the XIAO's pads by chip, the ports, the UART's rate |
| `main/jtag.c`, `tap.c` | JTAG bit-banged on the GPIO registers; the link's own scans (Gowin ID code, status) |
| `main/xvc_core.c`, `xvc.c` | the XVC protocol (portable: test/ runs it); its TCP server |
| `main/console.c` | the FPGA's UART to TCP and USB |
| `main/wifi.c` | the saved network, the access point, mDNS |
| `main/web.c`, `page.html` | the web server and its page |
| `main/logbuf.c` | the ESP's own log, in RAM (`avx.py log`): its UART pads and USB port are the FPGA's |
