/* audio.c: the sound through the CPU: each pair of samples from the converter (rtl/audio_fifo.v
 * holds them) made six channels (surround.c) and given back, to go out over HDMI as 5.1.  Called
 * wherever the program waits: a pair comes every 21 us, 512 of them can wait (11 ms). */
#include "hw.h"
#include "surround.h"

static bool on;
uint32_t audio_cycles;                  /* the core's clocks spent on the sound since it was last asked (hw.h) */
uint32_t audio_dsp_cycles;              /* ... of them in the decoder itself (the rest: the registers) */

void audio_set(bool want)
{
    if (want == on)
        return;
    on = want;
    surround_reset();
    REG(R_AUD) = on ? 3 : 2;            /* (both FIFOs emptied) */
}

bool audio_on(void)
{
    return on;
}

void audio_service(void)
{
    static bool busy;
    static uint8_t since;
    int32_t out[6];
    uint32_t l, r, t0, t1;
    if (!on || busy)
        return;
    /* (nothing waits, most times this is asked: one register read, 0.4 us) */
    l = REG(R_AUDL);
    if (!(l >> 31))
        return;
    busy = true;
    t0 = cycles();
    for (int n = 0; n < 512 && l >> 31; n++) {
        /* (kept from here too long: the pairs piled up, or were all made at once and now wait to
         * go out: the sound is late.  Both emptied, a short silence, and it is as little behind
         * the picture as before.  Looked at every 64th pair: a register read more) */
        if (!(++since & 63)) {
            uint32_t s = REG(R_AUD);
            if ((s & 0x3FF) > 480 || (s >> 16 & 0x3FF) > 384) {
                REG(R_AUD) = 3;
                break;
            }
        }
        r = REG(R_AUDR);
        t1 = cycles();
        surround((int32_t)(l << 8) >> 8, (int32_t)(r << 8) >> 8, out);
        audio_dsp_cycles += cycles() - t1;
        for (int k = 0; k < 6; k++)
            REG(R_AUDO) = (uint32_t)out[k] & 0xFFFFFF;
        l = REG(R_AUDL);                /* (the next pair, if it is there already: else at the next asking) */
    }
    audio_cycles += cycles() - t0;
    busy = false;
}
