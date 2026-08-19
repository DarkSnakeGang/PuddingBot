"""Hamiltonian *path* (not cycle) on a 10x9 wall grid.

Walkable cells are anything other than 2 (wall). A path visits every
walkable cell exactly once; it does not need to close.

Prunes, in order:
  1. Bipartite coloring: |black-white| >= 2 is impossible.
  2. More than two degree-1 cells is impossible (those must be endpoints).
  3. A degree-1 cell of the minority color is impossible when |B-W|=1.
  4. Disconnected leftover graph, isolated cells, leftover color parity.
  5. Warnsdorff-ordered exhaustive DFS (low-degree first, serpentine
     tie-break, forced corridors). Timeouts never count as no.
"""

import threading
import time

WIDTH = 10
HEIGHT = 9
N = WIDTH * HEIGHT
WALL = 2

# UP DOWN LEFT RIGHT
DY = (-1, 1, 0, 0)
DX = (0, 0, -1, 1)
OPP = (1, 0, 3, 2)

_tls = threading.local()


class SearchProgress:
    """Rate-limited status lines for a single-board search."""

    def __init__(self, emit, interval=1.0):
        self.emit = emit
        self.interval = interval
        self.t0 = time.perf_counter()
        self._last = 0.0
        self.steps = 0
        self.phase = "start"

    def set_phase(self, phase):
        self.phase = phase
        self.steps = 0
        self._send(force=True)

    def add(self, n=1, extra=""):
        """Cheap increment for tight DFS. Time is checked every 8192 steps."""
        self.steps += n
        if (self.steps & 8191) != 0:
            return
        self._maybe_send(extra)

    def tick(self, extra=""):
        """Increment and check the clock. Use from slower recursive solvers."""
        self.steps += 1
        self._maybe_send(extra)

    def _maybe_send(self, extra=""):
        now = time.perf_counter()
        if now - self._last >= self.interval:
            self._send(extra=extra)

    def _send(self, extra="", force=False):
        now = time.perf_counter()
        if not force and now - self._last < self.interval:
            return
        self._last = now
        elapsed = now - self.t0
        parts = [f"{elapsed:.0f}s", self.phase]
        if self.steps:
            rate = self.steps / elapsed if elapsed else 0
            parts.append(f"{self.steps:,} steps")
            if elapsed >= 1:
                parts.append(f"{rate:,.0f}/s")
        if extra:
            parts.append(extra)
        self.emit(" · ".join(parts))


class progress_scope:
    def __init__(self, emit, interval=1.0):
        self.progress = SearchProgress(emit, interval)

    def __enter__(self):
        _tls.progress = self.progress
        return self.progress

    def __exit__(self, *_exc):
        _tls.progress = None


def current_progress():
    return getattr(_tls, "progress", None)


def _idx(r, c):
    return r * WIDTH + c


def _neighbors_of(i):
    r, c = divmod(i, WIDTH)
    out = []
    if r > 0:
        out.append(i - WIDTH)
    if r + 1 < HEIGHT:
        out.append(i + WIDTH)
    if c > 0:
        out.append(i - 1)
    if c + 1 < WIDTH:
        out.append(i + 1)
    return tuple(out)


NEIGHBORS = tuple(_neighbors_of(i) for i in range(N))
NBR_MASK = tuple(sum(1 << n for n in NEIGHBORS[i]) for i in range(N))


def coloring_allows_path(grid):
    """True iff a ham path is not ruled out by checkerboard coloring."""
    black = white = 0
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if cell != WALL:
                if (r + c) & 1:
                    black += 1
                else:
                    white += 1
    return abs(black - white) <= 1


def bits_flip_h(bits: str) -> str:
    """Left-right mirror of a bit(90) 10x9 pattern."""
    bits = bits.replace(" ", "")
    return "".join(
        bits[r * WIDTH + (WIDTH - 1 - c)]
        for r in range(HEIGHT)
        for c in range(WIDTH)
    )


def bits_flip_v(bits: str) -> str:
    """Up-down mirror of a bit(90) 10x9 pattern."""
    bits = bits.replace(" ", "")
    return "".join(
        bits[(HEIGHT - 1 - r) * WIDTH + c]
        for r in range(HEIGHT)
        for c in range(WIDTH)
    )


def bits_rot180(bits: str) -> str:
    return bits_flip_h(bits_flip_v(bits))


def pattern_orbit(bits: str) -> tuple[str, ...]:
    """Identity, H-flip, V-flip, 180° — the symmetries of a 10x9 rectangle."""
    bits = bits.replace(" ", "")
    seen = []
    for img in (bits, bits_flip_h(bits), bits_flip_v(bits), bits_rot180(bits)):
        if img not in seen:
            seen.append(img)
    return tuple(seen)


def pack_tour(tour):
    """Encode [(row, col), ...] as cell-index bytes, or None."""
    if not tour:
        return None
    return bytes((int(r) * WIDTH + int(c)) & 255 for r, c in tour)


def unpack_tour(data):
    """Decode pack_tour bytes to [(row, col), ...], or None."""
    if not data:
        return None
    if isinstance(data, memoryview):
        data = data.tobytes()
    return [divmod(b, WIDTH) for b in data]


def tour_for_image(src_bits: str, tour, dest_bits: str):
    """Map a tour from src_bits onto another board in the same Klein orbit."""
    if not tour:
        return None
    src = src_bits.replace(" ", "")
    dest = dest_bits.replace(" ", "")
    if dest == src:
        return [tuple(p) for p in tour]
    if dest == bits_flip_h(src):
        return [(r, WIDTH - 1 - c) for r, c in tour]
    if dest == bits_flip_v(src):
        return [(HEIGHT - 1 - r, c) for r, c in tour]
    if dest == bits_rot180(src):
        return [(HEIGHT - 1 - r, WIDTH - 1 - c) for r, c in tour]
    return [tuple(p) for p in tour]


