/* Warnsdorff DFS kernel — mirrors hampath._warnsdorff_dfs (no progress hooks). */
#include "dfs_common.h"
#include <stdlib.h>
#include <string.h>

/* Neighbor tables filled once from Python or static init. */
static int g_nbr_count[DFS_N];
static int g_nbrs[DFS_N][4];
static DfsMask g_nbr_mask[DFS_N];
static int g_tables_ready = 0;

void dfs_set_neighbor_tables(const int *counts, const int *flat_nbrs, const uint64_t *mask_lo, const uint64_t *mask_hi) {
    int i, k, off = 0;
    for (i = 0; i < DFS_N; i++) {
        g_nbr_count[i] = counts[i];
        for (k = 0; k < counts[i]; k++)
            g_nbrs[i][k] = flat_nbrs[off++];
        for (; k < 4; k++)
            g_nbrs[i][k] = -1;
        g_nbr_mask[i].lo = mask_lo[i];
        g_nbr_mask[i].hi = mask_hi[i];
    }
    g_tables_ready = 1;
}

void dfs_init_default_neighbors(void) {
    int i, r, c, n;
    if (g_tables_ready)
        return;
    for (i = 0; i < DFS_N; i++) {
        r = i / DFS_WIDTH;
        c = i % DFS_WIDTH;
        n = 0;
        g_nbr_mask[i] = dfs_mask_zero();
        if (r > 0) {
            g_nbrs[i][n++] = i - DFS_WIDTH;
            g_nbr_mask[i] = dfs_bit_set(g_nbr_mask[i], i - DFS_WIDTH);
        }
        if (r + 1 < DFS_HEIGHT) {
            g_nbrs[i][n++] = i + DFS_WIDTH;
            g_nbr_mask[i] = dfs_bit_set(g_nbr_mask[i], i + DFS_WIDTH);
        }
        if (c > 0) {
            g_nbrs[i][n++] = i - 1;
            g_nbr_mask[i] = dfs_bit_set(g_nbr_mask[i], i - 1);
        }
        if (c + 1 < DFS_WIDTH) {
            g_nbrs[i][n++] = i + 1;
            g_nbr_mask[i] = dfs_bit_set(g_nbr_mask[i], i + 1);
        }
        g_nbr_count[i] = n;
        while (n < 4)
            g_nbrs[i][n++] = -1;
    }
    g_tables_ready = 1;
}

static inline int dfs_degree(int i, DfsMask rem) {
    return dfs_mask_popcount(dfs_mask_and(g_nbr_mask[i], rem));
}

DfsMask dfs_reachable_mask(int start, DfsMask rem) {
    DfsMask seen = dfs_mask_zero();
    int stack[DFS_N];
    int sp = 0;
    if (!dfs_bit_test(rem, start))
        return seen;
    stack[sp++] = start;
    while (sp) {
        int i = stack[--sp];
        if (dfs_bit_test(seen, i))
            continue;
        seen = dfs_bit_set(seen, i);
        DfsMask rest = dfs_mask_not_and(dfs_mask_and(g_nbr_mask[i], rem), seen);
        while (!dfs_mask_empty(rest)) {
            int b = dfs_mask_lowest(rest);
            stack[sp++] = b;
            rest = dfs_mask_clear_lowest(rest);
        }
    }
    return seen;
}

/* ---- failure memo (open addressing) ---- */
typedef struct {
    uint64_t rem_lo, rem_hi;
    int16_t head;
    int16_t required_end; /* -1 = None */
    uint8_t used;
} MemoSlot;

typedef struct {
    MemoSlot *slots;
    size_t cap;
    size_t count;
} MemoTable;

static uint64_t memo_hash(int head, DfsMask rem, int required_end) {
    uint64_t h = (uint64_t)(uint32_t)head * 0x9E3779B97F4A7C15ULL;
    h ^= rem.lo + 0xC2B2AE3D27D4EB4FULL;
    h *= 0x165667B19E3779F9ULL;
    h ^= rem.hi + 0x85EBCA77C2B2AE63ULL;
    h ^= (uint64_t)(uint32_t)(required_end + 1) * 0x27D4EB2F165667C5ULL;
    return h;
}

