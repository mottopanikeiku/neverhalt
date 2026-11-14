import sys
from collections import deque, defaultdict
from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(100000)

M = {}


def init(tm):
    if tm in M:
        return M[tm]
    table, ns, nsl = parse(tm)
    M[tm] = (table, ns, nsl)
    return table, ns, nsl


def halting_contexts(table, ns, nsl):
    h = []
    for q in range(ns):
        for s in range(nsl):
            if (q, s) not in table:
                h.append((q, s))
    return h


def step_right(table, q, s, w, q2, left, r):
    # transitions (q,s)->(w,move,q2)
    res = []
    n = len(left)
    for r2 in range(len(left)):
        if left[r2][s2_of(r2, s, left)] is None:
            pass
    return res


def s2_of(r2, s, left):
    # find s2 such that left[r2][s2] == r2? placeholder
    return None


def build_cps(table, ns, nsl, left, right, max_states=300000):
    # left/right: list of list, left[i][x] -> j or None
    contexts = set()
    contexts.add((0, 0, 0, 0))
    frontier = deque([(0, 0, 0, 0)])
    rule = {}
    # precompute transition list per (q,s)
    trans = {}
    for q in range(ns):
        for s in range(nsl):
            if (q, s) in table:
                trans[(q, s)] = table[(q, s)]
    # precompute predecessor pairs for left automaton
    left_pred = defaultdict(list)
    for i in range(len(left)):
        for x in range(nsl):
            j = left[i][x]
            if j is not None:
                left_pred[j].append((i, x))
    right_pred = defaultdict(list)
    for i in range(len(right)):
        for x in range(nsl):
            j = right[i][x]
            if j is not None:
                right_pred[j].append((i, x))
    while frontier:
        l, q, s, r = frontier.popleft()
        if (l, q, s, r) in contexts:
            continue
        contexts.add((l, q, s, r))
        if (q, s) not in trans:
            continue
        w, move, q2 = trans[(q, s)]
        if move > 0:
            l2 = left[l][w]
            if l2 is None:
                continue
            for (r2, s2) in right_pred.get(r, []):
                c = (l2, q2, s2, r2)
                if c not in contexts:
                    contexts.add(c)
                    frontier.append(c)
        else:
            r2 = right[r][w]
            if r2 is None:
                continue
            for (l2, s2) in left_pred.get(l, []):
                c = (l2, q2, s2, r2)
                if c not in contexts:
                    contexts.add(c)
                    frontier.append(c)
    return contexts


def has_halting(table, ns, nsl, contexts):
    for (l, q, s, r) in contexts:
        if (q, s) not in table:
            return True
    return False


def emit(tm, left, right, contexts):
    left_t = [[v for v in row] for row in left]
    right_t = [[v for v in row] for row in right]
    ctx = [[l, q, s, r] for (l, q, s, r) in contexts]
    return {"kind": "cps", "left": left_t, "right": right_t, "contexts": ctx}


def candidate_pairs():
    nsl = 2
    for n in (1, 2, 3):
        # enumerate transition tables with state 0 looping on symbol 0
        # states 0..n-1, symbols 0,1
        # state 0: on 0 -> (0,0) fixed; on 1 -> choose next state (0..n-1) or None
        # other states: each symbol choose target state 0..n-1 or None
        # represent each state as (out0, out1) with out in {None, 0..n-1}
        alphabet = [None] + list(range(n))
        # state 0 has out0 = 0 fixed
        choices = []
        for st in range(1, n):
            choices.append([(a, b) for a in alphabet for b in alphabet])
        import itertools
        for combo in itertools.product(*choices):
            # build left automaton
            left = [[0, 0]]
            for st in range(1, n):
                a, b = combo[st - 1]
                left.append([a, b])
            # right automaton can be same or different; try all pairs
            for n2 in (1, 2, 3):
                for combo2 in itertools.product(*choices[:0]) if False else [None]:
                    pass
            yield left
            yield left


def enumerate_automata(n, nsl=2):
    import itertools
    alphabet = [None] + list(range(n))
    choices = []
    for st in range(1, n):
        choices.append([(a, b) for a in alphabet for b in alphabet])
    for combo in itertools.product(*choices):
        left = [[0, 0]]
        for st in range(1, n):
            a, b = combo[st - 1]
            left.append([a, b])
        yield left


def try_all(tm, table, ns, nsl, max_states=3):
    # try small pairs first
    for n1 in range(1, max_states + 1):
        for n2 in range(1, max_states + 1):
            for left in enumerate_automata(n1, nsl):
                for right in enumerate_automata(n2, nsl):
                    contexts = build_cps(table, ns, nsl, left, right)
                    if len(contexts) > 200000:
                        continue
                    if not has_halting(table, ns, nsl, contexts):
                        try:
                            cert = emit(tm, left, right, contexts)
                            check(tm, cert)
                            return cert
                        except Reject:
                            pass
    return None


def decide(tm: str):
    table, ns, nsl = init(tm)
    if ns > 4 or nsl > 2:
        return None
    cert = try_all(tm, table, ns, nsl, max_states=3)
    if cert is not None:
        return cert
    return None


NAME = "cps_search_small"