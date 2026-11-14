/* store_test.c: sw/store.c on the host, against a model of rtl/sflash.v's registers and the flash
 * behind them: the settings kept and found again (3000 changes: the records go round), the power
 * cut at any moment of any write (what is found after is the settings before the change or
 * after it, never anything else, and the next change is kept), a table and the network's weights
 * kept, found, replaced and dropped.  The model refuses what sflash.v refuses and counts it, and
 * counts a read or a write while the flash is still writing: there must be none.
 *
 *   make test        (sw/Makefile; or: cc -O1 -DHOST_TEST -I.. -o store_test store_test.c ../store.c)
 *
 * Each start of the board is a process of its own (the program's variables begin again); the
 * flash is memory the processes share. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

#include "hw.h"

#define FLASH (16u << 20)
struct shared {
    uint8_t mem[FLASH];
    struct link_settings before, after;     /* the settings kept for sure; the ones on their way */
    long ops, cut;                          /* the flash's operations so far; the one the power goes at (0: never) */
    int refused, early, low;
    uint32_t tab[2][LINK_TABLE_WORDS];
    uint32_t net_seen[2 * 1024];
    int net_n;
} *sh;

/* ---- what store.c is built against ---- */
struct link_settings set = LINK_SETTINGS_DEFAULT;
struct link_status st;
int mem_state = MEM_GOOD;
uint32_t core_hz = 800000000u;
uint32_t test_netbuf[2 * 1024];
static uint64_t now;                        /* the core's cycles */
uint32_t cycles(void) { now += 400; return (uint32_t)now; }
uint32_t ms(void) { return (uint32_t)(now / 800000); }
void audio_service(void) {}
volatile uint32_t *table_words(int slot) { return sh->tab[slot & 1]; }

/* ---- rtl/sflash.v and the flash ---- */
static uint32_t fld, cur, neta;
static int open_, prog, np, wip;
static uint8_t page[256];
static uint32_t pa;

static void power(void)
{
    if (sh->cut && sh->ops >= sh->cut)
        _exit(7);
}

static void write_done(void)                /* (a write begun: the flash busy for some status reads) */
{
    wip = 3 + rand() % 5;
}

uint32_t test_reg_r(int n)
{
    now += 4000;
    if (n == R_FLD)
        return fld;
    if (n == R_FLS)
        return (prog ? 8 : 0) | (open_ ? 4 : 0);
    if (n == R_NET)
        return 1u << 30;
    return 0;
}

static void end_frame(void)
{
    if (open_ && prog && np) {
        sh->ops++;
        /* (the power may go part of the way through the page) */
        int upto = sh->cut && sh->ops >= sh->cut ? rand() % (np + 1) : np;
        for (int k = 0; k < upto && k < 256; k++)
            sh->mem[(pa & ~255u) | ((pa + k) & 255)] &= page[k];
        power();
        write_done();
    }
    open_ = prog = 0;
}

