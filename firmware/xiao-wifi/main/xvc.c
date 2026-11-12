/* JTAG over TCP: a Xilinx Virtual Cable server (xvc_core.c) on PORT_XVC.
 *
 *   openFPGALoader -c xvc-client --ip HOST --port 2542 image.fs
 *
 * One client at a time; it holds the JTAG pins for as long as it is connected. */

#include <string.h>

#include "app.h"
#include "board.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "jtag.h"
#include "lwip/sockets.h"
#include "xvc_core.h"

static const char *TAG = "xvc";
static struct xvc_state state;
static struct xvc_stats stats;

static int rd(void *ctx, uint8_t *buf, size_t n)
{
    int fd = (int)(intptr_t)ctx;
    while (n) {
        int r = recv(fd, buf, n, 0);
        if (r <= 0)
            return -1;
        buf += r;
        n -= r;
    }
    return 0;
}

static int wr(void *ctx, const uint8_t *buf, size_t n)
{
    int fd = (int)(intptr_t)ctx;
    while (n) {
        int r = send(fd, buf, n, 0);
        if (r <= 0)
            return -1;
        buf += r;
        n -= r;
    }
    return 0;
}

/* A load is some hundred long shifts back to back, and this chip has one core: a tick's rest
 * after each long one lets the idle task (and its watchdog) run. */
static void shift(const uint8_t *tms, const uint8_t *tdi, uint8_t *tdo, uint32_t nbits)
{
    jtag_shift(tms, tdi, tdo, nbits);
    if (nbits >= 8192)
        vTaskDelay(1);
}

static void serve(void *arg)
{
    uint8_t *buf = heap_caps_malloc(2 * XVC_VECTOR, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    int ls = socket(AF_INET, SOCK_STREAM, 0);
    int one = 1;
    setsockopt(ls, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    struct sockaddr_in a = {.sin_family = AF_INET, .sin_port = htons(PORT_XVC), .sin_addr.s_addr = htonl(INADDR_ANY)};
    if (!buf || ls < 0 || bind(ls, (struct sockaddr *)&a, sizeof a) || listen(ls, 1)) {
        ESP_LOGE(TAG, "no server on port %d", PORT_XVC);
        vTaskDelete(NULL);
    }
    for (;;) {
        struct sockaddr_in peer;
        socklen_t len = sizeof peer;
        int fd = accept(ls, (struct sockaddr *)&peer, &len);
        if (fd < 0) {
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }
        /* a client that went away without closing (Wi-Fi lost, the PC asleep) must not keep the
         * pins: a keepalive probe after 5 s of silence, 3 more 2 s apart, then the socket fails */
        int idle = 5, intvl = 2, cnt = 3;
        setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
        setsockopt(fd, SOL_SOCKET, SO_KEEPALIVE, &one, sizeof one);
        setsockopt(fd, IPPROTO_TCP, TCP_KEEPIDLE, &idle, sizeof idle);
        setsockopt(fd, IPPROTO_TCP, TCP_KEEPINTVL, &intvl, sizeof intvl);
        setsockopt(fd, IPPROTO_TCP, TCP_KEEPCNT, &cnt, sizeof cnt);

        jtag_take(true);
        inet_ntoa_r(peer.sin_addr, state.peer, sizeof state.peer);
        state.connected = true;
        state.sessions++;
        uint64_t bits0 = stats.bits;
        const struct xvc_io io = {.ctx = (void *)(intptr_t)fd, .rd = rd, .wr = wr, .shift = shift,
                                  .set_period = jtag_set_period};
        int rc = xvc_serve(&io, buf, &stats);
        state.connected = false;
        jtag_give();
        close(fd);
        ESP_LOGI(TAG, "%s: %llu bits, TCK %u ns%s", state.peer, (unsigned long long)(stats.bits - bits0),
                 (unsigned)jtag_period(), rc ? " (ended on an error)" : "");
    }
}

void xvc_start(void)
{
    xTaskCreate(serve, "xvc", 4096, NULL, 5, NULL);
}

void xvc_get(struct xvc_state *s)
{
    *s = state;
    s->bits = stats.bits;
    s->shifts = stats.shifts;
}
