from neverhalt.tm import parse, run
from neverhalt.kernel import Reject, check
from neverhalt.helpers import closure

def _build_side(n):
    """All deterministic 1-state-per-cell automata with n states; state 0 loops on 0."""
    out = []
    if n == 1:
        return [[0]]
    # enumerate tables: for states 1..n-1, each of 2 symbols maps to any state
    import itertools
    for vals in itertools.product(range(n), repeat=2 * (n - 1)):
        tab = [[0, 0]]
        for i in range(1, n):
            tab.append([vals[2 * (i - 1)], vals[2 * (i - 1) + 1]])
        out.append(tab)
    return out

def _try_pair(tm, max_states=3, cap=200000):
    tables, ns, nsm = parse(tm)
    # basic sanity: cannot halt under the invariant
    for L in range(1, max_states + 1):
        for R in _build_side(L):
            for Rr in _build_side(max_states + 1):
                pass
    # limit enumeration cost; try 1 state per side first, then 2, then 3
    for nL in range(1, max_states + 1):
        for nR in range(1, max_states + 1):
            if nL * nR > 9:
                continue
            for lt in _build_side(nL):
                for rt in _build_side(nR):
                    # skip automata that can reach a halting context:
                    # state 0 must loop on symbol 0 on both sides
                    if lt[0][0] != 0 or rt[0][0] != 0:
                        continue
                    try:
                        cert = closure(lt, rt, blank_left=0, blank_right=0, cap=cap)
                    except Exception:
                        continue
                    if cert is not None:
                        try:
                            check(tm, cert)
                        except Reject:
                            continue
                        return cert
    return None

def decide(tm: str):
    try:
        return _try_pair(tm, 3, 200000)
    except Exception:
        return None