static int memo_lookup(MemoTable *t, int head, DfsMask rem, int required_end) {
    size_t i, start;
    if (!t || !t->slots || t->cap == 0)
        return 0;
    start = (size_t)(memo_hash(head, rem, required_end) & (t->cap - 1));
    i = start;
    do {
        MemoSlot *s = &t->slots[i];
        if (!s->used)
            return 0;
        if (s->head == head && s->required_end == required_end &&
            s->rem_lo == rem.lo && s->rem_hi == rem.hi)
            return 1;
        i = (i + 1) & (t->cap - 1);
    } while (i != start);
    return 0;
}

static int memo_grow(MemoTable *t);

static void memo_insert(MemoTable *t, int head, DfsMask rem, int required_end) {
    size_t i;
    if (!t)
        return;
    if (t->cap == 0) {
        t->cap = 1024;
        t->slots = (MemoSlot *)calloc(t->cap, sizeof(MemoSlot));
        t->count = 0;
        if (!t->slots)
            return;
    }
    if (t->count * 2 >= t->cap) {
        if (!memo_grow(t))
            return;
    }
    i = (size_t)(memo_hash(head, rem, required_end) & (t->cap - 1));
    for (;;) {
        MemoSlot *s = &t->slots[i];
        if (!s->used) {
            s->used = 1;
            s->head = (int16_t)head;
            s->required_end = (int16_t)required_end;
            s->rem_lo = rem.lo;
            s->rem_hi = rem.hi;
            t->count++;
            return;
        }
        if (s->head == head && s->required_end == required_end &&
            s->rem_lo == rem.lo && s->rem_hi == rem.hi)
            return;
        i = (i + 1) & (t->cap - 1);
    }
}

static int memo_grow(MemoTable *t) {
    MemoSlot *old = t->slots;
    size_t old_cap = t->cap;
    size_t i;
    t->cap *= 2;
    t->slots = (MemoSlot *)calloc(t->cap, sizeof(MemoSlot));
    if (!t->slots) {
        t->slots = old;
        t->cap = old_cap;
        return 0;
    }
    t->count = 0;
    for (i = 0; i < old_cap; i++) {
        if (old[i].used) {
            DfsMask rem = {old[i].rem_lo, old[i].rem_hi};
            memo_insert(t, old[i].head, rem, old[i].required_end);
        }
    }
    free(old);
    return 1;
}

static void memo_free(MemoTable *t) {
    if (t && t->slots) {
        free(t->slots);
        t->slots = NULL;
        t->cap = 0;
        t->count = 0;
    }
}

typedef struct {
    int *path;
    int path_len;
    int path_cap;
    int *nodes;
    int node_limit;
    MemoTable *memo;
    int use_memo;
} DfsCtx;

static int dfs_fail(DfsCtx *ctx, int added) {
    if (ctx->path && added > 0)
        ctx->path_len -= added;
    return 0;
}

