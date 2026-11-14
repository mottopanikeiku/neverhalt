import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _delta(n_states, n_symbols):
    return [[None] * n_symbols for _ in range(n_states)]


def _closure(iface, left, right, n_states_m, n_states_
             symp):
    """iface: dict (l,q,s,r)->True. returns (contexts, ok)"""
    table = {}
    for (q, s), (w, mv, q2) in iface.items():
        if mv == +1:
            for (l, s2, r2) in table:
                if right[r2][s2] == r:
                    l2 = left[l][w]
                    if l2 is None:
                        return None, False
                    table[(l2, q2, w, r2)] = True
        else:
            for (l2, s2, r) in table:
                if left[l2][s2] == l:
                    r2 = right[r][w]
                    if r2 is None:
                        return None, False
                    table[(l2, q2, w, r2)] = True
    return table, True


def _try_pair(decide, tm, table, left, right, n_s_m, n_s_r, q0=0):
    """attempt to close the context set for this pair"""
    iface = {}
    for q in range(n_s_m):
        for s in range(2):
            if (q, s) in table:
                iface[(q, s)] = table[(q, s)]
    # start with blank tape contexts
    ctx = {(0, 0, 0, 0)}
    seen = set(ctx)
    queue = deque(ctx)
    while queue:
        l, q, s, r = queue.popleft()
        if (q, s) not in iface:
            continue
        w, mv, q2 = iface[(q, s)]
        if mv == +1:
            for (l2, s2, r2) in list(seen):
                if r2 == r and s2 == s:
                    pass
            # for each r2 with right[r2][?] == r, we need all s2
            for r2 in range(n_s_r):
                for s2 in range(2):
                    if right[r2][s2] == r:
                        l2 = left[l][w]
                        if l2 is None:
                            return None
                        nctx = (l2, q2, w, r2)
                        if nctx not in seen:
                            seen.add(nctx)
                            queue.append(nctx)
        else:
            for l2 in range(n_s_m):
                for s2 in range(2):
                    if left[l2][s2] == l:
                        r2 = right[r][w]
                        if r2 is None:
                            return None
                        nctx = (l2, q2, w, r2)
                        if nctx not in seen:
                            seen.add(nctx)
                            queue.append(nctx)
    return seen


def _emit(decide, tm, seen, left, right):
    contexts = [[list(c) for c in ctx] for ctx in seen]
    cert = {
        "kind": "cps",
        "left": left,
        "right": right,
        "contexts": contexts,
    }
    try:
        return check(tm, cert)
    except Reject:
        return None


def _build_ngram(n):
    # n-gram automaton: state = tuple of last n symbols read; 0 = blank
    states = [tuple([0] * n)]
    idx = {states[0]: 0}
    # transitions
    trans = [[None, None] for _ in range(len(states))]
    for i, st in enumerate(states):
        for x in (0, 1):
            ns = (st + (x,))[-n:]
            if ns not in idx:
                idx[ns] = len(states)
                states.append(ns)
                trans.append([None, None])
            trans[i][x] = idx[ns]
    # state 0 is the blank one
    return trans


def _is_blank_state(left, i, targ):
    """is state i equivalent to blank state on all-zero input?"""
    # check that reading all zeros stays in state i
    j = i
    for _ in range(64):
        j = left[j][0]
    return j == i


def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    if n_symbols != 2:
        return None
    # states are ints 0..n_states-1
    # the machine's transitions
    mtable = {}
    for q in range(n_states):
        for s in range(2):
            if (q, s) in table:
                w, mv, q2 = table[(q, s)]
                mtable[(q, s)] = (w, mv, q2)

    # build the blank state 0 for each ngram
    # try n from 1 to 4
    for n in (1, 2, 3, 4):
        left = _build_ngram(n)
        right = _build_ngram(n)
        # check blank half-tape invariant: state 0 on all zeros -> 0
        if not _is_blank_state(left, 0, 0):
            continue
        # attempt closure
        seen = _try_pair(decide, tm, mtable, left, right, len(left), len(right), 0)
        if seen is None:
            continue
        kind = _emit(decide, tm, seen, left, right)
        if kind is not None:
            return {"kind": "cps", "left": left, "right": right,
                    "contexts": [[list(c) for c in ctx] for ctx in seen]}
    return None


if __name__ == "__main__":
    import json
    import sys
    tm = sys.argv[1]
    r = decide(tm)
    if r:
        print(json.dumps(r))
