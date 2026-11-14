/* store.c: what the board keeps when the power is off, in the upper half of the SOM's flash (rtl/sflash.v:
 * the bitstream is in the lower half, and that module writes only from 0x800000 up): the settings,
 * the scaler's tables and the network's weights.  The board is whole without the link (the XIAO): the
 * link gives it things to keep, and need not be there when it starts.
 *
 * The flash from 0x800000 (4096-byte sectors):
 *   0x801000  the settings: 1024 records of 64 bytes, written one after the other and round again
 *             (a sector erased as the writing comes to it: the newest record is never in it).  A
 *             record: "SET1", its number, the settings' size, the settings, its words' sum.  The one
 *             with the greatest number and a right sum counts.
 *   0x820000  the network's weights: a head ("NETK", the values' sum, how many, a name), and from
 *             the next sector the values as cnn.v's port takes them: {address, value} pairs
 *   0x840000  the tables, slot 1 on, 0x40000 each: a head ("TABK", the words' sum, a name), and from
 *             the next sector the 32768 words
 * A head is written last, after its data has been read back and summed, and erased first: a
 * write cut short by the power leaves nothing, not something wrong.
 *
 * Writing takes long (a sector's erase 50 ms and more: a table some seconds), so it is done a step
 * each time round the program's loop.  Reading is quick (a table 0.2 s).
 */
#include "hw.h"

#ifdef HOST_TEST                        /* (sw/test/store_test.c: the flash's registers a model there) */
uint32_t test_reg_r(int n);
void test_reg_w(int n, uint32_t v);
#define RR(n)       test_reg_r(n)
#define RW(n, v)    test_reg_w(n, v)
extern uint32_t test_netbuf[];
#define NETBUF      test_netbuf
#else
#define RR(n)       REG(n)
#define RW(n, v)    (REG(n) = (v))
#define NETBUF      ((volatile uint32_t *)0x06200000u)     /* (the data memory, after the tables' slots: table.c) */
#endif

#define FL_READ     (1u << 28)
#define FL_NEXT     (2u << 28)
#define FL_END      (3u << 28)
#define FL_PROG     (4u << 28 | 0xAu << 24)
#define FL_ERASE    (5u << 28 | 0xAu << 24)
#define FL_STATUS   (6u << 28)
#define FL_ID       (7u << 28)

#define SET_AT      0x801000u
#define SET_RECS    1024u
#define NET_AT      0x820000u
#define TAB_AT      0x840000u
#define TAB_STEP    0x40000u
#define M_SET       0x31544553u         /* "SET1" */
#define M_NET       0x4B54454Eu         /* "NETK" */
#define M_TAB       0x4B424154u         /* "TABK" */
#define NET_MAX     1024

_Static_assert(sizeof(struct link_settings) <= 44, "the settings no longer fit a record");

enum { J_NONE, J_SET, J_NET, J_TAB, J_DROP };

static bool flash;                      /* the flash answers */
static bool waiting;                    /* it is writing: asked again each time */
static uint32_t t_poll;
static struct {
    uint8_t what, phase, slot, tries;
    uint32_t base, nerase;              /* the head's page; sectors erased from there */
    const volatile uint32_t *src;       /* the data, in the memory: to base + 4096 */
    uint32_t nwords, sum, pos, h;
    uint32_t head[16];
} job;

/* the settings */
static struct link_settings saved;
static uint32_t set_seq, set_next;      /* the newest record's number; the place of the next */
static uint16_t gen_seen;
static uint32_t t_change;
static bool set_dirty;
/* the tables, the network */
static uint8_t tab_kept, tab_want, tab_drop;
static uint32_t tab_sum[LINK_TABLES];
static char tab_name[LINK_TABLES][LINK_NAME];
static uint32_t net_sum;
static uint16_t net_count, net_new;
static char net_name[LINK_NAME];
static bool net_kept, net_want, net_drop, net_looked;
static uint8_t net_state;               /* LINK_NET_*: whose weights the network has */

