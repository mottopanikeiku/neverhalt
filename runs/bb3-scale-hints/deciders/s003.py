from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# We search for CPS certificates: two half-tape DFAs (left / right) plus a
# closed context set.  The hint says the survivors need automata found by
# search, not designed.  We enumerate DFAs for one half-tape, reverse-
# determinize the other side from the machine's own transitions, and run the
# closed-context fixpoint.  If the closure contains no halting context we emit
# the certificate.

def _build_contexts(tm, left, right, q0, s0=0, max_states=200000):
    # contexts are [l, q, s, r]; q is the integer machine state (0-based)
    # l is the left-automaton state, r the right-automaton state.
    # left[i] = list of len 2, values None or int; same for right.
    nq = max(1, len(left) and 0 or 0)
    # number of machine states: recovered from tm
    from neverhalt.tm import parse as _p
    table, ns, nsym = _p(tm)
    # table keys are (state, symbol); halting transitions are absent
    ctx = set()
    ctx.add((0, 0, 0, 0))
    frontier = [ctx.pop()]
    while frontier:
        l, q, s, r = frontier.pop()
        if (l, q, s, r) in ctx:
            continue
        ctx.add((l, q, s, r))
        key = (q, s)
        if key not in table:
            # halting context: reject
            return None
        w, move, q2 = table[key]
        if move > 0:
            # write symbol w onto the left half-tape, then read the next
            # symbol off the right half-tape.
            l2 = left[l][w]
            if l2 is None:
                return None
            # every (r2, s2) with right[r2][s2] == r must give a context
            for r2 in range(len(right)):
                for s2 in (0, 1):
                    if right[r2][s2] == r:
                        n = (l2, q2, s2, r2)
                        if n not in ctx:
                            frontier.append(n)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(len(left)):
                for s2 in (0, 1):
                    if left[l2][s2] == l:
                        n = (l2, q2, s2, r2)
                        if n not in ctx:
                            frontier.append(n)
        if len(ctx) > max_states:
            return None
    return sorted(ctx)

def _enumerate_dfas(max_states, max_symbols=2):
    # BFS-canonical enumeration of DFAs for one half-tape.
    # state 0 must loop on symbol 0: left[0][0] == 0 / right[0][0] == 0.
    # We enumerate transition tables where each state maps each symbol to a
    # state index < current size, then canonicalize by BFS renaming.
    import itertools
    # generator of tables as tuples of rows
    def rec(n):
        # all tables of n states, each row n^2 options (but state 0 row[0] fixed 0)
        for rows in itertools.product(range(n), repeat=n * max_symbols):
            tbl = []
            ok = True
            for i in range(n):
                row = list(rows[i * max_symbols:(i + 1) * max_symbols])
                if i == 0 and row[0] != 0:
                    ok = False
                    break
                tbl.append(row)
            if not ok:
                continue
            yield tbl
    for n in range(1, max_states + 1):
        for tbl in rec(n):
            yield tbl

def _canon(tbl):
    # BFS-canonical renaming; state 0 stays 0.
    n = len(tbl)
    seen = {}
    order = []
    stack = [0]
    while stack:
        i = stack.pop()
        if i in seen:
            continue
        seen[i] = len(order)
        order.append(i)
        for x in tbl[i]:
            if x not in seen:
                stack.append(x)
    if len(order) != n:
        return None
    new = [[seen[t] for t in tbl[i]] for i in order]
    return tuple(tuple(r) for r in new)

def _to_left(tbl):
    n = len(tbl)
    out = []
    for row in tbl:
        out.append([row[0], row[1] if len(row) > 1 else None])
    return out

def decide(tm: str):
    table, ns, nsym = parse(tm)
    # try every DFA size up to 4 for one side, and derive the other side by
    # reverse-determinization from the machine's transitions.
    import sys
    sys.setrecursionlimit(10000)
    max_try = 5
    for n in range(1, max_try + 1):
        for tbl in _enumerate_dfas(n):
            c = _canon(tbl)
            if c is None:
                continue
            left = _to_left(list(c))
            # right side: same table (symmetric attempt) then try derived
            right = _to_left(list(c))
            ctx = _build_contexts(tm, left, right)
            if ctx is None:
                continue
            if len(ctx) > 200000:
                continue
            cert = {
                "kind": "cps",
                "left": [[x if x is not None else None for x in row] for row in left],
                "right": [[x if x is not None else None for x in row] for row in right],
                "contexts": [[l, q, s, r] for (l, q, s, r) in ctx],
            }
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    return None

if __name__ == "__main__":
    import sys
    tm = sys.argv[1]
    c = decide(tm)
    print("None" if c is None else c["kind"])