# Wall all calculator originally by ScienceCrafter
# Tip: The primary and most useful function is check(amount,width,height)

from dataclasses import dataclass
from random import randint as rand
from copy import deepcopy as copy
from typing import Optional
import re

from . import hampath
from . import render as wall_render

# order --> UP DOWN LEFT RIGHT
piecedict = {
    "1001" : "╚",
    "1100" : "║",
    "0101" : "╔",
    "1010" : "╝",
    "0011" : "═",
    "0110" : "╗"
}
piecedicttemp = { # unused, could be for step by step view of .solve()
    "1001" : "└",
    "1100" : "│",
    "0101" : "┌",
    "1010" : "┘",
    "0011" : "─",
    "0110" : "┐"
}
# Single-connection cells (Ham Path endpoints)
ENDPOINT_PIECES = {
    "1000": "╨",
    "0100": "╥",
    "0010": "╡",
    "0001": "╞",
}


@dataclass
class PatternResult:
    """Solver reply for Discord: caption plus optional Board-tab PNG."""

    content: str
    png: Optional[bytes] = None


# Match Wall Research Board-tab closer-endpoint search.
IMPROVE_SECONDS = 90.0

## PHASE 1 :  Let's generate some wall patterns

def strpiece(l):
    ''' (list) -> string
    converts the list of piece connections in the snakemap into dictionary compatible strings
    '''
    s = ""
    for x in l:
        if x == 1:
            s += "1"
        elif x == 0:
            s += "0"
    return s

def newblank(x,y):
    ''' (int,int) -> list
    creates an blank board of size x by y
    '''
    b = []
    for i in range(y):
        r = []
        for j in range(x):
            r = r + [0]
        b = b + [r]
    b[0][1] = 1
    b[0][-2] = 1
    b[1][0] = 1
    b[1][-1] = 1
    b[-2][0] = 1
    b[-2][-1] = 1
    b[-1][1] = 1
    b[-1][-2] = 1
    return copy(b)

def generate_eligible(b):
    ''' (list) -> list
    takes in a wall map and returns a list of tuples containing coordinates of all eligible wall spawns
    '''
    lx = len(b[0])
    ly = len(b)
    elig = []
    for i in range(lx):
        for j in range(ly):
            if b[j][i] == 0:
                elig += [(i,j)]
    return elig

def new_wall(b):
    ''' (list) -> None
    adds a random eligible wall to the board and updates the eligible positions
    '''
    lx = len(b[0])
    ly = len(b)
    elig = generate_eligible(b)
    if len(elig) == 0:
        return False
    choice = elig[rand(0,len(elig)-1)]
    x = choice[0]
    y = choice[1]
    b[y][x] = 2
    # adjacency rules
    if y != 0:
        b[y-1][x] = 1
        if x != 0:
            b[y-1][x-1] = 1
        if x != lx-1:
            b[y-1][x+1] = 1
    if y != ly-1:
        b[y+1][x] = 1
        if x != 0:
            b[y+1][x-1] = 1
        if x != lx-1:
            b[y+1][x+1] = 1
    if x != 0:
        b[y][x-1] = 1
    if x != lx-1:
        b[y][x+1] = 1
    # edge rules
    if y == 0 or y == ly-1:
        if x < lx-2:
            b[y][x+2] = 1
        if x > 1:
            b[y][x-2] = 1
    if x == 0 or x == lx-1:
        if y < ly-2:
            b[y+2][x] = 1
        if y > 1:
            b[y-2][x] = 1
    # special rule
    if y == 0 and x == 2:
        b[2][0] = 1
    if y == 0 and x == lx-3:
        b[2][-1] = 1
    if y == 2 and x == 0:
        b[0][2] = 1
    if y == 2 and x == lx-1:
        b[0][-3] = 1
    if y == ly-1 and x == 2:
        b[-3][0] = 1
    if y == ly-1 and x == lx-3:
        b[-3][-1] = 1
    if y == ly-3 and x == 0:
        b[-1][2] = 1
    if y == ly-3 and x == lx-1:
        b[-1][-3] = 1
    return True

