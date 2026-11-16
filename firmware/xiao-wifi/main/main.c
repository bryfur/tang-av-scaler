#include <string.h>
/* A XIAO ESP32-C5 (or S3) on the AV board (rev C-A/C-B, hardware/av-board/rev-c/design.md "The
 * XIAO as programmer and console"): the FPGA loaded and debugged over Wi-Fi, no cable to a PC.
 *
 *   JTAG      D0-D3, a Xilinx Virtual Cable server on TCP 2542 (jtag.c, xvc.c):
 *             openFPGALoader -c xvc-client --ip HOST loads the FPGA or writes the SOM's flash
 *   console   the FPGA's UART (D6, D7) on TCP 2323, and on the USB serial port (console.c)
 *   web       http://avscaler.local/: status, the Wi-Fi network, firmware updates (web.c)
 *   Wi-Fi     the saved network, or its own access point to be given one (wifi.c)
 *
 * The user LED: a short flash every three seconds while the board stands by; else lit on a network; one flash a second with its access point open; fast while it
 * looks for the network. */

#include "app.h"
#include "board.h"
#include "driver/gpio.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_attr.h"
#include "esp_heap_caps.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "jtag.h"
#include "nvs_flash.h"

static const char *TAG = "main";

RTC_NOINIT_ATTR uint32_t crumb[4];
uint32_t crumb_was[4];

/* a crash: where it was (the instruction, and on a RISC-V chip the function's return address), kept
 * with the crumbs for the firmware that starts next (which may be the one before this: an update on
 * trial that crashes is gone, and its log with it).  The linker puts this before the system's
 * handler (CMakeLists.txt: --wrap). */
#include "esp_private/panic_internal.h"
#if CONFIG_IDF_TARGET_ARCH_RISCV
#include "riscv/rvruntime-frames.h"
#endif
void __real_esp_panic_handler(panic_info_t *info);
/* (more of a crash, kept the same way: its cause and what it touched, then the first words on its
 * stack that look like places in the program: who called whom.  GET /api/load shows them) */
RTC_NOINIT_ATTR uint32_t trace[12];
uint32_t trace_was[12];
void __wrap_esp_panic_handler(panic_info_t *info)
{
    crumb[3] = (uint32_t)info->addr;
#if CONFIG_IDF_TARGET_ARCH_RISCV
    if (info->frame) {
        const RvExcFrame *f = info->frame;
        const uint32_t *sp = (const uint32_t *)f->sp;
        int n = 2;
        crumb[2] = f->ra;
        trace[0] = f->mcause;
        trace[1] = f->mtval;
        /* (the program's code: the part in RAM, and the part in flash up to its constants) */
        extern char _instruction_reserved_end[];
        for (int k = 0; k < 512 && n < 12; k++)
            if ((sp[k] >= 0x40800000u && sp[k] < 0x40819000u) || (sp[k] >= 0x42000020u && sp[k] < (uint32_t)_instruction_reserved_end))
                trace[n++] = sp[k];
        while (n < 12)
            trace[n++] = 0;
    }
#endif
    __real_esp_panic_handler(info);
}

void *big(size_t n)
{
    void *p = heap_caps_calloc(1, n, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    return p ? p : calloc(1, n);
}

void app_main(void)
{
    logbuf_init();
    if (esp_reset_reason() != ESP_RST_POWERON)
        ESP_LOGW("main", "restarted (reason %d): the tasks were at %u %u %u %u", (int)esp_reset_reason(),
                 (unsigned)crumb[0], (unsigned)crumb[1], (unsigned)crumb[2], (unsigned)crumb[3]);
    memcpy(crumb_was, crumb, sizeof crumb_was);
    memcpy(trace_was, trace, sizeof trace_was);
    memset(trace, 0, sizeof trace);
    crumb[0] = crumb[1] = crumb[2] = crumb[3] = 0;
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
    ble_start();

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
        struct scaler_state sc;
        struct scaler_settings sv;
        scaler_get(&sc, &sv);
        /* (the board standing by: a short flash every three seconds, whatever the network) */
        bool lit = sc.standby ? tick % 30 == 0 : w.joined ? true : w.ap ? tick % 10 == 0 : tick % 2 == 0;
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
