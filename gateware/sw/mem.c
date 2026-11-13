/* mem.c: the CPU's data memory: the DDR3 (rtl/cpu_ddr.v), its 1 GB at address 0.  The picture's
 * fields are in it too: the first 4 MB of every 128 MB (a bank of the memory a field's slot:
 * rtl/cap_ddr.v; the program can read them there: a pixel pair's four bytes Cb Y Cr Y at
 * slot x 0x08000000 + line x 4096 + pair x 4); the rest is the program's to use:
 * MEM_FREE on in each.  Nothing uses it yet but the test here: the memory written and read back
 * once the controller is calibrated, more than the core's cache holds, and bytes and halves with
 * the cache off (the port's own gather and its masks). */
#include "hw.h"

#define TEST_AT     0x07000000u         /* (bank 0, far above its field) */
#define TEST_WORDS  (1u << 16)          /* 256 KB */

int mem_state;                          /* MEM_* (hw.h) */

static uint32_t pat(uint32_t i)
{
    return (i * 2654435761u) ^ 0x5a5a5a5au;
}

void mem_test(void)
{
    volatile uint32_t *m = (volatile uint32_t *)TEST_AT;
    volatile uint8_t *b = (volatile uint8_t *)(TEST_AT + 0x00100000u);
    uint32_t wrote, bad = 0;

    if (!(REG(R_DDR) & 1)) {            /* not calibrated: the port would not answer */
        mem_state = MEM_NONE;
        return;
    }
    wrote = REG(R_CPUMW);
    for (uint32_t i = 0; i < TEST_WORDS; i++)
        m[i] = pat(i);
    for (uint32_t i = 0; i < TEST_WORDS; i++)
        bad += m[i] != pat(i);
    /* the cache off: each of these is a transfer of its own on the port */
    __asm__ volatile ("csrci 0x7ca, 2");
    for (uint32_t i = 0; i < 96; i++)
        b[i] = (uint8_t)(i * 7 + 1);
    ((volatile uint16_t *)b)[20] = 0xBEEF;
    ((volatile uint32_t *)b)[16] = 0x12345678;
    for (uint32_t i = 0; i < 96; i++) {
        uint8_t want = i == 40 ? 0xEF : i == 41 ? 0xBE : i >= 64 && i < 68 ? (uint8_t)(0x12345678u >> 8 * (i - 64)) :
                       (uint8_t)(i * 7 + 1);
        bad += b[i] != want;
    }
    bad += ((volatile uint32_t *)b)[3] != 0x6A635C55u;      /* (bytes 12 to 15 as a word) */
    /* (and it stays off: the capture writes the memory behind the cache, and what the program reads of
     * the picture (pan.c) must be what is there now) */
    mem_state = REG(R_CPUMR) >> 31 ? MEM_DEAD : REG(R_CPUMW) == wrote ? MEM_NONE : bad ? MEM_BAD : MEM_GOOD;
    REG(R_CPUM + 2) = 0x4D450000u | (uint32_t)mem_state << 12 | (bad > 0xFFF ? 0xFFF : bad);   /* "ME", for a host */
}