def darklightcheck(b):
    dark = 0
    light = 0
    for j in range(len(b)):
        for i in range(len(b[0])):
            if b[j][i] != 2:
                if (i+j)%2 == 0:
                    light += 1
                else:
                    dark += 1
    if dark == light:
        return True
    return False


def render(b):
    ''' (list) -> None
    prints a nice version of the board (does not take snake into account) see also: render_compound()
    '''
    print("+"+"-"*len(b[0])+"+")
    for i in b:
        print("|",end="")
        for j in i:
            if j == 3:
                print("0",end="")
            elif j == 2:
                print("#",end="")
            elif j == 1:
                print(".",end="")
            else:
                print(" ",end="")
        print("|")
    print("+"+"-"*len(b[0])+"+")

def new_pattern(x,y):
    ''' (int,int) -> list
    creates a new pattern of size x by y
    '''
    b = newblank(x,y)
    d = True
    while d:
        d = new_wall(b)
    return b

## PHASE 2 :  Let's test these patterns

def new_4map(x,y):
    ''' (int,int) -> list
    creates an empty 3d list of size list[y][x][4]
    '''
    m = newblank(x,y)
    for i in range(x):
        for j in range(y):
            m[j][i] = [0,0,0,0]
    return m

def adj_check(wmap,smap,x,y):
    ''' (list,list,int,int) -> list
    checks the adjacencies at (x,y)
    order is UP DOWN LEFT RIGHT
    0 = Empty space
    1 = Wall or snake piece facing away
    2 = Snake piece facing towards
    '''
    lx = len(wmap[0])
    ly = len(wmap)
    adj = [0,0,0,0] # UP DOWN LEFT RIGHT # 0=Free 1=Wall 2=SnakeOpen
    # check above
    if y == 0:
        adj[0] = 1
    elif wmap[y-1][x] >= 2:
        adj[0] = 1
        if wmap[y-1][x] == 3 and smap[y-1][x][1] == 1:
            adj[0] = 2
    # check below
    if y == ly-1:
        adj[1] = 1
    elif wmap[y+1][x] >= 2:
        adj[1] = 1
        if wmap[y+1][x] == 3 and smap[y+1][x][0] == 1:
            adj[1] = 2
    # check left
    if x == 0:
        adj[2] = 1
    elif wmap[y][x-1] >= 2:
        adj[2] = 1
        if wmap[y][x-1] == 3 and smap[y][x-1][3] == 1:
            adj[2] = 2
    # check right
    if x == lx-1:
        adj[3] = 1
    elif wmap[y][x+1] >= 2:
        adj[3] = 1
        if wmap[y][x+1] == 3 and smap[y][x+1][2] == 1:
            adj[3] = 2
    return adj

def new_adjmap(wmap,smap):
    ''' (list,list) -> list
    creates a list of every tile's adjacency
    '''
    lx = len(wmap[0])
    ly = len(wmap)
    adjmap = new_4map(lx,ly)
    for i in range(lx):
        for j in range(ly):
            if wmap[j][i] == 1:
                adjmap[j][i] = adj_check(wmap,smap,i,j)
    return adjmap

def cyclecheck(smap,x,y):
    ''' (list,int,int) -> bool or int
    follows the snake, starting from (x,y) and checks to see if there is a cycle
    if there is a cycle, returns the length, otherwise returns false
    '''
    d = smap[y][x][:].index(1)
    x0 = x
    y0 = y
    n = 0
    while 1:
        n += 1
        if d == 0:
            y += -1
            if sum(smap[y][x]) == 2:
                a = smap[y][x][:]
                a[1] = [0]
                d = a.index(1)
            else:
                return False
        elif d == 1:
            y += 1
            if sum(smap[y][x]) == 2:
                a = smap[y][x][:]
                a[0] = [0]
                d = a.index(1)
            else:
                return False
        elif d == 2:
            x += -1
            if sum(smap[y][x]) == 2:
                a = smap[y][x][:]
                a[3] = [0]
                d = a.index(1)
            else:
                return False
        elif d == 3:
            x += 1
            if sum(smap[y][x]) == 2:
                a = smap[y][x][:]
                a[2] = [0]
                d = a.index(1)
            else:
                return False
        if x == x0 and y == y0:
            return n
        if n > len(smap)*len(smap[0]):
            return False

