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
    bool aa_dbg;        /* what SMAA finds shown in the picture's place */
    bool aa_diag;       /* SMAA's diagonal patterns */
    bool aa_corner;     /* SMAA's corners kept */
    uint8_t crop;       /* the part of the 720 x 480 shown, filling the output: 0 all of it, 1 where the
                         * picture is found to be (the black round a game's picture left out), 2 as set */
    uint16_t crop_x, crop_w, crop_y, crop_h;
    bool wide;          /* the picture is 16:9's (a game set to widescreen): all 1920 columns */
    uint8_t nr;         /* temporal noise reduction where the picture is still: 0 none, 1 to 3 */
    bool dn;            /* the sharpening leaves noise alone */
    uint8_t phase;      /* the decoder's sampling phase (its DLL: 0 to 31) */
    bool osd;           /* the on-screen text (the FPGA's CPU writes it) */
    bool nolock;        /* the output NOT kept in step with the input (so said because this byte was
                         * padding in what older firmware kept: 0, the lock on) (new settings go at the
                         * end: the ones kept in flash are read as far as they go) */
};
struct scaler_state {
    bool host;          /* a host has the console: nothing done */
    bool fpga;          /* the bring-up image answers */
    bool ok;            /* brought up, every chip set */
    bool hpd, pll, hist;
    uint32_t build, ups;
    uint16_t pix, lines, fields_s, frames_s;
    uint32_t llc_khz;
    uint16_t show_x, show_w, show_y, show_h;    /* the part shown now */
    uint8_t tune;       /* the sampling phase's tuning: 0 not asked, 1 at it, 2 done (the sharpest kept),
                         * 3 the picture moved meanwhile (as it was), 4 no fields to measure */
    uint16_t tune_gain; /* the sharpest phase's sharpness over the least's, in percent */
    int16_t temp4;      /* the FPGA's temperature, degrees C x 4 (-32768: not measured) */
    uint16_t delay_us10;/* the picture's delay, in 10 us (a field's end to its lines shown) */
    bool cpu;           /* the FPGA's CPU runs its program */
    bool relay;         /* ... and the scaler: the link relays (else the link runs it itself, the old way) */
    uint32_t cpu_build; /* the program's time (gateware/sw) */
    uint8_t lock;       /* the frame lock: 0 off, 1 no input to follow, 2 getting there, 3 in step */
    int16_t lock_err;   /* how far the frame's start is from where it should be, in 10 us */
    int16_t lock_ppm10; /* the clock's trim, in tenths of a ppm */
};
/* link.c: the SPI port to the FPGA: its registers, and messages to the scaler's CPU (gateware/sw/link.h) */
void link_start(void);
bool link_reg_read(uint8_t addr, uint32_t *v);
bool link_reg_write(uint8_t addr, const uint32_t *words, size_t n);
/* a request and its answer (max bytes of it at most, 2048 the most there is); its length, -1: none in ms */
int link_msg(const uint8_t *req, size_t n, uint8_t *reply, size_t max, int ms);
bool link_program(const uint8_t *bin, size_t bytes);

void scaler_start(void);
bool scaler_cpu(void);          /* the FPGA's CPU runs the scaler (the link relays) */
void scaler_get(struct scaler_state *s, struct scaler_settings *v);
void scaler_set(const struct scaler_settings *v);
void scaler_again(void);
void scaler_measure(void);      /* where the picture is: found again */
void scaler_tune(void);         /* the decoder's sampling phase: each tried (on a still picture), the sharpest kept */

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
