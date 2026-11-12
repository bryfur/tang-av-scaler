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
bool console_busy(void);                        /* a host is on the TCP port */
/* the link's own words with the FPGA's monitor: tx sent whole, then rxn bytes of answer waited for
 * (not passed on to a listener); false if they do not come in ms */
bool console_xfer(const uint8_t *tx, size_t txn, uint8_t *rx, size_t rxn, int ms);

/* scaler.c: the board brought up and kept up by the link itself; the picture's settings */
struct scaler_settings {
    bool on;            /* the link runs the scaler (else it is left alone) */
    bool ntsc;          /* the picture rate 60/1.001 Hz */
    uint8_t mode;       /* deinterlacing: 0 motion adaptive, 1 bob, 2 weave */
    uint8_t thr;        /* its motion threshold */
    bool aa;            /* SMAA */
    uint8_t aa_thr;     /* its edge threshold */
    uint8_t sharp;      /* RCAS sharpening, 0 (none) to 16 */
    bool swap, top1, pattern, freeze;
    bool audio;         /* HDMI's data islands: the sound and the InfoFrames (else DVI's plain blanking) */
    bool aa_dbg;        /* what SMAA finds shown in the picture's place (new settings go at the end: the
                         * ones kept in flash are read as far as they go) */
};
struct scaler_state {
    bool host;          /* a host has the console: nothing done */
    bool fpga;          /* the bring-up image answers */
    bool ok;            /* brought up, every chip set */
    bool hpd, pll, hist;
    uint32_t build, ups;
    uint16_t pix, lines, fields_s, frames_s;
    uint32_t llc_khz;
};
void scaler_start(void);
void scaler_get(struct scaler_state *s, struct scaler_settings *v);
void scaler_set(const struct scaler_settings *v);
void scaler_again(void);

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