static bool go(uint32_t c)
{
    uint32_t t = cycles();
    RW(R_FLC, c);
    while (RR(R_FLS) & 1)
        if (cycles() - t > core_hz / 50)
            return false;
    return true;
}

static void fl_read(uint32_t a, volatile uint32_t *d, int n)
{
    go(FL_READ | a);
    for (int k = 0; k < n; k++) {
        d[k] = RR(R_FLD);
        if (k + 1 < n)
            go(FL_NEXT);
        if ((k & 63) == 63)
            audio_service();
    }
    go(FL_END);
}

/* (within a page: 64 words at most) */
static void fl_prog(uint32_t a, const volatile uint32_t *d, int n)
{
    go(FL_PROG | a);
    for (int k = 0; k < n; k++) {
        RW(R_FLD, d[k]);
        go(FL_NEXT);
    }
    go(FL_END);
    waiting = true;
}

static uint32_t sum_words(uint32_t h, const volatile uint32_t *w, int n)
{
    for (int k = 0; k < n; k++)
        h = link_table_sum(h, w[k]);
    return h;
}

static uint32_t tab_at(int slot)
{
    return TAB_AT + (uint32_t)(slot - 1) * TAB_STEP;
}

static void name_to(uint32_t *w, const char *name)
{
    __builtin_memcpy(w, name, LINK_NAME);
}

static void report(void)
{
    st.store = (flash ? LINK_STORE_THERE : 0) | (set_seq ? LINK_STORE_SET : 0) |
               (job.what || set_dirty || tab_want || tab_drop || net_want || net_drop ? LINK_STORE_BUSY : 0) |
               (st.store & LINK_STORE_FAILED);
    st.net_state = net_state;
}

/* ---- at the start: the flash looked at, the settings kept taken ---- */
void store_init(void)
{
    uint32_t r[16], id;
    ms();                               /* (the core's clock known) */
    go(FL_ID);
    id = RR(R_FLD) & 0xFFFFFF;
    flash = !(RR(R_FLS) & 1) && id != 0 && id != 0xFFFFFF;
    if (!flash)
        return;
    set_next = 0;
    for (uint32_t k = 0; k < SET_RECS; k++) {
        fl_read(SET_AT + 64 * k, r, 16);
        if (r[0] == M_SET && r[2] == sizeof set && r[1] > set_seq && sum_words(LINK_TABLE_SUM0, r, 15) == r[15]) {
            set_seq = r[1];
            set_next = (k + 1) % SET_RECS;
            __builtin_memcpy(&saved, r + 3, sizeof saved);
        }
    }
    if (set_seq) {
        set = saved;
        st.gen = 1;                     /* (the link: these are the ones that count, not its copy) */
    }
    for (int s = 1; s < LINK_TABLES; s++) {
        fl_read(tab_at(s), r, 16);
        if (r[0] == M_TAB && sum_words(LINK_TABLE_SUM0, r, 15) == r[15]) {
            tab_kept |= 1u << s;
            tab_sum[s] = r[1];
            __builtin_memcpy(tab_name[s], r + 3, LINK_NAME);
        }
    }
    gen_seen = st.gen;
    report();
}

/* ---- the tables (table.c) ---- */
/* a kept table into the memory: its words' sum, or false */
bool store_table_load(int slot, volatile uint32_t *words, uint32_t *sum)
{
    if (!flash || slot < 1 || slot >= LINK_TABLES || !(tab_kept >> slot & 1))
        return false;
    fl_read(tab_at(slot) + 4096, words, LINK_TABLE_WORDS);
    *sum = tab_sum[slot];
    return sum_words(LINK_TABLE_SUM0, words, LINK_TABLE_WORDS) == tab_sum[slot];
}

