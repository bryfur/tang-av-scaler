/* hw.h: the scaler's registers as the CPU sees them (rtl/top.v: at 0xE8000000 + 4 x the register),
 * time, and the program's parts */
#ifndef HW_H
#define HW_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "link.h"

#define REG(n)      (*(volatile uint32_t *)(0xe8000000u + 4u * (n)))
#define CORE_HZ     400000000u          /* rtl/sys_pll.v */

enum { R_ID = 0x00, R_BUILD = 0x01, R_CTRL = 0x02, R_STAT = 0x03, R_I2C = 0x04, R_I2C_SH = 0x05, R_FREQ = 0x10,
       R_GT_CTRL = 0x20, R_GT_STAT = 0x21, R_MODE = 0x25, R_HDMI = 0x26, R_LAT = 0x27, R_OSD = 0x28, R_OSDW = 0x29,
       R_TEMP = 0x2a, R_VID = 0x30, R_CAP = 0x31, R_FIELDS = 0x32, R_DEINT = 0x35, R_DSTAT = 0x36, R_FOCUS = 0x37,
       R_GRAB = 0x38, R_GRABD = 0x39, R_GEOM = 0x3a, R_BORDER = 0x3e, R_BORDERL = 0x3f, R_CPUM = 0x64,
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
void board_grab_seen(void);         /* (a screen capture is still asking) */

/* osd.c */
void osd_init(void);
void osd_update(void);

/* main.c */
void service(void);                     /* the link's request, if there is one */

#endif