def snakefillstep(wmap,adjmap,smap,max,pairing=True,cycleblock=True):
    ''' (list,list,list,int,bool,bool) -> bool
    adds snake pieces wherever their existence is implied
    if pairing, then if there are two open snakes pointing towards a point, it will connect them (only optimal if hamcycle exists)
    if cycleblock, then it will automatically check for  bad cycles every time pairing occurs
    '''
    lx = len(wmap[0])
    ly = len(wmap)
    ham = True
    for i in range(lx):
        for j in range(ly):
            if wmap[j][i] == 1:
                if adjmap[j][i].count(1) == 2:
                    for n in range(4):
                        if adjmap[j][i][n] == 0 or adjmap[j][i][n] == 2:
                            smap[j][i][n] = 1
                    wmap[j][i] = 3
                if adjmap[j][i].count(2) >= 3:
                    ham = False
                if adjmap[j][i].count(1) >= 3:
                    ham = False
                if pairing and adjmap[j][i].count(2) == 2:  # note that while this segment always produces the best (only) path when a hamcycle IS present, it will often give bad paths if a hamcycle isn't present
                    if cycleblock:

                        test = copy(smap)
                        for n in range(4):
                            if adjmap[j][i][n] == 2:
                                test[j][i][n] = 1
                        x = cyclecheck(test,i,j)
                        if not x:
                            smap[j][i] = test[j][i]
                            wmap[j][i] = 3
                        elif x != max:
                            ham = False
                    else:
                        for n in range(4):
                            if adjmap[j][i][n] == 2:
                                smap[j][i][n] = 1
                            wmap[j][i] = 3

    return ham

def render_compound(wmap,smap):
    ''' (list,list) -> str
    returns a nicely formatted version of the wall, including the snake pieces
    '''
    lx = len(wmap[0])
    ly = len(wmap)
    s = ""
    s += "+"+"-"*lx+"+\n"
    for j in range(ly):
        s += "|"
        for i in range(lx):
            if wmap[j][i] == 3:
                key = strpiece(smap[j][i])
                s += piecedict.get(key) or ENDPOINT_PIECES.get(key) or "."
            elif wmap[j][i] == 2:
                s += "#"
            else:
                s += "."
        s += "|\n"
    s += "+"+"-"*lx+"+\n"
    return s

