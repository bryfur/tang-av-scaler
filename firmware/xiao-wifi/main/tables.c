/* tables.c: the scaler's tables (gateware/sw/table.c: the FPGA's CPU keeps them in its memory, in
 * slots, and puts the one the settings ask for into the scaler).  The board keeps what it is given
 * in its own flash (gateware/sw/store.c) and has it again at each start, link or no link; the link
 * holds the ones below and gives the board those it lacks or keeps another of:
 *   slot 0      the design's own (FSR's): the CPU has it from the design
 *   slots 1, 2  the pair the setting 1 chooses between by the anti-aliasing, off and on: two tables
 *               learnt from games' pictures (gateware/tables), part of this firmware
 *   slots 3-7   tables sent to the link (POST /api/table): kept in the flash's free end
 * A table: gateware/tables/README.md: 8192 entries of four words, 131072 bytes.
 */
#include <string.h>
#include "esp_attr.h"
#include "esp_flash.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

#include "app.h"
#include "link.h"

static const char *TAG = "tables";

extern const uint8_t plain_start[] asm("_binary_learnt_11games_tab_start");
extern const uint8_t aa12_start[] asm("_binary_learnt_11games_aa12_tab_start");

/* the flash after the two application slots (partitions.csv): a slot's table each TAB_STEP: a head
 * in the first sector, the words from the second */
#define STORE_AT    0x620000u
#define STORE_STEP  0x40000u
#define STORE_MAGIC 0x32424154u         /* "TAB2" */
#define BYTES       (4u * LINK_TABLE_WORDS)
#define CHUNK       4096u               /* a part of a table in hand */
struct stored {
    uint32_t magic, sum;
    char name[TABLE_NAME];
};

static SemaphoreHandle_t lock;
static struct stored kept[LINK_TABLES];         /* (3 on: what the flash holds) */
static bool resend[LINK_TABLES];                /* the CPU's copy is not ours: again */
static bool check[LINK_TABLES];                 /* the board's kept copy to be compared with ours */
static bool dropped[LINK_TABLES];               /* emptied here: to be emptied in the board */
static char theirs[LINK_TABLES + 1][TABLE_NAME];/* the names of what the board keeps and we do not (8: the network's weights) */
static uint8_t asked;                           /* (the slots whose name has been asked for) */
static uint8_t net_was = 255;
static uint32_t sums[3];

static uint32_t flash_at(int slot)
{
    return STORE_AT + (uint32_t)(slot - 3) * STORE_STEP;
}

static bool held(int slot)
{
    return slot == 1 || slot == 2 || (slot >= 3 && slot < LINK_TABLES && kept[slot].magic == STORE_MAGIC);
}

static uint32_t sum_bytes(uint32_t h, const uint8_t *d, size_t n)
{
    for (size_t k = 0; k + 3 < n; k += 4)
        h = link_table_sum(h, d[k] | (uint32_t)d[k + 1] << 8 | (uint32_t)d[k + 2] << 16 | (uint32_t)d[k + 3] << 24);
    return h;
}

void tables_start(void)
{
    lock = xSemaphoreCreateMutex();
    sums[1] = sum_bytes(LINK_TABLE_SUM0, plain_start, BYTES);
    sums[2] = sum_bytes(LINK_TABLE_SUM0, aa12_start, BYTES);
    for (int s = 3; s < LINK_TABLES; s++) {
        if (esp_flash_read(NULL, &kept[s], flash_at(s), sizeof kept[s]) != ESP_OK || kept[s].magic != STORE_MAGIC)
            memset(&kept[s], 0, sizeof kept[s]);
        kept[s].name[TABLE_NAME - 1] = 0;
        if (held(s))
            ESP_LOGI(TAG, "slot %d: \"%s\"", s, kept[s].name);
    }
    /* (the board may keep tables from a firmware before this one: each of ours is compared with its) */
    for (int s = 1; s < LINK_TABLES; s++)
        check[s] = held(s);
}

/* what the board's flash holds of a slot (8: the network's weights): kept, its sum, its name */
static bool about(int what, uint32_t *sum, char *name)
{
    uint8_t rq[2] = {LINK_STORE, what}, a[1 + 5 + LINK_NAME + 2];
    if (link_msg(rq, 2, a, sizeof a, 300) != 1 + 5 + LINK_NAME || a[0] != (LINK_STORE | 0x80))
        return false;
    memcpy(sum, a + 2, 4);
    memcpy(name, a + 6, TABLE_NAME);
    name[TABLE_NAME - 1] = 0;
    return a[1] != 0;
}

void tables_net_name(char *name)
{
    xSemaphoreTake(lock, portMAX_DELAY);
    strcpy(name, theirs[LINK_TABLES]);
    xSemaphoreGive(lock);
}

