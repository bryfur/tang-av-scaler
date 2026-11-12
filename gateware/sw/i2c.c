/* i2c.c: the clock chip's, the redriver's, the display's and the decoder's I2C buses, bit by bit
 * through the scaler's I2C register (rtl/top.v: a 1 written pulls a line low; a line let go is
 * waited for: bit 16 reads 1 until it has risen; the data line is shifted into I2C_SH + bus at
 * every rise of the clock).  As the link did it through the monitor (firmware/xiao-wifi scaler.c). */
#include "hw.h"

static uint8_t drv;                     /* the lines pulled low */

static void lines(int bus, int scl, int sda)
{
    if (scl >= 0)
        drv = (drv & ~(1 << 2 * bus)) | (scl ? 0 : 1) << 2 * bus;
    if (sda >= 0)
        drv = (drv & ~(2 << 2 * bus)) | (sda ? 0 : 2) << 2 * bus;
    REG(R_I2C) = drv;
    while (REG(R_I2C) >> 16 & 1)
        ;
}

static void start(int bus)
{
    lines(bus, -1, 1);
    lines(bus, 1, -1);
    lines(bus, -1, 0);
    lines(bus, 0, -1);
}

static void stop(int bus)
{
    lines(bus, -1, 0);
    lines(bus, 1, -1);
    lines(bus, -1, 1);
}

static void clock(int bus, int sda)
{
    lines(bus, -1, sda);
    lines(bus, 1, -1);
    lines(bus, 0, -1);
}

static void put(int bus, uint8_t b)
{
    for (int k = 7; k >= 0; k--)
        clock(bus, b >> k & 1);
    clock(bus, 1);
}

bool i2c_set(int bus, uint8_t dev, uint8_t reg, uint8_t val)
{
    uint32_t sh;
    start(bus);
    put(bus, dev << 1);
    put(bus, reg);
    put(bus, val);
    stop(bus);
    /* (the three bytes' acknowledge bits: each nine clocks back from the last) */
    sh = REG(R_I2C_SH + bus);
    return !(sh >> 1 & 1) && !(sh >> 10 & 1) && !(sh >> 19 & 1);
}

bool i2c_get(int bus, uint8_t dev, uint8_t reg, uint8_t *val)
{
    uint32_t sh;
    start(bus);
    put(bus, dev << 1);
    put(bus, reg);
    lines(bus, -1, 1);
    start(bus);
    put(bus, dev << 1 | 1);
    for (int k = 0; k < 8; k++)
        clock(bus, 1);
    clock(bus, 1);
    stop(bus);
    sh = REG(R_I2C_SH + bus);
    if (sh >> 10 & 1)
        return false;
    *val = sh >> 2 & 0xFF;
    return true;
}

bool i2c_sure(int bus, uint8_t dev, uint8_t reg, uint8_t val)
{
    for (int k = 0; k < 6; k++) {
        uint8_t got;
        if (i2c_set(bus, dev, reg, val) && i2c_get(bus, dev, reg, &got) && got == val)
            return true;
    }
    return false;
}
