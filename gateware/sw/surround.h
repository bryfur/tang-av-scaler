/* surround.h: two channels made five (surround.c) */
#ifndef SURROUND_H
#define SURROUND_H

#include <stdint.h>

void surround_reset(void);
/* a pair of samples in (24 bits signed), six out: left, right, centre, LFE (nothing), left
 * surround, right surround */
void surround(int32_t lt, int32_t rt, int32_t out[6]);

#endif