class Pattern:
    ''' pattern class
    '''
    def __init__(self,x,y,wmap=False,smap=False,walls=False):
        if wmap:
            self.wallmap = wmap
        else:
            self.wallmap = new_pattern(x,y)
        if smap:
            self.snakemap = smap
        else:
            self.snakemap = new_4map(x,y)
        self.lenx = x
        self.leny = y
        self.adjacencymap = new_adjmap(self.wallmap,self.snakemap)
        self.ham = True
        if walls:
            self.wallcount = walls
        else:
            self.wallcount = self.countwalls()

    def __repr__(self):
        return render_compound(self.wallmap,self.snakemap)

    def step(self,p=True):
        ''' (Pattern,bool) -> None
        does one snakefillstep on itself
        p regulates pairing
        '''
        x = snakefillstep(self.wallmap,self.adjacencymap,self.snakemap,(self.lenx*self.leny)-self.wallcount,p)
        self.adjacencymap = new_adjmap(self.wallmap,self.snakemap)
        if x == False:
            self.ham = False

    def work(self,p=True,lim=True): # False-False for weakest test, #True-False for stronger test, #False-True for weak development, #True-True for maximisation
        ''' (Pattern,bool,bool) -> None
        if lim, does as many snakefillsteps as it can (ie goes to the limit)
        if not lim, stops when reaches non hamcycle
        p regulates pairing
        '''
        prev = copy(self)
        if p:
            self.work(False,lim)
        self.step(p)
        while (self.ham or lim) and prev != self:
            prev = copy(self)
            if p:
                self.work(False,lim)
            self.step(p)

    def __eq__(self, other):
        if self.wallmap == other.wallmap and self.snakemap == other.snakemap:
            return True
        else:
            return False

    def countwalls(self):
        ''' (Pattern) -> int
        counts walls
        '''
        n = 0
        for j in range(self.leny):
            for i in range(self.lenx):
                if self.wallmap[j][i] == 2:
                    n += 1
        return n

    def basewallmap(self):
        ''' (Pattern) -> list
        returns wallmap without snake pieces
        '''
        w = newblank(self.lenx,self.leny)
        for j in range(self.leny):
            for i in range(self.lenx):
                if self.wallmap[j][i] == 2:
                    w[j][i] = 2
                else:
                    w[j][i] = 1
        return w

    def firstempty(self):
        ''' (Pattern) -> tuple
        returns coordinate pair of first empty tile in the pattern
        '''
        for j in range(self.leny):
            for i in range(self.lenx):
                if self.wallmap[j][i] == 1:
                    return (i,j)

    def allempty(self):
        ''' (Pattern) -> list
        returns list of coordinate pairs of all empty tiles
        '''
        l = []
        base = self.basewallmap()
        for j in range(self.leny):
            for i in range(self.lenx):
                if base[j][i] == 1:
                    l += [(i,j)]
        return l

    def solve(self):
        ''' (Pattern) -> bool
        solves the pattern
        '''
        if not self.ham:
            return False
        self.work()
        #print(self)
        if not self.ham:
            return False
        if (self.wallmap[0][0] == 3 and cyclecheck(self.snakemap,0,0) == (self.leny*self.lenx)-self.wallcount) or (self.wallmap[0][1] == 3 and cyclecheck(self.snakemap,1,0) == (self.leny*self.lenx)-self.wallcount):
            return self
        guess = copy(self)
        fe = self.firstempty()
        if fe == None:
            return False
        guess.wallmap[fe[1]][fe[0]] = 3
        # the following works because the first empty can be demonstrated to always be adjacent to two empties in the bottom and right, and to an open piece and wall to the left and above
        guesspiece = [0,0,0,0]
        if self.adjacencymap[fe[1]][fe[0]][0] == 2:
            guesspiece[0] = 1
        elif self.adjacencymap[fe[1]][fe[0]][2] == 2:
            guesspiece[2] = 1
        # first guess (║/╗)
        guesspiece[1] = 1
        guess.snakemap[fe[1]][fe[0]] = guesspiece[:]
        guess.adjacencymap = new_adjmap(guess.wallmap,guess.snakemap)
        if not cyclecheck(guess.snakemap,fe[0],fe[1]):
            g1 = guess.solve()
            if g1:
                return g1
        # second guess (╚/═)
        guess = copy(self)
        guess.wallmap[fe[1]][fe[0]] = 3
        guesspiece[1] = 0
        guesspiece[3] = 1
        guess.snakemap[fe[1]][fe[0]] = guesspiece[:]
        guess.adjacencymap = new_adjmap(guess.wallmap,guess.snakemap)
        if not cyclecheck(guess.snakemap,fe[0],fe[1]):
            g2 = guess.solve()
            if g2:
                return g2
        return False

    def analyse(self, depth=0):
        if depth <= 0:
            return copy(self).solve()
        else:
            c = self.analyse(depth-1)
            if c:
                return c
            for x in self.allempty():
                newmap = self.basewallmap()
                newmap[x[1]][x[0]] = 2
                c = Pattern(self.lenx,self.leny,wmap=newmap,walls=self.wallcount+1)
                c = c.analyse(depth-1)
                if c:
                    rmap = self.basewallmap()
                    for j in range(self.leny):
                        for i in range(self.lenx):
                            if c.wallmap[j][i] == 3:
                                rmap[j][i] = 3
                    print(render_compound(rmap,c.snakemap))
                    return c
        return False


last_res = []

