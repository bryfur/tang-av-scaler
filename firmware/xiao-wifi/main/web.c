/* The web server:
 *
 *   GET  /                 the page (page.html): status, the network form, the update form
 *   GET  /api/status       JSON: the firmware, Wi-Fi, the JTAG and console links, the FPGA
 *   GET  /api/fpga         JSON: the FPGA's ID code and status register, read over JTAG now
 *   GET  /api/log          the firmware's own log
 *   GET  /api/console      the last bytes the FPGA's UART sent
 *   POST /api/wifi         ssid=...&pass=...[&host=...] (a form): save and join
 *   POST /api/ota          the body is a firmware image (avwifi.bin from the build): written to the other
 *                          slot, then a restart into it
 *   POST /api/load?sum=N   the body is a bitstream (the .fs file's bits as bytes); the link loads it into
 *                          the FPGA's SRAM by itself (gowin.c) and answers with what happened
 *   GET  /api/video        JSON: the scaler as the link runs it (scaler.c): the picture in, the settings
 *   GET  /api/grab?step=N  the picture going out, read back from the FPGA: a BMP (N 1, 2, 4, 8: 4 is 480 x 270)
 *   POST /api/video        a form, any of: on, ntsc, mode, thr, aa, aa_thr, sharp, swap, top1, pattern, freeze, audio, aa_dbg,
 *                          aa_diag, aa_corner, crop (0 all, 1 found, 2 set), crop_x, crop_w, crop_y, crop_h, wide (16:9), nr (noise reduction 0 to 3),
 *                          dn (the sharpening leaves noise alone), phase (the decoder's sampling
 *                          phase, 0 to 31), osd (the on-screen text), lock (the output in step
 *                          with the input); tune=1: each phase tried on the picture as it is (a
 *                          still one), the sharpest kept;
 *                          measure=1: the picture's place found again
 *                          (numbers; 0 or 1 for the switches), again=1 (everything brought up again)
 *   POST /api/restart
 *
 * No passwords: whoever reaches the port on the local network may use it, as with the JTAG port. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "app.h"
#include "board.h"
#include "link.h"
#include "esp_app_desc.h"
#include "esp_chip_info.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "esp_ota_ops.h"
#include "esp_timer.h"
#include "gowin.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "jtag.h"
#include "soc/gpio_reg.h"
#include "soc/soc.h"

static const char *TAG = "web";
extern const char page_start[] asm("_binary_page_html_start");
extern const char page_end[] asm("_binary_page_html_end");

static bool reached;

bool web_reached(void)
{
    return reached;
}

static void restart_soon(void *arg)
{
    vTaskDelay(pdMS_TO_TICKS(800));
    esp_restart();
}

/* JSON string contents: the network's name is whatever its owner typed */
static void esc(char *dst, size_t max, const char *src)
{
    size_t n = 0;
    for (; *src && n + 7 < max; src++) {
        unsigned char c = *src;
        if (c == '"' || c == '\\')
            n += snprintf(dst + n, max - n, "\\%c", c);
        else if (c < 0x20)
            n += snprintf(dst + n, max - n, "\\u%04x", c);
        else
            dst[n++] = c;
    }
    dst[n] = 0;
}

static bool fpga_read(uint32_t *id, uint32_t *status)
{
    if (!jtag_take(false))
        return false;
    *id = jtag_gowin_read(GOWIN_IDCODE);
    *status = jtag_gowin_read(GOWIN_STATUS);
    jtag_give();
    return true;
}

static esp_err_t get_page(httpd_req_t *req)
{
    httpd_resp_set_type(req, "text/html; charset=utf-8");
    /* (TEXT data ends in a NUL the page does not want) */
    return httpd_resp_send(req, page_start, page_end - page_start - 1);
}

