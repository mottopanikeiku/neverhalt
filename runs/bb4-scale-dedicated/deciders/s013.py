from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def _build_tables(tm):
    table, ns, nsy = parse(tm)
    trans = {}
    for q in range(ns):
        for s in range(2):
            if (q, s) in table:
                trans[(q, s)] = table[(q, s)]
    return trans

def _dfa_trans(states, trans):
    # trans: list of (states, next_state) pairs for each symbol, or None
    out = []
    for s in trans:
        row = []
        for x in range(2):
            row.append(None)
        out.append(row)
    for (st, nxt) in trans:
        if st < len(out) and nxt < len(out):
            out[st][0] = nxt
    return out

def _dfa_row(states, trans):
    row = [None, None]
    for (st, nxt) in trans:
        if 0 <= st < states:
            row[0] = nxt
    return row

def decide(tm):
    try:
        trans = _build_tables(tm)
    except Exception:
        return None
    ns = max(q for (q, s) in trans) + 1
    # canonical DFA enumeration: each state gets a row (None,None) or (a,b)
    # generate all DFAs with up to N states, state 0 loops on 0
    N = 3
    best = None
    for size in range(1, N + 1):
        # enumerate all tables for size states with state 0 loops on 0
        import itertools
        rows_per_state = [(0, 0), (0, 1), (1, 0), (1, 1), (None, None)]
        for combo in itertools.product(rows_per_state, repeat=size):
            if combo[0][0] != 0:
                continue
            dfa = [list(combo[i]) for i in range(size)]
            if _closure_ok(dfa, trans, ns):
                return _emit(dfa, trans, ns)
    return None

def _closure_ok(dfa, trans, ns):
    # closed context fixpoint; return True if a closed set has no halting context
    # context: (l, q, s, r) where l,r are DFA states or None
    # Start from (0,0,0,0) and close
    start = (0, 0, 0, 0)
    seen = {start}
    stack = [start]
    while stack:
        (l, q, s, r) = stack.pop()
        if (q, s) not in trans:
            return False
        (w, move, q2) = trans[(q, s)]
        if move == 1:
            # right move: l2 = dfa[l][w]
            if l is None or l >= len(dfa):
                return False
            l2 = dfa[l][w]
            if l2 is None:
                return False
            # for every (r2, s2) with right[r2][s2] == r
            # we use the same dfa for right here (both half-tapes same language)
            for r2 in range(len(dfa)):
                for s2 in range(2):
                    if dfa[r2][s2] == r:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
        else:
            # left move: r2 = dfa[r][w]
            if r is None or r >= len(dfa):
                return False
            r2 = dfa[r][w]
            if r2 is None:
                return False
            for l2 in range(len(dfa)):
                for s2 in range(2):
                    if dfa[l2][s2] == l:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
    return True

def _emit(dfa, trans, ns):
    left = [list(r) for r in dfa]
    right = [list(r) for r in dfa]
    # contexts: enumerate all reachable contexts
    start = (0, 0, 0, 0)
    seen = {start}
    stack = [start]
    while stack:
        (l, q, s, r) = stack.pop()
        if (q, s) not in trans:
            return None
        (w, move, q2) = trans[(q, s)]
        if move == 1:
            l2 = left[l][w]
            if l2 is None:
                return None
            for r2 in range(len(right)):
                for s2 in range(2):
                    if right[r2][s2] == r:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(len(left)):
                for s2 in range(2):
                    if left[l2][s2] == l:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
    contexts = [[l, q, s, r] for (l, q, s, r) in seen]
    if len(contexts) > 200000:
        return None
    cert = {"kind": "cps", "left": left, "right": right, "contexts": contexts}
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None
    except Exception:
        return None
}