void test_reg_w(int n, uint32_t v)
{
    uint32_t op = v >> 28, a = v & 0xFFFFFF;
    now += 4000;
    if (n == R_NETA)
        neta = v;
    if (n == R_NETD && sh->net_n < 1024) {
        sh->net_seen[2 * sh->net_n] = neta;
        sh->net_seen[2 * sh->net_n++ + 1] = v;
    }
    if (n == R_FLD)
        fld = v;
    if (n != R_FLC || op < 1 || op > 7)
        return;
    if ((op == 4 || op == 5) && (!(v >> 23 & 1) || (v >> 24 & 15) != 10)) {
        sh->refused++;
        return;
    }
    if (op == 2 && !open_)
        return;
    if (op != 2 && op != 3)
        end_frame();
    if (wip && op != 6 && op != 7 && op != 3)
        sh->early++;                        /* (asked of a flash that is still writing) */
    switch (op) {
    case 1: cur = a; open_ = 1; prog = 0; memcpy(&fld, sh->mem + cur, 4); cur += 4; break;
    case 2:
        if (prog) {
            for (int k = 0; k < 4; k++)
                page[np++ & 255] = fld >> 8 * k;
        } else {
            memcpy(&fld, sh->mem + (cur & (FLASH - 1)), 4);
            cur += 4;
        }
        break;
    case 3: end_frame(); break;
    case 4: pa = a; np = 0; open_ = prog = 1; if (a < 0x800000) sh->low++; break;
    case 5:
        if (a < 0x800000)
            sh->low++;
        sh->ops++;
        {   /* (the power may go part of the way through the sector) */
            int upto = sh->cut && sh->ops >= sh->cut ? rand() % 4097 : 4096;
            memset(sh->mem + (a & ~4095u), 0xFF, upto);
        }
        power();
        write_done();
        break;
    case 6: fld = wip ? 1 : 0; if (wip) wip--; break;
    case 7: fld = 0xEF4018; break;
    }
}

/* ---- the tests ---- */
static int bad;
#define WANT(c, ...) do { if (!(c)) { bad++; printf("WRONG: " __VA_ARGS__); printf("\n"); } } while (0)

static void run(int rounds)                 /* the program's loop, some seconds of it */
{
    for (int k = 0; k < rounds; k++) {
        now += 800000 * 10;                 /* (10 ms a round) */
        store_service();
    }
}

static void settle(void)
{
    for (int k = 0; k < 400000 && (k < 300 || st.store & LINK_STORE_BUSY); k++) {
        now += 800000 * 10;
        store_service();
    }
}

static void change(int k)
{
    set.sharp = k & 15;
    set.crop_x = (uint16_t)(k * 7);
    set.phase = k % 31;
    st.gen++;
}

/* a start of the board in a process of its own: what() run after store_init(); its exit code */
static int boot(void (*what)(int), int arg, long cut)
{
    int status;
    sh->cut = cut ? sh->ops + cut : 0;
    fflush(stdout);
    pid_t p = fork();
    if (!p) {
        srand(arg * 7919 + (unsigned)sh->ops);
        store_init();
        what(arg);
        fflush(stdout);
        _exit(bad ? 1 : 0);
    }
    waitpid(p, &status, 0);
    return WEXITSTATUS(status);
}

static void t_empty(int a)
{
    (void)a;
    WANT(st.store == LINK_STORE_THERE, "an empty flash: store %d", st.store);
    WANT(st.gen == 0, "an empty flash: gen %d", st.gen);
}

static void t_many(int n)
{
    for (int k = 1; k <= n; k++) {
        change(k);
        sh->after = set;
        settle();
        WANT(!(st.store & (LINK_STORE_BUSY | LINK_STORE_FAILED)) && st.store & LINK_STORE_SET, "change %d: store %d", k, st.store);
        sh->before = set;
    }
}

static void t_same(int a)
{
    (void)a;
    WANT(st.store & LINK_STORE_SET && st.gen == 1, "after a start: store %d gen %d", st.store, st.gen);
    WANT(!memcmp(&set, &sh->before, sizeof set), "after a start: the settings are not the ones kept (sharp %d, kept %d)", set.sharp, sh->before.sharp);
}

/* (the power went during t_many: the settings are the last kept or the one on its way; then a change is kept) */
static void t_after_cut(int a)
{
    int was_after = !memcmp(&set, &sh->after, sizeof set);
    WANT(st.gen == 1 && (was_after || !memcmp(&set, &sh->before, sizeof set)), "after a cut: settings neither the ones before nor after (sharp %d)", set.sharp);
    change(1000 + a);
    sh->after = set;
    settle();
    WANT(!(st.store & LINK_STORE_BUSY) && st.store & LINK_STORE_SET, "after a cut: the next change: store %d", st.store);
    sh->before = set;
}