static esp_err_t get_status(httpd_req_t *req)
{
    static char out[1536];
    struct wifi_state w;
    struct xvc_state x;
    struct console_state c;
    char ssid[80], host[80];
    wifi_get(&w);
    xvc_get(&x);
    console_get(&c);
    esc(ssid, sizeof ssid, w.ssid);
    esc(host, sizeof host, w.host);
    const esp_app_desc_t *app = esp_app_get_description();
    const esp_partition_t *part = esp_ota_get_running_partition();
    int n = snprintf(out, sizeof out,
                     "{\"firmware\":{\"name\":\"%s\",\"version\":\"%s\",\"built\":\"%s %s\",\"idf\":\"%s\","
                     "\"chip\":\"%s\",\"slot\":\"%s\",\"uptime_s\":%llu,\"heap\":%u,\"reset\":%d},"
                     "\"wifi\":{\"joined\":%s,\"ssid\":\"%s\",\"ip\":\"%s\",\"rssi\":%d,\"channel\":%d,"
                     "\"host\":\"%s\",\"mac\":\"%s\",\"ap\":%s,\"ap_ssid\":\"%s\",\"drops\":%u},"
                     "\"jtag\":{\"port\":%d,\"connected\":%s,\"peer\":\"%s\",\"sessions\":%u,\"bits\":%llu,"
                     "\"tck_ns\":%u,\"fastest_ns\":%u},"
                     "\"console\":{\"port\":%d,\"baud\":%d,\"tcp\":%s,\"usb\":%s,\"peer\":\"%s\","
                     "\"to_fpga\":%u,\"from_fpga\":%u},"
                     "\"pads\":{\"tms\":%u,\"tck\":%u,\"tdi\":%u,\"tdo\":%u}}",
                     app->project_name, app->version, app->date, app->time, app->idf_ver, CONFIG_IDF_TARGET,
                     part ? part->label : "?", (unsigned long long)(esp_timer_get_time() / 1000000),
                     (unsigned)esp_get_free_heap_size(), (int)esp_reset_reason(),
                     w.joined ? "true" : "false", ssid, w.ip, w.rssi, w.channel, host, w.mac, w.ap ? "true" : "false",
                     w.ap_ssid, (unsigned)w.drops,
                     PORT_XVC, x.connected ? "true" : "false", x.peer, (unsigned)x.sessions, (unsigned long long)x.bits,
                     (unsigned)jtag_period(), (unsigned)jtag_fastest(),
                     PORT_CONSOLE, UART_BAUD, c.tcp ? "true" : "false", c.usb ? "true" : "false", c.peer,
                     (unsigned)c.to_fpga, (unsigned)c.from_fpga,
                     (unsigned)(REG_READ(GPIO_IN_REG) >> PIN_TMS & 1), (unsigned)(REG_READ(GPIO_IN_REG) >> PIN_TCK & 1),
                     (unsigned)(REG_READ(GPIO_IN_REG) >> PIN_TDI & 1), (unsigned)(REG_READ(GPIO_IN_REG) >> PIN_TDO & 1));
    httpd_resp_set_type(req, "application/json");
    esp_err_t e = httpd_resp_send(req, out, n);
    if (e == ESP_OK)
        reached = true;
    return e;
}

static esp_err_t get_fpga(httpd_req_t *req)
{
    char out[160];
    uint32_t id, status;
    int n;
    if (fpga_read(&id, &status))
        /* all ones or all zeros: nothing answers (no SOM, no power, a JTAG line open) */
        n = snprintf(out, sizeof out, "{\"busy\":false,\"idcode\":\"0x%08x\",\"status\":\"0x%08x\",\"answers\":%s}",
                     (unsigned)id, (unsigned)status, id != 0 && id != 0xFFFFFFFF ? "true" : "false");
    else
        n = snprintf(out, sizeof out, "{\"busy\":true}");
    httpd_resp_set_type(req, "application/json");
    return httpd_resp_send(req, out, n);
}

static esp_err_t get_text(httpd_req_t *req)
{
    size_t max = 16384;
    char *buf = malloc(max);
    if (!buf)
        return httpd_resp_send_500(req);
    size_t n = req->user_ctx ? console_tail(buf, max) : logbuf_copy(buf, max);
    httpd_resp_set_type(req, "text/plain; charset=utf-8");
    esp_err_t e = httpd_resp_send(req, buf, n);
    free(buf);
    return e;
}

static int hexval(int c)
{
    return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
}

/* one field of a form body, decoded; false if it is not there */
static bool field(const char *body, const char *name, char *dst, size_t max)
{
    size_t len = strlen(name);
    for (const char *p = body; p; p = strchr(p, '&'), p = p ? p + 1 : NULL) {
        if (strncmp(p, name, len) || p[len] != '=')
            continue;
        size_t n = 0;
        for (p += len + 1; *p && *p != '&' && n + 1 < max; p++) {
            if (*p == '+')
                dst[n++] = ' ';
            else if (*p == '%' && hexval(p[1]) >= 0 && hexval(p[2]) >= 0) {
                dst[n++] = hexval(p[1]) << 4 | hexval(p[2]);
                p += 2;
            } else
                dst[n++] = *p;
        }
        dst[n] = 0;
        return true;
    }
    return false;
}

