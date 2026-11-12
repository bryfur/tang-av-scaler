/* Wi-Fi: the saved network; without one, or when it cannot be joined, the firmware's own access
 * point, whose web page takes a network's name and password.
 *
 *   saved network    join it; not joined 25 s later: the access point too, a try every 30 s
 *   none saved       the access point only
 *   access point     "avscaler-XXXX" (the MAC's last two bytes), WPA2 password AP_PASSWORD,
 *                    the page at http://192.168.4.1/; switched off 10 s after a network is joined
 *
 * The name and password are kept in NVS (namespace "av"); the host name too ("avscaler" unless
 * set), announced over mDNS: http://avscaler.local/. */

#include <string.h>

#include "app.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "mdns.h"
#include "nvs.h"

static const char *TAG = "wifi";
static struct wifi_state state;
static char password[65];
static bool sta_on;
static esp_netif_t *sta_netif;
static esp_timer_handle_t timer;

static void set_mode(bool sta, bool ap)
{
    esp_wifi_set_mode(sta && ap ? WIFI_MODE_APSTA : ap ? WIFI_MODE_AP : WIFI_MODE_STA);
    if (ap && !state.ap) {
        wifi_config_t c = {.ap = {.channel = 1, .max_connection = 2, .authmode = WIFI_AUTH_WPA2_PSK}};
        strlcpy((char *)c.ap.ssid, state.ap_ssid, sizeof c.ap.ssid);
        strlcpy((char *)c.ap.password, AP_PASSWORD, sizeof c.ap.password);
        esp_wifi_set_config(WIFI_IF_AP, &c);
        ESP_LOGI(TAG, "access point %s", state.ap_ssid);
    }
    state.ap = ap;
    sta_on = sta;
}

static void join(void)
{
    wifi_config_t c = {.sta = {.scan_method = WIFI_ALL_CHANNEL_SCAN, .sort_method = WIFI_CONNECT_AP_BY_SIGNAL}};
    strlcpy((char *)c.sta.ssid, state.ssid, sizeof c.sta.ssid);
    strlcpy((char *)c.sta.password, password, sizeof c.sta.password);
    esp_wifi_set_config(WIFI_IF_STA, &c);
    esp_wifi_connect();
}

/* The one timer: after a start or a new network, "not joined yet: open the access point"; with
 * the access point open, "try the network again"; after joining, "close the access point". */
static void on_timer(void *arg)
{
    if (state.joined) {
        if (state.ap) {
            ESP_LOGI(TAG, "access point off");
            set_mode(true, false);
        }
        return;
    }
    if (!state.ap)
        set_mode(true, true);
    if (state.ssid[0])
        join();
    esp_timer_start_once(timer, 30 * 1000000ull);
}

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        if (state.ssid[0])
            join();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_event_sta_disconnected_t *d = data;
        if (state.joined) {
            state.drops++;
            ESP_LOGW(TAG, "lost %s (reason %d)", state.ssid, d->reason);
            esp_timer_stop(timer);
            esp_timer_start_once(timer, 25 * 1000000ull);
        }
        state.joined = false;
        state.ip[0] = 0;
        /* with the access point open every try takes its radio off its channel: the timer paces
         * those; without it, try again at once */
        if (!state.ap && sta_on && state.ssid[0])
            esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *e = data;
        esp_ip4addr_ntoa(&e->ip_info.ip, state.ip, sizeof state.ip);
        state.joined = true;
        ESP_LOGI(TAG, "%s: %s", state.ssid, state.ip);
        esp_timer_stop(timer);
        if (state.ap)
            esp_timer_start_once(timer, 10 * 1000000ull);
    }
}

static void load(const char *key, char *dst, size_t max)
{
    nvs_handle_t h;
    dst[0] = 0;
    if (nvs_open("av", NVS_READONLY, &h) == ESP_OK) {
        size_t n = max;
        if (nvs_get_str(h, key, dst, &n) != ESP_OK)
            dst[0] = 0;
        nvs_close(h);
    }
}

static void store(const char *key, const char *value)
{
    nvs_handle_t h;
    if (nvs_open("av", NVS_READWRITE, &h) == ESP_OK) {
        nvs_set_str(h, key, value);
        nvs_commit(h);
        nvs_close(h);
    }
}

void wifi_start(void)
{
    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    snprintf(state.mac, sizeof state.mac, "%02x:%02x:%02x:%02x:%02x:%02x", mac[0], mac[1], mac[2], mac[3], mac[4],
             mac[5]);
    snprintf(state.ap_ssid, sizeof state.ap_ssid, "avscaler-%02X%02X", mac[4], mac[5]);
    load("ssid", state.ssid, sizeof state.ssid);
    load("pass", password, sizeof password);
    load("host", state.host, sizeof state.host);
    if (!state.host[0])
        strcpy(state.host, "avscaler");

    sta_netif = esp_netif_create_default_wifi_sta();
    esp_netif_create_default_wifi_ap();
    esp_netif_set_hostname(sta_netif, state.host);
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    esp_wifi_init(&cfg);
    esp_wifi_set_storage(WIFI_STORAGE_RAM);
    esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_event, NULL, NULL);
    esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_event, NULL, NULL);
    const esp_timer_create_args_t t = {.callback = on_timer, .name = "wifi"};
    esp_timer_create(&t, &timer);

    set_mode(true, !state.ssid[0]);
    esp_wifi_start();
    /* no power saving: asleep between beacons, the link answers in 40-80 ms (measured: ping), and a
     * bitstream load, hundreds of small exchanges with the FPGA waiting, fails: after the SRAM erase
     * the FPGA is back at booting from its flash before the write comes ("Timeout", 2026-11-11) */
    esp_wifi_set_ps(WIFI_PS_NONE);
    if (state.ssid[0])
        esp_timer_start_once(timer, 25 * 1000000ull);

    mdns_init();
    mdns_hostname_set(state.host);
    mdns_instance_name_set("AV scaler debug link");
    mdns_service_add(NULL, "_http", "_tcp", 80, NULL, 0);
    mdns_service_add(NULL, "_xvc", "_tcp", 2542, NULL, 0);
}

void wifi_save(const char *ssid, const char *pass)
{
    strlcpy(state.ssid, ssid, sizeof state.ssid);
    strlcpy(password, pass, sizeof password);
    store("ssid", state.ssid);
    store("pass", password);
    ESP_LOGI(TAG, "network set: %s", state.ssid);
    esp_timer_stop(timer);
    state.joined = false;
    esp_wifi_disconnect();
    join();
    esp_timer_start_once(timer, 25 * 1000000ull);
}

void wifi_set_host(const char *host)
{
    store("host", host);
}

void wifi_get(struct wifi_state *s)
{
    wifi_ap_record_t ap;
    if (state.joined && esp_wifi_sta_get_ap_info(&ap) == ESP_OK) {
        state.rssi = ap.rssi;
        state.channel = ap.primary;
    }
    *s = state;
}