def bits_to_grid(bits: str):
    """bit(90) text: '1' = wall, '0' = empty. Also accepts legacy '2'/'1'."""
    bits = bits.replace(" ", "")
    if set(bits) <= {"1", "2"}:
        bits = bits.translate(str.maketrans("12", "01"))
    grid = []
    for r in range(HEIGHT):
        row = []
        for c in range(WIDTH):
            row.append(2 if bits[r * WIDTH + c] == "1" else 1)
        grid.append(row)
    return grid


def _color_of(i):
    r, c = divmod(i, WIDTH)
    return (r + c) & 1


def _free_mask(grid):
    free = 0
    for r in range(HEIGHT):
        row = grid[r]
        for c in range(WIDTH):
            if row[c] != WALL:
                free |= 1 << _idx(r, c)
    return free


def _degree(i, remaining):
    return (NBR_MASK[i] & remaining).bit_count()


def _reachable_mask(start, rem):
    """Bitmask of cells in rem reachable from start (start must be in rem)."""
    seen = 0
    stack = [start]
    while stack:
        i = stack.pop()
        bit = 1 << i
        if seen & bit:
            continue
        seen |= bit
        rest = (NBR_MASK[i] & rem) & ~seen
        while rest:
            b = rest & -rest
            stack.append(b.bit_length() - 1)
            rest ^= b
    return seen


def _early_impossible(grid):
    """Cheap graph prunes. True means no path. False means 'not sure'."""
    free = _free_mask(grid)
    nfree = free.bit_count()
    if nfree <= 1:
        return False
    deg1 = []
    black = white = 0
    for i in range(N):
        if not (free & (1 << i)):
            continue
        if _color_of(i):
            black += 1
        else:
            white += 1
        d = _degree(i, free)
        if d == 0:
            return True
        if d == 1:
            deg1.append(i)
    if abs(black - white) > 1:
        return True
    start = (free & -free).bit_length() - 1
    if _reachable_mask(start, free) != free:
        return True
    if len(deg1) > 2:
        return True
    n = black + white
    if n % 2 == 1:
        majority = 1 if black > white else 0
        for i in deg1:
            if _color_of(i) != majority:
                return True
    elif len(deg1) == 2 and _color_of(deg1[0]) == _color_of(deg1[1]):
        return True
    return False


def _color_count(rem):
    black = 0
    r = rem
    while r:
        b = r & -r
        if _color_of(b.bit_length() - 1):
            black += 1
        r ^= b
    return black


def _warnsdorff_dfs(head, rem, nleft, black, required_end=None, nodes=None, node_limit=0, path=None):
    """Exhaustive ham path from head covering rem. Neighbors in Warnsdorff order.

    Completeness: every neighbor is tried on backtrack. Speed: low-degree first,
    serpentine tie-break, forced corridors. If path is a list, it is filled with
    cell indexes of a covering path on success.
    """
    prog = current_progress()
    origin_len = len(path) if path is not None else None
    if path is not None:
        path.append(head)
    while True:
        if node_limit:
            nodes[0] += 1
            if nodes[0] > node_limit:
                if path is not None:
                    del path[origin_len:]
                return False
            if prog is not None:
                prog.add(1)
        elif prog is not None:
            prog.add(1)
        if nleft <= 1:
            ok = required_end is None or head == required_end
            if not ok and path is not None:
                del path[origin_len:]
            return ok
        if required_end is not None and head == required_end:
            if path is not None:
                del path[origin_len:]
            return False
        white = nleft - black
        if nleft & 1:
            if _color_of(head):
                if black != white + 1:
                    if path is not None:
                        del path[origin_len:]
                    return False
            elif white != black + 1:
                if path is not None:
                    del path[origin_len:]
                return False
        elif black != white:
            if path is not None:
                del path[origin_len:]
            return False
        open_cells = rem ^ (1 << head)
        n_open = nleft - 1
        black_open = black - (1 if _color_of(head) else 0)
        nbrs = [n for n in NEIGHBORS[head] if open_cells & (1 << n)]
        if not nbrs:
            if path is not None:
                del path[origin_len:]
            return False
        isolated = [n for n in nbrs if (NBR_MASK[n] & open_cells) == 0]
        if isolated:
            if len(isolated) > 1 or n_open != 1:
                if path is not None:
                    del path[origin_len:]
                return False
            nbrs = isolated
        if len(nbrs) == 1:
            head = nbrs[0]
            rem = open_cells
            nleft = n_open
            black = black_open
            if path is not None:
                path.append(head)
            continue
        n_deg1 = 0
        deg1_open = []
        r = open_cells
        while r:
            b = r & -r
            i = b.bit_length() - 1
            d = (NBR_MASK[i] & open_cells).bit_count()
            if d == 0:
                if path is not None:
                    del path[origin_len:]
                return False
            if d == 1:
                n_deg1 += 1
                if n_deg1 > 2:
                    if path is not None:
                        del path[origin_len:]
                    return False
                deg1_open.append(i)
            r ^= b
        if n_deg1 == 2:
            nbrs = [n for n in nbrs if n in set(deg1_open)]
            if not nbrs:
                if path is not None:
                    del path[origin_len:]
                return False
        hr = head // WIDTH
        nbrs.sort(
            key=lambda n: (
                (NBR_MASK[n] & open_cells).bit_count(),
                0 if (hr % 2 == 0 and n == head + 1) or (hr % 2 == 1 and n == head - 1) else 1,
            )
        )
        for n in nbrs:
            if _reachable_mask(n, open_cells) != open_cells:
                continue
            if _warnsdorff_dfs(
                n, open_cells, n_open, black_open, required_end, nodes, node_limit, path
            ):
                return True
        if path is not None:
            del path[origin_len:]
        return False


