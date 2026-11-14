import sys
from collections import defaultdict, deque
sys.setrecursionlimit(100000)

# ---------- helpers ----------

def parse_table(tm):
    """Parse bbchallenge notation into a transition table.

    Returns (table, n_states) where table[(state, symbol)] = (write, move, next_state)
    and move is +1 or -1.  A transition that is absent or jumps to a nonexistent
    state means HALT there (and the final transition counts as a step).
    """
    parts = tm.split('_')
    n_states = len(parts)
    table = {}
    for si, row in enumerate(parts):
        for sym in (0, 1):
            chunk = row[sym * 3:sym * 3 + 3]
            if len(chunk) < 3 or chunk == '---':
                continue
            w, m, ns = chunk[0], chunk[1], chunk[2]
            wi = int(w)
            if m == 'L':
                mv = -1
            elif m == 'R':
                mv = 1
            else:
                continue
            try:
                ni = ord(ns) - ord('A')
            except Exception:
                continue
            if 0 <= ni < n_states and wi in (0, 1):
                table[(si, sym)] = (wi, mv, ni)
    return table, n_states


def simulate(tm, max_steps):
    """Step the machine on a blank tape. Returns (halted, steps, state, pos, tape)."""
    table = {}
    parts = tm.split('_')
    n_states = len(parts)
    for si, row in enumerate(parts):
        for sym in (0, 1):
            chunk = row[sym * 3:sym * 3 + 3]
            if len(chunk) < 3 or chunk == '---':
                continue
            w, m, ns = chunk[0], chunk[1], chunk[2]
            wi = int(w)
            mv = -1 if m == 'L' else (1 if m == 'R' else 0)
            if mv == 0:
                continue
            try:
                ni = ord(ns) - ord('A')
            except Exception:
                continue
            if 0 <= ni < n_states:
                table[(si, sym)] = (wi, mv, ni)
    state = 0
    pos = 0
    tape = {}
    steps = 0
    while steps < max_steps:
        sym = tape.get(pos, 0)
        tr = table.get((state, sym))
        if tr is None:
            return True, steps, state, pos, tape
        w, mv, ns = tr
        tape[pos] = w
        pos += mv
        state = ns
        steps += 1
    return False, steps, state, pos, tape


# ---------- try to find a translated cycle by brute force ----------

