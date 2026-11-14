import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import Reject
from neverhalt.helpers import closure

sys.setrecursionlimit(100000)


def all_tables(n):
    # automaton states 0..n-1; state 0 loops on 0.
    # push functions: state -> symbol -> state
    out = []
    for combo in range(1, 2 ** n):
        tbl = {}
        for st in range(n):
            if st == 0 and combo & 1:
                tbl[0] = 0
                continue
            for sym in (0, 1):
                pass
        out.append(combo)
    return out


def enumerate_automata(n):
    # returns list of (push_left, push_right, blank_left, blank_right) as dicts
    # push: dict (state,sym) -> state or None
    res = []
    # total transitions: for each state (except 0's 0) and each symbol: n choices
    # n=1: 1 automaton (0->0 on 0), the 1 transition optional
    # We'll enumerate push tables as dict with values None or 0..n-1
    import itertools
    if n == 1:
        for combo in itertools.product([None, 0], repeat=1):
            # state 0, symbol 1
            tbl = {(0, 0): 0, (0, 1): combo[0]}
            if tbl[(0, 1)] is None:
                continue
            res.append(tbl)
        return res
    if n == 2:
        # transitions: (0,1),(1,0),(1,1) each in {None,0,1}
        for a in itertools.product([None, 0, 1], repeat=3):
            tbl = {(0, 0): 0, (0, 1): a[0], (1, 0): a[1], (1, 1): a[2]}
            res.append(tbl)
        return res
    if n == 3:
        # transitions: (0,1),(1,0),(1,1),(2,0),(2,1) each in {None,0,1,2}
        for a in itertools.product([None, 0, 1, 2], repeat=5):
            tbl = {(0, 0): 0, (0, 1): a[0], (1, 0): a[1], (1, 1): a[2],
                   (2, 0): a[3], (2, 1): a[4]}
            res.append(tbl)
        return res
    return res


def make_closure_fn(tbl):
    blank = 0

    def push(state, symbol):
        return tbl.get((state, symbol), None)

    return push, blank


def build_decider():
    # Precompute automata candidates for n=1,2,3
    cands = []
    for n in (1, 2, 3):
        for tbl in enumerate_automata(n):
            cands.append((n, tbl))

    def decide(tm):
        try:
            parsed = parse(tm)
        except Exception:
            return None
        n_states = parsed[1]
        # map machine states to ints already A=0
        for (n, tbl) in cands:
            pl, bl = make_closure_fn(tbl)
            try:
                cert = closure(bl, pl, bl, pl, cap=200000)
            except Exception:
                cert = None
            if cert is None:
                continue
            # validate with kernel
            try:
                kind = check(tm, cert)
            except Reject:
                continue
            except Exception:
                continue
            return cert
        return None

    from neverhalt.kernel import check
    return decide


def check(tm, cert):
    from neverhalt.kernel import check as _check
    return _check(tm, cert)


decide = build_decider()