def _path_starts(free, nfree, deg1):
    if deg1:
        return deg1[:1]
    black = _color_count(free)
    white = nfree - black
    if nfree & 1:
        maj = 1 if black > white else 0
        starts = [i for i in range(N) if (free & (1 << i)) and _color_of(i) == maj]
    else:
        starts = [i for i in range(N) if (free & (1 << i)) and _color_of(i)]
    starts.sort(key=lambda i: _degree(i, free))
    return starts


def _exhaustive_ham_path(grid, node_limit=0, budgets=None, path=None):
    """Warnsdorff-ordered DFS. Completes every branch; no timeout-as-no.

    Iterative deepening over starts so a good endpoint is tried before
    exhausting a bad one. node_limit > 0 is a yes-filter only.
    budgets: explicit list; 0 means unlimited. Default IDA then unlimited.
    If path is a list, it receives cell indexes of a covering path on success.
    """
    free = _free_mask(grid)
    nfree = free.bit_count()
    if nfree <= 1:
        if path is not None:
            path.clear()
            for i in range(N):
                if free & (1 << i):
                    path.append(i)
                    break
        return True
    black = _color_count(free)
    deg1 = [i for i in range(N) if (free & (1 << i)) and _degree(i, free) == 1]
    starts = _path_starts(free, nfree, deg1)
    required_end = deg1[1] if len(deg1) == 2 else None
    if budgets is None:
        if node_limit:
            budgets = (node_limit,)
        else:
            budgets = (4_000, 16_000, 64_000, 0)
    prog = current_progress()
    for budget in budgets:
        label = "unlimited" if not budget else f"{budget:,} node cap"
        if prog is not None:
            prog.set_phase(f"path DFS ({label})")
        nodes = [0] if budget else None
        for s in starts:
            if budget:
                nodes[0] = 0
            if path is not None:
                path.clear()
            if _warnsdorff_dfs(s, free, nfree, black, required_end, nodes, budget, path):
                return True
    if path is not None:
        path.clear()
    return False


def _in_bounds(x, y):
    return 0 <= x < WIDTH and 0 <= y < HEIGHT