/* the slot's table in the memory is whole (its words there: src): kept, if it is not the one kept */
void store_table_keep(int slot, uint32_t sum, const char *name, int n)
{
    char nm[LINK_NAME] = {0};
    if (!flash || slot < 1 || slot >= LINK_TABLES)
        return;
    __builtin_memcpy(nm, name, n < LINK_NAME - 1 ? n : LINK_NAME - 1);
    if (tab_kept >> slot & 1 && tab_sum[slot] == sum && (!n || !__builtin_memcmp(nm, tab_name[slot], LINK_NAME)))
        return;
    if (n || !(tab_kept >> slot & 1))
        __builtin_memcpy(tab_name[slot], nm, LINK_NAME);
    tab_sum[slot] = sum;
    tab_want |= 1u << slot;
    tab_drop &= ~(1u << slot);
    report();
}

/* the slot's table in the memory is being changed or is gone: what is kept of it too (gone: erased) */
void store_table_gone(int slot, bool erase)
{
    if (!flash || slot < 1 || slot >= LINK_TABLES)
        return;
    tab_want &= ~(1u << slot);
    if (job.what == J_TAB && job.slot == slot)
        job.what = J_NONE;              /* (cut short: its head is not there: nothing kept) */
    if (erase && tab_kept >> slot & 1)
        tab_drop |= 1u << slot;
    report();
}

const char *store_table_name(int slot)
{
    return tab_name[slot];
}

/* ---- the network's weights (the link's: LINK_NET, LINK_NET_END) ---- */
static bool net_apply(int count)
{
    if (!(RR(R_NET) >> 30 & 1))
        return false;
    for (int k = 0; k < count; k++) {
        uint32_t t = cycles();
        RW(R_NETA, NETBUF[2 * k]);
        RW(R_NETD, NETBUF[2 * k + 1]);
        while (RR(R_NET) >> 31)         /* (taken between the network's passes) */
            if (cycles() - t > core_hz / 100)
                return false;
        if ((k & 31) == 31)
            audio_service();
    }
    return true;
}

bool store_net_part(int at, const uint8_t *d, int n)
{
    if (mem_state != MEM_GOOD || at + n > NET_MAX)
        return false;
    for (int k = 0; k < n; k++, d += 6) {
        NETBUF[2 * (at + k)] = d[0] | d[1] << 8;
        NETBUF[2 * (at + k) + 1] = d[2] | (uint32_t)d[3] << 8 | (uint32_t)d[4] << 16 | (uint32_t)d[5] << 24;
    }
    if (job.what == J_NET)              /* (the ones being kept are no longer in the memory) */
        job.what = J_NONE;
    net_want = false;
    return true;
}

/* all of them are there (count, their sum): put into the network; flags: LINK_NET_KEEP kept too;
 * LINK_NET_FORGET (count 0): the kept ones erased (the network has what it has until others come) */
bool store_net_end(int count, uint32_t sum, int flags, const char *name, int n)
{
    if (flags & LINK_NET_FORGET) {
        net_want = false;
        if (job.what == J_NET)
            job.what = J_NONE;
        net_drop = flash;
        report();
        return true;
    }
    if (mem_state != MEM_GOOD || count < 1 || count > NET_MAX || sum_words(LINK_TABLE_SUM0, NETBUF, 2 * count) != sum ||
        !net_apply(count))
        return false;
    net_state = LINK_NET_GIVEN;
    if (flags & LINK_NET_KEEP && flash) {
        __builtin_memset(net_name, 0, sizeof net_name);
        __builtin_memcpy(net_name, name, n < LINK_NAME - 1 ? n : LINK_NAME - 1);
        net_new = count;
        net_sum = sum;
        net_want = true;
        net_drop = false;
    }
    report();
    return true;
}

/* what is kept, for the link: slot 0 to 7 a table, 8 the network: {kept, sum, name} */
int store_about(int what, uint8_t *a)
{
    bool kept = what == 8 ? net_kept : what < LINK_TABLES && (tab_kept >> what & 1);
    uint32_t sum = what == 8 ? net_sum : what < LINK_TABLES ? tab_sum[what] : 0;
    a[0] = kept;
    __builtin_memcpy(a + 1, &sum, 4);
    __builtin_memset(a + 5, 0, LINK_NAME);
    if (kept)
        __builtin_memcpy(a + 5, what == 8 ? net_name : tab_name[what], LINK_NAME);
    return 5 + LINK_NAME;
}