static int warnsdorff_dfs_inner(
    int head,
    DfsMask rem,
    int nleft,
    int black,
    int required_end,
    DfsCtx *ctx
) {
    int added = 0;
    dfs_init_default_neighbors();

    while (1) {
        int white, n_open, black_open, hr;
        int nbrs[4];
        int nn = 0;
        int isolated[4];
        int niso = 0;
        int n_deg1, deg1_open[3];
        DfsMask open_cells, rscan;
        int k, i, d;

        if (ctx->use_memo && memo_lookup(ctx->memo, head, rem, required_end))
            return dfs_fail(ctx, added);

        if (ctx->node_limit) {
            ctx->nodes[0] += 1;
            if (ctx->nodes[0] > ctx->node_limit)
                return dfs_fail(ctx, added);
        }

        if (nleft <= 1) {
            if (required_end < 0 || head == required_end) {
                if (ctx->path && ctx->path_len < ctx->path_cap)
                    ctx->path[ctx->path_len++] = head;
                return 1;
            }
            return dfs_fail(ctx, added);
        }
        if (required_end >= 0 && head == required_end)
            return dfs_fail(ctx, added);

        white = nleft - black;
        if (nleft & 1) {
            if (dfs_color_of(head)) {
                if (black != white + 1)
                    return dfs_fail(ctx, added);
            } else if (white != black + 1) {
                return dfs_fail(ctx, added);
            }
        } else if (black != white) {
            return dfs_fail(ctx, added);
        }

        open_cells = dfs_bit_clear(rem, head);
        n_open = nleft - 1;
        black_open = black - (dfs_color_of(head) ? 1 : 0);

        for (k = 0; k < g_nbr_count[head]; k++) {
            int n = g_nbrs[head][k];
            if (dfs_bit_test(open_cells, n))
                nbrs[nn++] = n;
        }
        if (!nn)
            return dfs_fail(ctx, added);

        for (k = 0; k < nn; k++) {
            if (dfs_degree(nbrs[k], open_cells) == 0)
                isolated[niso++] = nbrs[k];
        }
        if (niso) {
            if (niso > 1 || n_open != 1)
                return dfs_fail(ctx, added);
            nbrs[0] = isolated[0];
            nn = 1;
        }

        if (nn == 1) {
            if (ctx->path && ctx->path_len < ctx->path_cap) {
                ctx->path[ctx->path_len++] = head;
                added++;
            }
            head = nbrs[0];
            rem = open_cells;
            nleft = n_open;
            black = black_open;
            continue;
        }

        n_deg1 = 0;
        rscan = open_cells;
        while (!dfs_mask_empty(rscan)) {
            i = dfs_mask_lowest(rscan);
            rscan = dfs_mask_clear_lowest(rscan);
            d = dfs_degree(i, open_cells);
            if (d == 0)
                return dfs_fail(ctx, added);
            if (d == 1) {
                n_deg1++;
                if (n_deg1 > 2)
                    return dfs_fail(ctx, added);
                deg1_open[n_deg1 - 1] = i;
            }
        }
        if (n_deg1 == 2) {
            int filtered[4];
            int nf = 0;
            for (k = 0; k < nn; k++) {
                if (nbrs[k] == deg1_open[0] || nbrs[k] == deg1_open[1])
                    filtered[nf++] = nbrs[k];
            }
            if (!nf)
                return dfs_fail(ctx, added);
            for (k = 0; k < nf; k++)
                nbrs[k] = filtered[k];
            nn = nf;
        }

        /* Warnsdorff sort: low remaining degree, then serpentine tie-break */
        hr = head / DFS_WIDTH;
        for (k = 0; k < nn; k++) {
            int best = k;
            int bk, bdeg, btie, jk, jdeg, jtie;
            bdeg = dfs_degree(nbrs[k], open_cells);
            btie = ((hr % 2 == 0 && nbrs[k] == head + 1) || (hr % 2 == 1 && nbrs[k] == head - 1)) ? 0 : 1;
            for (jk = k + 1; jk < nn; jk++) {
                jdeg = dfs_degree(nbrs[jk], open_cells);
                jtie = ((hr % 2 == 0 && nbrs[jk] == head + 1) || (hr % 2 == 1 && nbrs[jk] == head - 1)) ? 0 : 1;
                if (jdeg < bdeg || (jdeg == bdeg && jtie < btie)) {
                    best = jk;
                    bdeg = jdeg;
                    btie = jtie;
                }
            }
            if (best != k) {
                int tmp = nbrs[k];
                nbrs[k] = nbrs[best];
                nbrs[best] = tmp;
            }
        }

        if (ctx->path && ctx->path_len < ctx->path_cap) {
            ctx->path[ctx->path_len++] = head;
            added++;
        }

        for (k = 0; k < nn; k++) {
            int n = nbrs[k];
            if (!dfs_mask_eq(dfs_reachable_mask(n, open_cells), open_cells))
                continue;
            if (warnsdorff_dfs_inner(n, open_cells, n_open, black_open, required_end, ctx))
                return 1;
        }

        if (ctx->use_memo)
            memo_insert(ctx->memo, head, rem, required_end);
        return dfs_fail(ctx, added);
    }
}

/* Public API used by the Python module and Cython wrapper. */
int warnsdorff_dfs_run(
    int head,
    uint64_t rem_lo,
    uint64_t rem_hi,
    int nleft,
    int black,
    int required_end, /* -1 = None */
    int *nodes,
    int node_limit,
    int *path_out,
    int path_cap,
    int *path_len_out,
    int use_memo
) {
    DfsMask rem = {rem_lo, rem_hi};
    DfsCtx ctx;
    MemoTable memo;
    int ok;

    memset(&ctx, 0, sizeof(ctx));
    memset(&memo, 0, sizeof(memo));
    ctx.nodes = nodes;
    ctx.node_limit = node_limit;
    ctx.path = path_out;
    ctx.path_cap = path_cap;
    ctx.path_len = 0;
    ctx.use_memo = use_memo;
    ctx.memo = use_memo ? &memo : NULL;

    ok = warnsdorff_dfs_inner(head, rem, nleft, black, required_end, &ctx);
    if (path_len_out)
        *path_len_out = ctx.path_len;
    memo_free(&memo);
    return ok;
}
