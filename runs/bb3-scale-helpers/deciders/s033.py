import itertools
from neverhalt.tm import parse, run
from neverhalt.plot import plot
from neverhalt.helpers import closure

try:
    from neverhalt.tm import parse
    from neverhalt.helpers import closure
except Exception:
    from neverhalt.tm import parse
    from neverhalt.helpers import closure

NAME = "cps_auto_search"

def _build_automata(n_states):
    # states 0..n_states-1, state 0 loops on symbol 0 (blank)
    # enumerate transitions for each state and symbol
    results = []
    for trans in itertools.product(range(n_states), repeat=2*n_states):
        table = {}
        ok = True
        for i in range(n_states):
            for s in range(2):
                nxt = trans[i*2 + s]
                if nxt is None:
                    ok = False
                    break
                if nxt >= n_states:
                    ok = False
                    break
                table[(i, s)] = nxt
            if not ok:
                break
        if not ok:
            continue
        # enforce state 0 loops on symbol 0
        if table.get((0, 0)) != 0:
            continue
        results.append(table)
    return results

def _make_push(table, blank):
    def push(state, symbol):
        return table.get((state, symbol), state)
    return push

def decide(tm):
    table, n_states, n_symbols = parse(tm)
    n = n_states
    for k in (1, 2, 3):
        left_tabs = _build_automata(k)
        right_tabs = _build_automata(k)
        for lt in left_tabs:
            for rt in right_tabs:
                lp = _make_push(lt, 0)
                rp = _make_push(rt, 0)
                cert = closure(lp, rp, cap=200000)
                if cert is not None:
                    return cert
    return None