static uint32_t tsum(const uint32_t *w, int n)
{
    uint32_t h = LINK_TABLE_SUM0;
    for (int k = 0; k < n; k++)
        h = link_table_sum(h, w[k]);
    return h;
}

static void t_table_keep(int slot)
{
    for (int k = 0; k < LINK_TABLE_WORDS; k++)
        sh->tab[slot & 1][k] = (uint32_t)k * 2654435761u ^ slot;
    store_table_keep(slot, tsum(sh->tab[slot & 1], LINK_TABLE_WORDS), "a-table", 7);
    settle();
    WANT(!(st.store & (LINK_STORE_BUSY | LINK_STORE_FAILED)), "table %d kept: store %d", slot, st.store);
}

static void t_table_find(int slot)
{
    uint32_t sum = 0, want = tsum(sh->tab[slot & 1], LINK_TABLE_WORDS);
    uint8_t a[5 + LINK_NAME];
    static uint32_t back[LINK_TABLE_WORDS];
    WANT(store_table_load(slot, back, &sum) && sum == want && !memcmp(back, sh->tab[slot & 1], sizeof back), "table %d not found again", slot);
    store_about(slot, a);
    WANT(a[0] == 1 && !memcmp(a + 1, &want, 4) && !strcmp((char *)a + 5, "a-table"), "table %d: about: kept %d name %s", slot, a[0], a + 5);
    WANT(!store_table_load(2, back, &sum), "a table in a slot that has none");
}

static void t_table_drop(int slot)
{
    store_table_gone(slot, true);
    settle();
}

static void t_table_none(int slot)
{
    uint32_t sum;
    static uint32_t back[LINK_TABLE_WORDS];
    WANT(!store_table_load(slot, back, &sum), "table %d still there", slot);
}

/* (a table changed while it is being kept: nothing kept of it; then kept whole) */
static void t_table_change(int slot)
{
    for (int k = 0; k < LINK_TABLE_WORDS; k++)
        sh->tab[slot & 1][k] = k;
    store_table_keep(slot, tsum(sh->tab[slot & 1], LINK_TABLE_WORDS), "first", 5);
    run(30 + rand() % 200);
    store_table_gone(slot, false);
    for (int k = 0; k < LINK_TABLE_WORDS; k++)
        sh->tab[slot & 1][k] = ~k;
    store_table_keep(slot, tsum(sh->tab[slot & 1], LINK_TABLE_WORDS), "a-table", 7);
    settle();
}

static void t_net_keep(int n)
{
    uint8_t d[6 * 41];
    uint32_t pairs[2 * 1024];
    for (int k = 0; k < n; k++) {
        pairs[2 * k] = k * 3 % 2400;
        pairs[2 * k + 1] = (uint32_t)k * 40503u & 0x3FFFFF;
    }
    for (int at = 0; at < n; at += 41) {
        int m = n - at < 41 ? n - at : 41;
        for (int k = 0; k < m; k++) {
            d[6 * k] = pairs[2 * (at + k)], d[6 * k + 1] = pairs[2 * (at + k)] >> 8;
            memcpy(d + 6 * k + 2, &pairs[2 * (at + k) + 1], 4);
        }
        WANT(store_net_part(at, d, m), "net part at %d", at);
    }
    sh->net_n = 0;
    WANT(!store_net_end(n, 1234, LINK_NET_KEEP, "x", 1), "a wrong sum taken");
    WANT(store_net_end(n, tsum(pairs, 2 * n), LINK_NET_KEEP, "net-one", 7), "net end");
    WANT(sh->net_n == n && !memcmp(sh->net_seen, pairs, 8 * n) && st.net_state == LINK_NET_GIVEN, "the network was not given them (%d)", sh->net_n);
    settle();
    WANT(st.net_state == LINK_NET_KEPT && !(st.store & (LINK_STORE_BUSY | LINK_STORE_FAILED)), "net kept: state %d store %d", st.net_state, st.store);
}