/* ---- the writing, a step a time ---- */
static void begin(int what, int slot, uint32_t base, uint32_t nerase, const volatile uint32_t *src, uint32_t nwords, uint32_t sum)
{
    job.what = what;
    job.slot = slot;
    job.phase = 0;
    job.tries = 0;
    job.base = base;
    job.nerase = nerase;
    job.src = src;
    job.nwords = nwords;
    job.sum = sum;
    job.pos = 0;
}

static void done(bool ok)
{
    static uint8_t set_failed;
    if (!ok)
        st.store |= LINK_STORE_FAILED;
    if (job.what == J_SET) {            /* (not kept: again at the next place, three times) */
        set_failed = ok ? 0 : set_failed + 1;
        if (!ok && set_failed < 3) {
            set_dirty = true;
            t_change = ms();
        }
    }
    if (job.what == J_SET && ok) {
        set_seq = job.head[1];
        __builtin_memcpy(&saved, job.head + 3, sizeof saved);
        set_next = (set_next + 1) % SET_RECS;
    }
    if (job.what == J_TAB && ok)
        tab_kept |= 1u << job.slot;
    if (job.what == J_NET && ok) {
        net_kept = true;
        net_count = net_new;
        net_state = LINK_NET_KEPT;
    }
    job.what = J_NONE;
}

static void next_job(void)
{
    uint32_t r[16];
    /* the settings, two seconds after they last changed */
    if (st.gen != gen_seen) {
        gen_seen = st.gen;
        t_change = ms();
        set_dirty = true;
    }
    if (set_dirty && ms() - t_change >= 2000) {
        set_dirty = false;
        if (!set_seq || __builtin_memcmp(&set, &saved, sizeof set)) {
            uint32_t at;
            /* (the next place that is erased, or a sector's first: erased before it is written) */
            for (int k = 0; k < 64; k++) {
                fl_read(SET_AT + 64 * set_next, r, 16);
                for (at = 0; at < 16 && r[at] == 0xFFFFFFFFu; at++)
                    ;
                if (at == 16 || set_next % 64 == 0)
                    break;
                set_next = (set_next + 1) % SET_RECS;
            }
            begin(J_SET, 0, SET_AT + 64 * set_next, set_next % 64 == 0, 0, 0, 0);
            __builtin_memset(job.head, 0, sizeof job.head);
            job.head[0] = M_SET;
            job.head[1] = set_seq + 1;
            job.head[2] = sizeof set;
            __builtin_memcpy(job.head + 3, &set, sizeof set);
            job.head[15] = sum_words(LINK_TABLE_SUM0, job.head, 15);
            return;
        }
    }
    if (net_drop) {
        net_drop = false;
        net_kept = false;
        if (net_state == LINK_NET_KEPT)
            net_state = LINK_NET_GIVEN;
        begin(J_DROP, 0, NET_AT, 1, 0, 0, 0);
        return;
    }
    if (net_want) {
        net_want = false;
        net_kept = false;
        begin(J_NET, 0, NET_AT, 1 + (8 * net_new + 4095) / 4096, NETBUF, 2 * net_new, net_sum);
        __builtin_memset(job.head, 0, sizeof job.head);
        job.head[0] = M_NET;
        job.head[1] = net_sum;
        job.head[2] = net_new;
        name_to(job.head + 3, net_name);
        job.head[15] = sum_words(LINK_TABLE_SUM0, job.head, 15);
        return;
    }
    for (int s = 1; s < LINK_TABLES; s++) {
        if (tab_drop >> s & 1) {
            tab_drop &= ~(1u << s);
            tab_kept &= ~(1u << s);
            begin(J_DROP, s, tab_at(s), 1, 0, 0, 0);
            return;
        }
        if (tab_want >> s & 1 && mem_state == MEM_GOOD) {
            tab_want &= ~(1u << s);
            tab_kept &= ~(1u << s);
            begin(J_TAB, s, tab_at(s), 33, table_words(s), LINK_TABLE_WORDS, tab_sum[s]);
            __builtin_memset(job.head, 0, sizeof job.head);
            job.head[0] = M_TAB;
            job.head[1] = tab_sum[s];
            job.head[2] = LINK_TABLE_WORDS;
            name_to(job.head + 3, tab_name[s]);
            job.head[15] = sum_words(LINK_TABLE_SUM0, job.head, 15);
            return;
        }
    }
}

