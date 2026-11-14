/* table.c: the scaler's table (rtl/easu.v: for a pixel's place, the edge's direction and its
 * strength there, the twelve source pixels' weights).  The design is built with FSR's (sim/fsr.py);
 * its table is a RAM, and this puts others there: tables are kept in the data memory, in slots, and
 * the setting says which the scaler is to have (link.h: table); when that is not the one it has,
 * its entries are written one by one through the design's port (TABA, TABD: an entry whole, in the
 * picture's blanking, so the picture goes on, made with one table's entries or the other's), then
 * read back and compared.  A little each time round the program's loop.
 *
 * Slot 0 is the design's own table: read out of the RAM into the memory before anything else is
 * written there.  The others are the link's to fill (LINK_TABLE, LINK_TABLE_END): 1 and 2 the pair
 * the setting 1 chooses between by the anti-aliasing (off, on), 3 on by the settings 2 on.  A
 * table the link gives is kept in the board's flash (store.c), and is there again at the next
 * start, link or no link.
 *
 * A slot: TAB_STEP of the memory from TAB_AT (bank 0, above the picture's field), a head (it holds
 * a table: the magic, the design's build for slot 0, the words' sum) and from TAB_DATA the 8192
 * entries, four words each (a quarter's three weights, 10 bits each).  A program that begins
 * again finds them there.
 */
#include "hw.h"

#define TAB_AT      0x06000000u
#define TAB_STEP    0x00040000u
#define TAB_DATA    0x00001000u
#define TAB_MAGIC   0x31424154u         /* "TAB1" */
#define TAB_ENTRIES 8192
#define BUSY        (1u << 31)
#define READ        (1u << 31)
#define THERE       (1u << 30)
#define WRITTEN     (1u << 29)

struct head {
    uint32_t magic, build, sum;
};

enum { T_IDLE = LINK_TAB_IDLE, T_PUT = LINK_TAB_PUT, T_CHECK = LINK_TAB_CHECK, T_KEEP = LINK_TAB_KEEP };

static uint8_t have;                    /* the slots that hold a table */
static int scan;                        /* slots looked at since the program began */
static int in_ram = -1;                 /* the slot whose table the scaler has (-1: not known) */
static int going;                       /* the one on its way there */
static int state = T_IDLE;
static uint32_t pos;                    /* the next entry */
static bool asked;                      /* (that entry is being read) */
static uint32_t bad, t_begun;
static bool kept_tried;
static int there = -1;                  /* the design has the port (-1: not looked at yet) */

static volatile struct head *head(int s)
{
    return (volatile struct head *)(TAB_AT + (uint32_t)s * TAB_STEP);
}

static volatile uint32_t *words(int s)
{
    return (volatile uint32_t *)(TAB_AT + (uint32_t)s * TAB_STEP + TAB_DATA);
}

volatile uint32_t *table_words(int slot)
{
    return words(slot);
}

static uint32_t sum_of(int s)
{
    volatile uint32_t *w = words(s);
    uint32_t h = LINK_TABLE_SUM0;
    for (int k = 0; k < 4 * TAB_ENTRIES; k++) {
        h = link_table_sum(h, w[k]);
        if ((k & 255) == 255)
            audio_service();
    }
    return h;
}

static bool port(void)
{
    return (REG(R_TABA) & THERE) != 0;
}

/* the slot the settings ask for; the design's own if that one holds nothing; -1: nor does that */
static int wanted(void)
{
    int s = set.table == 0 ? 0 : set.table == 1 ? 1 + (set.aa != 0) : set.table + 1;
    if (s >= LINK_TABLES || !(have >> s & 1))
        s = 0;
    return have & 1 << s ? s : -1;
}

static void report(void)
{
    st.tab_have = have;
    st.tab_slot = in_ram < 0 ? 255 : in_ram;
    st.tab_state = state;
}

/* a part of a table from the link: n words from the slot's word at */
bool table_part(int slot, uint32_t at, const uint8_t *d, int n)
{
    volatile uint32_t *w;
    if (mem_state != MEM_GOOD || slot < 1 || slot >= LINK_TABLES || at + n > 4 * TAB_ENTRIES)
        return false;
    if (have >> slot & 1 || head(slot)->magic == TAB_MAGIC) {
        head(slot)->magic = 0;
        have &= ~(1u << slot);
    }
    store_table_gone(slot, n == 0);     /* (no words: the slot emptied, in the flash too) */
    w = words(slot) + at;
    for (int k = 0; k < n; k++)
        w[k] = d[4 * k] | (uint32_t)d[4 * k + 1] << 8 | (uint32_t)d[4 * k + 2] << 16 | (uint32_t)d[4 * k + 3] << 24;
    report();
    return true;
}