def check(n,x,y,m=False,pre=False):
    ''' (int,int,int,int,list) -> None
    checks n patterns of size x by y for hampaths, and prints all the ones it finds as well as a count
    if you want to increase the amount of results (won't increase ham, but can give some insight) then you can set an m value
    if you set an m value, instead of having to pass all steps, it will only need to pass m (so the results will be less filtered)
    '''
    r = 0
    q = []
    for i in range(n):
        w = new_pattern(x,y)
        if darklightcheck(w):
            b = Pattern(x,y,wmap=w)
            prev = copy(b)
            j = 0
            if m:
                while j < m:
                    b.step()
                    if not b.ham:
                        j = m
                    j += 1
            else:
                b.work(lim=False)
            if b.ham:
                if m:
                    c = m
                    h = m
                while prev != b:
                    prev = copy(b)
                    if b.step(True):
                        if m:
                            h += 1
                    if m:
                        c += 1
                if m:
                    print(b,h,"/",c)
                q += [copy(b)]
                r += 1
    print(r,"results")
    global last_res
    last_res = copy(q)
    r2 = 0
    for p in q:
        s = p.solve()
        if s:
            print(s)
            r2 += 1
    print(f"{r2} hamcycles (out of {r} results)")

def stringToBoardArray(board_string):
    # Initialize a 2D array of 10x9 with all '1's (empty tiles)
    board = [[1] * 10 for _ in range(9)]

    # Convert the string into a 2D array representation
    for i in range(90):
        x = i % 10
        y = i // 10
        if board_string[i] == '2':
            board[y][x] = 2  # Set '2' for wall tiles

    return board

def replace_char_at_index(original_string, index, new_char):
    if index < 0 or index >= len(original_string):
        raise IndexError("Index is out of range")
    if len(new_char) != 1:
        raise ValueError("New character must be a single character string")

    # Create the new string with the replaced character
    new_string = original_string[:index] + new_char + original_string[index + 1:]
    return new_string    

MIN_WALLS = 12

_CODE_FENCE_RE = re.compile(r"^```(?:\w+)?\s*|\s*```$", re.DOTALL)
_LEADING_MENTION_RE = re.compile(r"^<@!?\d+>\s*")
_PATTERN_PREFIX_RE = re.compile(r"(?is)^\s*pattern\b")


def unwrap_copied_pattern(raw: str) -> str:
    """Strip quotes, code fences, and a leading mention from a pudding copy paste."""
    text = (raw or "").strip()
    text = _CODE_FENCE_RE.sub("", text).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'`":
        text = text[1:-1].strip()
    return _LEADING_MENTION_RE.sub("", text).strip()


def parse_pattern_input(raw: str) -> str:
    """90-cell 0/1/2 string from pudding clipboard (`pattern 12…`) or a raw grid."""
    return normalize_pattern_string(unwrap_copied_pattern(raw))


def is_pattern_message(raw: str) -> bool:
    """True for pudding copy (`pattern …`) after stripping quotes/fences."""
    return bool(_PATTERN_PREFIX_RE.match(unwrap_copied_pattern(raw)))


def normalize_pattern_string(pattern_string: str) -> str:
    """Keep only 0/1/2 cells (spaces, letters, and other glyphs are ignored)."""
    return "".join(ch for ch in (pattern_string or "") if ch in "012")


def canonicalize_pattern_string(pattern_string: str) -> str:
    """Map 0/1 or 1/2 grids to solver form: 1 = empty, 2 = wall."""
    cleaned = normalize_pattern_string(pattern_string)
    if not cleaned:
        return cleaned
    return _map_to_empty_and_wall(cleaned)


def _map_to_empty_and_wall(cleaned: str) -> str:
    """The digit that appears fewer times is walls; the other is empty.

    Solver form is always 1 = empty, 2 = wall. A single digit (or a count
    tie) uses the higher digit as walls (so pudding `2` still wins a 45/45).
    """
    counts = {ch: cleaned.count(ch) for ch in set(cleaned)}
    if len(counts) <= 1:
        return "1" * len(cleaned)
    wall_char = min(counts, key=lambda ch: (counts[ch], -int(ch)))
    return "".join("2" if ch == wall_char else "1" for ch in cleaned)


def _cycle_coloring_possible(grid) -> bool:
    black = white = 0
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if cell != 2:
                if (r + c) & 1:
                    black += 1
                else:
                    white += 1
    return black == white


