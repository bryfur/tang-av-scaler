/* A XIAO ESP32-C5 (or S3) on the AV board (rev C-A/C-B, hardware/av-board/rev-c/design.md "The
 * XIAO as programmer and console"): the FPGA loaded and debugged over Wi-Fi, no cable to a PC.
 *
 *   JTAG      D0-D3, a Xilinx Virtual Cable server on TCP 2542 (jtag.c, xvc.c):
 *             openFPGALoader -c xvc-client --ip HOST loads the FPGA or writes the SOM's flash
 *   console   the FPGA's UART (D6, D7) on TCP 2323, and on the USB serial port (console.c)
 *   web       http://avscaler.local/: status, the Wi-Fi network, firmware updates (web.c)
 *   Wi-Fi     the saved network, or its own access point to be given one (wifi.c)
 *
 * The user LED: lit on a network; one flash a second with its access point open; fast while it
 * looks for the network. */

#include "app.h"
#include "board.h"
#include "driver/gpio.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_ota_ops.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "jtag.h"
#include "nvs_flash.h"

static const char *TAG = "main";

void app_main(void)
{
    logbuf_init();
    esp_err_t e = nvs_flash_init();
    if (e == ESP_ERR_NVS_NO_FREE_PAGES || e == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }
    esp_netif_init();
    esp_event_loop_create_default();

    jtag_init();
    console_start();
    jtag_usb_bridge();
    wifi_start();
    web_start();
    xvc_start();
    scaler_start();

    /* An update is on trial until something has reached it over the network (the tool that sent
     * it asks for its status; so does the web page): then it is kept.  One that nobody can reach
     * for 3 minutes restarts, and the loader goes back to the firmware before it. */
    esp_ota_img_states_t ota = ESP_OTA_IMG_VALID;
    esp_ota_get_state_partition(esp_ota_get_running_partition(), &ota);
    bool trial = ota == ESP_OTA_IMG_PENDING_VERIFY;
    if (trial)
        ESP_LOGW(TAG, "a new firmware, on trial");

    const gpio_config_t led = {.pin_bit_mask = 1ull << PIN_LED, .mode = GPIO_MODE_OUTPUT};
    gpio_config(&led);
    for (unsigned tick = 0;; tick++) {
        struct wifi_state w;
        wifi_get(&w);
        /* tenths of a second; the LED is lit when its pad is low */
        bool lit = w.joined ? true : w.ap ? tick % 10 == 0 : tick % 2 == 0;
        gpio_set_level(PIN_LED, !lit);
        if (trial && web_reached()) {
            trial = false;
            esp_ota_mark_app_valid_cancel_rollback();
            ESP_LOGI(TAG, "reached over the network: this firmware is kept");
        } else if (trial && tick > 1800) {
            ESP_LOGE(TAG, "nobody reached this firmware: back to the one before");
            esp_restart();
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}