static esp_err_t post_wifi(httpd_req_t *req)
{
    char body[400], ssid[33], pass[65], host[33];
    if (req->content_len == 0 || req->content_len >= sizeof body)
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "a form: ssid=...&pass=...");
    size_t got = 0;
    while (got < req->content_len) {
        int r = httpd_req_recv(req, body + got, req->content_len - got);
        if (r <= 0)
            return ESP_FAIL;
        got += r;
    }
    body[got] = 0;
    if (field(body, "host", host, sizeof host) && host[0])
        wifi_set_host(host);
    if (!field(body, "ssid", ssid, sizeof ssid) || !ssid[0])
        return httpd_resp_sendstr(req, "host name saved (used from the next start)\n");
    if (!field(body, "pass", pass, sizeof pass))
        pass[0] = 0;
    httpd_resp_sendstr(req, "saved: joining it now. This page is at http://avscaler.local/ on that network; "
                            "if the network cannot be joined the access point comes back in half a minute.\n");
    wifi_save(ssid, pass);
    return ESP_OK;
}

static esp_err_t post_ota(httpd_req_t *req)
{
    const esp_partition_t *part = esp_ota_get_next_update_partition(NULL);
    esp_ota_handle_t h;
    char msg[96];
    if (!part || req->content_len < 1024 || req->content_len > part->size)
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "the body: a firmware image that fits the slot");
    if (esp_ota_begin(part, OTA_SIZE_UNKNOWN, &h) != ESP_OK)
        return httpd_resp_send_500(req);
    char *buf = malloc(4096);
    size_t left = req->content_len;
    esp_err_t e = buf ? ESP_OK : ESP_ERR_NO_MEM;
    while (e == ESP_OK && left) {
        int r = httpd_req_recv(req, buf, left < 4096 ? left : 4096);
        if (r == HTTPD_SOCK_ERR_TIMEOUT)
            continue;
        if (r <= 0) {
            e = ESP_FAIL;
            break;
        }
        e = esp_ota_write(h, buf, r);
        left -= r;
    }
    free(buf);
    if (e != ESP_OK) {
        esp_ota_abort(h);
        return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "the upload broke off: nothing changed");
    }
    /* (checks the image: its magic, its chip, its checksum and hash) */
    e = esp_ota_end(h);
    if (e == ESP_OK)
        e = esp_ota_set_boot_partition(part);
    if (e != ESP_OK) {
        snprintf(msg, sizeof msg, "not a firmware image for this chip (%s): nothing changed", esp_err_to_name(e));
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, msg);
    }
    ESP_LOGI(TAG, "update: %u bytes in %s, restarting", (unsigned)req->content_len, part->label);
    snprintf(msg, sizeof msg, "written to %s (%u bytes): restarting into it\n", part->label, (unsigned)req->content_len);
    httpd_resp_sendstr(req, msg);
    xTaskCreate(restart_soon, "restart", 2048, NULL, 5, NULL);
    return ESP_OK;
}

/* A load runs in its own task (it may take the CPU from Wi-Fi for its length: gowin.c hold); the
 * request is answered at once and GET /api/load tells how it went: its number, then the report. */
static struct {
    uint8_t *data;
    size_t len;
    unsigned sum, id;
    struct gowin_opt opt;
    bool running;
    char msg[700];
} load = {.msg = "0 no load yet\n"};

static void load_task(void *arg)
{
    char *m = load.msg + snprintf(load.msg, sizeof load.msg, "%u running\n", load.id);
    int64_t t0 = esp_timer_get_time();
    char msg[600];
    bool ok = gowin_load(load.data, load.len, load.sum, &load.opt, msg, sizeof msg);
    jtag_give();
    free(load.data);
    (void)m;
    snprintf(load.msg, sizeof load.msg, "%u done\n%s%u bytes, %u ms\n", load.id, msg, (unsigned)load.len,
             (unsigned)((esp_timer_get_time() - t0) / 1000));
    ESP_LOGI(TAG, "load %u: %u bytes: %s", load.id, (unsigned)load.len, ok ? "loaded" : "not loaded");
    load.running = false;
    vTaskDelete(NULL);
}