def _result(content: str, grid=None, tour=None, is_cycle: bool = False) -> PatternResult:
    png = None
    if grid is not None:
        png = wall_render.render_board_png(
            grid, tour, is_cycle=is_cycle, caption=content
        )
    return PatternResult(content=content, png=png)


def _path_caption(wall_count: int, gap, min_gap, *, best: bool, searching: bool) -> str:
    if searching and not best:
        return (
            f"Ham Path · gap {gap} · closest possible {min_gap} · "
            f"{wall_count} walls · searching closer…"
        )
    if best:
        return f"Ham Path · gap {gap} · closest · {wall_count} walls"
    return (
        f"Ham Path · gap {gap} · not proven closest (min {min_gap}) · "
        f"{wall_count} walls"
    )


def _emit_path(on_update, wall_count, grid, tour, *, cycle_possible: bool, searching: bool, best=None):
    gap = hampath.path_end_gap(tour)
    min_gap = hampath.min_path_end_gap(len(tour), cycle_possible=cycle_possible)
    if best is None:
        best = gap is not None and gap <= min_gap
    result = _result(
        _path_caption(wall_count, gap, min_gap, best=best, searching=searching),
        grid,
        tour,
        False,
    )
    if on_update:
        on_update(result)
    return result, best


def solve_pattern(pattern_string, on_update=None) -> PatternResult:
    """Solve, then tighten head–tail gap like the Wall Research Board tab.

    on_update(PatternResult) is called for the first tour and each closer one.
    """
    pattern_string = canonicalize_pattern_string(pattern_string)

    if len(pattern_string) != 90:
        result = PatternResult(
            "I can solve only Small Board patterns, so I'm expecting exactly 90 characters"
        )
        if on_update:
            on_update(result)
        return result

    grid = stringToBoardArray(pattern_string)
    wall_count = pattern_string.count("2")
    cycle_coloring = _cycle_coloring_possible(grid)
    searched_cycle = False

    if wall_count >= MIN_WALLS and cycle_coloring:
        searched_cycle = True
        pattern = Pattern(10, 9, wmap=copy(grid), walls=wall_count)
        solution = pattern.solve()
        if solution:
            tour = hampath.tour_from_snakemap(solution.wallmap, solution.snakemap)
            if tour:
                result = _result(f"Ham Cycle · {wall_count} walls", grid, tour, True)
            else:
                result = PatternResult("Ham Cycle (could not draw tour)")
            if on_update:
                on_update(result)
            return result

    if not hampath.coloring_allows_path(grid):
        result = _result("No Ham Cycle or Ham Path (coloring)", grid)
        if on_update:
            on_update(result)
        return result

    tour = hampath.find_hamiltonian_path(grid)
    if not tour:
        result = _result("No Ham Cycle or Ham Path", grid)
        if on_update:
            on_update(result)
        return result

    # After a failed cycle search, gap 1 is a cycle, so the path minimum is 3
    # on even boards. If we skipped cycle search, still allow gap 1.
    cycle_possible = cycle_coloring and not searched_cycle
    gap = hampath.path_end_gap(tour)
    min_gap = hampath.min_path_end_gap(len(tour), cycle_possible=cycle_possible)
    already_best = gap is not None and gap <= min_gap
    result, best = _emit_path(
        on_update, wall_count, grid, tour,
        cycle_possible=cycle_possible, searching=not already_best, best=already_best,
    )
    if best:
        return result

    def on_better(new_tour, new_gap, is_best):
        nonlocal tour
        tour = new_tour
        _emit_path(
            on_update, wall_count, grid, tour,
            cycle_possible=cycle_possible, searching=True, best=is_best,
        )

    tour, _gap, best = hampath.improve_path_endpoints(
        grid,
        tour,
        time_limit=IMPROVE_SECONDS,
        on_better=on_better,
        cycle_possible=cycle_possible,
    )
    result, _ = _emit_path(
        on_update, wall_count, grid, tour,
        cycle_possible=cycle_possible, searching=False, best=best,
    )
    return result


def check_pattern(pattern_string) -> PatternResult:
    """Solve a small-board pattern: Ham Cycle first, then closest Ham Path."""
    return solve_pattern(pattern_string)