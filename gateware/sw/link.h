/* link.h: what the link (the XIAO: firmware/xiao-wifi) and the scaler's CPU (sw/) say to each
 * other over the SPI port (rtl/spis.v): a request, an answer.  Both sides build with this file.
 *
 * A request's first byte says what it is; an answer's first byte is the same with bit 7 set (or
 * LINK_BAD: not understood), the rest as below.  Numbers are little-endian.
 */
#ifndef LINK_H
#define LINK_H

#include <stdint.h>

#define LINK_MAGIC   0x32435641u        /* "AVC2": the program speaks this */

enum {
    LINK_STATUS = 0x01,                 /* -> struct link_status */
    LINK_SET_ALL = 0x02,                /* struct link_settings -> (nothing): the settings, all of them */
    LINK_SET_ONE = 0x03,                /* offset u8, size u8 (1, 2), value u16: one of them, by its place */
    LINK_CMD = 0x04,                    /* u8: one of LINK_CMD_* */
    LINK_GRAB = 0x05,                   /* step u8, row u16, column u16, pixels u16 (680 at most) ->
                                         * that many pixels of the picture as it goes out (row and
                                         * column counted in steps), blue green red each */
    LINK_BAD = 0xFF,
};

enum {
    LINK_CMD_AGAIN = 1,                 /* bring everything up again */
    LINK_CMD_MEASURE = 2,               /* find the picture's border again */
    LINK_CMD_TUNE = 3,                  /* try every sampling phase, keep the sharpest */
    LINK_CMD_HOST_ON = 4,               /* a host tool has the monitor: the scaler is left alone */
    LINK_CMD_HOST_OFF = 5,
    LINK_CMD_GRAB_BEGIN = 6,            /* the fields held still for a screen capture ... */
    LINK_CMD_GRAB_END = 7,              /* ... and let go (by itself after 3 s with no LINK_GRAB) */
};

/* the settings: the CPU's are the ones that count; the link keeps a copy for when the power is off */
struct link_settings {
    uint8_t on;             /* the scaler is run (else left alone) */
    uint8_t ntsc;           /* the picture rate 60/1.001 Hz */
    uint8_t mode;           /* deinterlacing: 0 motion adaptive, 1 bob, 2 weave */
    uint8_t thr;            /* its motion threshold */
    uint8_t aa;             /* SMAA */
    uint8_t aa_thr;         /* its edge threshold */
    uint8_t sharp;          /* RCAS sharpening, 0 to 16 */
    uint8_t swap, top1, pattern, freeze;
    uint8_t audio;          /* HDMI's data islands: the sound and the InfoFrames */
    uint8_t aa_dbg, aa_diag, aa_corner;
    uint8_t crop;           /* the part shown: 0 all, 1 where the picture is found, 2 as set */
    uint8_t wide;           /* the picture is 16:9's: all 1920 columns */
    uint8_t nr;             /* temporal noise reduction, 0 to 3 */
    uint8_t dn;             /* the sharpening leaves noise alone */
    uint8_t phase;          /* the decoder's sampling phase, 0 to 31 */
    uint8_t osd;            /* the on-screen text */
    uint8_t rsvd[3];
    uint16_t crop_x, crop_w, crop_y, crop_h;
};

#define LINK_SETTINGS_DEFAULT { .on = 1, .ntsc = 1, .thr = 6, .aa = 1, .aa_thr = 12, .sharp = 8, .audio = 1, \
                                .aa_diag = 1, .aa_corner = 1, .crop = 1, .nr = 2, .dn = 1, .crop_w = 720, .crop_h = 480 }

struct link_status {
    uint32_t magic;         /* LINK_MAGIC */
    uint32_t build;         /* the program's (sw/Makefile: its time) */
    uint32_t fpga_build;    /* the bitstream's */
    uint32_t up_s;          /* seconds since the program began */
    uint16_t gen;           /* counts each change of the settings (0: none yet: the program's own) */
    uint16_t ups;           /* bring-ups */
    uint8_t up_ok;          /* brought up, every chip set */
    uint8_t hpd, pll, hist; /* a display is there; the transceivers' PLL is locked; four fields in order */
    uint8_t host;           /* left to a host tool */
    uint8_t tune;           /* the phase's tuning: 0 not asked, 1 at it, 2 done, 3 the picture moved, 4 no fields */
    uint16_t tune_gain;     /* the sharpest phase over the least, percent */
    uint16_t pix, lines;    /* the capture: samples a line, lines a field */
    uint16_t fields_s, frames_s;
    uint32_t llc_hz;        /* the decoder's clock */
    uint16_t show_x, show_w, show_y, show_h;    /* the part shown */
    int16_t temp4;          /* the chip's temperature, degrees C x 4 (-32768: not measured) */
    uint16_t delay_us10;    /* a field's end to its lines shown, in 10 us */
    struct link_settings set;
};

#endif
