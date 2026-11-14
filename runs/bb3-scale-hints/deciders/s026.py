import sys
from collections import deque, defaultdict

# The kernel's conventions: symbols 0 and 1, states ints (A=0), blank = 0.
# A certificate is a closed set of contexts [l, q, s, r] with two half-tape
# automata "left" and "right" given as row-major transition tables.

# ---------- helpers ----------

def build_table(tm):
    """Return {(state, symbol): (write, move, next_or_None)}."""
    parts = tm.split('_')
    table = {}
    for si, row in enumerate(parts):
        if len(row) < 3:
            continue
        for sym in range(2):
            chunk = row[sym*3:(sym+1)*3]
            if len(chunk) < 3 or chunk.strip() == '':
                continue
            w, m, ns = chunk[0], chunk[1], chunk[2]
            if w not in '01' or m not in 'LR' or ns not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                continue
            nxt = None
            if ns != 'Z':
                nxt = ord(ns) - ord('A')
            table[(si, sym)] = (int(w), 1 if m == 'R' else -1, nxt)
    return table

# ---------- DFA enumeration for one half-tape ----------

def canonical_transitions(n_states, alphabet):
    """All deterministic transition tables on n_states states over `alphabet`
    with state 0 looping on symbol 0, as tuples of tuples.  Rows for other
    states are arbitrary functions into [0, n_states)."""
    n = n_states
    rows = []
    # state 0 is forced on symbol 0
    def rec(state, acc):
        if state == n:
            rows.append(tuple(acc))
            return
        if state == 0:
            # row 0: on symbol 0 must go to 0
            rec(state + 1, acc + [(0,)] * 0 + [tuple([0] + [None]*(len(alphabet)-1))])
            # fill remaining symbols freely
            for vals in itertools_product(alphabet, n, len(alphabet) - 1):
                full = (0,) + vals
                rec(state + 1, acc + [full])
        else:
            for vals in itertools_product(alphabet, n, len(alphabet)):
                rec(state + 1, acc + [vals])
    def itertools_product(ntuples, n, k):
        if k == 0:
            yield ()
            return
        for v in ntuples:
            for rest in itertools_product(ntuples, n, k - 1):
                yield (v,) + rest
    rec(0, [])
    return rows

def bfs_canonical_dfa(n_states, alphabet):
    """Enumerate DFAs in BFS-canonical order (states introduced on first use).
    Returns a generator of (n_used, trans) where trans[i][x] is a state index."""
    # Represent partial DFA: dict mapping (state, sym) -> state or None.
    # We enumerate by number of *used* states, canonical BFS order.
    frontier = {}
    def rec_used(used, edges):
        # edges: list of (state, sym, target_or_None) fixed; remaining symbols
        # for the newest state are free.
        pass
    # Simpler: enumerate all transition tables on up to n_states states,
    # then canonicalize and dedupe by BFS-reachable state count.
    seen = set()
    out = []
    for trans in canonical_transitions(n_states, alphabet):
        # canonical BFS labelling
        canon = canonicalize(trans)
        if canon in seen:
            continue
        seen.add(canon)
        out.append(canon)
    return out

def canonicalize(trans):
    n = len(trans)
    # trans[i] is a tuple of length len(alphabet); entries may be None.
    # BFS from state 0, assign new indices in discovery order.
    mapping = {0: 0}
    order = [0]
    i = 0
    while i < len(order):
        cur = order[i]
        i += 1
        for x in range(len(trans[cur])):
            t = trans[cur][x]
            if t is None:
                continue
            if t not in mapping:
                mapping[t] = len(order)
                order.append(t)
    if len(order) == 1:
        return ((0,),)
    new = []
    for s in order:
        row = []
        for x in range(len(trans[s])):
            t = trans[s][x]
            row.append(mapping.get(t, None))
        new.append(tuple(row))
    return tuple(new)

# ---------- reverse NFA -> DFA for the other half-tape ----------

def complement_language_dfa(left_dfa, machine):
    """Given DFA `left_dfa` for one half-tape (state 0 all blank), build a DFA
    for the other half-tape whose language is the complement of what the
    machine can accept while `left_dfa` accepts.  In practice we simply build
    the DFA that tracks the symbols read from the other side and rejects the
    blank tape; the fixpoint below is what actually matters."""
    return None

# ---------- closed-context fixpoint ----------

def closure(left, right, table, n_states_machine, max_ctx=200000):
    """Compute the smallest set of contexts containing [0,0,0,0] closed under
    the kernel's transition rule.  Returns (contexts, ok) where ok is False if
    a halting context is forced."""
    contexts = set()
    contexts.add((0, 0, 0, 0))
    # left[l][s] -> l2 or None ; right[r][s] -> r2 or None
    def L(l, x):
        return left[l][x] if l < len(left) else None
    def R(r, x):
        return right[r][x] if r < len(right) else None
    work = deque([(0, 0, 0, 0)])
    while work:
        (l, q, s, r) = work.popleft()
        key = (l, q, s, r)
        if key not in contexts:
            continue
        if (q, s) not in table:
            return contexts, False
        w, move, q2 = table[(q, s)]
        if move == 1:
            l2 = L(l, w)
            if l2 is None:
                return contexts, False
            # for EVERY (r2, s2) with right[r2][s2] == r
            for r2 in range(len(right)):
                for s2 in range(2):
                    if R(r2, s2) == r:
                        nk = (l2, q2, s2, r2)
                        if nk not in contexts:
                            contexts.add(nk)
                            work.append(nk)
        else:
            r2 = R(r, w)
            if r2 is None:
                return contexts, False
            for l2 in range(len(left)):
                for s2 in range(2):
                    if L(l2, s2) == l:
                        nk = (l2, q2, s2, r2)
                        if nk not in contexts:
                            contexts.add(nk)
                            work.append(nk)
        if len(contexts) > max_ctx:
            return contexts, False
    return contexts, True

def emit_cert(left, right, contexts):
    """Convert internal DFA tables to kernel format."""
    def rows(dfa):
        out = []
        for row in dfa:
            newrow = []
            for x in row:
                newrow.append(None if x is None else x)
            out.append(newrow)
        return out
    return {
        "kind": "cps",
        "left": rows(left),
        "right": rows(right),
        "contexts": [list(c) for c in contexts],
    }

# ---------- main search ----------

def decide(tm):
    from neverhalt.kernel import check, Reject
    table = build_table(tm)
    n_states = max((q for (q, s) in table), default=0) + 1
    # try small DFAs for the left half-tape first
    for n in (1, 2, 3, 4):
        for left in bfs_canonical_dfa(n, [0, 1]):
            if len(left) > 3:
                continue
            # try to find a right DFA too: start with all-blank (1 state)
            for nr in (1, 2, 3):
                for right in bfs_canonical_dfa(nr, [0, 1]):
                    if len(right) > 3:
                        continue
                    ctxs, ok = closure(left, right, table, n_states)
                    if ok and len(ctxs) <= 200000:
                        cert = emit_cert(left, right, ctxs)
                        try:
                            check(tm, cert)
                            return cert
                        except Reject:
                            pass
    return None

if __name__ == '__main__':
    import json, sys
    tm = sys.argv[1]
    print(json.dumps(decide(tm)))