void store_service(void)
{
    uint32_t r[64];
    if (!flash || st.host)              /* (a host tool has the monitor: the flash's port may be its) */
        return;
    if (waiting) {                      /* the flash is writing: asked five thousand times a second at most */
        if (cycles() - t_poll < core_hz / 5000)
            return;
        t_poll = cycles();
        go(FL_STATUS);
        if (RR(R_FLD) & 1)
            return;
        waiting = false;
    }
    /* the kept weights into the network, once it and the memory are there */
    if (!net_looked && mem_state == MEM_GOOD && RR(R_NET) >> 30 & 1 && !job.what) {
        net_looked = true;
        fl_read(NET_AT, r, 16);
        if (r[0] == M_NET && r[2] >= 1 && r[2] <= NET_MAX && sum_words(LINK_TABLE_SUM0, r, 15) == r[15]) {
            fl_read(NET_AT + 4096, NETBUF, 2 * r[2]);
            if (sum_words(LINK_TABLE_SUM0, NETBUF, 2 * r[2]) == r[1] && net_apply(r[2])) {
                net_kept = true;
                net_sum = r[1];
                net_count = r[2];
                __builtin_memcpy(net_name, r + 3, LINK_NAME);
                net_state = LINK_NET_KEPT;
            }
        }
        report();
        return;
    }
    if (!job.what) {
        if (st.gen != gen_seen || set_dirty || tab_want || tab_drop || net_want || net_drop) {
            next_job();
            report();
        }
        return;
    }
    switch (job.phase) {
    case 0:                             /* erased: the head's sector first */
        if (job.pos < job.nerase) {
            go(FL_ERASE | (job.base + 4096 * job.pos++));
            waiting = true;
        } else {
            job.phase = job.what == J_DROP ? 5 : 1;
            job.pos = 0;
        }
        break;
    case 1:                             /* the data, a page a time */
        if (job.pos < job.nwords) {
            int n = job.nwords - job.pos < 64 ? job.nwords - job.pos : 64;
            fl_prog(job.base + 4096 + 4 * job.pos, job.src + job.pos, n);
            job.pos += n;
        } else {
            job.phase = job.nwords ? 2 : 3;
            job.pos = 0;
            job.h = LINK_TABLE_SUM0;
        }
        break;
    case 2:                             /* read back and summed */
        if (job.pos < job.nwords) {
            int n = job.nwords - job.pos < 64 ? job.nwords - job.pos : 64;
            fl_read(job.base + 4096 + 4 * job.pos, r, n);
            job.h = sum_words(job.h, r, n);
            job.pos += n;
        } else if (job.h == job.sum) {
            job.phase = 3;
        } else if (job.tries++ < 1) {
            job.phase = 0;
            job.pos = 0;
        } else
            done(false);
        break;
    case 3:                             /* the head (the settings: the record) */
        fl_prog(job.base, job.head, 16);
        job.phase = 4;
        break;
    case 4:
        fl_read(job.base, r, 16);
        if (!__builtin_memcmp(r, job.head, sizeof job.head))
            done(true);
        else if (job.tries++ < 1 && job.what != J_SET) {
            job.phase = 0;
            job.pos = 0;
        } else {
            if (job.what == J_SET)      /* (the place is spoilt: the next one, the next time) */
                set_next = (set_next + 1) % SET_RECS;
            done(false);
        }
        break;
    default:
        done(true);
    }
    report();
}
