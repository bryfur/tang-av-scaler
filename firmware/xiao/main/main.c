/* The XIAO ESP32-S3 on the AV board (rev C-A/C-B, hardware/av-board/rev-c/design.md "The XIAO
 * as programmer and console"):
 *
 *  - its USB is the chip's own USB-Serial-JTAG (303a:1001).  The JTAG half is taken off the
 *    ESP32's own TAP and put on D0-D3, the FPGA's JTAG (USB_JTAG_BRIDGE_EN): openFPGALoader's
 *    cable "esp32s3" loads the FPGA through it;
 *  - the serial half is the FPGA's UART (D6 the XIAO's TX, D7 its RX), UART_BAUD.
 *
 * esptool still resets the chip into its loader over the same USB (no BOOT button).
 */

#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>

#include "driver/gpio.h"
#include "driver/uart.h"
#include "driver/usb_serial_jtag.h"
#include "esp_rom_gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "soc/gpio_reg.h"
#include "soc/gpio_sig_map.h"
#include "soc/usb_serial_jtag_reg.h"

/* XIAO ESP32-S3 pads [Seeed: XIAO ESP32S3 pin map] */
#define D0_TMS   1
#define D1_TCK   2
#define D2_TDI   3
#define D3_TDO   4
#define D6_TX    43
#define D7_RX    44

#define UART_BAUD 1000000
#define FPGA_UART UART_NUM_1

static void jtag_bridge(void)
{
    const gpio_config_t out = {.pin_bit_mask = 1ull << D0_TMS | 1ull << D1_TCK | 1ull << D2_TDI,
                               .mode = GPIO_MODE_OUTPUT};
    const gpio_config_t in = {.pin_bit_mask = 1ull << D3_TDO, .mode = GPIO_MODE_INPUT,
                              .pull_up_en = GPIO_PULLUP_ENABLE};
    gpio_config(&out);
    gpio_config(&in);
    esp_rom_gpio_connect_out_signal(D1_TCK, USB_JTAG_TCK_IDX, false, false);
    esp_rom_gpio_connect_out_signal(D0_TMS, USB_JTAG_TMS_IDX, false, false);
    esp_rom_gpio_connect_out_signal(D2_TDI, USB_JTAG_TDI_IDX, false, false);
    esp_rom_gpio_connect_in_signal(D3_TDO, USB_JTAG_TDO_BRIDGE_IDX, false);
    SET_PERI_REG_MASK(USB_SERIAL_JTAG_CONF0_REG, USB_SERIAL_JTAG_USB_JTAG_BRIDGE_EN);
}

/* The XIAO's own commands, inside the serial stream: KNOCK then a letter (the bytes go on to the
 * FPGA too; its monitor skips them).  Answers are text lines starting "avxiao:".
 *   s  status: bytes each way, the pads' levels (GPIO_IN, GPIO_IN1), the USB-JTAG bridge's bit
 *   t  the UART's TX line inverted for 2 ms: what RX (and the pads) read with TX low, then high */
static const uint8_t KNOCK[4] = {0x1D, 0x0E, 0x1F, 0x0F};
static uint32_t n_to_fpga, n_from_fpga;

static void say(const char *fmt, ...)
{
    char line[160];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    usb_serial_jtag_write_bytes(line, n, pdMS_TO_TICKS(50));
}

static void command(uint8_t c)
{
    if (c == 's') {
        say("avxiao: 2 to_fpga %u from_fpga %u gpio_in %08x %08x conf0 %08x\r\n", (unsigned)n_to_fpga,
            (unsigned)n_from_fpga, (unsigned)REG_READ(GPIO_IN_REG), (unsigned)REG_READ(GPIO_IN1_REG),
            (unsigned)REG_READ(USB_SERIAL_JTAG_CONF0_REG));
    } else if (c == 't') {
        uart_wait_tx_done(FPGA_UART, pdMS_TO_TICKS(100));
        uart_set_line_inverse(FPGA_UART, UART_SIGNAL_TXD_INV);
        vTaskDelay(pdMS_TO_TICKS(2));
        uint32_t lo0 = REG_READ(GPIO_IN_REG), lo1 = REG_READ(GPIO_IN1_REG);
        uart_set_line_inverse(FPGA_UART, UART_SIGNAL_INV_DISABLE);
        vTaskDelay(pdMS_TO_TICKS(2));
        uint32_t hi0 = REG_READ(GPIO_IN_REG), hi1 = REG_READ(GPIO_IN1_REG);
        say("avxiao: tx low: gpio_in %08x %08x (tx %u rx %u); tx high: %08x %08x (tx %u rx %u)\r\n",
            (unsigned)lo0, (unsigned)lo1, (unsigned)(lo1 >> (D6_TX - 32) & 1), (unsigned)(lo1 >> (D7_RX - 32) & 1),
            (unsigned)hi0, (unsigned)hi1, (unsigned)(hi1 >> (D6_TX - 32) & 1), (unsigned)(hi1 >> (D7_RX - 32) & 1));
    }
}

static void to_fpga(void *arg)
{
    static uint8_t buf[1024];
    unsigned match = 0;
    for (;;) {
        int n = usb_serial_jtag_read_bytes(buf, sizeof buf, portMAX_DELAY);
        if (n <= 0)
            continue;
        uart_write_bytes(FPGA_UART, buf, n);
        n_to_fpga += n;
        for (int k = 0; k < n; k++) {
            if (match == sizeof KNOCK) {
                command(buf[k]);
                match = 0;
            } else if (buf[k] == KNOCK[match])
                match++;
            else
                match = buf[k] == KNOCK[0];
        }
    }
}

static void from_fpga(void *arg)
{
    static uint8_t buf[1024];
    for (;;) {
        /* whatever is there, at once: 1 tick for the first byte, none for the rest */
        int n = uart_read_bytes(FPGA_UART, buf, 1, portMAX_DELAY);
        if (n <= 0)
            continue;
        size_t more = 0;
        uart_get_buffered_data_len(FPGA_UART, &more);
        if (more > sizeof buf - 1)
            more = sizeof buf - 1;
        if (more)
            n += uart_read_bytes(FPGA_UART, buf + 1, more, 0);
        /* no host listening: drop after 20 ms, do not stall the UART's side */
        n_from_fpga += n;
        usb_serial_jtag_write_bytes(buf, n, pdMS_TO_TICKS(20));
    }
}

void app_main(void)
{
    usb_serial_jtag_driver_config_t usb = {.tx_buffer_size = 16384, .rx_buffer_size = 65536};
    usb_serial_jtag_driver_install(&usb);
    /* (after the driver: with no console on it, startup gates the peripheral's clock and a
     * write before the driver has enabled it is lost) */
    jtag_bridge();

    const uart_config_t cfg = {.baud_rate = UART_BAUD, .data_bits = UART_DATA_8_BITS, .parity = UART_PARITY_DISABLE,
                               .stop_bits = UART_STOP_BITS_1, .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
                               .source_clk = UART_SCLK_DEFAULT};
    uart_driver_install(FPGA_UART, 16384, 16384, 0, NULL, 0);
    uart_param_config(FPGA_UART, &cfg);
    uart_set_pin(FPGA_UART, D6_TX, D7_RX, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    gpio_set_pull_mode(D7_RX, GPIO_PULLUP_ONLY);

    xTaskCreate(to_fpga, "to_fpga", 4096, NULL, 10, NULL);
    xTaskCreate(from_fpga, "from_fpga", 4096, NULL, 10, NULL);
}