def try_cycle(tm, max_steps=200000):
    """Look for a cycle in the configuration space, up to a translation.

    The classic pattern for these holdouts: the machine lays down a periodic
    wall of 1s to one side and then the head bounces between two markers
    forever, translating the pattern by one cell each lap. We look for a
    pair of configurations (state, head pos, tape-window) that repeat after
    some number of steps, where the tape-window is compared up to a shift.

    Certificate form (kernel format):
        {"kind": "cycle", "t": T, "p": P}
    The kernel re-simulates T steps, then P more, and checks the translated
    cycle condition itself.  So we only need to GUESS (T, P); we do not build
    the certificate by hand.  But the kernel is strict: it requires that the
    tape content in the window is reproduced (shifted), and that everything
    outside the window is blank on the far side.

    Strategy: record full configurations (state, pos, tape-dict) at every step
    up to max_steps.  Look for a pair of times T < T+P such that
      state_T == state_{T+P},
      pos_T == pos_{T+P}  (d == 0 plain cycle)
    or, allowing translation, compare the tape content over the window seen
    between T and T+P.  Then verify with the kernel itself.
    """
    from neverhalt.kernel import check, Reject
    # We need the actual tape and pos at time T to evaluate, so we step here.
    table = {}
    parts = tm.split('_')
    n_states = len(parts)
    for si, row in enumerate(parts):
        for sym in (0, 1):
            chunk = row[sym * 3:sym * 3 + 3]
            if len(chunk) < 3 or chunk == '---':
                continue
            w, m, ns = chunk[0], chunk[1], chunk[2]
            wi = int(w)
            mv = -1 if m == 'L' else (1 if m == 'R' else 0)
            if mv == 0:
                continue
            try:
                ni = ord(ns) - ord('A')
            except Exception:
                continue
            if 0 <= ni < n_states:
                table[(si, sym)] = (wi, mv, ni)

    state = 0
    pos = 0
    tape = {}
    # history of (state, pos, tuple(sorted(tape.items())))
    hist = []
    steps = 0
    while steps < max_steps:
        sym = tape.get(pos, 0)
        tr = table.get((state, sym))
        if tr is None:
            return None
        hist.append((state, pos, tuple(sorted(tape.items()))))
        w, mv, ns = tr
        tape[pos] = w
        pos += mv
        state = ns
        steps += 1

    # First: look for exact repeats (plain cycle, d == 0).
    # Then: translated repeats.  For translated repeats we try to find T, P
    # with state_T == state_{T+P} and pos_T == pos_{T+P} - d for some d != 0,
    # and tape_{T+P}[y+d] == tape_T[y] for all y in the window.
    #
    # To keep this cheap we only look at candidate T, P with P bounded, and
    # we only try a limited set of P values (small multiples of the smallest
    # lap seen).  The kernel will do the real check.

    # Collect candidate (T, P) pairs where state and pos match up to translation.
    # We scan all T and a modest set of P.
    n = len(hist)
    # index by (state, pos) for exact repeat
    exact = {}
    for i in range(n):
        st, p, _ = hist[i]
        exact.setdefault((st, p), i)
    for i in range(n):
        st, p, _ = hist[i]
        j = exact.get((st, p))
        if j is not None and j > i:
            T, P = i, j - i
            if T + P <= 100000:
                cert = {"kind": "cycle", "t": T, "p": P}
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass

    # translated: try to match by aligning the head positions
    # pos_{T+P} - pos_T = d != 0 and state equal.
    # We look for the smallest set of P values that are plausible laps:
    # P values that appear repeatedly as the time between successive visits
    # to the same (state, pos) up to translation is hard; instead, we take
    # all pairs (i, j) with equal state and |pos_i - pos_j| small and
    # j - i not huge, then let the kernel decide.
    cand = []
    for i in range(n):
        st_i, p_i, _ = hist[i]
        for j in range(i + 1, min(n, i + 4000)):
            st_j, p_j, _ = hist[j]
            if st_j != st_i:
                continue
            d = p_j - p_i
            if d == 0:
                continue
            # require the lap to be reasonably short
            P = j - i
            if P > 20000:
                break
            cand.append((i, P))
    # try the shorter laps first
    cand.sort(key=lambda x: x[1])
    for (T, P) in cand[:200000]:
        cert = {"kind": "cycle", "t": T, "p": P}
        try:
            check(tm, cert)
            return cert
        except Reject:
            continue
    return None


# ---------- CPS: n-gram context set ----------

def build_cps(tm, n=4):
    """Build an n-gram CPS certificate.

    Abstract configuration: (l, q, s, r) where
      l = automaton state of the left half-tape (last n cells to the left,
          read from far to near),
      q = machine state, s = symbol under head,
      r = automaton state of the right half-tape.
    Automaton states are n-grams (tuples of length n over {0,1}); state 0 is
    the all-blank n-gram.

    Transition rule (from the kernel):
      on (q, s) -> (w, move, q2):
        if move == +1 (right):
            l2 = left[l][w]   # push w onto the left half-tape
            and for EVERY (r2, s2) with right[r2][s2] == r:
                (l2, q2, s2, r2) must be a context.
        if move == -1 (left):
            r2 = right[r][w]
            and for EVERY (l2, s2) with left[l2][s2] == l:
                (l2, q2, s2, r2) must be a context.
    """
    table, n_states = parse_table(tm)
    blank = (0,) * n

    def step_gram(g, x):
        return g[1:] + (x,)

    # Build the two automata lazily; the set of reachable n-grams is finite.
    left_states = {blank: 0}
    right_states = {blank: 0}
    left_tab = {}
    right_tab = {}

    def left_next(g, x):
        ng = step_gram(g, x)
        if ng not in left_states:
            left_states[ng] = len(left_states)
        return left_states[ng]

    def right_next(g, x):
        ng = step_gram(g, x)
        if ng not in right_states:
            right_states[ng] = len(right_states)
        return right_states[ng]

    # We will compute the least fixed point of contexts.
    # Start with the initial context: blank tape, state A, symbol 0 under head,
    # blank half-tapes.
    init = (0, 0, 0, 0)
    ctx = {init}
    changed = True
    while changed:
        changed = False
        new = set(ctx)
        for (l, q, s, r) in list(ctx):
            tr = table.get((q, s))
            if tr is None:
                continue
            w, mv, q2 = tr
            if mv == 1:
                l2 = left_next(tuple([None] * 0) if False else None, None) if False else None
                # left automaton: push w onto the left half-tape.
                # l is an n-gram of the cells left of head, read far->near.
                # Pushing w (the cell just written, which is now left of the
                # head) means the new left n-gram is step_gram(l, w).
                gl = left_states.get(step_gram(_gram_of(l), w))
                if gl is None:
                    # extend
                    pass
                # We need the actual n-gram; easier: store contexts with the
                # n-gram objects directly.
        break

    # The above got tangled. Rewrite cleanly with n-grams as context members.
    return None