class PathBoard:
    """Forced snake-fill + guess. 1=empty, 2=wall, 3=snake piece."""

    last_win = None
    __slots__ = ("w", "s", "nfree", "ends", "dead", "_g", "_deadline", "_timed_out")

    def __init__(self, grid):
        self.w = [row[:] for row in grid]
        self.s = [[[0, 0, 0, 0] for _ in range(WIDTH)] for _ in range(HEIGHT)]
        self.nfree = sum(cell != WALL for row in grid for cell in row)
        self.ends = 0
        self.dead = False
        self._g = 0
        self._deadline = 0.0
        self._timed_out = False

    def clone(self):
        b = PathBoard.__new__(PathBoard)
        b.w = [row[:] for row in self.w]
        b.s = [[cell[:] for cell in row] for row in self.s]
        b.nfree = self.nfree
        b.ends = self.ends
        b.dead = self.dead
        b._g = getattr(self, "_g", 0)
        b._deadline = getattr(self, "_deadline", 0.0)
        b._timed_out = getattr(self, "_timed_out", False)
        return b

    def adj(self, x, y):
        a = [0, 0, 0, 0]
        for d in range(4):
            nx, ny = x + DX[d], y + DY[d]
            if not _in_bounds(nx, ny):
                a[d] = 1
            elif self.w[ny][nx] == 2:
                a[d] = 1
            elif self.w[ny][nx] == 3:
                a[d] = 2 if self.s[ny][nx][OPP[d]] else 1
        return a

    def place(self, x, y, dirs):
        self.w[y][x] = 3
        self.s[y][x] = [0, 0, 0, 0]
        for d in dirs:
            self.s[y][x][d] = 1
        if len(dirs) == 1:
            self.ends += 1

    def _other_dir(self, x, y, came):
        found = None
        for d in range(4):
            if self.s[y][x][d] and d != came:
                if found is not None:
                    return found  # shouldn't happen
                found = d
        return found

    def _join_cycle_len(self, x, y, d1, d2):
        """If connecting d1 and d2 at (x,y) closes a snake loop, return that
        loop length (including the new cell). Otherwise 0."""
        n1x, n1y = x + DX[d1], y + DY[d1]
        n2x, n2y = x + DX[d2], y + DY[d2]
        if not (_in_bounds(n1x, n1y) and _in_bounds(n2x, n2y)):
            return 0
        if self.w[n1y][n1x] != 3 or self.w[n2y][n2x] != 3:
            return 0
        if not self.s[n1y][n1x][OPP[d1]] or not self.s[n2y][n2x][OPP[d2]]:
            return 0
        cx, cy = n1x, n1y
        came = OPP[d1]
        length = 1
        for _ in range(self.nfree + 2):
            nxt = self._other_dir(cx, cy, came)
            if nxt is None:
                return 0
            nx, ny = cx + DX[nxt], cy + DY[nxt]
            length += 1
            if nx == n2x and ny == n2y:
                return length + 1
            cx, cy, came = nx, ny, OPP[nxt]
        return 0

    def join_ok(self, x, y, dirs):
        """True if placing a through-piece is allowed. 'full' if it is a ham cycle."""
        if len(dirs) != 2:
            return True
        loop = self._join_cycle_len(x, y, dirs[0], dirs[1])
        if not loop:
            return True
        if loop == self.nfree:
            return "full"
        return False

    def force(self):
        """Apply implied snake pieces. Returns True if a ham cycle/path is forced."""
        while not self.dead:
            changed = False
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    if self.w[y][x] != 1:
                        continue
                    a = self.adj(x, y)
                    n_block = a.count(1)
                    n_head = a.count(2)
                    if n_head >= 3:
                        self.dead = True
                        return False
                    if n_block == 4:
                        self.dead = True
                        return False
                    if n_block == 3:
                        if self.ends >= 2:
                            self.dead = True
                            return False
                        d = next(d for d in range(4) if a[d] != 1)
                        self.place(x, y, (d,))
                        changed = True
                        continue
                    heads = [d for d in range(4) if a[d] == 2]
                    opens = [d for d in range(4) if a[d] != 1]
                    if len(heads) == 2:
                        ok = self.join_ok(x, y, heads)
                        if ok == "full":
                            self.place(x, y, heads)
                            return self._win()
                        if ok:
                            # Merge two snake heads. Safe when they are not
                            # already on the same path; join_ok filters that.
                            self.place(x, y, heads)
                            changed = True
                            continue
                    if len(heads) == 2 and n_block == 2:
                        ok = self.join_ok(x, y, heads)
                        if ok == "full":
                            self.place(x, y, heads)
                            return self._win()
                        if not ok:
                            self.dead = True
                            return False
                        self.place(x, y, heads)
                        changed = True
                        continue
                    if self.ends >= 2 and n_block == 2:
                        ok = self.join_ok(x, y, opens)
                        if ok == "full":
                            self.place(x, y, opens)
                            return self._win()
                        if not ok:
                            self.dead = True
                            return False
                        self.place(x, y, opens)
                        changed = True
            if not changed:
                break
        return False

    def walk_from_end(self, x, y):
        d = next(d for d in range(4) if self.s[y][x][d])
        seen = {(x, y)}
        came = OPP[d]
        cx, cy = x + DX[d], y + DY[d]
        for _ in range(self.nfree + 2):
            if not _in_bounds(cx, cy) or self.w[cy][cx] != 3:
                return 0
            if (cx, cy) in seen:
                return 0
            seen.add((cx, cy))
            nxt = self._other_dir(cx, cy, came)
            if nxt is None:
                return len(seen)
            cx, cy, came = cx + DX[nxt], cy + DY[nxt], OPP[nxt]
        return 0

    def is_cover(self):
        ends = []
        snakes = 0
        for y in range(HEIGHT):
            for x in range(WIDTH):
                if self.w[y][x] == 1:
                    return False
                if self.w[y][x] == 3:
                    snakes += 1
                    deg = sum(self.s[y][x])
                    if deg == 1:
                        ends.append((x, y))
                    elif deg != 2:
                        return False
        if snakes != self.nfree:
            return False
        if len(ends) == 2:
            return self.walk_from_end(*ends[0]) == self.nfree
        if len(ends) == 0 and snakes:
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    if self.w[y][x] == 3:
                        loop = self._join_cycle_len(x, y, *[d for d in range(4) if self.s[y][x][d]][:2])
                        # walk around using the piece itself: follow one dir all the way back
                        ds = [d for d in range(4) if self.s[y][x][d]]
                        if len(ds) != 2:
                            return False
                        seen = {(x, y)}
                        cx, cy = x + DX[ds[0]], y + DY[ds[0]]
                        came = OPP[ds[0]]
                        for _ in range(self.nfree + 2):
                            if not _in_bounds(cx, cy) or self.w[cy][cx] != 3:
                                return False
                            if (cx, cy) in seen:
                                return False
                            seen.add((cx, cy))
                            nxt = self._other_dir(cx, cy, came)
                            if nxt is None:
                                return False
                            nx, ny = cx + DX[nxt], cy + DY[nxt]
                            if nx == x and ny == y:
                                return len(seen) == self.nfree
                            cx, cy, came = nx, ny, OPP[nxt]
                        return False
        return False

    def pick_empty(self):
        best = None
        best_open = 5
        for y in range(HEIGHT):
            for x in range(WIDTH):
                if self.w[y][x] != 1:
                    continue
                n_open = 4 - self.adj(x, y).count(1)
                if n_open < best_open:
                    best_open = n_open
                    best = (x, y)
                    if n_open <= 2:
                        return best
        return best

    def guesses(self, x, y, allow_new_ends=False):
        opens = [d for d in range(4) if self.adj(x, y)[d] != 1]
        out = []
        for i in range(len(opens)):
            for j in range(i + 1, len(opens)):
                out.append((opens[i], opens[j]))
        if allow_new_ends and self.ends < 2:
            for d in opens:
                out.append((d,))
        return out

    def path_cells(self):
        """Return the covering path as (row, col) cells, or None."""
        if not self.is_cover():
            return None
        ends = [
            (x, y)
            for y in range(HEIGHT)
            for x in range(WIDTH)
            if self.w[y][x] == 3 and sum(self.s[y][x]) == 1
        ]
        if len(ends) == 2:
            x, y = ends[0]
            d = next(d for d in range(4) if self.s[y][x][d])
            cells = [(y, x)]
            came = OPP[d]
            cx, cy = x + DX[d], y + DY[d]
            for _ in range(self.nfree):
                cells.append((cy, cx))
                nxt = self._other_dir(cx, cy, came)
                if nxt is None:
                    return cells if len(cells) == self.nfree else None
                cx, cy, came = cx + DX[nxt], cy + DY[nxt], OPP[nxt]
            return None
        # cycle: pick any snake cell and walk
        for y in range(HEIGHT):
            for x in range(WIDTH):
                if self.w[y][x] == 3:
                    ds = [d for d in range(4) if self.s[y][x][d]]
                    if len(ds) != 2:
                        continue
                    cells = [(y, x)]
                    cx, cy = x + DX[ds[0]], y + DY[ds[0]]
                    came = OPP[ds[0]]
                    for _ in range(self.nfree):
                        cells.append((cy, cx))
                        if cx == x and cy == y:
                            return cells[:-1]
                        nxt = self._other_dir(cx, cy, came)
                        if nxt is None:
                            return None
                        cx, cy, came = cx + DX[nxt], cy + DY[nxt], OPP[nxt]
                    return None
        return None


    def _win(self):
        PathBoard.last_win = self
        return True

    def original_deg2(self):
        cells = []
        for y in range(HEIGHT):
            for x in range(WIDTH):
                if self.w[y][x] == 1 and self.adj(x, y).count(1) == 2:
                    cells.append((x, y))
        return cells

    def _place_through(self, x, y):
        if self.w[y][x] != 1:
            return True
        opens = [d for d in range(4) if self.adj(x, y)[d] != 1]
        if len(opens) != 2:
            return True
        ok = self.join_ok(x, y, opens)
        if ok == "full":
            self.place(x, y, opens)
            return "full"
        if not ok:
            self.dead = True
            return False
        self.place(x, y, opens)
        return True

    def _guess_rest(self, allow_new_ends=False):
        """Through-only fill by default (cycle-solver style). Nested endpoint
        guesses explode; choose the two ends up front instead."""
        self._g += 1
        prog = current_progress()
        if prog is not None:
            prog.tick()
        if self._deadline and time.perf_counter() > self._deadline:
            self._timed_out = True
            return False
        if self.force():
            return True
        if self.dead:
            return False
        if self.is_cover():
            return self._win()
        cell = self.pick_empty()
        if cell is None:
            return False
        x, y = cell
        for piece in self.guesses(x, y, allow_new_ends=allow_new_ends):
            nxt = self.clone()
            if len(piece) == 1:
                if nxt.ends >= 2:
                    continue
            else:
                ok = nxt.join_ok(x, y, piece)
                if ok == "full":
                    nxt.place(x, y, piece)
                    return nxt._win()
                if not ok:
                    continue
            nxt.place(x, y, piece)
            if nxt._guess_rest(allow_new_ends=allow_new_ends):
                return True
            if nxt._timed_out:
                self._timed_out = True
                return False
        return False

    def _dirs_of(self, cell):
        x, y = cell
        return [d for d in range(4) if self.adj(x, y)[d] != 1]

    def _legal_end_cells(self):
        empties = [
            (x, y)
            for y in range(HEIGHT)
            for x in range(WIDTH)
            if self.w[y][x] == 1
        ]
        empties.sort(key=lambda p: 4 - self.adj(p[0], p[1]).count(1))
        n = self.nfree

        def col(p):
            return (p[0] + p[1]) & 1

        if n % 2 == 1:
            black = sum(
                1
                for y in range(HEIGHT)
                for x in range(WIDTH)
                if self.w[y][x] != 2 and ((x + y) & 1)
            )
            maj = 1 if black > n - black else 0
            return [p for p in empties if col(p) == maj], None
        return [p for p in empties if col(p) == 1], [p for p in empties if col(p) == 0]

    def _try_end_pair(self, a, b):
        if a == b:
            return False
        if self._deadline and time.perf_counter() > self._deadline:
            self._timed_out = True
            return False
        for da in self._dirs_of(a):
            for db in self._dirs_of(b):
                c = self.clone()
                c._g = 0
                if c.w[a[1]][a[0]] != 1 or c.w[b[1]][b[0]] != 1:
                    continue
                c.place(a[0], a[1], (da,))
                c.place(b[0], b[1], (db,))
                if c._guess_rest(allow_new_ends=False):
                    return True
                if c._timed_out:
                    self._timed_out = True
                    return False
        return False

    def _solve_remaining_ends(self):
        """Pick leftover endpoints among remaining empties, then through-fill."""
        if self.force():
            return True
        if self.dead:
            return False
        if self.is_cover():
            return self._win()
        need = 2 - self.ends
        if need <= 0:
            return self._guess_rest(allow_new_ends=False)
        group_a, group_b = self._legal_end_cells()
        if need == 1:
            already = [
                (x, y)
                for y in range(HEIGHT)
                for x in range(WIDTH)
                if self.w[y][x] == 3 and sum(self.s[y][x]) == 1
            ]
            placed_col = None
            if already:
                placed_col = (already[0][0] + already[0][1]) & 1
            cands = group_a if group_b is None else (
                group_b if placed_col == 1 else group_a
            )
            for p in cands:
                for d in self._dirs_of(p):
                    c = self.clone()
                    if c.w[p[1]][p[0]] != 1:
                        continue
                    c.place(p[0], p[1], (d,))
                    if c._guess_rest(allow_new_ends=False):
                        return True
            return False
        if group_b is None:
            for i in range(len(group_a)):
                for j in range(i + 1, len(group_a)):
                    if self._try_end_pair(group_a[i], group_a[j]):
                        return True
            return False
        for s in group_a:
            for t in group_b:
                if self._try_end_pair(s, t):
                    return True
        return False

    def _try_deg2_exceptions(self, deg2, exceptions, end_dirs):
        b = self.clone()
        ex = set(exceptions)
        for (x, y), d in zip(exceptions, end_dirs):
            if b.w[y][x] != 1:
                return False
            a = b.adj(x, y)
            if a[d] == 1:
                return False
            b.place(x, y, (d,))
        for x, y in deg2:
            if (x, y) in ex:
                continue
            r = b._place_through(x, y)
            if r == "full":
                return b._win()
            if not r:
                return False
        if b.ends >= 2:
            ok = b._guess_rest(allow_new_ends=False)
        else:
            ok = b._solve_remaining_ends()
        if b._timed_out:
            self._timed_out = True
        return ok

    def solve(self, time_limit=15.0):
        self._deadline = (time.perf_counter() + time_limit) if time_limit else 0.0
        if self.force():
            return True
        if self.dead:
            return False
        if self.is_cover():
            return self._win()

        all_deg2 = self.original_deg2()
        if self.ends >= 2:
            return self._guess_rest()

        def dirs_of(cell):
            x, y = cell
            return [d for d in range(4) if self.adj(x, y)[d] != 1]

        def cell_color(cell):
            return (cell[0] + cell[1]) & 1

        n = self.nfree
        if n % 2 == 1:
            black = sum(
                1
                for y in range(HEIGHT)
                for x in range(WIDTH)
                if self.w[y][x] != 2 and ((x + y) & 1)
            )
            majority = 1 if black > n - black else 0
            candidates = [c for c in all_deg2 if cell_color(c) == majority]
        else:
            majority = None
            candidates = all_deg2

        need = 2 - self.ends
        for k in range(need + 1):
            if self._deadline and time.perf_counter() > self._deadline:
                self._timed_out = True
                return False
            if k == 0:
                if self._try_deg2_exceptions(all_deg2, [], []):
                    return True
                continue
            if k == 1:
                for cell in candidates:
                    if self._deadline and time.perf_counter() > self._deadline:
                        self._timed_out = True
                        return False
                    for d in dirs_of(cell):
                        if self._try_deg2_exceptions(all_deg2, [cell], [d]):
                            return True
                continue
            for i in range(len(candidates)):
                for j in range(i + 1, len(candidates)):
                    if self._deadline and time.perf_counter() > self._deadline:
                        self._timed_out = True
                        return False
                    a, b = candidates[i], candidates[j]
                    if majority is None and cell_color(a) == cell_color(b):
                        continue
                    for da in dirs_of(a):
                        for db in dirs_of(b):
                            if self._try_deg2_exceptions(all_deg2, [a, b], [da, db]):
                                return True
        return False


