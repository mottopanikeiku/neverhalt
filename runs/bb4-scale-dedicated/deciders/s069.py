import sys
from collections import deque
from neverhalt.tm import parse

STATES = 5  # machine states A..E


def _machine_tables(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states


def _transitions_only(tm):
    """Return {(q,s):(w,move,q2)} for defined transitions."""
    table, _ = _machine_tables(tm)
    out = {}
    for (q, s), (w, m, q2) in table.items():
        out[(q, s)] = (w, m, q2)
    return out


def _enumerate_dfa_tables(n, max_states):
    """Yield DFA transition tables for one half-tape.

    Table: dict (state, symbol) -> next_state, or None (never).
    State 0 is the all-blank tape: (0, 0) -> 0 always.
    Enumerate all deterministic tables with states 0..n-1,
    symbols 0 and 1, where 0 loops on 0.
    """
    syms = (0, 1)
    total = n * len(syms)
    for mask in range(2 ** total):
        tab = {}
        ok = True
        for i in range(total):
            st = i // 2
            sy = i % 2
            v = (mask >> i) & 1
            if st == 0 and sy == 0:
                tab[(0, 0)] = 0
            elif v:
                tab[(st, sy)] = (i + 1) % n  # placeholder; replaced below
        # re-enumerate properly: value encodes target state
        tab = {}
        for st in range(n):
            for sy in (0, 1):
                if st == 0 and sy == 0:
                    tab[(0, 0)] = 0
                else:
                    idx = st * 2 + sy
                    if (mask >> idx) & 1:
                        tab[(st, sy)] = (st + 1) % n
        yield tab


def _dfa_tables(n):
    """Proper enumeration of all DFAs with n states; state 0 loops on 0."""
    syms = (0, 1)
    total = n * len(syms)
    for mask in range(2 ** total):
        tab = {}
        for st in range(n):
            for sy in syms:
                if st == 0 and sy == 0:
                    tab[(0, 0)] = 0
                else:
                    idx = st * 2 + sy
                    v = (mask >> idx) & 1
                    if v:
                        tab[(st, sy)] = st  # 0 means undefined; fix below
        # decode: bit 0 = defined, bits above = target
        tab = {}
        for st in range(n):
            for sy in syms:
                idx = st * 2 + sy
                if st == 0 and sy == 0:
                    tab[(0, 0)] = 0
                    continue
                if (mask >> idx) & 1:
                    target = (mask >> (idx + 1)) & 0x7F
                    if target < n:
                        tab[(st, sy)] = target
        yield tab


def _context_key(l, q, s, r):
    return (l, q, s, r)


def _close_contexts(tm, left, right, max_ctx=200000):
    """Fixpoint closure of contexts. Return list or None if halting context found."""
    table = _transitions_only(tm)
    seen = set()
    stack = [(_context_key(0, 0, 0, 0))]
    seen.add(_context_key(0, 0, 0, 0))
    contexts = []
    while stack:
        ctx = stack.pop()
        l, q, s, r = ctx
        if ctx not in seen:
            seen.add(ctx)
        if len(seen) > max_ctx:
            return None
        key = (q, s)
        if key not in table:
            return None  # halting context
        w, m, q2 = table[key]
        if m == 1:  # right move
            l2 = left.get((l, w))
            if l2 is None:
                return None
            # every (r2, s2) with right[r2][s2] == r
            for (r2, s2), rr in right.items():
                if rr == r:
                    nk = (_context_key(l2, q2, s2, r2))
                    if nk not in seen:
                        seen.add(nk)
                        stack.append(nk)
        else:  # left move
            r2 = right.get((r, w))
            if r2 is None:
                return None
            for (l2, s2), ll in left.items():
                if ll == l:
                    nk = (_context_key(l2, q2, s2, r2))
                    if nk not in seen:
                        seen.add(nk)
                        stack.append(nk)
    # rebuild list from seen
    contexts = [list(c) for c in seen]
    return contexts


def _dfa_pairs(n):
    tabs = list(_dfa_tables(n))
    for L in tabs:
        for R in tabs:
            yield L, R


def decide(tm: str):
    try:
        table, n_states = _machine_tables(tm)
    except Exception:
        return None
    # Try one DFA per side, growing sizes.
    for n in (1, 2, 3):
        for left, right in _dfa_pairs(n):
            # normalize: state 0 must loop on 0
            if left.get((0, 0)) != 0 or right.get((0, 0)) != 0:
                continue
            contexts = _close_contexts(tm, left, right)
            if contexts is None:
                continue
            # Build certificate: left/right tables including nulls.
            def fmt(tab):
                nst = max([k[0] for k in tab] + [0]) + 1
                out = []
                for i in range(nst):
                    row = []
                    for x in (0, 1):
                        row.append(tab.get((i, x)))
                    out.append(row)
                return out
            cert = {
                "kind": "cps",
                "left": fmt(left),
                "right": fmt(right),
                "contexts": contexts,
            }
            return cert
    return None


if __name__ == "__main__":
    import sys
    from neverhalt.kernel import check
    tm = sys.argv[1]
    c = decide(tm)
    if c is None:
        print("none")
    else:
        try:
            k = check(tm, c)
            print("accepted", k)
        except Exception as e:
            print("rejected", e)
