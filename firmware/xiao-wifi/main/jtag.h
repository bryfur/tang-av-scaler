/* The FPGA's JTAG on D0-D3, bit-banged. */
#pragma once
#include <stdbool.h>
#include <stdint.h>

void jtag_init(void);

/* The pads to the chip's USB-JTAG unit, as they are whenever nobody holds the port (jtag.c): call
 * once after the USB serial driver is up (console_start): before it the unit's clock is off. */
void jtag_usb_bridge(void);

/* One user at a time: the XVC client for as long as it is connected, the web page's status read
 * for one scan.  jtag_take(false) returns at once. */
bool jtag_take(bool wait);
void jtag_give(void);

/* nbits clocks: tms and tdi out LSB first, tdo back the same way (tdo may alias tms or tdi) */
void jtag_shift(const uint8_t *tms, const uint8_t *tdi, uint8_t *tdo, uint32_t nbits);

/* Long runs of data bits (TMS as it stands) by the SPI master at hz, each byte's top bit first:
 * begin, send as often as wanted, end (which waits for the last bit).  jtag.c. */
bool jtag_bulk_begin(uint32_t hz);
void jtag_bulk_send(const uint8_t *data, size_t n);
void jtag_bulk_end(void);

/* TCK's period in ns: asks for one, returns the one it got (never shorter than asked, but for the
 * fastest the loop can do) */
uint32_t jtag_set_period(uint32_t ns);
uint32_t jtag_period(void);
uint32_t jtag_fastest(void);

/* A Gowin scan by the firmware itself: instruction ir (8 bits), then its 32-bit data register */
uint32_t jtag_gowin_read(uint8_t ir);
#define GOWIN_IDCODE 0x11
#define GOWIN_STATUS 0x41
#define GOWIN_USERCODE 0x13
