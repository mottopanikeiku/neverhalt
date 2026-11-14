import itertools
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

STATES = "ABC"

def _table(tm):
    t, ns, nsy = parse(tm)
    return t, ns

def _halts_from_blank(tm, max_steps=200000):
    h, steps, st, pos, tape = run(tm, max_steps)
    return h

def _build_cps_contexts(t, ns, left, right):
    # left: dict (state,sym)->state or None ; right likewise
    # states 0..L-1, 0 is blank loop
    L = len(left)
    R = len(right)
    # context = (l, q, s, r)
    # start closure with [0,0,0,0]
    contexts = set()
    contexts.add((0, 0, 0, 0))
    changed = True
    while changed:
        changed = False
        for (l, q, s, r) in list(contexts):
            if q >= ns:
                continue
            # transition (q,s)
            if (q, s) not in t:
                # halting context -> reject this closure
                return None
            w, mv, q2 = t[(q, s)]
            if mv == 1:
                # right move: l2 = left[l][w]
                if w not in (0, 1):
                    return None
                l2 = left.get((l, w))
                if l2 is None:
                    return None
                # for EVERY pair (r2,s2) with right[r2][s2]==r, need (l2,q2,s2,r2)
                for r2 in range(R):
                    for s2 in (0, 1):
                        if right.get((r2, s2)) == r:
                            c = (l2, q2, s2, r2)
                            if c not in contexts:
                                contexts.add(c)
                                changed = True
            else:
                if w not in (0, 1):
                    return None
                r2 = right.get((r, w))
                if r2 is None:
                    return None
                for l2 in range(L):
                    for s2 in (0, 1):
                        if left.get((l2, s2)) == l:
                            c = (l2, q2, s2, r2)
                            if c not in contexts:
                                contexts.add(c)
                                changed = True
    # sanity: no halting context encountered
    for (l, q, s, r) in contexts:
        if (q, s) not in t:
            return None
    # convert to kernel format
    left_t = [[None, None] for _ in range(L)]
    right_t = [[None, None] for _ in range(R)]
    for (l, x), v in left.items():
        left_t[l][x] = v
    for (r, x), v in right.items():
        right_t[r][x] = v
    ctx = [[l, q, s, r] for (l, q, s, r) in contexts]
    return {"kind": "cps", "left": left_t, "right": right_t, "contexts": ctx}

def _dfa_from_transitions(ns, table, max_states=10):
    # enumerate DFA tables of size n (states 1..n-1 plus 0 loop on 0)
    # state 0 must loop on 0 (blank), and on 1 can go to 0 or another state.
    # we build incrementally: for n in 1..max_states, enumerate all tables
    for n in range(1, max_states + 1):
        total = n * 2
        # state 0: on 0 -> 0 (forced); on 1 -> any of 0..n-1
        # other states: on 0 -> any of 0..n-1; on 1 -> any of 0..n-1
        for combo in itertools.product(range(n), repeat=n * 2 - 1):
            left = {(0, 0): 0}
            idx = 0
            # state 0 on symbol 1
            left[(0, 1)] = combo[0]
            idx = 1
            for st in range(1, n):
                left[(st, 0)] = combo[idx]; idx += 1
                left[(st, 1)] = combo[idx]; idx += 1
            yield left

def _build_cps(tm):
    t, ns = _table(tm)
    # sanity: check machine actually runs (may halt early -> not our concern)
    if _halts_from_blank(tm, 100000):
        return None
    # try small symmetric DFA pairs first
    for n in range(1, 4):
        count = 0
        for left in _dfa_from_transitions(ns, None, n):
            count += 1
            if count > 20000:
                break
            for right in _dfa_from_transitions(ns, None, n):
                cert = _build_cps_contexts(t, ns, left, right)
                if cert is not None:
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
    # then try 1 vs 2
    for n1 in range(1, 3):
        for right in _dfa_from_transitions(ns, None, 2):
            for left in _dfa_from_transitions(ns, None, n1):
                cert = _build_cps_contexts(t, ns, left, right)
                if cert is not None:
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
    return None

def decide(tm: str):
    try:
        return _build_cps(tm)
    except Exception:
        return None
