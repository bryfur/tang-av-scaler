/* The ESP's log in a ring in RAM: the UART pads and the USB port are the FPGA's. */

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "app.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"

#define RING 8192
static char ring[RING];
static size_t head, used;
static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

static int to_ring(const char *fmt, va_list ap)
{
    char line[192];
    int n = vsnprintf(line, sizeof line, fmt, ap);
    if (n <= 0)
        return n;
    if (n >= (int)sizeof line)
        n = sizeof line - 1;
    portENTER_CRITICAL(&mux);
    for (int k = 0; k < n; k++) {
        ring[head] = line[k];
        head = (head + 1) % RING;
    }
    used = used + n > RING ? RING : used + n;
    portEXIT_CRITICAL(&mux);
    return n;
}

void logbuf_init(void)
{
    esp_log_set_vprintf(to_ring);
}

size_t logbuf_copy(char *dst, size_t max)
{
    portENTER_CRITICAL(&mux);
    size_t n = used < max ? used : max;
    size_t from = (head + RING - n) % RING;
    for (size_t k = 0; k < n; k++)
        dst[k] = ring[(from + k) % RING];
    portEXIT_CRITICAL(&mux);
    return n;
}
