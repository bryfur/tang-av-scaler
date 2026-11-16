/* The FPGA's UART (D6 the XIAO's TX, D7 its RX, UART_BAUD), raw bytes both ways:
 *
 *  - on TCP port PORT_CONSOLE, one client at a time (a new one takes the place of the old);
 *  - on the XIAO's USB serial port too, when a cable is in (as the wired firmware, ../xiao);
 *  - the last bytes the FPGA sent are kept (GET /api/console): what it said with nobody listening.
 *
 * Nothing holds the UART up: what a slow or absent listener cannot take is dropped. */

#include <errno.h>
#include <string.h>

#include "app.h"
#include "board.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "driver/usb_serial_jtag.h"
#include "esp_attr.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "freertos/idf_additions.h"
#include "lwip/sockets.h"

#define FPGA_UART UART_NUM_1
#define TAIL 16384

static const char *TAG = "console";
static struct console_state state;
static int client = -1;
static SemaphoreHandle_t lock;          /* client, tail */
static char *tail;                      /* (big(): TAIL bytes) */
static size_t tail_head, tail_used;

static void from_fpga(void *arg)
{
    enum { BUF = 2048 };
    uint8_t *buf = big(BUF);
    for (;;) {
        /* whatever is there, at once: wait for the first byte, take the rest without waiting */
        int n = uart_read_bytes(FPGA_UART, buf, 1, portMAX_DELAY);
        if (n <= 0)
            continue;
        size_t more = 0;
        uart_get_buffered_data_len(FPGA_UART, &more);
        if (more > BUF - 1)
            more = BUF - 1;
        if (more)
            n += uart_read_bytes(FPGA_UART, buf + 1, more, 0);
        state.from_fpga += n;
        xSemaphoreTake(lock, portMAX_DELAY);
        for (int k = 0; k < n; k++) {
            tail[tail_head] = buf[k];
            tail_head = (tail_head + 1) % TAIL;
        }
        tail_used = tail_used + n > TAIL ? TAIL : tail_used + n;
        /* all of it to the client: what its connection cannot take now waits a little (a send that
         * takes a part was left at that: a monitor's long answer lost bytes when it came faster than
         * the client's acknowledgements, 2026-11-14); a client that takes nothing for half a second
         * loses these bytes, and the count says so */
        if (client >= 0) {
            int sent = 0, waited = 0;
            while (sent < n) {
                int r = send(client, buf + sent, n - sent, MSG_DONTWAIT);
                if (r > 0) {
                    sent += r;
                    waited = 0;
                } else if (r < 0 && errno != EAGAIN && errno != EWOULDBLOCK)
                    break;
                else if (++waited > 250) {
                    break;
                } else
                    vTaskDelay(pdMS_TO_TICKS(2));
            }
            state.lost += n - sent;
        }
        xSemaphoreGive(lock);

        state.usb = usb_serial_jtag_is_connected();
        if (state.usb)
            usb_serial_jtag_write_bytes(buf, n, pdMS_TO_TICKS(20));
    }
}

static void from_usb(void *arg)
{
    enum { BUF = 1024 };
    uint8_t *buf = big(BUF);
    for (;;) {
        int n = usb_serial_jtag_read_bytes(buf, BUF, portMAX_DELAY);
        if (n <= 0)
            continue;
        uart_write_bytes(FPGA_UART, buf, n);
        state.to_fpga += n;
    }
}

static void drop_client(void)
{
    xSemaphoreTake(lock, portMAX_DELAY);
    int fd = client;
    client = -1;
    state.tcp = false;
    xSemaphoreGive(lock);
    if (fd >= 0)
        close(fd);
}

