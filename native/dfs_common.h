/* Shared DFS bitmask helpers for 10x9 = 90 cells. */
#ifndef DFS_COMMON_H
#define DFS_COMMON_H

#include <stdint.h>
#include <string.h>

#if defined(_MSC_VER)
#include <intrin.h>
#endif

#define DFS_N 90
#define DFS_WIDTH 10
#define DFS_HEIGHT 9

typedef struct {
    uint64_t lo;
    uint64_t hi;
} DfsMask;

static inline DfsMask dfs_mask_zero(void) {
    DfsMask m = {0, 0};
    return m;
}

static inline int dfs_bit_test(DfsMask m, int i) {
    if (i < 64)
        return (int)((m.lo >> i) & 1ULL);
    return (int)((m.hi >> (i - 64)) & 1ULL);
}

static inline DfsMask dfs_bit_set(DfsMask m, int i) {
    if (i < 64)
        m.lo |= 1ULL << i;
    else
        m.hi |= 1ULL << (i - 64);
    return m;
}

static inline DfsMask dfs_bit_clear(DfsMask m, int i) {
    if (i < 64)
        m.lo &= ~(1ULL << i);
    else
        m.hi &= ~(1ULL << (i - 64));
    return m;
}

static inline DfsMask dfs_mask_and(DfsMask a, DfsMask b) {
    DfsMask m = {a.lo & b.lo, a.hi & b.hi};
    return m;
}

static inline DfsMask dfs_mask_xor(DfsMask a, DfsMask b) {
    DfsMask m = {a.lo ^ b.lo, a.hi ^ b.hi};
    return m;
}

static inline DfsMask dfs_mask_not_and(DfsMask a, DfsMask b) {
    DfsMask m = {a.lo & ~b.lo, a.hi & ~b.hi};
    return m;
}

static inline int dfs_mask_eq(DfsMask a, DfsMask b) {
    return a.lo == b.lo && a.hi == b.hi;
}

static inline int dfs_mask_empty(DfsMask m) {
    return m.lo == 0 && m.hi == 0;
}

static inline int dfs_ctz64(uint64_t x) {
#if defined(_MSC_VER)
    unsigned long idx;
    _BitScanForward64(&idx, x);
    return (int)idx;
#else
    return __builtin_ctzll(x);
#endif
}

static inline int dfs_popcount64(uint64_t x) {
#if defined(_MSC_VER)
    return (int)__popcnt64(x);
#else
    return __builtin_popcountll(x);
#endif
}

static inline int dfs_mask_popcount(DfsMask m) {
    return dfs_popcount64(m.lo) + dfs_popcount64(m.hi);
}

static inline int dfs_mask_lowest(DfsMask m) {
    if (m.lo)
        return dfs_ctz64(m.lo);
    return 64 + dfs_ctz64(m.hi);
}

static inline DfsMask dfs_mask_clear_lowest(DfsMask m) {
    if (m.lo) {
        m.lo &= m.lo - 1;
        return m;
    }
    m.hi &= m.hi - 1;
    return m;
}

static inline int dfs_color_of(int i) {
    int r = i / DFS_WIDTH;
    int c = i % DFS_WIDTH;
    return (r + c) & 1;
}

#endif /* DFS_COMMON_H */
