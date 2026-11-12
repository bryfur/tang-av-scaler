/* The FPGA's JTAG on D0-D3, bit-banged on the GPIO registers.
 *
 * Each clock: TCK low with the new TMS and TDI, half a period, TCK high (the FPGA samples), half a
 * period, read TDO.  TDO changes at TCK's fall, so it is read almost a whole period later: the
 * way through the two level translators and back (U22, the FPGA, U23, 470 R) has all of it.
 * Interrupts stay on: one only stretches a clock. */

#include "jtag.h"

#include <string.h>

#include "board.h"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_heap_caps.h"
#include "esp_rom_gpio.h"
#include "hal/usb_serial_jtag_ll.h"
#include "soc/gpio_sig_map.h"
#include "esp_attr.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "soc/gpio_reg.h"
#include "soc/soc.h"

static const char *TAG = "jtag";

#define M_TMS (1u << PIN_TMS)
#define M_TCK (1u << PIN_TCK)
#define M_TDI (1u << PIN_TDI)

static SemaphoreHandle_t lock;
#define MIN_HALF_NS 150
static uint32_t half_wait;          /* delay loop turns per half period */
static uint32_t min_turns;          /* turns for MIN_HALF_NS, in every half */
static uint32_t base_ps, turn_ps;   /* a clock with no delay; one more turn in each half */

static inline __attribute__((always_inline)) void wait_turns(uint32_t n)
{
    for (; n; n--)
        __asm__ __volatile__("nop");
}

/* (the pin masks as arguments: the calibration runs the same loop on no pins) */
static void IRAM_ATTR shift(const uint8_t *tms, const uint8_t *tdi, uint8_t *tdo, uint32_t nbits, uint32_t m_tms,
                            uint32_t m_tdi, uint32_t m_tck, uint32_t turns)
{
    for (uint32_t i = 0; i < nbits; i += 8) {
        uint32_t m = tms[i >> 3], d = tdi[i >> 3], q = 0;
        uint32_t n = nbits - i < 8 ? nbits - i : 8;
        for (uint32_t b = 0; b < n; b++) {
            uint32_t set = (m >> b & 1 ? m_tms : 0) | (d >> b & 1 ? m_tdi : 0);
            REG_WRITE(GPIO_OUT_W1TC_REG, set ^ (m_tms | m_tdi));
            REG_WRITE(GPIO_OUT_W1TS_REG, set);
            wait_turns(turns + min_turns);          /* TMS and TDI stand before the rise */
            REG_WRITE(GPIO_OUT_W1TS_REG, m_tck);
            wait_turns(turns + min_turns);
            q |= (REG_READ(GPIO_IN_REG) >> PIN_TDO & 1) << b;
            REG_WRITE(GPIO_OUT_W1TC_REG, m_tck);    /* the fall here: the loop's own work is in the low half */
        }
        tdo[i >> 3] = q;
    }
}

void jtag_shift(const uint8_t *tms, const uint8_t *tdi, uint8_t *tdo, uint32_t nbits)
{
    shift(tms, tdi, tdo, nbits, M_TMS, M_TDI, M_TCK, half_wait);
}

static uint32_t timed_ps(uint32_t turns)
{
    static uint8_t z[2048];
    int64_t t0 = esp_timer_get_time();
    shift(z, z, z, sizeof z * 8, 0, 0, 0, turns);
    int64_t t = esp_timer_get_time() - t0;
    memset(z, 0, sizeof z);
    return (uint32_t)(t * 1000000 / (sizeof z * 8));
}