void tables_name(int slot, char *name)
{
    name[0] = 0;
    if (slot == 0)
        strcpy(name, "FSR");
    else if (slot == 1)
        strcpy(name, "learnt-11games");
    else if (slot == 2)
        strcpy(name, "learnt-11games-aa12");
    else if (slot < LINK_TABLES) {
        xSemaphoreTake(lock, portMAX_DELAY);
        if (held(slot))
            strcpy(name, kept[slot].name[0] ? kept[slot].name : "table");
        else                            /* (one the board keeps and we do not) */
            strcpy(name, theirs[slot]);
        xSemaphoreGive(lock);
    }
}

/* a slot's table to the CPU: its parts, then its sum */
static bool give(int slot)
{
    static uint8_t *buf;
    if (!buf)
        buf = big(CHUNK);
    uint8_t rq[4 + 4 * 62], a[4];
    uint32_t sum = slot < 3 ? sums[slot] : kept[slot].sum;
    for (uint32_t at = 0; at < BYTES; at += CHUNK) {
        const uint8_t *d = slot == 1 ? plain_start + at : slot == 2 ? aa12_start + at : buf;
        if (slot >= 3 && esp_flash_read(NULL, buf, flash_at(slot) + 4096 + at, CHUNK) != ESP_OK)
            return false;
        for (uint32_t k = 0; k < CHUNK; k += 4 * 62) {
            uint32_t n = CHUNK - k < 4 * 62 ? CHUNK - k : 4 * 62, w = (at + k) / 4;
            rq[0] = LINK_TABLE;
            rq[1] = slot;
            rq[2] = w;
            rq[3] = w >> 8;
            memcpy(rq + 4, d + k, n);
            if (link_msg(rq, 4 + n, a, sizeof a, 300) != 2 || a[0] != (LINK_TABLE | 0x80) || !a[1])
                return false;
        }
    }
    char nm[TABLE_NAME];
    tables_name(slot, nm);
    rq[0] = LINK_TABLE_END;
    rq[1] = slot;
    memcpy(rq + 2, &sum, 4);
    memcpy(rq + 6, nm, strlen(nm));      /* (the board keeps it under this name) */
    return link_msg(rq, 6 + strlen(nm), a, sizeof a, 1000) == 2 && a[0] == (LINK_TABLE_END | 0x80) && a[1];
}

/* (the slot emptied in the CPU's memory) */
static bool take_away(int slot)
{
    uint8_t rq[4] = {LINK_TABLE, slot, 0, 0}, a[4];
    return link_msg(rq, 4, a, sizeof a, 300) == 2 && a[0] == (LINK_TABLE | 0x80) && a[1];
}

/* each second, the CPU's status in hand: a table it lacks (or has an old one of) given, one a time */
void tables_second(uint8_t have, uint8_t tab_state, bool cpu_new, uint8_t net_state)
{
    char nm[TABLE_NAME];
    uint32_t sum;
    if (cpu_new) {                      /* (a CPU that has just begun: what it keeps looked at again) */
        asked = 0;
        net_was = 255;
        for (int s = 1; s < LINK_TABLES; s++)
            check[s] = held(s);
    }
    /* the name of the weights the board keeps */
    if (net_state != net_was) {
        bool k = about(8, &sum, nm);
        xSemaphoreTake(lock, portMAX_DELAY);
        strcpy(theirs[LINK_TABLES], k ? (nm[0] ? nm : "weights") : "");
        xSemaphoreGive(lock);
        net_was = net_state;
    }
    if (tab_state == LINK_TAB_NONE)
        return;
    for (int s = 1; s < LINK_TABLES; s++) {
        bool mine, again;
        xSemaphoreTake(lock, portMAX_DELAY);
        mine = held(s);
        again = resend[s];
        resend[s] = false;
        xSemaphoreGive(lock);
        /* (ours against the one the board keeps: given again only if it keeps none or another) */
        if (mine && check[s] && !again) {
            check[s] = false;
            if (!about(s, &sum, nm) || sum != (s < 3 ? sums[s] : kept[s].sum))
                again = true;
        }
        /* (one the board has and we do not: its name, for the page) */
        if (!mine && have >> s & 1 && !(asked >> s & 1)) {
            bool k = about(s, &sum, nm);
            asked |= 1u << s;
            xSemaphoreTake(lock, portMAX_DELAY);
            strcpy(theirs[s], k && nm[0] ? nm : "table");
            xSemaphoreGive(lock);
        }
        if (!(have >> s & 1) && theirs[s][0]) {
            xSemaphoreTake(lock, portMAX_DELAY);
            theirs[s][0] = 0;
            xSemaphoreGive(lock);
            asked &= ~(1u << s);
        }
        if (mine && (again || !(have >> s & 1))) {
            int64_t t0 = esp_timer_get_time();
            bool ok = give(s);
            ESP_LOGI(TAG, "slot %d to the CPU: %s (%d ms)", s, ok ? "given" : "NOT taken", (int)((esp_timer_get_time() - t0) / 1000));
            if (!ok && again)
                resend[s] = true;
            return;
        }
        /* (emptied here: emptied in the board.  One the board keeps and we never had is left alone:
         * the board's tables are its own) */
        if (!mine && dropped[s]) {
            dropped[s] = false;
            ESP_LOGI(TAG, "slot %d: %s", s, take_away(s) ? "emptied in the board" : "the board did not empty it");
            return;
        }
    }
}

