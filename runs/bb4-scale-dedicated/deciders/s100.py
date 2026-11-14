import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# A machine is described by a list of rows, each row is a list of 3-char strings.
# We work with the parsed table: table[(state, symbol)] = (write, move, next_state)
# with states as ints and symbols 0/1. Halting transitions are absent.


def _bfs_tables(max_states, max_sym=2):
    """Yield every transition table for an automaton with 1..max_states states.

    State 0 is special: it is the blank-tape state and must loop on symbol 0
    (left[0][0] == 0). States are numbered 0..n-1; all tables are canonical
    (no unreachable states, state 0 is the initial state).
    """
    for n in range(1, max_states + 1):
        # table[i][x] in {0..n-1} or None (meaning: transition never happens)
        # We enumerate all n x max_sym matrices with entries in range(n+1) where
        # n means None. To keep the search small we require state 0 loops on 0.
        idx = [0] * (n * max_sym)
        total = (n + 1) ** (n * max_sym - 1)
        if total > 4_000_000:
            # too many; fall back to random sampling for this size
            import random
            rng = random.Random(12345 + n)
            for _ in range(20000):
                yield _random_table(n, max_sym, rng)
            continue
        for _ in range(total):
            # build table
            tab = [[None] * max_sym for _ in range(n)]
            tab[0][0] = 0
            v = idx[:]
            for i in range(n):
                for x in range(max_sym):
                    if i == 0 and x == 0:
                        continue
                    e = v[i * max_sym + x]
                    tab[i][x] = None if e == n else e
            yield tab
            # increment odometer over the free entries
            pos = 0
            while True:
                i, x = divmod(pos, max_sym)
                if i == 0 and x == 0:
                    break
                e = tab[i][x]
                cur = n if e is None else e
                tab[i][x] = None if cur + 1 == n else cur + 1
                pos += 1
                if pos < n * max_sym:
                    break
                pos = 1 if n * max_sym > 1 else 0
        # end for n


def _random_table(n, max_sym, rng):
    tab = [[None] * max_sym for _ in range(n)]
    tab[0][0] = 0
    for i in range(n):
        for x in range(max_sym):
            if i == 0 and x == 0:
                continue
            r = rng.random()
            if r < 0.5:
                tab[i][x] = rng.randrange(n)
            else:
                tab[i][x] = None
    return tab


def _canonical(tab):
    """Return a canonical key for a table (states reachable from 0)."""
    n = len(tab)
    reach = [False] * n
    dq = deque([0])
    reach[0] = True
    while dq:
        s = dq.popleft()
        for x in range(2):
            t = tab[s][x]
            if t is not None and not reach[t]:
                reach[t] = True
                dq.append(t)
    # remap reachable states to 0..k-1 in BFS order
    order = [s for s in range(n) if reach[s]]
    remap = {s: i for i, s in enumerate(order)}
    k = len(order)
    new = [[None] * 2 for _ in range(k)]
    for s in order:
        for x in range(2):
            t = tab[s][x]
            new[remap[s]][x] = None if t is None else remap[t]
    return tuple(tuple(r) for r in new)


def _closure(tm, left, right, max_ctx=200000):
    """Closed context fixpoint.

    left/right are transition tables (list of lists of int or None) for the
    automata over the left and right half-tape respectively.  Returns the
    context set (as a list of [l, q, s, r]) or None if a halting context is
    forced, or if the set exceeds max_ctx.
    """
    table, n_states, _ = parse(tm)
    ctx = set()
    ctx.add((0, 0, 0, 0))
    stack = [(0, 0, 0, 0)]
    while stack:
        l, q, s, r = stack.pop()
        item = (q, s)
        if item not in table:
            # halting transition: the machine halts in this context
            return None
        w, move, q2 = table[item]
        if move == +1:
            l2 = left[l][w]
            if l2 is None:
                return None
            # for every (r2, s2) with right[r2][s2] == r, add (l2, q2, s2, r2)
            for r2 in range(len(right)):
                for s2 in range(2):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            stack.append(c)
        else:  # move == -1
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(len(left)):
                for s2 in range(2):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            stack.append(c)
        if len(ctx) > max_ctx:
            return None
    return ctx


def _emit(tm, left, right, ctx):
    """Convert a closed context set into the cps certificate format."""
    left_cert = [[None if v is None else v for v in row] for row in left]
    right_cert = [[None if v is None else v for v in row] for row in right]
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    return {
        "kind": "cps",
        "left": left_cert,
        "right": right_cert,
        "contexts": contexts,
    }


def decide(tm):
    table, n_states, _ = parse(tm)
    # Try to find a pair of automata (left, right) whose closure is closed
    # and contains no halting context.
    # We search left automata in BFS-canonical order up to 3 states (the hint
    # says start small; the earlier hint suggested 1,2,3 states per side).
    lefts = []
    seen = set()
    for tab in _bfs_tables(3, 2):
        key = _canonical(tab)
        if key in seen:
            continue
        seen.add(key)
        lefts.append(tab)
        if len(lefts) >= 400:
            break
    # Also try the identity automaton (n-gram of length 1: remembers nothing)
    # and a 2-state counter-ish automaton.
    ident = [[0, 0]]
    lefts.append(ident)
    lefts = list(dict.fromkeys(tuple(tuple(r) for r in t) for t in lefts))

    rights = []
    seenr = set()
    for tab in _bfs_tables(3, 2):
        key = _canonical(tab)
        if key in seenr:
            continue
        seenr.add(key)
        rights.append(tab)
        if len(rights) >= 400:
            break
    rights.append(ident)
    rights = list(dict.fromkeys(tuple(tuple(r) for r in t) for t in rights))

    for ltab in lefts:
        for rtab in rights:
            ctx = _closure(tm, ltab, rtab)
            if ctx is None:
                continue
            cert = _emit(tm, ltab, rtab, ctx)
            try:
                from neverhalt.kernel import check
                check(tm, cert)
                return cert
            except Exception:
                continue
    return None


# Make sure the module has a runnable entry point when imported by the harness.
if __name__ == "__main__":
    import sys
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            c = decide(line)
            print(line, "->", "None" if c is None else c["kind"])
        except Exception as e:
            print(line, "-> error", e)
    sys.exit(0)