def _warnsdorff_yes(grid, node_limit=12000):
    """Fast incomplete search. True means a path exists; False means unknown."""
    return _exhaustive_ham_path(grid, node_limit=node_limit)


def has_hamiltonian_path(array, node_limit=0):
    """Return True iff the open cells admit a Hamiltonian path.

    Exhaustive Warnsdorff-ordered DFS with iterative deepening. Stops at
    the first covering path. Forced snake-fill is only a prune. Timeouts
    never count as no.
    """
    if len(array) != HEIGHT or len(array[0]) != WIDTH:
        raise ValueError(f"expected {HEIGHT}x{WIDTH} grid")
    if not coloring_allows_path(array):
        return False
    if _early_impossible(array):
        return False
    nfree = sum(cell != WALL for row in array for cell in row)
    if nfree <= 1:
        return True
    board = PathBoard(array)
    if board.force():
        return True
    if board.dead:
        return False
    if _exhaustive_ham_path(array, budgets=(4_000, 16_000)):
        return True
    if node_limit:
        return False
    return _exhaustive_ham_path(array, budgets=(0,))


def tour_from_snakemap(wmap, smap):
    """Walk a filled snake into a list of (row, col), or None if broken."""
    h = len(wmap)
    w = len(wmap[0])
    nfree = sum(cell != WALL for row in wmap for cell in row)
    if nfree <= 0:
        return []
    if nfree == 1:
        for y in range(h):
            for x in range(w):
                if wmap[y][x] != WALL:
                    return [(y, x)]
        return []

    def other_dir(x, y, came):
        found = None
        for d in range(4):
            if smap[y][x][d] and d != came:
                found = d
        return found

    ends = []
    any_snake = None
    for y in range(h):
        for x in range(w):
            deg = sum(smap[y][x])
            if not deg:
                continue
            if any_snake is None:
                any_snake = (x, y)
            if deg == 1:
                ends.append((x, y))
    if ends:
        x, y = ends[0]
        d = next(d for d in range(4) if smap[y][x][d])
        cells = [(y, x)]
        came = OPP[d]
        cx, cy = x + DX[d], y + DY[d]
        for _ in range(nfree - 1):
            if not (0 <= cx < w and 0 <= cy < h):
                return None
            cells.append((cy, cx))
            nxt = other_dir(cx, cy, came)
            if nxt is None:
                return cells if len(cells) == nfree else None
            cx, cy, came = cx + DX[nxt], cy + DY[nxt], OPP[nxt]
        return cells if len(cells) == nfree else None
    if any_snake is None:
        return None
    x, y = any_snake
    ds = [d for d in range(4) if smap[y][x][d]]
    if len(ds) != 2:
        return None
    cells = [(y, x)]
    cx, cy = x + DX[ds[0]], y + DY[ds[0]]
    came = OPP[ds[0]]
    for _ in range(nfree):
        if cx == x and cy == y:
            return cells if len(cells) == nfree else None
        if not (0 <= cx < w and 0 <= cy < h):
            return None
        cells.append((cy, cx))
        nxt = other_dir(cx, cy, came)
        if nxt is None:
            return None
        cx, cy, came = cx + DX[nxt], cy + DY[nxt], OPP[nxt]
    return cells if len(cells) == nfree else None


