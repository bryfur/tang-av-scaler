/* Bluetooth LE: the web server's API over L2CAP, for a phone (the app) where Wi-Fi is not to hand.
 *
 * Each L2CAP channel a phone opens (LE credit-based, PSM BLE_PSM) is one TCP connection to this
 * firmware's own web server (127.0.0.1:80), its bytes passed both ways as they are: whatever the
 * page and the tools do over Wi-Fi (GET /api/video, POST /api/ota, ...) works the same over
 * Bluetooth, with no second set of handlers.  The web server closing the connection closes the
 * channel, and the other way round.
 *
 * Anyone in range may open a channel: no pairing asked for (the user's choice, 2026-11-16: a
 * passkey the board had to show somewhere was no way to pair; the network already lets anyone on it
 * at the same API).  A phone that pairs anyway (Linux does) gets LE Secure Connections, Just Works
 * (no code), the bond kept.
 *
 * NimBLE's host and its buffers are in the PSRAM (CONFIG_BT_NIMBLE_MEM_ALLOC_MODE_EXTERNAL), as are
 * the channels' buffers here: the chip's own RAM is short (app.h big()). */

#include <errno.h>
#include <string.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <fcntl.h>
#include <unistd.h>

#include "app.h"
#include "esp_log.h"
#include "esp_random.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "freertos/stream_buffer.h"
#include "freertos/idf_additions.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"
#include "host/ble_l2cap.h"
#include "host/util/util.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"

static const char *TAG = "ble";

/* The service the board advertises (the app scans for it); its one characteristic says the PSM */
#define BLE_PSM 0x0081
static const ble_uuid128_t svc_uuid =       /* 7a6e0001-5461-6e67-2041-562053636c72 ("Tang AV Scl") */
    BLE_UUID128_INIT(0x72, 0x6c, 0x63, 0x53, 0x20, 0x56, 0x41, 0x20, 0x67, 0x6e, 0x61, 0x54, 0x01, 0x00, 0x6e, 0x7a);
static const ble_uuid128_t psm_uuid =       /* 7a6e0002-... */
    BLE_UUID128_INIT(0x72, 0x6c, 0x63, 0x53, 0x20, 0x56, 0x41, 0x20, 0x67, 0x6e, 0x61, 0x54, 0x02, 0x00, 0x6e, 0x7a);

enum {
    CHANS = 4,              /* channels at once (CONFIG_BT_NIMBLE_L2CAP_COC_MAX_NUM) */
    COC_MTU = 2048,         /* the largest SDU taken from a phone */
    POOL_BLOCK = 512,
    POOL_COUNT = 48,        /* (enough for a whole SDU on every channel) */
    RXBUF = 3 * COC_MTU,    /* a channel's bytes from the phone, waiting for the socket */
};

struct chan {
    struct ble_l2cap_chan *l2;
    uint16_t conn, peer_mtu;
    int sock;
    StreamBufferHandle_t rx;        /* phone -> socket */
    bool armed;                     /* an SDU buffer given to NimBLE */
    bool stalled;                   /* our last SDU waits for credits */
    struct os_mbuf *pending;        /* an SDU NimBLE was too busy for */
    bool closing;
    bool eof;                       /* the web server is done (or a failure): close once all is sent */
    uint32_t to_web, from_web;
};

static struct chan chans[CHANS];
static SemaphoreHandle_t lock;
static struct os_mbuf_pool sdu_pool;
static struct os_mempool sdu_mempool;
static uint8_t own_addr_type;
static struct ble_state state;
static TaskHandle_t bridge;

static void advertise(void);
static int quiet;           /* ble_quiet(): advertising paused while it is above 0 */
void ble_store_config_init(void);
#define FAIL(...) do { snprintf(state.err, sizeof state.err, __VA_ARGS__); ESP_LOGE(TAG, "%s", state.err); } while (0)

/* (recursive: NimBLE may call on_l2cap from inside ble_l2cap_send, the lock held) */
#define LOCK() xSemaphoreTakeRecursive(lock, portMAX_DELAY)
#define UNLOCK() xSemaphoreGiveRecursive(lock)