static esp_err_t get_load(httpd_req_t *req)
{
    httpd_resp_set_type(req, "text/plain");
    return httpd_resp_sendstr(req, load.msg);
}

static esp_err_t post_load(httpd_req_t *req)
{
    char q[120], v[16], msg[64];
    unsigned sum = 0;
    struct gowin_opt o = {.gap_ms = 0, .stop_ms = 30, .pre_ms = 0, .spi_hz = 0, .reverse = true, .hold = false};
    if (httpd_req_get_url_query_str(req, q, sizeof q) == ESP_OK) {
        if (httpd_query_key_value(q, "sum", v, sizeof v) == ESP_OK)
            sum = strtoul(v, NULL, 0);
        if (httpd_query_key_value(q, "gap", v, sizeof v) == ESP_OK)
            o.gap_ms = strtoul(v, NULL, 0);
        if (httpd_query_key_value(q, "stop", v, sizeof v) == ESP_OK)
            o.stop_ms = strtoul(v, NULL, 0);
        if (httpd_query_key_value(q, "pre", v, sizeof v) == ESP_OK)
            o.pre_ms = strtoul(v, NULL, 0);
        if (httpd_query_key_value(q, "rev", v, sizeof v) == ESP_OK)
            o.reverse = strtoul(v, NULL, 0);
        if (httpd_query_key_value(q, "hold", v, sizeof v) == ESP_OK)
            o.hold = strtoul(v, NULL, 0);
        if (httpd_query_key_value(q, "spi", v, sizeof v) == ESP_OK)
            o.spi_hz = strtoul(v, NULL, 0);
    }
    if (load.running)
        return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "a load is running");
    if (req->content_len < 1024 || req->content_len > 6 * 1024 * 1024)
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "the body: a bitstream");
    uint8_t *data = heap_caps_malloc(req->content_len, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!data)
        data = malloc(req->content_len);
    if (!data)
        return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "no memory for the bitstream");
    size_t got = 0;
    while (got < req->content_len) {
        int r = httpd_req_recv(req, (char *)data + got, req->content_len - got);
        if (r == HTTPD_SOCK_ERR_TIMEOUT)
            continue;
        if (r <= 0)
            break;
        got += r;
    }
    if (got != req->content_len) {
        free(data);
        return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "the upload broke off: the FPGA was not touched");
    }
    if (!jtag_take(false)) {
        free(data);
        return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "the JTAG port is in use by a client");
    }
    load.data = data;
    load.len = got;
    load.sum = sum;
    load.opt = o;
    load.id++;
    load.running = true;
    snprintf(msg, sizeof msg, "%u started\n", load.id);
    httpd_resp_sendstr(req, msg);
    vTaskDelay(pdMS_TO_TICKS(300));             /* the answer out before the task takes the CPU */
    if (xTaskCreate(load_task, "load", 8192, NULL, 5, NULL) != pdPASS) {
        load.running = false;
        jtag_give();
        free(data);
        snprintf(load.msg, sizeof load.msg, "%u done\nno task for the load\nNOT loaded\n", load.id);
    }
    return ESP_OK;
}

/* GET /api/grab?step=N: the picture as the FPGA sends it (gateware/rtl/grab.v: eight rows a frame,
 * read back through the monitor), every Nth row and column (N 1, 2, 4 or 8: 4 is 480 x 270, in
 * some seven seconds), a BMP.  The fields are held still meanwhile: the rows are of several frames. */
static bool mon_rd(uint8_t addr, uint32_t *v)
{
    uint8_t tx[2] = {'R', addr}, rx[4];
    bool ok = console_xfer(tx, 2, rx, 4, 400);
    *v = ok ? rx[0] | rx[1] << 8 | rx[2] << 16 | (uint32_t)rx[3] << 24 : 0;
    return ok;
}

static void mon_wr(uint8_t addr, uint32_t v)
{
    uint8_t tx[6] = {'W', addr, v, v >> 8, v >> 16, v >> 24};
    console_xfer(tx, 6, NULL, 0, 0);
}