void jtag_init(void)
{
    lock = xSemaphoreCreateMutex();
    /* the levels first, then the drivers: TMS high and TCK low is where the FPGA's TAP rests */
    gpio_set_level(PIN_TMS, 1);
    gpio_set_level(PIN_TCK, 0);
    gpio_set_level(PIN_TDI, 0);
    const gpio_config_t out = {.pin_bit_mask = 1ull << PIN_TMS | 1ull << PIN_TCK | 1ull << PIN_TDI,
                               .mode = GPIO_MODE_OUTPUT};
    const gpio_config_t in = {.pin_bit_mask = 1ull << PIN_TDO, .mode = GPIO_MODE_INPUT,
                              .pull_up_en = GPIO_PULLUP_ENABLE};
    gpio_config(&out);
    gpio_set_level(PIN_TMS, 1);
    gpio_config(&in);

    timed_ps(0);                    /* (the code into the cache) */
    base_ps = timed_ps(0);
    turn_ps = (timed_ps(32) - base_ps) / 32;
    if (turn_ps == 0)
        turn_ps = 1;
    /* (a turn in each half costs turn_ps: half of it in one) */
    min_turns = (MIN_HALF_NS * 2000u + turn_ps - 1) / turn_ps;
    base_ps = timed_ps(0);          /* the fastest clock, with the halves' least */
    jtag_set_period(200);
    ESP_LOGI(TAG, "fastest clock %u ps, %u ps a delay turn; now %u ns", (unsigned)base_ps, (unsigned)turn_ps,
             (unsigned)jtag_period());
}

uint32_t jtag_set_period(uint32_t ns)
{
    uint64_t ps = (uint64_t)ns * 1000;
    half_wait = ps <= base_ps ? 0 : (uint32_t)((ps - base_ps + turn_ps - 1) / turn_ps);
    if (half_wait > 100000)
        half_wait = 100000;
    return jtag_period();
}

uint32_t jtag_period(void)
{
    return (base_ps + half_wait * turn_ps + 999) / 1000;
}

uint32_t jtag_fastest(void)
{
    return (base_ps + 999) / 1000;
}

/* Whose the pads are.  At rest they are the chip's USB-JTAG unit's (its bridge: the unit's TCK, TMS
 * and TDI out through the pin matrix, TDO in), so a PC on the XIAO's USB cable is the FPGA's JTAG
 * cable (openFPGALoader -c esp32s3: the ESP32-C5 has the unit the ESP32-S3 has), with the unit's own
 * clock.  The firmware's own users (the XVC port, the status page, gowin.c) take them for the GPIO
 * registers while they hold the port. */
#if CONFIG_IDF_TARGET_ESP32S3
#define USB_TDO_IN USB_JTAG_TDO_BRIDGE_IDX
#else
#define USB_TDO_IN USB_JTAG_TDO_IDX
#endif

static void pads_usb(void)
{
    usb_serial_jtag_ll_phy_enable_jtag_bridge(true);
    esp_rom_gpio_connect_in_signal(PIN_TDO, USB_TDO_IN, false);
    esp_rom_gpio_connect_out_signal(PIN_TCK, USB_JTAG_TCK_IDX, false, false);
    esp_rom_gpio_connect_out_signal(PIN_TMS, USB_JTAG_TMS_IDX, false, false);
    esp_rom_gpio_connect_out_signal(PIN_TDI, USB_JTAG_TDI_IDX, false, false);
}

static void pads_gpio(void)
{
    REG_WRITE(GPIO_OUT_W1TC_REG, M_TCK);
    REG_WRITE(GPIO_OUT_W1TS_REG, M_TMS);
    esp_rom_gpio_connect_out_signal(PIN_TCK, SIG_GPIO_OUT_IDX, false, false);
    esp_rom_gpio_connect_out_signal(PIN_TMS, SIG_GPIO_OUT_IDX, false, false);
    esp_rom_gpio_connect_out_signal(PIN_TDI, SIG_GPIO_OUT_IDX, false, false);
}

void jtag_usb_bridge(void)
{
    pads_usb();
}

bool jtag_take(bool wait)
{
    if (xSemaphoreTake(lock, wait ? portMAX_DELAY : 0) != pdTRUE)
        return false;
    pads_gpio();
    return true;
}

