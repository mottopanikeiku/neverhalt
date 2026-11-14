import sys
sys.setrecursionlimit(100000)

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _halt_steps(tm):
    table, ns, nsym = parse(tm)
    out = []
    for q in range(ns):
        for s in range(2):
            if (q, s) not in table:
                out.append((q, s))
    return out


def _target_loop():
    # enumerate DFAs (transition tables) for a half-tape automaton.
    # state 0 loops on symbol 0. symbols are 0 and 1.
    for n in range(1, 4):
        for bits in range(4 ** n):
            t = []
            ok = True
            for i in range(n):
                for x in range(2):
                    d = (bits >> (2 * i + x)) & 1
                    if d:
                        t.append((i, x, None))
                    else:
                        t.append((i, x, (i + 1) % n))
            yield n, t


def _reachable_loop(n):
    # enumerate reachable DFAs with n states more cleverly: canonical BFS
    # order, growing state count.  We emit all deterministic tables where
    # state 0 loops on 0 and every state is reachable from 0.  Simplest:
    # enumerate transition tables for states 1..n-1 (2 choices each),
    # state 0 = (0,0)->0 fixed, (0,1)->s in 1..n-1 or 0.
    if n == 1:
        yield 1, [(0, 0, 0), (0, 1, 0)]
        return
    for bits in range((2 * (n - 1)) ** (n - 1)):
        t = [(0, 0, 0)]
        for i in range(1, n):
            for x in range(2):
                d = (bits >> (2 * (i - 1) + x)) & 1
                if d:
                    t.append((i, x, None))
                else:
                    t.append((i, x, (i + 1) % n))
        # state 0 on 1: choose a target
        for s in range(n):
            yield n, t + [(0, 1, s)]


def _build_right(aut):
    # aut: list of (i, x, j or None).  right[i][x] = j or None.
    n = len(aut)
    right = [[None, None] for _ in range(n)]
    for i, x, j in aut:
        right[i][x] = j
    return right


def _closure(tm, left, right, limit=200000):
    table, ns, nsym = parse(tm)
    # context: (l, q, s, r)
    start = (0, 0, 0, 0)
    seen = {start}
    stack = [start]
    halting = _halt_steps(tm)
    while stack:
        l, q, s, r = stack.pop()
        if (q, s) not in table:
            return None
        w, mv, q2 = table[(q, s)]
        if mv == 1:
            l2 = left[l][w]
            if l2 is None:
                return None
            for r2 in range(len(right)):
                for s2 in range(2):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            stack.append(c)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(len(left)):
                for s2 in range(2):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            stack.append(c)
        if len(seen) > limit:
            return None
    return seen


def _cert_from_contexts(tm, left, right, contexts):
    left_t = [[None, None] for _ in range(len(left))]
    for i in range(len(left)):
        for x in range(2):
            left_t[i][x] = left[i][x]
    right_t = [[None, None] for _ in range(len(right))]
    for i in range(len(right)):
        for x in range(2):
            right_t[i][x] = right[i][x]
    ctx = [[l, q, s, r] for (l, q, s, r) in contexts]
    cert = {"kind": "cps",
            "left": [[a, b] for a, b in [(None, None)]] if False else left_t,
            "right": right_t,
            "contexts": ctx}
    # kernel wants states as 0/None, not ints?  ints are fine (states are ints).
    return cert


def decide(tm):
    table, ns, nsym = parse(tm)
    # cheap precheck: reject if the machine halts quickly
    try:
        halted, steps, state, pos, tape = run(tm, 300)
        if halted:
            return None
    except Exception:
        pass
    best = None
    for n in range(1, 4):
        for aut in _target_loop():
            if aut[0] != n:
                continue
            right = _build_right(aut)
            # left automaton: the same enumeration, but state 0 loops on 0.
            for n2 in range(1, 4):
                for aut2 in _target_loop():
                    if aut2[0] != n2:
                        continue
                    left = _build_right(aut2)
                    ctx = _closure(tm, left, right)
                    if ctx is None:
                        continue
                    if (0, 0, 0, 0) not in ctx:
                        continue
                    cert = _cert_from_contexts(tm, left, right, ctx)
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        continue
    return None


if __name__ == "__main__":
    import neverhalt
    print(decide("1RB1LB_1LA---"))
