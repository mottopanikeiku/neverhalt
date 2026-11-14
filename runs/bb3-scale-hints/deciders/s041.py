import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

NAME = "fa_search"


def _transitions(n_states, n_symbols):
    out = []
    for i in range(n_states):
        for x in range(n_symbols):
            yield (i, x)


def _build_table(assign, n_states, n_symbols):
    table = {}
    for (i, x), v in assign.items():
        table[i, x] = v
    return table


def _close_contexts(tm, left, right, n_states):
    """Closed context set fixpoint for given left/right automata."""
    contexts = set()
    contexts.add((0, 0, 0, 0))
    changed = True
    while changed and len(contexts) < 200000:
        changed = False
        for (l, q, s, r) in list(contexts):
            if (q, s) not in tm:
                return None  # halting context
            w, mv, q2 = tm[(q, s)]
            if mv == +1:
                if (l, w) not in left:
                    return None
                l2 = left[(l, w)]
                if l2 is None:
                    return None
                for (r2, s2) in contexts_by_right:
                    if right[(r2, s2)] == r:
                        c = (l2, q2, s2, r2)
                        if c not in contexts:
                            contexts.add(c)
                            changed = True
            else:
                if (r, w) not in right:
                    return None
                r2 = right[(r, w)]
                if r2 is None:
                    return None
                for (l2, s2) in contexts_by_left:
                    if left[(l2, s2)] == l:
                        c = (l2, q2, s2, r2)
                        if c not in contexts:
                            contexts.add(c)
                            changed = True
    return contexts


def _contexts_by(table, n_states):
    out = []
    for i in range(n_states):
        for x in range(2):
            if (i, x) in table:
                out.append((i, x))
    return out


def _enumerate_tables(n_states, n_symbols, max_total, cur=(), used=0):
    """Enumerate deterministic automata with state 0 looping on 0."""
    if cur:
        yield cur
    if used >= max_total:
        return
    rem = max_total - used
    for i in range(n_states):
        for x in range(n_symbols):
            if (i, x) in cur:
                continue
            if i == 0 and x == 0:
                continue
            n_new = 1 + 1
            if n_new > rem:
                continue
            # assign j (existing or new)
            for j in range(n_states + (1 if used < n_states else 0)):
                if j < n_states:
                    nc = cur + ((i, x, j),)
                else:
                    nc = cur + ((i, x, None),)
                # placeholder; full enumeration is expensive, so we rely on
                # caller to bound n_states small
                yield nc


def _try_pair(tm, lt, rt, n_states):
    global contexts_by_left, contexts_by_right
    contexts_by_left = _contexts_by(lt, n_states)
    contexts_by_right = _contexts_by(rt, n_states)
    ctx = _close_contexts(tm, lt, rt, n_states)
    if ctx is None:
        return None
    # convert to certificate format
    left = []
    right = []
    for i in range(n_states):
        row = []
        for x in range(2):
            row.append(lt.get((i, x), None))
        left.append(row)
    for i in range(n_states):
        row = []
        for x in range(2):
            row.append(rt.get((i, x), None))
        right.append(row)
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    return {"kind": "cps", "left": left, "right": right, "contexts": contexts}


def decide(tm):
    parsed = parse(tm)
    table, n_states, n_symbols = parsed
    # Machine state -> int, symbol -> 0/1
    tm_table = table
    # Try small automata sizes
    for n in range(1, 4):
        # Build all deterministic automata over 2 symbols with n states,
        # state 0 loops on 0.
        for lt in _all_dfa(n):
            for rt in _all_dfa(n):
                if n > 2 and 0:
                    pass
                cert = _try_pair(tm_table, lt, rt, n)
                if cert is not None:
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
        if n >= 2:
            break
    return None


def _all_dfa(n):
    """All deterministic automata with n states, 2 symbols, state 0 loops on 0."""
    from itertools import product
    choices = list(range(n)) + [None]
    # state 0 on symbol 0 fixed to 0
    for rest in product(choices, repeat=n * 2 - 1):
        assign = {}
        k = 0
        for i in range(n):
            for x in range(2):
                if i == 0 and x == 0:
                    assign[(i, x)] = 0
                else:
                    assign[(i, x)] = rest[k]
                    k += 1
        yield assign