static esp_err_t get_grab(httpd_req_t *req)
{
    enum { VID = 0x30, GRAB = 0x38, GRABD = 0x39, N = 480 };
    static uint8_t tx[2 * N], rx[4 * N], line[3 * 1920];
    char q[32], f[8];
    int step = 4;
    if (httpd_req_get_url_query_str(req, q, sizeof q) == ESP_OK && httpd_query_key_value(q, "step", f, sizeof f) == ESP_OK)
        step = atoi(f);
    if (step != 1 && step != 2 && step != 4 && step != 8)
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "step=1, 2, 4 or 8");
    struct scaler_state t;
    struct scaler_settings v;
    uint32_t vid, x;
    scaler_get(&t, &v);
    if (scaler_cpu()) {
        /* the FPGA's CPU reads it out (gateware/sw/main.c), a row a message: some 3 s for 480 x 270 */
        int w = 1920 / step, h = 1080 / step;
        uint32_t size = 54 + 3u * w * h;
        uint8_t hd[54] = {'B', 'M', size, size >> 8, size >> 16, size >> 24, 0, 0, 0, 0, 54, 0, 0, 0, 40, 0, 0, 0,
                          w, w >> 8, 0, 0, -h, -h >> 8, 0xFF, 0xFF, 1, 0, 24, 0};
        uint8_t rq[8] = {LINK_CMD, LINK_CMD_GRAB_BEGIN}, a[4];
        bool ok = link_msg(rq, 2, a, sizeof a, 1000) >= 1;
        httpd_resp_set_type(req, "image/bmp");
        httpd_resp_set_hdr(req, "Cache-Control", "no-store");
        httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=\"avscaler.bmp\"");
        esp_err_t e = httpd_resp_send_chunk(req, (const char *)hd, sizeof hd);
        for (int y = 0; y < h && e == ESP_OK; y++) {
            for (int x0 = 0; x0 < w; x0 += 600) {
                int n = w - x0 < 600 ? w - x0 : 600;
                rq[0] = LINK_GRAB, rq[1] = step, rq[2] = y, rq[3] = y >> 8, rq[4] = x0, rq[5] = x0 >> 8, rq[6] = n, rq[7] = n >> 8;
                /* (the answer's first byte, then the pixels: into the line a byte early, the byte before kept) */
                uint8_t keep = x0 ? line[3 * x0 - 1] : 0;
                if (link_msg(rq, 8, x0 ? line + 3 * x0 - 1 : rx, 1 + 3 * n, 500) != 1 + 3 * n) {
                    memset(line + 3 * x0, 0, 3 * n);
                    ok = false;
                } else if (!x0)
                    memcpy(line, rx + 1, 3 * n);
                if (x0)
                    line[3 * x0 - 1] = keep;
            }
            e = httpd_resp_send_chunk(req, (const char *)line, 3 * w);
        }
        rq[0] = LINK_CMD, rq[1] = LINK_CMD_GRAB_END;
        link_msg(rq, 2, a, sizeof a, 500);
        if (!ok)
            ESP_LOGW("web", "grab: the CPU did not answer all of it");
        return e == ESP_OK ? httpd_resp_send_chunk(req, NULL, 0) : e;
    }
    if (t.host || !t.fpga || !mon_rd(VID, &vid)) {
        httpd_resp_set_status(req, "503 Service Unavailable");
        return httpd_resp_sendstr(req, "the FPGA is not the link's to ask\n");
    }
    int w = 1920 / step, h = 1080 / step;
    uint32_t size = 54 + 3u * w * h;
    uint8_t hd[54] = {'B', 'M', size, size >> 8, size >> 16, size >> 24, 0, 0, 0, 0, 54, 0, 0, 0, 40, 0, 0, 0,
                      w, w >> 8, 0, 0, -h, -h >> 8, 0xFF, 0xFF, 1, 0, 24, 0};     /* (the rows from the top) */
    httpd_resp_set_type(req, "image/bmp");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=\"avscaler.bmp\"");
    esp_err_t e = httpd_resp_send_chunk(req, (const char *)hd, sizeof hd);
    for (int k = 0; k < N; k++)
        tx[2 * k] = 'R', tx[2 * k + 1] = GRABD;
    mon_wr(VID, vid | 2);
    vTaskDelay(pdMS_TO_TICKS(150));
    bool ok = true;
    for (int y = 0; y < h && e == ESP_OK; ) {
        mon_wr(GRAB, (uint32_t)step << 12 | (y * step));
        x = 0;
        for (int n = 0; n < 60 && !(x >> 31); n++) {
            vTaskDelay(pdMS_TO_TICKS(10));
            mon_rd(GRAB, &x);
        }
        ok &= x >> 31;
        for (int k = 0; k < 8 && y < h && e == ESP_OK; k++, y++) {
            mon_wr(GRABD, (uint32_t)k << 11);
            for (int i = 0; i < w; i += N) {
                int n = w - i < N ? w - i : N;
                if (!console_xfer(tx, 2 * n, rx, 4 * n, 1000)) {
                    memset(rx, 0, 4 * n);
                    ok = false;
                }
                for (int p = 0; p < n; p++)
                    memcpy(line + 3 * (i + p), rx + 4 * p, 3);      /* (blue, green, red: as a BMP has them) */
            }
            e = httpd_resp_send_chunk(req, (const char *)line, 3 * w);
        }
    }
    mon_wr(VID, vid);
    if (!ok)
        ESP_LOGW("web", "grab: the FPGA did not answer all of it");
    return e == ESP_OK ? httpd_resp_send_chunk(req, NULL, 0) : e;
}

