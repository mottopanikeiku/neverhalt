import sys
from neverhalt.tm import parse

sys.setrecursionlimit(100000)


def _table(t, q):
    row = t.get((q, 1), t.get((q, 0)))
    return row


def _build_left(t, ns, sizes, budget):
    # enumerate DFAs for the left half-tape read far-to-head.
    # state 0 = all-blank half-tape, loops on 0.
    out = []
    for n in sizes:
        for bits in range(1 << (n - 1)):
            tab = [[None, None] for _ in range(n)]
            tab[0][0] = 0
            ok = True
            for i in range(1, n):
                # state i's transition on 0: either stay or move to a lower state
                for x in range(1 << (n - 1)):
                    pass
                break
            if ok:
                out.append(tab)
    return out


def decide(tm):
    try:
        t, ns, nsym = parse(tm)
    except Exception:
        return None
    # quick simulate to detect halting (then no certificate needed)
    try:
        from neverhalt.tm import run
        h, steps, st, pos, tape = run(tm, 300)
        if h:
            return None
    except Exception:
        pass
    # design small left automaton: 1, 2, 3 states; right automaton computed by search.
    # For the 3-state hint machines, a 2-state "last symbol" automaton on the left
    # plus a 2-state automaton on the right usually closes.
    for nsL in (1, 2, 3):
        for nsR in (1, 2, 3):
            cert = _try(tm, t, ns, nsL, nsR)
            if cert is not None:
                return cert
    return None


def _try(tm, t, ns, nsL, nsR):
    from neverhalt.kernel import Reject
    # build left automaton: state 0 blank, states 1..nsL-1 track last nsL-1 cells
    def mk(n):
        tab = [[None, None] for _ in range(n)]
        tab[0][0] = 0
        for i in range(1, n):
            tab[i][0] = i
        return tab
    left = mk(nsL)
    right = mk(nsR)
    # fixpoint over contexts
    ctx = set()
    ctx.add((0, 0, 0, 0))
    frontier = list(ctx)
    seen = set(ctx)
    while frontier:
        c = frontier.pop()
        l, q, s, r = c
        if q >= ns:
            continue
        tr = t.get((q, s))
        if tr is None:
            # halting context: reject this pair
            return None
        w, mv, q2 = tr
        if mv > 0:
            l2 = left[l][w]
            if l2 is None:
                return None
            # pop nearest cell s2 from right: any (r2, s2) with right[r2][s2] == r
            pairs = [(rr, ss) for rr in range(nsR) for ss in (0, 1) if right[rr][ss] == r]
            for rr, ss in pairs:
                nc = (l2, q2, ss, rr)
                if nc not in seen:
                    seen.add(nc)
                    ctx.add(nc)
                    frontier.append(nc)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            pairs = [(ll, ss) for ll in range(nsL) for ss in (0, 1) if left[ll][ss] == l]
            for ll, ss in pairs:
                nc = (ll, q2, ss, r2)
                if nc not in seen:
                    seen.add(nc)
                    ctx.add(nc)
                    frontier.append(nc)
    # emit certificate in kernel format
    return {
        "kind": "cps",
        "left": left,
        "right": right,
        "contexts": [list(c) for c in ctx],
    }