/* a table for a slot (3 on), its bytes as more() brings them; NULL: done, else what went wrong */
const char *tables_store(int slot, const char *name, int (*more)(void *ctx, uint8_t *buf, size_t n), void *ctx)
{
    static uint8_t *buf;
    if (!buf)
        buf = big(CHUNK);
    struct stored h = {.magic = STORE_MAGIC, .sum = LINK_TABLE_SUM0};
    const char *err = NULL;
    if (slot < 3 || slot >= LINK_TABLES)
        return "the slot: 3 to 7";
    strncpy(h.name, name, TABLE_NAME - 1);
    xSemaphoreTake(lock, portMAX_DELAY);
    memset(&kept[slot], 0, sizeof kept[slot]);          /* (not held from here: nobody reads it meanwhile) */
    xSemaphoreGive(lock);
    if (esp_flash_erase_region(NULL, flash_at(slot), 4096 + BYTES) != ESP_OK)
        err = "the flash would not erase";
    for (uint32_t at = 0; !err && at < BYTES; at += CHUNK) {
        if (more(ctx, buf, CHUNK) != (int)CHUNK)
            err = "the table did not all come";
        else if (esp_flash_write(NULL, buf, flash_at(slot) + 4096 + at, CHUNK) != ESP_OK)
            err = "the flash would not write";
        h.sum = sum_bytes(h.sum, buf, CHUNK);
    }
    if (!err && esp_flash_write(NULL, &h, flash_at(slot), sizeof h) != ESP_OK)
        err = "the flash would not write";
    xSemaphoreTake(lock, portMAX_DELAY);
    if (!err)
        kept[slot] = h;
    resend[slot] = true;
    xSemaphoreGive(lock);
    ESP_LOGI(TAG, "slot %d \"%s\": %s", slot, h.name, err ? err : "kept");
    return err;
}

const char *tables_drop(int slot)
{
    const char *err = NULL;
    if (slot < 3 || slot >= LINK_TABLES)
        return "the slot: 3 to 7";
    xSemaphoreTake(lock, portMAX_DELAY);
    memset(&kept[slot], 0, sizeof kept[slot]);
    if (esp_flash_erase_region(NULL, flash_at(slot), 4096) != ESP_OK)
        err = "the flash would not erase";
    dropped[slot] = true;
    theirs[slot][0] = 0;
    xSemaphoreGive(lock);
    return err;
}

/* the network's weights passed on to the board's CPU (gateware/sw/store.c) */
const char *tables_net(const uint8_t *pairs, int n, bool keep, const char *name)
{
    uint8_t rq[8 + TABLE_NAME], a[4];
    uint32_t sum = LINK_TABLE_SUM0;
    for (int at = 0; at < n; at += 41) {
        int m = n - at < 41 ? n - at : 41;
        uint8_t part[3 + 6 * 41] = {LINK_NET, at, at >> 8};
        memcpy(part + 3, pairs + 6 * at, 6 * m);
        if (link_msg(part, 3 + 6 * m, a, sizeof a, 300) != 2 || a[0] != (LINK_NET | 0x80) || !a[1])
            return "the board did not take them (an older program, or its memory is not up)";
    }
    for (int k = 0; k < n; k++) {
        const uint8_t *p = pairs + 6 * k;
        sum = link_table_sum(sum, p[0] | p[1] << 8);
        sum = link_table_sum(sum, p[2] | (uint32_t)p[3] << 8 | (uint32_t)p[4] << 16 | (uint32_t)p[5] << 24);
    }
    rq[0] = LINK_NET_END;
    rq[1] = n, rq[2] = n >> 8;
    memcpy(rq + 3, &sum, 4);
    rq[7] = n ? (keep ? LINK_NET_KEEP : 0) : LINK_NET_FORGET;
    size_t l = strlen(name) < TABLE_NAME - 1 ? strlen(name) : TABLE_NAME - 1;
    memcpy(rq + 8, name, l);
    if (link_msg(rq, 8 + l, a, sizeof a, 2000) != 2 || a[0] != (LINK_NET_END | 0x80) || !a[1])
        return "the board did not put them in (no network in this design, or the output is not running)";
    net_was = 255;                      /* (the name asked for again) */
    return NULL;
}
