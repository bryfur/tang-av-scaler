/* audio.c: the sound through the CPU: each pair of samples from the converter (rtl/audio_fifo.v
 * holds them) made six channels (surround.c) and given back, to go out over HDMI as 5.1.  Called
 * wherever the program waits: a pair comes every 21 us, 512 of them can wait (11 ms). */
#include "hw.h"
#include "surround.h"

static bool on;

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
    int32_t out[6];
    if (!on || busy)
        return;
    /* (kept from here too long: the pairs piled up, and what is waiting to go out is old: both
     * emptied, a short silence, and the sound is as little behind the picture as before) */
    if ((REG(R_AUD) & 0x3FF) > 480) {
        REG(R_AUD) = 3;
        return;
    }
    busy = true;
    for (int n = 0; n < 512; n++) {
        uint32_t l = REG(R_AUDL), r;
        if (!(l >> 31)) {
            if (!(REG(R_AUD) & 0x3FF))
                break;
            continue;                   /* (the next pair is on its way out of the memory) */
        }
        r = REG(R_AUDR);
        surround((int32_t)(l << 8) >> 8, (int32_t)(r << 8) >> 8, out);
        for (int k = 0; k < 6; k++)
            REG(R_AUDO) = (uint32_t)out[k] & 0xFFFFFF;
    }
    busy = false;
}