void jtag_give(void)
{
    pads_usb();
    xSemaphoreGive(lock);
}


/* Long runs of data bits by the SPI master: its clock on TCK's pad and its data on TDI's, TMS
 * left as it stands (in Shift-DR: low).  Mode 0: the clock rests low, data changes at its fall and
 * is taken at its rise, as JTAG's; each byte's top bit first.  The clock is the peripheral's, even
 * and without a break inside a block, whatever Wi-Fi does with the CPU; blocks are queued two
 * deep, so the next starts from the interrupt that ends the one before. */
#define BULK_CHUNK 16384
static spi_device_handle_t spi;
static uint32_t spi_hz;
static uint8_t *bulk_buf[2];
static spi_transaction_t bulk_tr[2];
static int bulk_queued, bulk_next;

static void pads_to(uint32_t tck_signal, uint32_t tdi_signal)
{
    esp_rom_gpio_connect_out_signal(PIN_TCK, tck_signal, false, false);
    esp_rom_gpio_connect_out_signal(PIN_TDI, tdi_signal, false, false);
}

bool jtag_bulk_begin(uint32_t hz)
{
    if (!bulk_buf[0]) {
        const spi_bus_config_t bus = {.mosi_io_num = PIN_TDI, .miso_io_num = -1, .sclk_io_num = PIN_TCK,
                                      .quadwp_io_num = -1, .quadhd_io_num = -1, .max_transfer_sz = BULK_CHUNK};
        if (spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO) != ESP_OK)
            return false;
        pads_to(SIG_GPIO_OUT_IDX, SIG_GPIO_OUT_IDX);    /* (the bus took the pads: back to the registers) */
        bulk_buf[0] = heap_caps_malloc(BULK_CHUNK, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
        bulk_buf[1] = heap_caps_malloc(BULK_CHUNK, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
        if (!bulk_buf[0] || !bulk_buf[1])
            return false;
    }
    if (spi && hz != spi_hz) {
        spi_bus_remove_device(spi);
        spi = NULL;
    }
    if (!spi) {
        const spi_device_interface_config_t dev = {.clock_speed_hz = hz, .mode = 0, .spics_io_num = -1, .queue_size = 2};
        if (spi_bus_add_device(SPI2_HOST, &dev, &spi) != ESP_OK)
            return false;
        spi_hz = hz;
    }
    spi_device_acquire_bus(spi, portMAX_DELAY);
    REG_WRITE(GPIO_OUT_W1TC_REG, M_TCK);
    pads_to(FSPICLK_OUT_IDX, FSPID_OUT_IDX);
    bulk_queued = bulk_next = 0;
    return true;
}

void jtag_bulk_send(const uint8_t *data, size_t n)
{
    while (n) {
        spi_transaction_t *done;
        if (bulk_queued == 2) {                         /* the older one's buffer is the next to fill */
            spi_device_get_trans_result(spi, &done, portMAX_DELAY);
            bulk_queued--;
        }
        size_t k = n > BULK_CHUNK ? BULK_CHUNK : n;
        spi_transaction_t *t = &bulk_tr[bulk_next];
        memcpy(bulk_buf[bulk_next], data, k);
        memset(t, 0, sizeof *t);
        t->length = k * 8;
        t->tx_buffer = bulk_buf[bulk_next];
        spi_device_queue_trans(spi, t, portMAX_DELAY);
        bulk_queued++;
        bulk_next ^= 1;
        data += k;
        n -= k;
    }
}

void jtag_bulk_end(void)
{
    spi_transaction_t *done;
    for (; bulk_queued; bulk_queued--)
        spi_device_get_trans_result(spi, &done, portMAX_DELAY);
    REG_WRITE(GPIO_OUT_W1TC_REG, M_TCK);                /* TCK low, as the SPI clock rests */
    pads_to(SIG_GPIO_OUT_IDX, SIG_GPIO_OUT_IDX);
    spi_device_release_bus(spi);
}
