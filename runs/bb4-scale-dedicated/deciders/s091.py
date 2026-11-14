import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(10000)

def build_table(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states, n_symbols

def automaton_states(left, right):
    # left/right: list of rows [trans0, trans1] or None
    # state 0 is blank loop
    pass

# ---- CPS closure ----
def closure_contexts(tm, left, right):
    table, n_states, n_symbols = parse(tm)
    # contexts: set of (l,q,s,r)
    contexts = set()
    contexts.add((0, 0, 0, 0))
    changed = True
    while changed:
        changed = False
        for (l, q, s, r) in list(contexts):
            if q >= n_states:
                continue
            key = (q, s)
            if key not in table:
                # halting context -> invalid
                return None
            w, move, q2 = table[key]
            if move > 0:  # right
                if w >= 2:
                    return None
                l2 = left[l][w] if w < len(left[l]) else None
                if l2 is None:
                    return None
                # for every (r2, s2) with right[r2][s2] == r
                for r2 in range(len(right)):
                    for s2 in range(2):
                        if right[r2][s2] == r:
                            ct = (l2, q2, s2, r2)
                            if ct not in contexts:
                                contexts.add(ct)
                                changed = True
            else:  # left
                if w >= 2:
                    return None
                r2 = right[r][w] if w < len(right[r]) else None
                if r2 is None:
                    return None
                for l2 in range(len(left)):
                    for s2 in range(2):
                        if left[l2][s2] == l:
                            ct = (l2, q2, s2, r2)
                            if ct not in contexts:
                                contexts.add(ct)
                                changed = True
    return contexts

def emit_cps(tm, left, right, contexts):
    lc = []
    for i in range(len(left)):
        row = []
        for x in range(2):
            t = left[i][x]
            row.append(t)
        lc.append(row)
    rc = []
    for i in range(len(right)):
        row = []
        for x in range(2):
            t = right[i][x]
            row.append(t)
        rc.append(row)
    ctx = [[l, q, s, r] for (l, q, s, r) in contexts]
    return {"kind": "cps", "left": lc, "right": rc, "contexts": ctx}

def try_cps(tm, left, right):
    table, n_states, n_symbols = parse(tm)
    contexts = closure_contexts(tm, left, right)
    if contexts is None:
        return None
    cert = emit_cps(tm, left, right, contexts)
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None
    return cert

# ---- enumerate small automata ----
def enum_automata(max_states):
    out = []
    for n in range(1, max_states + 1):
        # rows: list of length 2, values 0..n-1 or None
        # state 0 must loop on 0
        def rec(i, rows):
            if i == n:
                if rows[0][0] != 0:
                    return
                out.append([list(r) for r in rows])
                return
            for a in [0, 1]:
                for b in [0, 1]:
                    rows.append([a, b])
                    rec(i + 1, rows)
                    rows.pop()
        rec(0, [])
    return out

def decide(tm: str):
    for left in enum_automata(3):
        for right in enum_automata(3):
            c = try_cps(tm, left, right)
            if c is not None:
                return c
    # also try 2-state on one side
    for left in enum_automata(2):
        for right in enum_automata(3):
            c = try_cps(tm, left, right)
            if c is not None:
                return c
    for left in enum_automata(3):
        for right in enum_automata(2):
            c = try_cps(tm, left, right)
            if c is not None:
                return c
    return None

if __name__ == "__main__":
    import sys
    print(decide(sys.argv[1]))