/* ---- the state GET /api/status gives ---- */
void ble_get(struct ble_state *s)
{
    LOCK();
    *s = state;
    s->chans = 0;
    for (int k = 0; k < CHANS; k++)
        s->chans += chans[k].l2 != NULL;
    UNLOCK();
}

/* ---- the channels ---- */
static struct chan *find(struct ble_l2cap_chan *l2)
{
    for (int k = 0; k < CHANS; k++)
        if (chans[k].l2 == l2)
            return &chans[k];
    return NULL;
}

/* an SDU buffer to NimBLE (the phone may send one more), if the channel's buffer has room for it */
static void arm(struct chan *c)
{
    if (c->armed || !c->l2 || c->closing || xStreamBufferSpacesAvailable(c->rx) < COC_MTU)
        return;
    struct os_mbuf *m = os_mbuf_get_pkthdr(&sdu_pool, 0);
    if (!m)
        return;
    if (ble_l2cap_recv_ready(c->l2, m) == 0)
        c->armed = true;
    else
        os_mbuf_free_chain(m);
}

static int web_connect(void)
{
    int s = socket(AF_INET, SOCK_STREAM, IPPROTO_IP);
    if (s < 0)
        return -1;
    struct sockaddr_in a = {.sin_family = AF_INET, .sin_port = htons(80), .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
    if (connect(s, (struct sockaddr *)&a, sizeof a) != 0) {
        close(s);
        return -1;
    }
    int one = 1;
    setsockopt(s, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
    fcntl(s, F_SETFL, fcntl(s, F_GETFL) | O_NONBLOCK);
    return s;
}

static void chan_free(struct chan *c)
{
    if (c->sock >= 0)
        close(c->sock);
    if (c->pending)
        os_mbuf_free_chain(c->pending);
    StreamBufferHandle_t rx = c->rx;
    memset(c, 0, sizeof *c);
    c->sock = -1;
    c->rx = rx;
    xStreamBufferReset(rx);
}

static int on_l2cap(struct ble_l2cap_event *ev, void *arg)
{
    struct ble_gap_conn_desc d;
    struct chan *c;
    switch (ev->type) {
    case BLE_L2CAP_EVENT_COC_ACCEPT:
        (void)d;
        LOCK();
        c = find(NULL);
        int s = c ? web_connect() : -1;
        if (s < 0) {
            UNLOCK();
            ESP_LOGW(TAG, "a channel refused: %s", c ? "the web server does not answer" : "too many");
            return BLE_HS_ENOMEM;
        }
        c->l2 = ev->accept.chan;
        c->conn = ev->accept.conn_handle;
        c->peer_mtu = ev->accept.peer_sdu_size;
        c->sock = s;
        arm(c);
        bool ok = c->armed;
        if (!ok)
            chan_free(c);
        UNLOCK();
        return ok ? 0 : BLE_HS_ENOMEM;

    case BLE_L2CAP_EVENT_COC_CONNECTED:
        if (ev->connect.status == 0) {
            struct ble_l2cap_chan_info i;
            if (ble_l2cap_get_chan_info(ev->connect.chan, &i) == 0)
                ESP_LOGI(TAG, "channel open: SDU %u / %u, PDU %u / %u", i.our_coc_mtu, i.peer_coc_mtu,
                         i.our_l2cap_mtu, i.peer_l2cap_mtu);
            xTaskNotifyGive(bridge);
        }
        return 0;

    case BLE_L2CAP_EVENT_COC_DATA_RECEIVED:
        LOCK();
        c = find(ev->receive.chan);
        if (c) {
            c->armed = false;
            struct os_mbuf *m = ev->receive.sdu_rx;
            ESP_LOGD(TAG, "SDU in: %u bytes", (unsigned)OS_MBUF_PKTLEN(m));
            for (struct os_mbuf *p = m; p; p = SLIST_NEXT(p, om_next))
                xStreamBufferSend(c->rx, p->om_data, p->om_len, 0);
            arm(c);
        }
        os_mbuf_free_chain(ev->receive.sdu_rx);
        UNLOCK();
        xTaskNotifyGive(bridge);
        return 0;

    case BLE_L2CAP_EVENT_COC_TX_UNSTALLED:
        LOCK();
        if ((c = find(ev->tx_unstalled.chan)))
            c->stalled = false;
        UNLOCK();
        xTaskNotifyGive(bridge);
        return 0;

    case BLE_L2CAP_EVENT_COC_DISCONNECTED:
        LOCK();
        if ((c = find(ev->disconnect.chan))) {
            ESP_LOGI(TAG, "channel closed: %u bytes in, %u out%s", (unsigned)c->to_web, (unsigned)c->from_web,
                     c->closing ? "" : " (by the phone)");
            chan_free(c);
        }
        UNLOCK();
        return 0;
    }
    return 0;
}

/* The bridge: one task for every channel.  The socket's bytes go out as SDUs no larger than the
 * phone takes; the phone's go into the socket as it takes them. */
static void bridge_task(void *arg)
{
    uint8_t *buf = big(COC_MTU);
    for (;;) {
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(5));
        for (int k = 0; k < CHANS; k++) {
            struct chan *c = &chans[k];
            LOCK();
            if (!c->l2 || c->closing) {
                UNLOCK();
                continue;
            }
            bool shut = false;
            const char *why = NULL;
            int code = 0;
            /* phone -> web server */
            size_t n;
            while ((n = xStreamBufferReceive(c->rx, buf, COC_MTU, 0)) > 0) {
                size_t off = 0;
                while (off < n) {
                    int w = send(c->sock, buf + off, n - off, 0);
                    if (w > 0) {
                        off += w;
                        c->to_web += w;
                    } else if (w < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
                        UNLOCK();
                        vTaskDelay(1);
                        LOCK();
                        if (!c->l2)
                            break;
                    } else {
                        shut = true;
                        why = "send to the web server";
                        code = errno;
                        break;
                    }
                }
                if (shut || !c->l2)
                    break;
            }
            if (c->l2)
                arm(c);
            /* web server -> phone */
            if (c->l2 && !shut && c->pending && !c->stalled) {
                int rc = ble_l2cap_send(c->l2, c->pending);
                if (rc == 0 || rc == BLE_HS_ESTALLED) {
                    c->pending = NULL;
                    c->stalled = rc == BLE_HS_ESTALLED;
                } else if (rc != BLE_HS_EBUSY) {
                    shut = true;
                    why = "ble_l2cap_send (pending)";
                    code = rc;
                }
            }
            while (c->l2 && !shut && !c->eof && !c->pending && !c->stalled) {
                int r = recv(c->sock, buf, c->peer_mtu < COC_MTU ? c->peer_mtu : COC_MTU, 0);
                if (r == 0 || (r < 0 && errno != EAGAIN && errno != EWOULDBLOCK)) {
                    c->eof = true;          /* the web server closed it */
                    why = r == 0 ? "the web server closed" : "recv from the web server";
                    code = r == 0 ? 0 : errno;
                    break;
                }
                if (r < 0)
                    break;
                c->from_web += r;
                struct os_mbuf *m = os_msys_get_pkthdr(r, 0);
                if (!m || os_mbuf_append(m, buf, r) != 0) {
                    if (m)
                        os_mbuf_free_chain(m);
                    shut = true;
                    why = "no mbuf";
                    code = r;
                    break;
                }
                int rc = ble_l2cap_send(c->l2, m);
                if (rc == BLE_HS_ESTALLED)
                    c->stalled = true;
                else if (rc == BLE_HS_EBUSY)
                    c->pending = m;
                else if (rc != 0) {
                    shut = true;
                    why = "ble_l2cap_send";
                    code = rc;
                    break;
                }
            }
            if (shut)
                c->eof = true;
            if (why)
                ESP_LOGI(TAG, "channel %d: %s (%d): %u bytes in, %u out", k, why, code, (unsigned)c->to_web,
                         (unsigned)c->from_web);
            if (c->eof && c->l2 && !c->pending && !c->stalled) {
                /* (the rest sent first: the channel closed once the last SDU is out) */
                c->closing = true;
                ble_l2cap_disconnect(c->l2);
            }
            UNLOCK();
        }
    }
}

/* ---- the GATT service: its UUID is what the app scans for; the PSM is readable ---- */
static int psm_read(uint16_t conn, uint16_t attr, struct ble_gatt_access_ctxt *ctxt, void *arg)
{
    uint16_t psm = htole16(BLE_PSM);
    return os_mbuf_append(ctxt->om, &psm, sizeof psm) == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}

static const struct ble_gatt_svc_def services[] = {
    {.type = BLE_GATT_SVC_TYPE_PRIMARY, .uuid = &svc_uuid.u,
     .characteristics = (struct ble_gatt_chr_def[]){
         {.uuid = &psm_uuid.u, .access_cb = psm_read, .flags = BLE_GATT_CHR_F_READ},
         {0}}},
    {0}};

/* ---- connections, pairing ---- */
static int on_gap(struct ble_gap_event *ev, void *arg)
{
    struct ble_gap_conn_desc d;
    switch (ev->type) {
    case BLE_GAP_EVENT_CONNECT:
        if (ev->connect.status != 0) {
            advertise();
            return 0;
        }
        LOCK();
        state.connected++;
        if (ble_gap_conn_find(ev->connect.conn_handle, &d) == 0)
            snprintf(state.peer, sizeof state.peer, "%02x:%02x:%02x:%02x:%02x:%02x", d.peer_id_addr.val[5],
                     d.peer_id_addr.val[4], d.peer_id_addr.val[3], d.peer_id_addr.val[2], d.peer_id_addr.val[1],
                     d.peer_id_addr.val[0]);
        UNLOCK();
        ESP_LOGI(TAG, "connected: %s", state.peer);
        /* the channels' speed: the 2M PHY, the longest packets (Data Length Extension: 251 bytes),
         * and a connection event every 7.5 to 15 ms (the phone's own default, 30 to 50 ms, moved a
         * screen capture at 3.6 KB/s) */
        ble_gap_set_prefered_le_phy(ev->connect.conn_handle, BLE_GAP_LE_PHY_2M_MASK, BLE_GAP_LE_PHY_2M_MASK, 0);
        ble_gap_set_data_len(ev->connect.conn_handle, 251, 2120);
        {
            struct ble_gap_upd_params u = {.itvl_min = BLE_GAP_CONN_ITVL_MS(7.5), .itvl_max = BLE_GAP_CONN_ITVL_MS(15),
                                           .latency = 0, .supervision_timeout = BLE_GAP_SUPERVISION_TIMEOUT_MS(4000)};
            int rc = ble_gap_update_params(ev->connect.conn_handle, &u);
            if (rc)
                ESP_LOGW(TAG, "connection parameters: %d", rc);
        }
        advertise();        /* (a second phone may connect too) */
        return 0;

    case BLE_GAP_EVENT_DISCONNECT:
        ESP_LOGI(TAG, "disconnected (reason 0x%x)", ev->disconnect.reason);
        LOCK();
        if (state.connected)
            state.connected--;
        if (!state.connected) {
            state.encrypted = false;
            state.peer[0] = 0;
        }
        state.passkey = 0;
        UNLOCK();
        advertise();
        return 0;

    case BLE_GAP_EVENT_PASSKEY_ACTION:
        if (ev->passkey.params.action == BLE_SM_IOACT_DISP) {
            struct ble_sm_io io = {.action = BLE_SM_IOACT_DISP, .passkey = esp_random() % 1000000};
            LOCK();
            state.passkey = io.passkey ? io.passkey : 1;
            io.passkey = state.passkey;
            UNLOCK();
            ESP_LOGW(TAG, "pairing: passkey %06u", (unsigned)io.passkey);
            ble_sm_inject_io(ev->passkey.conn_handle, &io);
        }
        return 0;

    case BLE_GAP_EVENT_ENC_CHANGE:
        LOCK();
        state.passkey = 0;
        if (ev->enc_change.status == 0 && ble_gap_conn_find(ev->enc_change.conn_handle, &d) == 0) {
            state.encrypted = d.sec_state.encrypted && d.sec_state.authenticated;
            if (d.sec_state.bonded)
                state.bonded = true;
        }
        UNLOCK();
        ESP_LOGI(TAG, "encryption: %s", ev->enc_change.status == 0 ? "on" : "failed");
        return 0;

    case BLE_GAP_EVENT_REPEAT_PAIRING:
        /* a phone that lost its bond pairs again: the old one forgotten */
        if (ble_gap_conn_find(ev->repeat_pairing.conn_handle, &d) == 0)
            ble_store_util_delete_peer(&d.peer_id_addr);
        return BLE_GAP_REPEAT_PAIRING_RETRY;

    case BLE_GAP_EVENT_CONN_UPDATE:
        if (ble_gap_conn_find(ev->conn_update.conn_handle, &d) == 0)
            ESP_LOGI(TAG, "connection: every %u.%02u ms (status %d)", d.conn_itvl * 125 / 100, d.conn_itvl * 125 % 100,
                     ev->conn_update.status);
        return 0;

    case BLE_GAP_EVENT_ADV_COMPLETE:
        advertise();
        return 0;
    }
    return 0;
}

static void advertise(void)
{
    if (quiet || ble_gap_adv_active())
        return;
    struct ble_hs_adv_fields f = {0};
    f.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    f.uuids128 = (ble_uuid128_t *)&svc_uuid;
    f.num_uuids128 = 1;
    f.uuids128_is_complete = 1;
    if (ble_gap_adv_set_fields(&f) != 0)
        return;
    struct ble_hs_adv_fields r = {0};
    const char *name = ble_svc_gap_device_name();
    r.name = (uint8_t *)name;
    r.name_len = strlen(name);
    r.name_is_complete = 1;
    ble_gap_adv_rsp_set_fields(&r);
    /* every 250 ms.  (While it advertises, the radio's sharing with Wi-Fi puts the network's
     * latency up some threefold (2026-11-16, 150 pings: 35 ms median, 190 at the 99th percentile,
     * against 10 and 100), however often it advertises (500 ms and 2 s alike, one channel or
     * three) and whichever the coexistence prefers: the latency-bound work over Wi-Fi pauses it,
     * ble_quiet().  Bluetooth itself, up and not advertising, costs Wi-Fi nothing measurable.) */
    struct ble_gap_adv_params p = {.conn_mode = BLE_GAP_CONN_MODE_UND, .disc_mode = BLE_GAP_DISC_MODE_GEN,
                                   .itvl_min = BLE_GAP_ADV_ITVL_MS(250), .itvl_max = BLE_GAP_ADV_ITVL_MS(260)};
    int rc = ble_gap_adv_start(own_addr_type, NULL, BLE_HS_FOREVER, &p, on_gap, NULL);
    if (rc != 0 && rc != BLE_HS_EALREADY)
        ESP_LOGW(TAG, "advertising: %d", rc);
}

static void on_sync(void)
{
    ble_hs_util_ensure_addr(0);
    ble_hs_id_infer_auto(0, &own_addr_type);
    uint8_t a[6] = {0};
    ble_hs_id_copy_addr(own_addr_type, a, NULL);
    LOCK();
    snprintf(state.addr, sizeof state.addr, "%02x:%02x:%02x:%02x:%02x:%02x", a[5], a[4], a[3], a[2], a[1], a[0]);
    state.on = true;
    UNLOCK();
    int rc = ble_l2cap_create_server(BLE_PSM, COC_MTU, on_l2cap, NULL);
    if (rc != 0)
        FAIL("the L2CAP server: %d", rc);
    ESP_LOGI(TAG, "up: %s, PSM 0x%04x", state.addr, BLE_PSM);
    advertise();
}

static void on_reset(int reason)
{
    FAIL("host reset (%d)", reason);
}

static void host_task(void *arg)
{
    nimble_port_run();
    nimble_port_freertos_deinit();
}

/* Started once Wi-Fi is up, Wi-Fi's own buffers taken: the board stays reachable over the network
 * whatever Bluetooth finds (the chip's own RAM is short; what it took is said in state.mem). */
static void start_task(void *arg)
{
    vTaskDelay(pdMS_TO_TICKS(8000));
    unsigned before = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    for (int k = 0; k < CHANS; k++) {
        chans[k].sock = -1;
        chans[k].rx = xStreamBufferCreateWithCaps(RXBUF, 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    }
    void *mem = heap_caps_malloc(OS_MEMPOOL_BYTES(POOL_COUNT, POOL_BLOCK), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!mem || os_mempool_init(&sdu_mempool, POOL_COUNT, POOL_BLOCK, mem, "ble_sdu") != 0 ||
        os_mbuf_pool_init(&sdu_pool, &sdu_mempool, POOL_BLOCK, POOL_COUNT) != 0) {
        FAIL("no memory for the channels");
        vTaskDelete(NULL);
    }
    esp_err_t e = nimble_port_init();
    if (e != ESP_OK) {
        FAIL("nimble_port_init: %s (0x%x), %u internal free", esp_err_to_name(e), e,
             (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
        vTaskDelete(NULL);
    }
    ble_hs_cfg.reset_cb = on_reset;
    ble_hs_cfg.sync_cb = on_sync;
    ble_hs_cfg.store_status_cb = ble_store_util_status_rr;
    /* (a phone that pairs: LE Secure Connections, Just Works, the bond kept) */
    ble_hs_cfg.sm_io_cap = BLE_SM_IO_CAP_NO_IO;
    ble_hs_cfg.sm_bonding = 1;
    ble_hs_cfg.sm_mitm = 0;
    ble_hs_cfg.sm_sc = 1;
    ble_hs_cfg.sm_our_key_dist = BLE_SM_PAIR_KEY_DIST_ENC | BLE_SM_PAIR_KEY_DIST_ID;
    ble_hs_cfg.sm_their_key_dist = BLE_SM_PAIR_KEY_DIST_ENC | BLE_SM_PAIR_KEY_DIST_ID;
    ble_svc_gap_init();
    ble_svc_gatt_init();
    if (ble_gatts_count_cfg(services) != 0 || ble_gatts_add_svcs(services) != 0)
        FAIL("the GATT service");
    ble_svc_gap_device_name_set("Tang AV Scaler");
    ble_store_config_init();
    xTaskCreateWithCaps(bridge_task, "ble-bridge", 4096, NULL, 5, &bridge, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);   /* (no flash) */
    nimble_port_freertos_init(host_task);
    vTaskDelay(pdMS_TO_TICKS(2000));
    LOCK();
    snprintf(state.mem, sizeof state.mem, "%u -> %u", before, (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
    UNLOCK();
    ESP_LOGI(TAG, "the chip's own RAM: %s", state.mem);
    vTaskDelete(NULL);
}

/* Advertising paused while Wi-Fi does latency-bound work (a bitstream load, a JTAG session, a
 * firmware upload): nested, each ble_quiet(true) undone by a ble_quiet(false).  A phone already
 * connected stays connected. */
void ble_quiet(bool on)
{
    if (!lock)
        return;
    LOCK();
    quiet += on ? 1 : -1;
    if (quiet < 0)
        quiet = 0;
    int q = quiet;
    bool up = state.on;
    UNLOCK();
    if (!up)
        return;
    if (q)
        ble_gap_adv_stop();
    else
        advertise();
}

void ble_start(void)
{
    lock = xSemaphoreCreateRecursiveMutex();
    /* (its stack in the chip's own RAM, freed when it ends: starting the stack reads NVS, and while
     * the flash is busy the PSRAM cannot be reached) */
    xTaskCreate(start_task, "ble-start", 4096, NULL, 4, NULL);
}
