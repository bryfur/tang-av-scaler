/* time.c: the core's cycle counter as milliseconds; waits that keep answering the link */
#include "hw.h"

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
        begun = true;
        last = c;
    }
    while (c - last >= CORE_HZ / 1000) {
        last += CORE_HZ / 1000;
        now_ms++;
    }
    return now_ms;
}

void wait_ms(uint32_t n)
{
    uint32_t t = ms();
    while (ms() - t < n)
        service();
}

void wait_us(uint32_t n)
{
    uint32_t t = cycles();
    while (cycles() - t < n * (CORE_HZ / 1000000))
        ;
}
