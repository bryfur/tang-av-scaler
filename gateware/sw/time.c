/* time.c: the core's cycle counter as milliseconds; waits that keep answering the link */
#include "hw.h"

uint32_t core_hz;

uint32_t cycles(void)
{
    uint32_t c;
    __asm__ volatile ("csrr %0, mcycle" : "=r"(c));
    return c;
}

uint32_t ms(void)
{
    static uint32_t last, now_ms;
    static bool begun;
    uint32_t c = cycles();
    if (!begun) {
        uint32_t mhz = REG(R_CPUMHZ);
        core_hz = (mhz >= 100 && mhz <= 1000 ? mhz : 400) * 1000000u;     /* (0: a design from before: 400) */
        begun = true;
        last = c;
    }
    while (c - last >= core_hz / 1000) {
        last += core_hz / 1000;
        now_ms++;
    }
    return now_ms;
}

void wait_ms(uint32_t n)
{
    uint32_t t = ms();
    while (ms() - t < n) {
        service();
        audio_service();
    }
}

void wait_us(uint32_t n)
{
    uint32_t t = cycles();
    if (!core_hz)
        ms();
    while (cycles() - t < n * (core_hz / 1000000))
        audio_service();
}