static esp_err_t get_video(httpd_req_t *req)
{
    static char out[1500];
    struct scaler_state t;
    struct scaler_settings v;
    scaler_get(&t, &v);
#define B(x) ((x) ? "true" : "false")
    int n = snprintf(out, sizeof out,
                     "{\"host\":%s,\"fpga\":%s,\"ok\":%s,\"hpd\":%s,\"pll\":%s,\"hist\":%s,\"build\":%u,\"ups\":%u,"
                     "\"pix\":%u,\"lines\":%u,\"fields_s\":%u,\"frames_s\":%u,\"llc_khz\":%u,"
                     "\"set\":{\"on\":%d,\"ntsc\":%d,\"mode\":%u,\"thr\":%u,\"aa\":%d,\"aa_thr\":%u,\"sharp\":%u,\"swap\":%d,"
                     "\"top1\":%d,\"pattern\":%d,\"freeze\":%d,\"audio\":%d,\"aa_dbg\":%d,\"aa_diag\":%d,\"aa_corner\":%d,\"crop\":%u,"
                     "\"crop_x\":%u,\"crop_w\":%u,\"crop_y\":%u,\"crop_h\":%u,\"wide\":%d,\"nr\":%u,\"dn\":%d,\"phase\":%u,\"osd\":%d,\"lock\":%d,\"lowlat\":%d},\"ll\":%s,\"ll_lines\":%u,\"lock\":%u,\"lock_us\":%d,\"lock_ppm\":%.1f,\"tune\":%u,\"tune_gain\":%u,\"temp_c\":%.2f,\"delay_ms\":%.2f,\"cpu\":%s,\"relay\":%s,\"cpu_build\":%u,\"shown\":[%u,%u,%u,%u]}",
                     B(t.host), B(t.fpga), B(t.ok), B(t.hpd), B(t.pll), B(t.hist), (unsigned)t.build, (unsigned)t.ups,
                     t.pix, t.lines, t.fields_s, t.frames_s, (unsigned)t.llc_khz, v.on, v.ntsc, v.mode, v.thr, v.aa,
                     v.aa_thr, v.sharp, v.swap, v.top1, v.pattern, v.freeze, v.audio, v.aa_dbg, v.aa_diag, v.aa_corner, v.crop, v.crop_x, v.crop_w, v.crop_y,
                     v.crop_h, v.wide, v.nr, v.dn, v.phase, v.osd, !v.nolock, v.lowlat, t.ll ? "true" : "false", t.ll_lines, t.lock, t.lock_err * 10, t.lock_ppm10 / 10.0, t.tune, t.tune_gain, t.temp4 / 4.0, t.delay_us10 / 100.0, t.cpu ? "true" : "false", t.relay ? "true" : "false", (unsigned)t.cpu_build, t.show_x, t.show_w, t.show_y, t.show_h);
#undef B
    httpd_resp_set_type(req, "application/json");
    return httpd_resp_send(req, out, n);
}

