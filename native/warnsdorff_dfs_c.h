#ifndef WARNSDORFF_DFS_C_H
#define WARNSDORFF_DFS_C_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void dfs_init_default_neighbors(void);
void dfs_set_neighbor_tables(const int *counts, const int *flat_nbrs,
                             const uint64_t *mask_lo, const uint64_t *mask_hi);

int warnsdorff_dfs_run(
    int head,
    uint64_t rem_lo,
    uint64_t rem_hi,
    int nleft,
    int black,
    int required_end,
    int *nodes,
    int node_limit,
    int *path_out,
    int path_cap,
    int *path_len_out,
    int use_memo
);

#ifdef __cplusplus
}
#endif

#endif