static void from_tcp(void *arg)
{
    enum { BUF = 1024 };
    uint8_t *buf = big(BUF);
    int ls = socket(AF_INET, SOCK_STREAM, 0);
    int one = 1;
    setsockopt(ls, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    struct sockaddr_in a = {.sin_family = AF_INET, .sin_port = htons(PORT_CONSOLE),
                            .sin_addr.s_addr = htonl(INADDR_ANY)};
    if (ls < 0 || bind(ls, (struct sockaddr *)&a, sizeof a) || listen(ls, 1)) {
        ESP_LOGE(TAG, "no server on port %d", PORT_CONSOLE);
        vTaskDelete(NULL);
    }
    for (;;) {
        fd_set r;
        FD_ZERO(&r);
        FD_SET(ls, &r);
        int top = ls;
        if (client >= 0) {
            FD_SET(client, &r);
            if (client > top)
                top = client;
        }
        if (select(top + 1, &r, NULL, NULL, NULL) <= 0) {
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }
        if (FD_ISSET(ls, &r)) {
            struct sockaddr_in peer;
            socklen_t len = sizeof peer;
            int fd = accept(ls, (struct sockaddr *)&peer, &len);
            if (fd >= 0) {
                int idle = 5, intvl = 2, cnt = 3;
                setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
                setsockopt(fd, SOL_SOCKET, SO_KEEPALIVE, &one, sizeof one);
                setsockopt(fd, IPPROTO_TCP, TCP_KEEPIDLE, &idle, sizeof idle);
                setsockopt(fd, IPPROTO_TCP, TCP_KEEPINTVL, &intvl, sizeof intvl);
                setsockopt(fd, IPPROTO_TCP, TCP_KEEPCNT, &cnt, sizeof cnt);
                drop_client();
                xSemaphoreTake(lock, portMAX_DELAY);
                client = fd;
                inet_ntoa_r(peer.sin_addr, state.peer, sizeof state.peer);
                state.tcp = true;
                xSemaphoreGive(lock);
            }
            continue;
        }
        int n = recv(client, buf, BUF, 0);
        if (n <= 0) {
            drop_client();
            continue;
        }
        uart_write_bytes(FPGA_UART, buf, n);
        state.to_fpga += n;
    }
}

bool console_busy(void)
{
    return state.tcp;
}

void console_start(void)
{
    lock = xSemaphoreCreateMutex();
    tail = big(TAIL);
    usb_serial_jtag_driver_config_t usb = {.tx_buffer_size = 16384, .rx_buffer_size = 16384};
    usb_serial_jtag_driver_install(&usb);

    const uart_config_t cfg = {.baud_rate = UART_BAUD, .data_bits = UART_DATA_8_BITS, .parity = UART_PARITY_DISABLE,
                               .stop_bits = UART_STOP_BITS_1, .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
                               .source_clk = UART_SCLK_DEFAULT};
    uart_driver_install(FPGA_UART, 16384, 16384, 0, NULL, 0);
    uart_param_config(FPGA_UART, &cfg);
    uart_set_pin(FPGA_UART, PIN_TX, PIN_RX, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    gpio_set_pull_mode(PIN_RX, GPIO_PULLUP_ONLY);

    /* (their stacks in the PSRAM: none of them touches the flash, and the chip's own RAM is for
     * Wi-Fi and Bluetooth) */
    xTaskCreateWithCaps(from_fpga, "from_fpga", 4096, NULL, 10, NULL, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    xTaskCreateWithCaps(from_usb, "from_usb", 4096, NULL, 10, NULL, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    xTaskCreateWithCaps(from_tcp, "from_tcp", 4096, NULL, 10, NULL, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
}

void console_get(struct console_state *s)
{
    *s = state;
}

size_t console_tail(char *dst, size_t max)
{
    xSemaphoreTake(lock, portMAX_DELAY);
    size_t n = tail_used < max ? tail_used : max;
    size_t from = (tail_head + TAIL - n) % TAIL;
    for (size_t k = 0; k < n; k++)
        dst[k] = tail[(from + k) % TAIL];
    xSemaphoreGive(lock);
    return n;
}