def _warnsdorff_tour(grid, node_limit=12000):
    """Return a Hamiltonian path as (row, col) cells, or None."""
    free = _free_mask(grid)
    nfree = free.bit_count()
    if nfree <= 1:
        for i in range(N):
            if free & (1 << i):
                return [divmod(i, WIDTH)]
        return []
    deg1 = [i for i in range(N) if (free & (1 << i)) and _degree(i, free) == 1]
    if len(deg1) > 2:
        return None
    starts = deg1 or [i for i in range(N) if (free & (1 << i)) and _degree(i, free) == 2]
    if not starts:
        starts = [i for i in range(N) if free & (1 << i)]
    nodes = 0
    path = []
    prog = current_progress()

    def deg(i, rem):
        d = 0
        for n in NEIGHBORS[i]:
            if rem & (1 << n):
                d += 1
        return d

    def dfs(head, rem):
        nonlocal nodes
        nodes += 1
        if nodes > node_limit:
            return False
        if prog is not None:
            prog.add(1)
        path.append(head)
        leftover = rem.bit_count()
        if leftover <= 1:
            return True
        open_cells = rem & ~(1 << head)
        nbrs = [n for n in NEIGHBORS[head] if open_cells & (1 << n)]
        if not nbrs:
            path.pop()
            return False
        hr = head // WIDTH
        nbrs.sort(key=lambda n: (
            deg(n, open_cells),
            0 if (hr % 2 == 0 and n == head + 1) or (hr % 2 == 1 and n == head - 1) else 1,
        ))
        for n in nbrs:
            if dfs(n, open_cells):
                return True
        path.pop()
        return False

    for s in starts[:6]:
        path = []
        nodes = 0
        if dfs(s, free) and len(path) == nfree:
            return [divmod(i, WIDTH) for i in path]
    return None


