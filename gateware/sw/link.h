/* link.h: what the link (the XIAO: firmware/xiao-wifi) and the scaler's CPU (sw/) say to each
 * other over the SPI port (rtl/spis.v): a request, an answer.  Both sides build with this file.
 *
 * A request's first byte says what it is; an answer's first byte is the same with bit 7 set (or
 * LINK_BAD: not understood), the rest as below.  Numbers are little-endian.
 */
#ifndef LINK_H
#define LINK_H

#include <stdint.h>

/* "AVC5": the program speaks this.  A change to the messages, the settings or the status below is a
 * new number: a link whose firmware has another gives the CPU its own program (2026-11-13: without
 * that, a firmware from before the tables read this status as its own shorter one, took what lay
 * where its settings had been for the settings, and kept them) */
#define LINK_MAGIC   0x37435641u

enum {
    LINK_STATUS = 0x01,                 /* -> struct link_status */
    LINK_SET_ALL = 0x02,                /* struct link_settings -> (nothing): the settings, all of them */
    LINK_SET_ONE = 0x03,                /* offset u8, size u8 (1, 2), value u16: one of them, by its place */
    LINK_CMD = 0x04,                    /* u8: one of LINK_CMD_* */
    LINK_GRAB = 0x05,                   /* step u8, row u16, column u16, pixels u16 (680 at most) ->
                                         * that many pixels of the picture as it goes out (row and
                                         * column counted in steps), blue green red each */
    LINK_TABLE = 0x06,                  /* slot u8 (1 to LINK_TABLES - 1), place u16, words u32 ... (62 at most) ->
                                         * u8 1 taken: a part of a table for the scaler (sw/table.c), from
                                         * its word at this place (4 x entry + quarter); the slot holds no
                                         * table from here until LINK_TABLE_END says it does (so with no
                                         * words: the slot emptied) */
    LINK_TABLE_END = 0x07,              /* slot u8, sum u32, a name (LINK_NAME - 1 bytes at most; none: the
                                         * name it had) -> u8 1: all of it is there (the words' sum is this:
                                         * link_table_sum()): the slot holds a table, and the board keeps it in
                                         * its flash */
    LINK_NET = 0x08,                    /* place u16, then {address u16, value u32} ... (41 at most) -> u8 1 taken:
                                         * values for the network's port (rtl/cnn.v's l_a, l_d: sim/model.py
                                         * net_words()), from this place in their order */
    LINK_NET_END = 0x09,                /* count u16, sum u32, flags u8, a name (LINK_NAME - 1 bytes at most) ->
                                         * u8 1: all of them are there (their sum: link_table_sum() over each
                                         * address then value): put into the network; LINK_NET_KEEP: and kept
                                         * in the board's flash, for every start from here on; LINK_NET_FORGET
                                         * (count 0): the kept ones erased */
    LINK_STORE = 0x0A,                  /* what u8 (1 to 7 a table's slot, 8 the network) -> kept u8, sum u32,
                                         * name LINK_NAME bytes: what the board's flash holds of it (sw/store.c) */
    LINK_BAD = 0xFF,
};
#define LINK_NAME           24          /* a kept thing's name, with its 0 */
enum { LINK_NET_KEEP = 1, LINK_NET_FORGET = 2 };
/* the board's own storage (sw/store.c: the SOM's flash): link_status.store */
enum { LINK_STORE_THERE = 1,            /* the flash answers */
       LINK_STORE_SET = 2,              /* the settings are kept there: the board's count, not the link's copy */
       LINK_STORE_BUSY = 4,             /* something waits to be kept or is being */
       LINK_STORE_FAILED = 8 };         /* something could not be kept */
/* whose weights the network has: link_status.net_state */
enum { LINK_NET_OWN, LINK_NET_GIVEN, LINK_NET_KEPT };  /* the design's; given since (not kept); the kept ones */

/* the scaler's tables: slots in the CPU's memory.  0 is the design's own (FSR's); the link fills the
 * rest.  A table is 8192 entries ({place below 2, place right 3, direction 5, strength 3}) of four
 * words, three weights (10 bits, signed, in 256ths) a word: twelve, for the twelve source pixels. */
#define LINK_TABLES         8
#define LINK_TABLE_WORDS    32768
#define LINK_TABLE_SUM0     2166136261u
static inline uint32_t link_table_sum(uint32_t h, uint32_t word)       /* over the words in order, from LINK_TABLE_SUM0 */
{
    return (h ^ word) * 16777619u;
}
enum { LINK_TAB_IDLE, LINK_TAB_PUT, LINK_TAB_CHECK, LINK_TAB_KEEP, LINK_TAB_NONE = 255 };

enum {
    LINK_CMD_AGAIN = 1,                 /* bring everything up again */
    LINK_CMD_MEASURE = 2,               /* find the picture's border again */
    LINK_CMD_TUNE = 3,                  /* try every sampling phase, keep the sharpest */
    LINK_CMD_HOST_ON = 4,               /* a host tool has the monitor: the scaler is left alone */
    LINK_CMD_HOST_OFF = 5,
    LINK_CMD_GRAB_BEGIN = 6,            /* the fields held still for a screen capture ... */
    LINK_CMD_GRAB_END = 7,              /* ... and let go (by itself after 3 s with no LINK_GRAB) */
};

/* the settings: the CPU's are the ones that count, and it keeps them in the board's flash (sw/store.c);
 * the link keeps a copy too, for a board whose flash holds none yet */
