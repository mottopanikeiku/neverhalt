from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

HALTING_STATES = -10**9

def build_cps(tm, left_trans, right_trans, max_steps=200000):
    table, n_states, n_symbols = parse(tm)
    states = list(range(n_states))
    # BFS closed-context fixpoint
    contexts = set()
    contexts.add((0, 0, 0, 0))
    frontier = [(0, 0, 0, 0)]
    while frontier:
        newf = []
        for (l, q, s, r) in frontier:
            trans = table.get((q, s))
            if trans is None:
                return None  # halting context -> not closed
            w, mv, q2 = trans
            if mv == +1:
                l2 = left_trans[l][w]
                if l2 is None:
                    return None
                for (r2, s2) in right_pairs(right_trans, r):
                    ctx = (l2, q2, s2, r2)
                    if ctx not in contexts:
                        contexts.add(ctx)
                        newf.append(ctx)
            else:
                r2 = right_trans[r][w]
                if r2 is None:
                    return None
                for (l2, s2) in left_pairs(left_trans, l):
                    ctx = (l2, q2, s2, r2)
                    if ctx not in contexts:
                        contexts.add(ctx)
                        newf.append(ctx)
        frontier = newf
        if len(contexts) > 200000:
            return None
    return contexts

def right_pairs(right_trans, r):
    out = []
    for s2 in range(len(right_trans[0])):
        rr = right_trans[r][s2]
        if rr is not None:
            out.append((rr, s2))
    return out

def left_pairs(left_trans, l):
    out = []
    for s2 in range(len(left_trans[0])):
        ll = left_trans[l][s2]
        if ll is not None:
            out.append((ll, s2))
    return out

def synth_decider(tm):
    table, n_states, n_symbols = parse(tm)
    # 1) enumerate small automata: 1..3 states, state 0 loops on 0
    best = None
    for n in (1, 2, 3):
        # enumerate all tables: state 0 forced to [0, 0] (loop on zero)
        # other states: (n-1) states * 2 symbols each 0..n-1 or None
        import itertools
        choices = [None] + list(range(n))
        for combo in itertools.product(choices, repeat=(n - 1) * 2):
            left_trans = [[0, 0]]
            for i in range(1, n):
                row = list(combo[(i - 1) * 2:(i - 1) * 2 + 2])
                left_trans.append(row)
            # build right automaton: mirror, but allow different table; try same first
            for rcombo in itertools.product(choices, repeat=(n - 1) * 2):
                right_trans = [[0, 0]]
                for i in range(1, n):
                    row = list(rcombo[(i - 1) * 2:(i - 1) * 2 + 2])
                    right_trans.append(row)
                ctxs = build_cps(tm, left_trans, right_trans)
                if ctxs is not None:
                    cert = {"kind": "cps", "left": left_trans, "right": right_trans,
                            "contexts": [list(c) for c in ctxs]}
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
    return None

def decide(tm: str):
    try:
        return synth_decider(tm)
    except Exception:
        return None