def path_end_gap(tour, is_cycle=False):
    """Manhattan distance between path ends. A cycle is gap 1."""
    if not tour:
        return None
    if is_cycle:
        return 1
    if len(tour) <= 1:
        return 0
    a, b = tour[0], tour[-1]
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def min_path_end_gap(nfree, cycle_possible=False):
    """Smallest Manhattan gap a ham path (or cycle) can have."""
    if nfree <= 1:
        return 0
    if nfree == 2:
        return 1
    if nfree % 2:
        return 2
    return 1 if cycle_possible else 3


def find_hamiltonian_path(grid):
    """Return covering path as [(row, col), ...], or None if none found.

    First path is enough; does not search for closer endpoints.
    """
    if len(grid) != HEIGHT or len(grid[0]) != WIDTH:
        raise ValueError(f"expected {HEIGHT}x{WIDTH} grid")
    if not coloring_allows_path(grid):
        return None
    if _early_impossible(grid):
        return None
    nfree = sum(cell != WALL for row in grid for cell in row)
    if nfree <= 1:
        for r in range(HEIGHT):
            for c in range(WIDTH):
                if grid[r][c] != WALL:
                    return [(r, c)]
        return []
    prog = current_progress()
    if prog is not None:
        prog.set_phase("path Warnsdorff tour")
    tour = _warnsdorff_tour(grid)
    if tour and verify_path(grid, tour):
        return tour
    if prog is not None:
        prog.set_phase("path exhaustive DFS")
    path_idx: list = []
    if _exhaustive_ham_path(grid, path=path_idx) and path_idx:
        cells = [divmod(i, WIDTH) for i in path_idx]
        if verify_path(grid, cells):
            return cells
    if prog is not None:
        prog.set_phase("path forced-fill search")
    limit = 0.0 if prog is not None else 15.0
    if PathBoard(grid).solve(time_limit=limit) and PathBoard.last_win:
        cells = PathBoard.last_win.path_cells()
        if cells and verify_path(grid, cells):
            return cells
    return None


def _cell_manhattan(a, b):
    r1, c1 = divmod(a, WIDTH)
    r2, c2 = divmod(b, WIDTH)
    return abs(r1 - r2) + abs(c1 - c2)


