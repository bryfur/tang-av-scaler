/* The firmware's parts (main.c starts them). */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* logbuf.c: the ESP's own log, kept in RAM (nothing of it goes to a UART or the USB port) */
void logbuf_init(void);
size_t logbuf_copy(char *dst, size_t max);

/* xvc.c: JTAG over TCP */
void xvc_start(void);
struct xvc_state {
    bool connected;
    char peer[16];
    uint64_t bits;
    uint32_t shifts, sessions;
};
void xvc_get(struct xvc_state *s);

/* console.c: the FPGA's UART on a TCP port and on the USB serial port */
void console_start(void);
struct console_state {
    bool tcp, usb;
    char peer[16];
    uint32_t to_fpga, from_fpga;
};
void console_get(struct console_state *s);
size_t console_tail(char *dst, size_t max);     /* the last bytes the FPGA sent */

/* wifi.c: the saved network, or the firmware's own access point to be given one */
void wifi_start(void);
void wifi_save(const char *ssid, const char *pass);     /* and join it */
void wifi_set_host(const char *host);                   /* the name: takes effect at the next start */
struct wifi_state {
    bool joined, ap;
    char ssid[33], ip[16], host[33], ap_ssid[33], mac[18];
    int rssi, channel;
    uint32_t drops;
};
void wifi_get(struct wifi_state *s);
#define AP_PASSWORD "avscaler"

/* web.c: the status page, settings, updates */
void web_start(void);
bool web_reached(void);                 /* a status request has been answered since the start */