static esp_err_t post_video(httpd_req_t *req)
{
    char body[300], f[12];
    struct scaler_state t;
    struct scaler_settings v;
    if (req->content_len == 0 || req->content_len >= sizeof body)
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "a form: mode=0&aa=1&...");
    size_t got = 0;
    while (got < req->content_len) {
        int r = httpd_req_recv(req, body + got, req->content_len - got);
        if (r <= 0)
            return ESP_FAIL;
        got += r;
    }
    body[got] = 0;
    scaler_get(&t, &v);
#define NUM(name, dst, max) if (field(body, name, f, sizeof f)) { int x = atoi(f); dst = x < 0 ? 0 : x > (max) ? (max) : x; }
    NUM("on", v.on, 1)
    NUM("ntsc", v.ntsc, 1)
    NUM("mode", v.mode, 2)
    NUM("thr", v.thr, 255)
    NUM("aa", v.aa, 1)
    NUM("aa_thr", v.aa_thr, 255)
    NUM("sharp", v.sharp, 16)
    NUM("swap", v.swap, 1)
    NUM("top1", v.top1, 1)
    NUM("pattern", v.pattern, 1)
    NUM("freeze", v.freeze, 1)
    NUM("audio", v.audio, 1)
    NUM("aa_dbg", v.aa_dbg, 1)
    NUM("aa_diag", v.aa_diag, 1)
    NUM("aa_corner", v.aa_corner, 1)
    NUM("crop", v.crop, 2)
    NUM("crop_x", v.crop_x, 719)
    NUM("crop_w", v.crop_w, 720)
    NUM("crop_y", v.crop_y, 479)
    NUM("crop_h", v.crop_h, 480)
    NUM("wide", v.wide, 1)
    NUM("nr", v.nr, 3)
    NUM("dn", v.dn, 1)
    NUM("phase", v.phase, 31)
    NUM("osd", v.osd, 1)
    NUM("lowlat", v.lowlat, 1)
    if (field(body, "lock", f, sizeof f))
        v.nolock = !atoi(f);
#undef NUM
    scaler_set(&v);
    if (field(body, "tune", f, sizeof f) && atoi(f))
        scaler_tune();
    if (field(body, "measure", f, sizeof f) && atoi(f))
        scaler_measure();
    if (field(body, "again", f, sizeof f) && atoi(f))
        scaler_again();
    return httpd_resp_sendstr(req, "set\n");
}

static esp_err_t post_restart(httpd_req_t *req)
{
    httpd_resp_sendstr(req, "restarting\n");
    xTaskCreate(restart_soon, "restart", 2048, NULL, 5, NULL);
    return ESP_OK;
}

void web_start(void)
{
    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    cfg.stack_size = 8192;
    cfg.max_uri_handlers = 16;
    /* (a browser keeps several connections open, and there are few to have: with all of them taken
     * nothing more is answered, so the one used longest ago makes way) */
    cfg.lru_purge_enable = true;
    cfg.lru_purge_enable = true;
    cfg.recv_wait_timeout = 10;
    httpd_handle_t srv;
    if (httpd_start(&srv, &cfg) != ESP_OK) {
        ESP_LOGE(TAG, "no web server");
        return;
    }
    static const httpd_uri_t uris[] = {
        {.uri = "/", .method = HTTP_GET, .handler = get_page},
        {.uri = "/api/status", .method = HTTP_GET, .handler = get_status},
        {.uri = "/api/fpga", .method = HTTP_GET, .handler = get_fpga},
        {.uri = "/api/log", .method = HTTP_GET, .handler = get_text},
        {.uri = "/api/console", .method = HTTP_GET, .handler = get_text, .user_ctx = (void *)1},
        {.uri = "/api/wifi", .method = HTTP_POST, .handler = post_wifi},
        {.uri = "/api/ota", .method = HTTP_POST, .handler = post_ota},
        {.uri = "/api/load", .method = HTTP_POST, .handler = post_load},
        {.uri = "/api/load", .method = HTTP_GET, .handler = get_load},
        {.uri = "/api/restart", .method = HTTP_POST, .handler = post_restart},
        {.uri = "/api/video", .method = HTTP_GET, .handler = get_video},
        {.uri = "/api/grab", .method = HTTP_GET, .handler = get_grab},
        {.uri = "/api/video", .method = HTTP_POST, .handler = post_video},
    };
    for (size_t k = 0; k < sizeof uris / sizeof uris[0]; k++)
        httpd_register_uri_handler(srv, &uris[k]);
}
