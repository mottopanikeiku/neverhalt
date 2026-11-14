from neverhalt.tm import parse
from neverhalt.helpers import closure

# Enumerate small 1/2/3-state automata per side, including a loop on blank at
# state 0, and build a CPS certificate whenever the smallest closed context set
# has no halting context.  Only the transitions used by the closure are kept.

def _auto_tables(n):
    out = []
    for seq in _prod(n):
        tab = {}
        for i in range(n):
            for x in (0, 1):
                tab[(i, x)] = seq[i * 2 + x]
        if tab[(0, 0)] != 0:
            continue
        out.append(tab)
    return out

def _prod(n):
    if n == 1:
        return [[0], [1]]
    res = []
    for p in _prod(n - 1):
        for x in (0, 1):
            res.append(p + [x])
    return res

def _push_from(tab, s):
    # push_left/right: state after half-tape grows by one cell next to head
    def push(state, symbol):
        return tab.get((state, symbol))
    return push

def _from_state(state):
    return state

def _cert_from_pair(tm, left_tab, right_tab):
    try:
        cert = closure(
            _push_from(left_tab, 0), _push_from(right_tab, 0),
            blank_left=0, blank_right=0, cap=200000,
        )
    except Exception:
        return None
    if cert is None:
        return None
    return cert

_BASE = [None]

def decide(tm):
    from neverhalt.tm import parse as _p
    _p(tm)
    for n in (1, 2, 3):
        tabs = _auto_tables(n)
        for lt in tabs:
            for rt in tabs:
                c = _cert_from_pair(tm, lt, rt)
                if c is not None:
                    return c
    return None