def _gram_of(l):
    # l is an automaton index; we keep a reverse map instead
    return None


# ---------- clean CPS implementation ----------

def cps(tm, n=4, max_ctx=200000):
    table, n_states = parse_table(tm)
    blank = (0,) * n

    def step_gram(g, x):
        return g[1:] + (x,)

    # Map n-gram -> index
    L = {blank: 0}
    R = {blank: 0}

    def lidx(g):
        if g not in L:
            L[g] = len(L)
        return L[g]

    def ridx(g):
        if g not in R:
            R[g] = len(R)
        return R[g]

    # contexts: set of (lgram, q, s, rgram)
    ctx = {(blank, 0, 0, blank)}
    # We iterate to a fixed point.  For each context, for the transition,
    # we need to enumerate predecessor states of the automaton:
    #   left:  for every (l2, s2) with step_gram(l2, s2) == l
    #   right: for every (r2, s2) with step_gram(r2, s2) == r
    # We precompute reverse maps.
    def rev_left(lg):
        out = []
        for (g, i) in L.items():
            if step_gram(g, lg[-1]) == lg:
                out.append((i, lg[-1]))
        return out

    def rev_right(rg):
        out = []
        for (g, i) in R.items():
            if step_gram(g, rg[-1]) == rg:
                out.append((i, rg[-1]))
        return out

    changed = True
    while changed:
        changed = False
        cur = list(ctx)
        for (lg, q, s, rg) in cur:
            tr = table.get((q, s))
            if tr is None:
                continue
            w, mv, q2 = tr
            if mv == 1:
                l2g = step_gram(lg, w)
                l2 = lidx(l2g)
                # predecessor states of right automaton
                for (r2, s2) in rev_right(rg):
                    c = (l2g, q2, s2, rg)
                    if c not in ctx:
                        ctx.add(c)
                        changed = True
            else:
                r2g = step_gram(rg, w)
                r2 = ridx(r2g)
                for (l2, s2) in rev_left(lg):
                    c = (lg, q2, s2, r2g)
                    if c not in ctx:
                        ctx.add(c)
                        changed = True
        if len(ctx) > max_ctx:
            return None

    # Build the certificate
    # Automaton transition tables: left[i][x], right[i][x]
    # left[i] must be a list of length 2 (symbols 0 and 1).
    def build_tab(index):
        # index: dict gram -> idx
        # left[i][x] = index of step_gram(gram_i, x)
        inv = {v: k for (k, v) in index.items()}
        tab = []
        for i in range(len(index)):
            g = inv[i]
            row = []
            for x in (0, 1):
                ng = step_gram(g, x)
                row.append(index[ng])
            tab.append(row)
        return tab

    left_tab = build_tab(L)
    right_tab = build_tab(R)
    contexts = []
    invL = {v: k for (k, v) in L.items()}
    invR = {v: k for (k, v) in R.items()}
    for (lg, q, s, rg) in ctx:
        contexts.append([invL[lg], q, s, invR[rg]])

    cert = {
        "kind": "cps",
        "left": left_tab,
        "right": right_tab,
        "contexts": contexts,
    }
    from neverhalt.kernel import check, Reject
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None


# ---------- main decider ----------

NAME = "cycle_cps"

def decide(tm):
    # First try a translated cycle search (cheap for many machines).
    c = try_cycle(tm, max_steps=30000)
    if c is not None:
        return c
    # Then try n-gram CPS with increasing n.
    for n in (2, 3, 4, 5, 6):
        c = cps(tm, n=n, max_ctx=200000)
        if c is not None:
            return c
    return None
