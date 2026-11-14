from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# BFS-canonical DFA enumeration over alphabet {0,1}, with state 0 looping on 0.
# We build smallest DFAs first; for each DFA on the left half-tape we reverse-determinize
# the NFA language described by the right half-tape (built as a trie walk of a 0-bounded
# tape word), then close contexts forward.

def _dfa_tables(max_states):
    """Yield (left_table, right_table) with left[i][x] in 0..max_states-1 or None, right likewise.
    left[0][0] == right[0][0] == 0.  Only canonical (BFS-first) transitions are explored."""
    # Represent table as tuple over (state, symbol).
    # Enumerate left tables with up to max_states states.
    import itertools
    def gen_tables():
        # canonical form: state 0 loops on 0; transitions to currently-used states only
        # (state indices are assigned on first use in BFS order of creation).
        # Small tables first.
        # Generate all functions from (states, symbol) -> state or None, but keep only
        # those where the "used" state set is closed under reachability and
        # state 0 is the initial state (looping on 0).
        # We generate by increasing number of states, and require that the last state
        # (max index) is reachable from 0 by a non-empty word.
        for n_states in range(1, max_states + 1):
            # transitions: for each state 0..n_states-1 and symbol 0,1 -> value in
            # range(-1, n_states) with -1 meaning None.
            for vals in itertools.product(range(-1, n_states), repeat=2 * n_states):
                # state 0 must loop on 0
                if vals[0] != 0:
                    continue
                tab = [[vals[2 * i], vals[2 * i + 1]] for i in range(n_states)]
                # canonical: no state index > highest reachable state; reachability check
                # (to guarantee canonical BFS order: state indices are first-use order)
                # enforce that for each state s, the transitions from states < s only
                # use indices <= s; i.e., states are created in order.
                ok = True
                for i in range(n_states):
                    for x in range(2):
                        v = tab[i][x]
                        if v >= 0 and v > i + 1:
                            ok = False
                            break
                    if not ok:
                        break
                if not ok:
                    continue
                # last state must be reachable (non-trivial last state)
                if n_states > 1:
                    reach = {0}
                    frontier = {0}
                    while frontier:
                        nf = set()
                        for st in frontier:
                            for x in range(2):
                                v = tab[st][x]
                                if v >= 0 and v not in reach:
                                    nf.add(v)
                                    reach.add(v)
                        frontier = nf
                    if (n_states - 1) not in reach:
                        continue
                yield tuple(tab)
    for t in gen_tables():
        yield t, t  # symmetric first, then we try other pairs below

def _table_to_list(t):
    return [list(row) for row in t]

def _context_key(l, q, s, r):
    return (l, q, s, r)

def _close(tm, parse_tm, max_states, budget_steps=100000):
    table, n_states, n_symbols = parse_tm
    # transitions: for each (state,symbol) -> (w,move,next) or None
    # We'll build a context set of (l, q, s, r) with l,r in 0..max_states-1
    # Start from [0,0,0,0].
    # Need left/right tables.  We try all pairs (L,R) of tables.
    # To keep the search bounded, we generate candidate tables once.
    import itertools
    # enumerate candidate DFA tables up to max_states
    cands = []
    for t in _dfa_tables(max_states):
        cands.append(t)
    # dedupe
    seen = set()
    cands = [c for c in cands if not (c in seen or seen.add(c))]
    # Sort by size (number of states) then lexicographic: small first.
    cands.sort(key=lambda t: (len(t), t))
    for L in cands:
        nL = len(L)
        for R in cands:
            nR = len(R)
            # counts of states in left/right automata
            if nL + nR > 2 * max_states:
                continue
            # check transition table
            ctx = set()
            start = (0, 0, 0, 0)
            ctx.add(start)
            stack = [start]
            ok = True
            halted = False
            while stack:
                l, q, s, r = stack.pop()
                key = (l, q, s, r)
                if key not in ctx:
                    ctx.add(key)
                tr = table.get((q, s))
                if tr is None:
                    halted = True
                    ok = False
                    break
                w, move, q2 = tr
                if move == 1:  # right move
                    l2 = L[l][w]
                    if l2 is None:
                        ok = False
                        break
                    for r2 in range(nR):
                        for s2 in range(2):
                            if R[r2][s2] == r:
                                nk = (l2, q2, s2, r2)
                                if nk not in ctx:
                                    ctx.add(nk)
                                    stack.append(nk)
                else:  # left move
                    r2 = R[r][w]
                    if r2 is None:
                        ok = False
                        break
                    for l2 in range(nL):
                        for s2 in range(2):
                            if L[l2][s2] == l:
                                nk = (l2, q2, s2, r2)
                                if nk not in ctx:
                                    ctx.add(nk)
                                    stack.append(nk)
                if len(ctx) > 200000:
                    ok = False
                    break
            if not ok:
                continue
            if not ctx:
                continue
            if (0, 0, 0, 0) not in ctx:
                continue
            # Check that no halting context exists: we already broke out if a
            # transition was missing.  Now build the certificate.
            left_list = []
            for i in range(nL):
                row = []
                for x in range(2):
                    v = L[i][x]
                    row.append(v if v is not None else None)
                left_list.append(row)
            right_list = []
            for i in range(nR):
                row = []
                for x in range(2):
                    v = R[i][x]
                    row.append(v if v is not None else None)
                right_list.append(row)
            contexts_list = [[l, q, s, r] for (l, q, s, r) in ctx]
            cert = {"kind": "cps", "left": left_list, "right": right_list, "contexts": contexts_list}
            # try to verify with kernel
            try:
                res = check(tm, cert)
                return cert
            except Reject:
                return None
            except Exception:
                return None
    return None

def decide(tm: str):
    parse_tm = parse(tm)
    table, n_states, n_symbols = parse_tm
    # Try closures with growing max DFA size, but cap by time budget heuristic:
    # try max_states = 1,2,3 first, then 4,5,6.
    for max_states in (1, 2, 3, 4):
        cert = _close(tm, parse_tm, max_states)
        if cert is not None:
            return cert
    return None