/* ... and all of it there: the slot holds a table, if its words' sum is this */
bool table_end(int slot, uint32_t sum, const char *name, int n)
{
    if (mem_state != MEM_GOOD || slot < 1 || slot >= LINK_TABLES || scan < LINK_TABLES || sum_of(slot) != sum)
        return false;
    head(slot)->build = 0;
    head(slot)->sum = sum;
    head(slot)->magic = TAB_MAGIC;
    have |= 1u << slot;
    if (in_ram == slot)                 /* (what the scaler has is this slot's table from before) */
        in_ram = -1;
    if (state != T_KEEP && going == slot)
        state = T_IDLE;
    store_table_keep(slot, sum, name, n);
    report();
    return true;
}

/* some entries of the slot going into the scaler's RAM, for a millisecond at most */
static void put(uint32_t t0)
{
    volatile uint32_t *w = words(going) + 4 * pos;
    REG(R_TABA) = pos;
    while (pos < TAB_ENTRIES && cycles() - t0 < core_hz / 1000) {
        if (REG(R_TABA) & BUSY)
            continue;
        REG(R_TABD) = w[0];
        REG(R_TABD) = w[1];
        REG(R_TABD) = w[2];
        REG(R_TABD) = w[3];
        w += 4;
        pos++;
    }
}

/* some entries of the scaler's RAM read: compared with the slot's (keep: put there) */
static void get(uint32_t t0, bool keep)
{
    volatile uint32_t *w = words(going) + 4 * pos;
    while (pos < TAB_ENTRIES && cycles() - t0 < core_hz / 1000) {
        if (!asked) {
            REG(R_TABA) = READ | pos;
            asked = true;
        }
        if (REG(R_TABA) & BUSY)
            continue;
        asked = false;
        if (keep) {
            for (int q = 0; q < 4; q++)
                w[q] = REG(R_TABQ + q);
        } else if (((w[0] ^ REG(R_TABQ)) | (w[1] ^ REG(R_TABQ + 1)) | (w[2] ^ REG(R_TABQ + 2)) |
                    (w[3] ^ REG(R_TABQ + 3))) & 0x3FFFFFFFu)
            bad++;
        w += 4;
        pos++;
    }
}

void table_service(void)
{
    uint32_t t0 = cycles();
    int want;

    if (mem_state == MEM_GOOD && there < 0)
        there = port();
    if (mem_state != MEM_GOOD || there <= 0) {
        st.tab_state = LINK_TAB_NONE;
        st.tab_slot = 255;
        return;
    }
    /* the slots as a program before this left them (one a time round: a sum takes a while) */
    if (scan < LINK_TABLES) {
        volatile struct head *h = head(scan);
        uint32_t sum;
        if (h->magic == TAB_MAGIC && (scan ? h->build == 0 : h->build == REG(R_BUILD)) && sum_of(scan) == h->sum)
            have |= 1u << scan;
        else if (scan && store_table_load(scan, words(scan), &sum)) {   /* (a start from cold: the flash's) */
            h->build = 0;
            h->sum = sum;
            h->magic = TAB_MAGIC;
            have |= 1u << scan;
        }
        if (++scan == LINK_TABLES && have & 1 && !(REG(R_TABA) & WRITTEN))
            in_ram = 0;
        report();
        return;
    }
    /* nothing to do, as nearly always: no word on the register bus (the monitor and the link share
     * it: a program that asks it something each time round is in their way) */
    want = wanted();
    if (state == T_IDLE && (want < 0 || want == in_ram) && (have & 1 || kept_tried))
        return;
    if (REG(R_TABA) & BUSY)             /* (an entry on its way: the output's clock may not run yet) */
        return;
    /* the design's own table, while the RAM still has it: into slot 0 */
    if (!(have & 1) && !kept_tried && state != T_KEEP) {
        kept_tried = true;
        if (!(REG(R_TABA) & WRITTEN)) {
            state = T_KEEP;
            going = 0;
            pos = 0;
            asked = false;
        }
    }
    if (state == T_KEEP) {
        get(t0, true);
        if (pos == TAB_ENTRIES && !(REG(R_TABA) & WRITTEN)) {
            head(0)->build = REG(R_BUILD);
            head(0)->sum = sum_of(0);
            head(0)->magic = TAB_MAGIC;
            have |= 1;
            in_ram = 0;
            state = T_IDLE;
        }
        report();
        return;
    }
    if (want >= 0 && (state == T_IDLE ? want != in_ram : want != going)) {
        state = T_PUT;
        going = want;
        in_ram = -1;
        pos = 0;
        t_begun = ms();
    }
    if (state == T_PUT) {
        put(t0);
        if (pos == TAB_ENTRIES) {
            uint32_t t = ms() - t_begun;
            st.tab_ms = t > 65535 ? 65535 : t;
            in_ram = going;
            state = T_CHECK;
            pos = 0;
            bad = 0;
            asked = false;
        }
    } else if (state == T_CHECK) {
        get(t0, false);
        if (pos == TAB_ENTRIES) {
            st.tab_bad = bad > 65535 ? 65535 : bad;
            state = T_IDLE;
        }
    }
    report();
}