struct link_settings {
    uint8_t on;             /* the scaler is run (else left alone) */
    uint8_t ntsc;           /* the picture rate 60/1.001 Hz */
    uint8_t mode;           /* deinterlacing: 0 motion adaptive, 1 bob, 2 weave; + 8 (motion adaptive):
                             * motion compensation: where the picture moves the lines made are the field
                             * before's, moved by each block's own vector (rtl/deint.v mc; sw/pan.c finds
                             * the picture's pan for it to start from) */
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
    uint8_t flock;          /* the output's frames kept in step with the input's fields (the clock trimmed) */
    uint8_t lowlat;         /* a frame made from the field still coming in: the output a few lines behind
                             * the input (with flock: without it only when it happens to fit) */
    uint8_t surround;       /* the sound's two channels made 5.1 (a game's Pro Logic II mix decoded: sw/surround.c) */
    uint8_t table;          /* the scaler's table (sw/table.c): 0 the design's own (FSR's); 1 the pair in slots 1
                             * and 2: 1 with the anti-aliasing off, 2 with it on; 2 on: slot 3 on.  A slot
                             * that holds none: the design's own */
    uint8_t mv_dbg;         /* the motion compensation's vectors shown (rtl/deint.v mvdbg; with mode 8): the
                             * picture grey, each block of eight pixels the colour of its vector */
    uint8_t net;            /* the scaler's first stage: 0 none (the table's kernel does it all: rtl/easu.v), 1 the
                             * network (rtl/cnn.v: the picture's luma made twice the size by it, then a
                             * bicubic stretch: rtl/bicu.v; the table is not used then) */
    uint8_t aa_keep;        /* SMAA: the edges of the frame before count (rtl/smaa_hist.v): 0 not; 1 to 7: an edge
                             * that was there is kept that many levels more easily, one that was not needs as
                             * many more (a still picture's edges then stay as they are, noise or not) */
    /* (No gaps in this: the two sides compare theirs byte for byte.  With one the link found the CPU's
     * "changed" each second, by whatever lay in the gap, and kept them in flash again each time) */
    uint16_t crop_x, crop_w, crop_y, crop_h;
};
_Static_assert(sizeof(struct link_settings) == 28 + 8, "link_settings: a gap, or a new member not counted here");

#define LINK_SETTINGS_DEFAULT { .on = 1, .ntsc = 1, .thr = 6, .aa = 1, .aa_thr = 10, .sharp = 8, .audio = 1, \
                                .aa_diag = 1, .aa_corner = 1, .aa_keep = 3, .crop = 1, .nr = 2, .dn = 1, .flock = 1, .crop_w = 720, .crop_h = 480 }

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
    uint8_t lock;           /* the frame lock: 0 off, 1 no input to follow, 2 getting there, 3 in step */
    uint8_t ll;             /* the frame now shown is made from the field coming in */
    int16_t lock_err;       /* how far the frame's start is from where it should be, in 10 us */
    int16_t lock_ppm10;     /* the clock's trim, in tenths of a ppm */
    uint16_t ll_lines;      /* lines of that field in the memory when the frame was begun */
    uint8_t in_std;         /* what comes in, by the decoder's own measurement: LINK_IN_* */
    uint8_t in_ok;          /* the scaler shows it (else: its test picture and the on-screen text) */
    uint16_t in_lines;      /* its lines, blanking and all: a field's (interlaced) or a frame's */
    uint16_t in_hz100;      /* its fields or frames a second x 100 */
    uint8_t pan;            /* the picture's pan (sw/pan.c): the deinterlacer is given one */
    int8_t pan_dx, pan_dy;  /* what was found (pixels, the field's lines, in two fields) */
    uint8_t pan_ms10;       /* the time finding it took, in 0.1 ms */
    uint8_t tab_have;       /* the scaler's tables: the slots that hold one (bit 0: the design's own) */
    uint8_t tab_slot;       /* the slot whose table the scaler has (255: not known) */
    uint8_t tab_state;      /* LINK_TAB_*: nothing going on; a table on its way into the scaler; read back;
                             * the design's own read into slot 0; NONE: the design has no port for it (or
                             * the memory is not there) */
    uint8_t store;          /* the board's own storage: LINK_STORE_* */
    uint16_t tab_bad;       /* entries that read back other than put, the last time (0: as it should be) */
    uint16_t tab_ms;        /* the time putting it in took */
    uint8_t net_there;      /* the design has the network (rtl/cnn.v) */
    uint8_t net_state;      /* whose weights it has: LINK_NET_* */
    uint16_t net_under;     /* rows the network was late for, since the program began (there should be none
                             * while a picture comes in) */
    uint16_t pad2;          /* 0 (no gap before the settings, none at the end) */
    struct link_settings set;
};
_Static_assert(sizeof(struct link_status) == 84 + sizeof(struct link_settings), "link_status: a gap, or a new member not counted here");

/* what comes in */
enum { LINK_IN_NONE, LINK_IN_240P, LINK_IN_480I, LINK_IN_288P, LINK_IN_576I, LINK_IN_480P, LINK_IN_576P,
       LINK_IN_720P, LINK_IN_1080I, LINK_IN_OTHER };
#define LINK_IN_NAMES {"none", "240p", "480i", "288p", "576i", "480p", "576p", "720p", "1080i", "unknown"}

#endif
