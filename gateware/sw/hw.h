/* hw.h: the scaler's registers as the CPU sees them (rtl/top.v: at 0xE8000000 + 4 x the register),
 * time, and the program's parts */
#ifndef HW_H
#define HW_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "link.h"

#define REG(n)      (*(volatile uint32_t *)(0xe8000000u + 4u * (n)))
extern uint32_t core_hz;            /* the core's clock (rtl/sys_pll.v), as the design says (R_CPUMHZ): time.c */

enum { R_ID = 0x00, R_BUILD = 0x01, R_CTRL = 0x02, R_STAT = 0x03, R_I2C = 0x04, R_I2C_SH = 0x05, R_FREQ = 0x10,
       R_GT_CTRL = 0x20, R_GT_STAT = 0x21, R_MODE = 0x25, R_HDMI = 0x26, R_LAT = 0x27, R_OSD = 0x28, R_OSDW = 0x29,
       R_TEMP = 0x2a, R_LLMIN = 0x2b, R_SRC = 0x2c, R_CPUMHZ = 0x2d, R_VID = 0x30, R_CAP = 0x31, R_FIELDS = 0x32, R_DEINT = 0x35, R_DSTAT = 0x36, R_FOCUS = 0x37,
       R_GRAB = 0x38, R_GRABD = 0x39, R_GEOM = 0x3a, R_BORDER = 0x3e, R_BORDERL = 0x3f,
       R_CPUMR = 0x2e, R_CPUMW = 0x2f, R_DDR = 0x40, R_MV = 0x53, R_AUD = 0x54, R_AUDL = 0x55, R_AUDR = 0x56, R_AUDO = 0x57, R_CPUM = 0x64,
       R_SPIS = 0x70, R_SPIRX = 0x71, R_SPITXA = 0x72, R_SPITXD = 0x73 };
#define DP_OE       (1u << 2)
#define IN_RESET_N  (1u << 3)
enum { BUS_PLL, BUS_DP, BUS_DDC, BUS_IN };

/* time.c */
uint32_t cycles(void);
uint32_t ms(void);                      /* since the program began (call it every few seconds at least) */
void wait_ms(uint32_t n);               /* (the link is answered meanwhile) */
void wait_us(uint32_t n);

/* i2c.c: the four buses, bit by bit through the I2C register */
bool i2c_set(int bus, uint8_t dev, uint8_t reg, uint8_t val);
bool i2c_get(int bus, uint8_t dev, uint8_t reg, uint8_t *val);
bool i2c_sure(int bus, uint8_t dev, uint8_t reg, uint8_t val);  /* set and seen to be */

/* board.c: the chips brought up, the settings applied, what is looked after each second */
extern struct link_settings set;
extern struct link_status st;
void board_init(void);
void board_second(void);                /* once a second */
void board_apply(const struct link_settings *was);      /* the settings changed */
void board_cmd(int cmd);
bool board_hd(void);                /* 1280 x 720 comes in and goes out as it is */
bool board_ed(void);                /* 720 x 480 progressive comes in (480p) */
void board_grab_seen(void);         /* (a screen capture is still asking) */
bool board_grabbing(void);
void board_field(void);             /* often: a new field in: the pan found (pan.c) */
void board_lock(void);              /* ten times a second: the output's clock trimmed to follow the input */

/* audio.c: the sound made 5.1 (the surround setting) */
void audio_set(bool want);
bool audio_on(void);
void audio_service(void);          /* the pairs of samples that wait, each made six channels */
extern uint32_t audio_cycles;       /* the core's clocks it has taken (board.c: thousandths of the core's time, register 67) */
extern uint32_t audio_dsp_cycles;   /* ... the decoder's part (register 67's upper half) */

/* mem.c: the data memory (the DDR3) */
enum { MEM_NONE, MEM_GOOD, MEM_BAD, MEM_DEAD };     /* not there (or not calibrated), tested good, wrong, no answer */
#define MEM_FREE 0x00400000u        /* (in every 128 MB: below it a field of the picture) */
extern int mem_state;
void mem_test(void);

/* pan.c: the picture's pan, for the deinterlacer */
extern int8_t pan_dx, pan_dy;
extern bool pan_ok;
extern uint32_t pan_us;
void pan_service(int latest, int lines, bool on);     /* a field has come in */

/* osd.c */
void osd_init(void);
void osd_update(void);

/* main.c */
void service(void);                     /* the link's request, if there is one */

#endif