def _path_between(grid, start, end, node_limit, deadline):
    """Warnsdorff search for a ham path from start index to end index."""
    free = _free_mask(grid)
    nfree = free.bit_count()
    if not ((free & (1 << start)) and (free & (1 << end))):
        return None
    if start == end:
        return [divmod(start, WIDTH)] if nfree == 1 else None
    nodes = 0
    path = []
    prog = current_progress()

    def deg(i, rem):
        d = 0
        for n in NEIGHBORS[i]:
            if rem & (1 << n):
                d += 1
        return d

    def dfs(head, rem):
        nonlocal nodes
        if time.perf_counter() > deadline:
            return False
        nodes += 1
        if nodes > node_limit:
            return False
        if prog is not None:
            prog.add(1)
        leftover = rem.bit_count()
        if leftover == 1:
            if head != end:
                return False
            path.append(head)
            return True
        if head == end:
            return False
        path.append(head)
        open_cells = rem & ~(1 << head)
        if not (open_cells & (1 << end)):
            path.pop()
            return False
        nbrs = [n for n in NEIGHBORS[head] if open_cells & (1 << n)]
        if leftover == 2:
            if end not in nbrs:
                path.pop()
                return False
            nbrs = [end]
        else:
            nbrs = [n for n in nbrs if n != end]
            if not nbrs:
                path.pop()
                return False
            er, ec = divmod(end, WIDTH)
            nbrs.sort(key=lambda n: (
                deg(n, open_cells),
                -(abs(n // WIDTH - er) + abs(n % WIDTH - ec)),
            ))
        for n in nbrs:
            if dfs(n, open_cells):
                return True
        path.pop()
        return False

    if dfs(start, free) and len(path) == nfree:
        tour = [divmod(i, WIDTH) for i in path]
        return tour if verify_path(grid, tour) else None
    return None


def improve_path_endpoints(grid, tour, time_limit=12.0, on_better=None, cycle_possible=False):
    """Search for a covering path with a smaller head-tail gap.

    Calls on_better(tour, gap, best) each time a closer path is found.
    Returns (tour, gap, best). best means the gap is the theoretical minimum
    or every closer endpoint pair was exhausted.
    """
    if not tour:
        return None, None, False
    nfree = len(tour)
    best_d = path_end_gap(tour)
    min_d = min_path_end_gap(nfree, cycle_possible=cycle_possible)
    if best_d is None:
        return tour, None, False
    if nfree <= 2 or best_d <= min_d:
        return tour, best_d, True

    free = _free_mask(grid)
    deg1 = [i for i in range(N) if (free & (1 << i)) and _degree(i, free) == 1]
    if len(deg1) == 2:
        return tour, best_d, True

    prog = current_progress()
    if prog is not None:
        prog.set_phase(f"closer endpoints (gap {best_d}, best {min_d})")

    cells = [i for i in range(N) if free & (1 << i)]
    black = sum(1 for i in cells if _color_of(i))
    white = len(cells) - black
    deadline = time.perf_counter() + time_limit

    def pair_ok(a, b):
        if a == b:
            return False
        same = _color_of(a) == _color_of(b)
        if nfree % 2:
            if not same:
                return False
            majority = 1 if black > white else 0
            if _color_of(a) != majority:
                return False
        elif same:
            return False
        if len(deg1) == 1 and a != deg1[0] and b != deg1[0]:
            return False
        return True

    by_dist = {}
    for i, a in enumerate(cells):
        for b in cells[i + 1 :]:
            d = _cell_manhattan(a, b)
            if d < min_d or d >= best_d:
                continue
            if not pair_ok(a, b):
                continue
            by_dist.setdefault(d, []).append((a, b))

    for d in range(best_d - 1, min_d - 1, -1):
        pairs = by_dist.get(d) or []
        found = False
        for node_limit in (4000, 16000, 50000, 250000):
            for a, b in pairs:
                if time.perf_counter() > deadline:
                    return tour, best_d, False
                for start, end in ((a, b), (b, a)):
                    if len(deg1) == 1 and start != deg1[0]:
                        continue
                    cand = _path_between(grid, start, end, node_limit, deadline)
                    if cand:
                        tour = cand
                        best_d = d
                        is_best = best_d <= min_d
                        if on_better is not None:
                            on_better(tour, best_d, is_best)
                        if is_best:
                            return tour, best_d, True
                        found = True
                        break
                if found:
                    break
            if found:
                break
        if found and prog is not None:
            prog.set_phase(f"closer endpoints (gap {best_d}, best {min_d})")
    return tour, best_d, True


def find_hamiltonian_path_closest_ends(grid, time_limit=12.0):
    """Board-tab helper: first path, then closer head-tail if time allows."""
    tour = find_hamiltonian_path(grid)
    if not tour:
        return None
    tour, _gap, _best = improve_path_endpoints(grid, tour, time_limit=time_limit)
    return tour


def ham_path_status(grid):
    """'no_path' or 'path' — coloring and search combined."""
    return "path" if has_hamiltonian_path(grid) else "no_path"


def verify_path(grid, cells):
    """True iff cells is a Hamiltonian path on grid."""
    if not cells:
        return False
    open_cells = {
        (r, c)
        for r, row in enumerate(grid)
        for c, v in enumerate(row)
        if v != WALL
    }
    if len(cells) != len(open_cells) or set(cells) != open_cells:
        return False
    for (r1, c1), (r2, c2) in zip(cells, cells[1:]):
        if abs(r1 - r2) + abs(c1 - c2) != 1:
            return False
    return True


def update_db():
    pass


def calc_ham_path(pattern):
    return has_hamiltonian_path(pattern)


def draw_ham_path():
    pass


def _blank(fill=2):
    return [[fill] * WIDTH for _ in range(HEIGHT)]


def _self_test():
    assert min_path_end_gap(79) == 2
    assert min_path_end_gap(76) == 3
    assert min_path_end_gap(76, cycle_possible=True) == 1
    assert path_end_gap([(0, 0), (0, 1)], is_cycle=True) == 1
    assert path_end_gap([(0, 0), (8, 9)]) == 17

    empty = [[1] * WIDTH for _ in range(HEIGHT)]
    assert has_hamiltonian_path(empty)

    small = _blank(2)
    for r in range(3):
        for c in range(3):
            small[r][c] = 1
    assert coloring_allows_path(small)
    assert has_hamiltonian_path(small)
    assert PathBoard(small).solve()
    assert verify_path(small, PathBoard.last_win.path_cells())

    split = _blank(2)
    split[0][0] = 1
    split[8][9] = 1
    assert not has_hamiltonian_path(split)

    branch = _blank(2)
    branch[0][0] = 1
    branch[0][1] = 1
    branch[0][2] = 1
    branch[1][1] = 1
    assert not has_hamiltonian_path(branch)

    one_wall = _blank(2)
    for r in range(2):
        for c in range(2):
            one_wall[r][c] = 1
    one_wall[0][0] = 2
    assert has_hamiltonian_path(one_wall)

    same = _blank(2)
    for r in range(3):
        for c in range(3):
            same[r][c] = 1
    same[0][1] = 2
    same[1][0] = 2
    assert not coloring_allows_path(same)
    assert not has_hamiltonian_path(same)

    # Even n, path yes, cycle no: a 4-cell corridor (not only the odd-n case).
    line = _blank(2)
    for c in range(4):
        line[0][c] = 1
    assert coloring_allows_path(line)
    assert has_hamiltonian_path(line)
    assert PathBoard(line).solve()
    assert verify_path(line, PathBoard.last_win.path_cells())

    # Exhaustive leftover DFS (skip Warnsdorff) still decides these.
    assert _exhaustive_ham_path(empty)
    assert _exhaustive_ham_path(small)
    assert not _exhaustive_ham_path(split)
    assert not _exhaustive_ham_path(branch)
    assert _exhaustive_ham_path(line)

    wall_bits = "1" + "0" * (N - 1)
    assert bits_flip_h(bits_flip_h(wall_bits)) == wall_bits
    assert bits_flip_v(bits_flip_v(wall_bits)) == wall_bits
    assert bits_rot180(bits_rot180(wall_bits)) == wall_bits
    assert wall_bits in pattern_orbit(wall_bits)
    assert len(pattern_orbit(wall_bits)) == 4
    g = bits_to_grid(wall_bits)
    assert has_hamiltonian_path(g) == has_hamiltonian_path(bits_to_grid(bits_flip_h(wall_bits)))
    assert has_hamiltonian_path(g) == has_hamiltonian_path(bits_to_grid(bits_flip_v(wall_bits)))

    print("hampath self-test ok")


if __name__ == "__main__":
    _self_test()
