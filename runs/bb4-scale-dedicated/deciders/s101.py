import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---------- helpers ----------

def machine_info(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states, n_symbols

# ---------- search over small half-tape automata ----------

def enumerate_automata(max_states, alphabet):
    """Yield transition tables for deterministic automata with states 0..k-1.
    State 0 is the all-blank half-tape: table[0][0] == 0.
    Each entry is either an int state or None (never happens).
    """
    states = list(range(max_states))
    # transitions: for each state, a tuple of targets per symbol
    # BFS over partial tables in canonical order of growing size
    def rec(idx, cur):
        if idx == max_states:
            # canonical: require state 0 loops on symbol 0
            if cur[0][0] != 0:
                return
            yield [list(row) for row in cur]
            return
        for targets in _choice_space(alphabet):
            nxt = [row[:] for row in cur]
            nxt[idx] = targets
            yield from rec(idx + 1, nxt)
    # We iterate over all assignments lazily; but to keep it bounded, we
    # produce tables in a fixed order.
    def _choice_space(alphabet):
        opts = [None] + states
        for _ in range(len(alphabet)):
            yield tuple(_prod(alphabet, opts))
        # the above generator is awkward; replaced below
    # simpler: build all tuple assignments directly
    total = len(alphabet) * max_states
    for mask in range(_count_assignments(max_states, len(alphabet))):
        cur = _decode_mask(mask, max_states, len(alphabet), alphabet)
        if cur is None:
            continue
        if cur[0][0] != 0:
            continue
        yield cur

def _count_assignments(k, m):
    return (k + 1) ** m

def _decode_mask(mask, k, m, alphabet):
    # one entry per (state, symbol) in row-major order; each entry range 0..k
    # 0 means state 0, k means None
    cur = [[None] * m for _ in range(k)]
    for i in range(k):
        for j in range(m):
            v = mask % (k + 1)
            mask //= (k + 1)
            cur[i][j] = None if v == k else v
    return cur

# ---------- fixpoint closure for context sets ----------

def close_contexts(table, n_states, n_symbols, left, right, max_contexts=200000):
    """Compute the smallest closed context set for given automaton tables.
    Returns (contexts, ok) where ok is False if a halting context is forced."""
    # context: (l, q, s, r)
    init = (0, 0, 0, 0)
    seen = {init}
    stack = [init]
    contexts = {}
    while stack:
        l, q, s, r = stack.pop()
        if (l, q, s, r) in contexts:
            continue
        # transition must exist
        key = (q, s)
        if key not in table:
            return None, False
        w, move, q2 = table[key]
        if move == +1:
            l2 = left[l][w] if l < len(left) and w < len(left[l]) else None
            if l2 is None:
                return None, False
            # for every (r2, s2) with right[r2][s2] == r
            for r2 in range(len(right)):
                for s2 in range(len(right[r2])):
                    if right[r2][s2] == r:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
        else:
            r2 = right[r][w] if r < len(right) and w < len(right[r]) else None
            if r2 is None:
                return None, False
            for l2 in range(len(left)):
                for s2 in range(len(left[l2])):
                    if left[l2][s2] == l:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
        contexts[(l, q, s, r)] = True
        if len(seen) > max_contexts:
            return None, False
    # check no halting context: by construction all transitions existed,
    # but we must ensure no context is a halting one: we already rejected
    # missing transitions.  Also ensure init is present (it is).
    if init not in contexts:
        return None, False
    ctx_list = [[l, q, s, r] for (l, q, s, r) in seen]
    return ctx_list, True

# ---------- main ----------

def decide(tm: str):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    if n_symbols != 2:
        return None
    alphabet = [0, 1]
    # search over small automata sizes
    for size in (1, 2, 3, 4):
        for left in enumerate_automata(size, alphabet):
            # quick sanity: state 0 loops on 0
            if left[0][0] != 0:
                continue
            for right in enumerate_automata(size, alphabet):
                if right[0][0] != 0:
                    continue
                ctx, ok = close_contexts(table, n_states, 2, left, right)
                if ok and ctx is not None:
                    cert = {
                        "kind": "cps",
                        "left": left,
                        "right": right,
                        "contexts": ctx,
                    }
                    try:
                        check(tm, cert)
                    except Reject:
                        continue
                    except Exception:
                        continue
                    return cert
    return None
