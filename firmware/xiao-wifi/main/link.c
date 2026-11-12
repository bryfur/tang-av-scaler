/* link.c: the XIAO's SPI port to the FPGA (gateware/rtl/spis.v; the XIAO the master, mode 0):
 *
 *  - registers, with no program needed on the other side: written (a stream of words to one
 *    register: so the CPU's program is loaded), read;
 *  - messages to the scaler's CPU (gateware/sw/link.h): a request, then its answer when the FPGA's
 *    interrupt line says it is there.
 *
 * One exchange at a time (the scaler's task and the web server's both come here).
 */
#include <string.h>

#include "app.h"
#include "board.h"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#define MAXF 2304                       /* a frame: an answer of 2048 bytes and what is round it */
static const char *TAG = "link";
static spi_device_handle_t dev;
static SemaphoreHandle_t mtx;
static uint8_t *txb, *rxb;

void link_start(void)
{
    const spi_bus_config_t bus = {.mosi_io_num = PIN_MOSI, .miso_io_num = PIN_MISO, .sclk_io_num = PIN_SCK,
                                  .quadwp_io_num = -1, .quadhd_io_num = -1, .max_transfer_sz = MAXF};
    /* (4 MHz: the FPGA samples the lines with its 50 MHz, and its answer's bit comes three of those
     * clocks after the clock's fall) */
    const spi_device_interface_config_t d = {.clock_speed_hz = 4000000, .mode = 0, .spics_io_num = PIN_CS,
                                             .queue_size = 1, .cs_ena_pretrans = 2, .cs_ena_posttrans = 2};
    const gpio_config_t irq = {.pin_bit_mask = 1ull << PIN_IRQ, .mode = GPIO_MODE_INPUT, .pull_up_en = GPIO_PULLUP_ENABLE};
    mtx = xSemaphoreCreateMutex();
    txb = heap_caps_malloc(MAXF, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    rxb = heap_caps_malloc(MAXF, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    gpio_config(&irq);
    if (!txb || !rxb || spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO) != ESP_OK ||
        spi_bus_add_device(SPI2_HOST, &d, &dev) != ESP_OK) {
        ESP_LOGE(TAG, "no SPI port");
        dev = NULL;
    }
}

static bool xfer(size_t n)
{
    spi_transaction_t t = {.length = 8 * n, .tx_buffer = txb, .rx_buffer = rxb};
    return dev && spi_device_transmit(dev, &t) == ESP_OK;
}

bool link_reg_read(uint8_t addr, uint32_t *v)
{
    bool ok;
    if (!dev)
        return false;
    xSemaphoreTake(mtx, portMAX_DELAY);
    memset(txb, 0, 7);
    txb[0] = 0x02;
    txb[1] = addr;
    ok = xfer(7);
    *v = rxb[3] | rxb[4] << 8 | rxb[5] << 16 | (uint32_t)rxb[6] << 24;
    xSemaphoreGive(mtx);
    return ok;
}

bool link_reg_write(uint8_t addr, const uint32_t *words, size_t n)
{
    bool ok = dev != NULL;
    if (!dev)
        return false;
    xSemaphoreTake(mtx, portMAX_DELAY);
    while (ok && n) {
        size_t k = n > 512 ? 512 : n;
        txb[0] = 0x01;
        txb[1] = addr;
        memcpy(txb + 2, words, 4 * k);
        ok = xfer(2 + 4 * k);
        words += k;
        n -= k;
    }
    xSemaphoreGive(mtx);
    return ok;
}

/* an answer read, if one is there: its length (max at most kept), or -1 */
static int answer(uint8_t *reply, size_t max)
{
    size_t len;
    memset(txb, 0, 4 + max);
    txb[0] = 0x04;
    if (!xfer(4 + max) || !(rxb[1] & 1))
        return -1;
    len = rxb[2] | rxb[3] << 8;
    if (len > max)
        len = max;
    if (reply)
        memcpy(reply, rxb + 4, len);
    return (int)len;
}

int link_msg(const uint8_t *req, size_t n, uint8_t *reply, size_t max, int ms)
{
    int got = -1;
    if (!dev || n > 252 || max > 2048)
        return -1;
    xSemaphoreTake(mtx, portMAX_DELAY);
    if (!gpio_get_level(PIN_IRQ))
        answer(NULL, 2048);             /* (an answer nobody took: out of the way) */
    txb[0] = 0x03;
    memcpy(txb + 1, req, n);
    if (xfer(1 + n)) {
        /* (most answers are there within a few hundred microseconds) */
        int64_t t0 = esp_timer_get_time();
        while (gpio_get_level(PIN_IRQ)) {
            int64_t dt = esp_timer_get_time() - t0;
            if (dt > (int64_t)ms * 1000)
                break;
            if (dt < 1500)
                esp_rom_delay_us(50);
            else
                vTaskDelay(1);
        }
        if (!gpio_get_level(PIN_IRQ))
            got = answer(reply, max);
    }
    xSemaphoreGive(mtx);
    return got;
}

/* the CPU's program (gateware/rtl/cpu.v: the core held in reset, its RAM written through the
 * register that counts on, the core let go); words: the program, n of them */
bool link_program(const uint8_t *bin, size_t bytes)
{
    enum { CPU = 0x60, CPUA = 0x61, CPUD = 0x62 };
    static uint32_t w[512];
    uint32_t zero = 0, one = 1, at = 0;
    size_t n = (bytes + 3) / 4;
    bool ok = n <= 8192 && link_reg_write(CPU, &zero, 1) && link_reg_write(CPUA, &zero, 1);
    for (size_t k = 0; ok && k < n; k += 512) {
        size_t c = n - k > 512 ? 512 : n - k, b = 4 * c > bytes - 4 * k ? bytes - 4 * k : 4 * c;
        memset(w, 0, sizeof w);
        memcpy(w, bin + 4 * k, b);
        ok = link_reg_write(CPUD, w, c);
    }
    ok = ok && link_reg_read(CPUA, &at) && at == n;
    link_reg_write(CPU, &one, 1);
    ESP_LOGI(TAG, "the CPU's program: %u bytes %s", (unsigned)bytes, ok ? "loaded" : "NOT loaded");
    return ok;
}