static void t_net_find(int n)
{
    uint8_t a[5 + LINK_NAME];
    sh->net_n = 0;
    run(20);
    WANT(sh->net_n == n && st.net_state == LINK_NET_KEPT, "the kept weights were not put in at the start (%d of %d)", sh->net_n, n);
    for (int k = 0; k < n; k++)
        if (sh->net_seen[2 * k] != (uint32_t)(k * 3 % 2400) || sh->net_seen[2 * k + 1] != ((uint32_t)k * 40503u & 0x3FFFFF)) {
            WANT(0, "weight %d wrong", k);
            break;
        }
    store_about(8, a);
    WANT(a[0] == 1 && !strcmp((char *)a + 5, "net-one"), "net: about: kept %d name %s", a[0], a + 5);
}

static void t_net_forget(int a)
{
    (void)a;
    run(20);
    WANT(store_net_end(0, 0, LINK_NET_FORGET, "", 0), "forget");
    settle();
}

static void t_net_none(int a)
{
    (void)a;
    sh->net_n = 0;
    run(20);
    WANT(sh->net_n == 0 && st.net_state == LINK_NET_OWN, "weights put in though forgotten (%d)", sh->net_n);
}

int main(void)
{
    int cuts = 0, after = 0;
    sh = mmap(NULL, sizeof *sh, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    memset(sh->mem, 0xFF, FLASH);
    for (uint32_t k = 0; k < 0x800000; k++)     /* (the bitstream's half: must come through as it is) */
        sh->mem[k] = k * 31 + (k >> 9);
    bad += boot(t_empty, 0, 0) != 0;
    bad += boot(t_many, 3000, 0) != 0;
    bad += boot(t_same, 0, 0) != 0;
    printf("3000 changes of the settings: %ld writes and erases of the flash\n", sh->ops);
    /* the power cut at any of the next writes, 3000 times */
    for (int k = 0; k < 3000; k++) {
        int r = boot(t_many, 1 + k % 5, 1 + rand() % 12);
        cuts += r == 7;
        bad += r != 7 && r != 0;
        r = boot(t_after_cut, k, 0);
        after += r != 0;
        bad += r != 0;
    }
    printf("the power cut in %d writes: %d starts after them wrong\n", cuts, after);
    bad += boot(t_table_keep, 3, 0) != 0;
    bad += boot(t_table_find, 3, 0) != 0;
    bad += boot(t_table_change, 6, 0) != 0;
    bad += boot(t_table_find, 6, 0) != 0;
    bad += boot(t_table_drop, 3, 0) != 0;
    bad += boot(t_table_none, 3, 0) != 0;
    /* (the power cut while a table is kept: nothing of it there after) */
    for (int k = 0; k < 60; k++) {
        bad += boot(t_table_drop, 5, 0) != 0;
        int r = boot(t_table_keep, 5, 1 + rand() % 540);
        bad += r != 7 && r != 0;
        if (r == 7)
            bad += boot(t_table_none, 5, 0) != 0;
    }
    bad += boot(t_net_keep, 983, 0) != 0;
    bad += boot(t_net_find, 983, 0) != 0;
    bad += boot(t_net_forget, 0, 0) != 0;
    bad += boot(t_net_none, 0, 0) != 0;
    bad += boot(t_same, 0, 0) != 0;
    for (uint32_t k = 0; k < 0x800000; k++)
        if (sh->mem[k] != (uint8_t)(k * 31 + (k >> 9))) {
            printf("WRONG: the flash's lower half changed at %x\n", k);
            bad++;
            break;
        }
    printf("refused by the flash's port: %d; asked while it was writing: %d; writes below 0x800000: %d\n", sh->refused, sh->early, sh->low);
    bad += sh->refused + sh->early + sh->low;
    printf("%s\n", bad ? "FAIL" : "PASS");
    return bad != 0;
}
