/* The XIAO's pads on the AV board (hardware/av-board/rev-c/design.md "The XIAO as programmer and
 * console"), by chip [Seeed: XIAO ESP32-C5 and XIAO ESP32S3 pin maps]. */
#pragma once
#include "sdkconfig.h"

#if CONFIG_IDF_TARGET_ESP32C5
#define PIN_TMS  1   /* D0 */
#define PIN_TCK  0   /* D1 */
#define PIN_TDI  25  /* D2 */
#define PIN_TDO  7   /* D3 */
#define PIN_TX   11  /* D6: to the FPGA */
#define PIN_RX   12  /* D7: from the FPGA */
#define PIN_CS   23  /* D4: the SPI port to the FPGA (link.c) */
#define PIN_IRQ  24  /* D5: from the FPGA, low: an answer waits */
#define PIN_SCK  8   /* D8 */
#define PIN_MISO 9   /* D9 */
#define PIN_MOSI 10  /* D10 */
#define PIN_LED  27  /* the yellow user LED, lit when low */
#elif CONFIG_IDF_TARGET_ESP32S3
#define PIN_TMS  1
#define PIN_TCK  2
#define PIN_TDI  3
#define PIN_TDO  4
#define PIN_TX   43
#define PIN_RX   44
#define PIN_CS   5
#define PIN_IRQ  6
#define PIN_SCK  7
#define PIN_MISO 8
#define PIN_MOSI 9
#define PIN_LED  21
#else
#error "no XIAO pin map for this chip"
#endif

#define UART_BAUD     1000000     /* gateware/rtl/top.v: the monitor's rate */
#define PORT_XVC      2542        /* Xilinx Virtual Cable: openFPGALoader -c xvc-client */
#define PORT_CONSOLE  2323        /* the FPGA's UART, raw bytes */
