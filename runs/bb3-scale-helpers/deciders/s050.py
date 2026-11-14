from neverhalt.tm import parse, run
from neverhalt.helpers import closure

# Small automata search for CPS certificates.
# Enumerate transition tables for left/right half-tape automata,
# find pairs whose smallest closed context set contains [0,0,0,0]
# and no halting context.

def _enumerate(n_states, cap):
    # returns list of (table, blank) where table[(state,sym)] = next state or None
    syms = (0, 1)
    # state 0 must loop on symbol 0 (all-blank half-tape)
    def rec(state, rows):
        if state == n_states:
            return rows
        out = []
        choices = [0] if state == 0 and syms[0] == 0 else range(n_states)
        # we build row by row: for state 0, symbol 0 must be 0
        for a in ([0] if state == 0 else range(n_states)):
            for b in range(n_states):
                rows.append((state, 0, a, state, 1, b))
                r = rec(state + 1, rows)
                if r: out.extend(r)
                rows.pop()
        return out
    # simpler: build lists
    res = []
    def build(state, rows):
        if state == n_states:
            res.append(rows)
            return
        for a in ([0] if state == 0 else range(n_states)):
            for b in range(n_states):
                rows.append(((state, 0), a, (state, 1), b))
                build(state + 1, rows)
                rows.pop()
    build(0, [])
    return res

def _mk_push(rows):
    # rows: list of (state, sym, next)
    tab = {}
    for st, sym, nx in rows:
        tab[(st, sym)] = nx
    return tab

def decide(tm):
    table, n_states, n_syms = parse(tm)
    # machine state encoding: states are ints A=0. Halting transitions absent.
    # push functions: automaton state -> (next_state, symbol)
    # For left automaton: reading cells left of head towards head.
    # push_left(state, symbol) returns new automaton state after adding a cell.
    # We treat automaton states as ints; blank state 0; push(blank,0)=blank.
    for ns in (1, 2, 3):
        rows = _enumerate(ns, 200000)
        for L in rows:
            lt = _mk_push(L)
            for R in rows:
                rt = _mk_push(R)
                def blank_l():
                    return 0
                def blank_r():
                    return 0
                # closure expects push functions; wrap
                def pl(s, x, _t=lt):
                    # if transition absent, return None sentinel? closure handles null
                    return _t.get((s, x))
                def pr(s, x, _t=rt):
                    return _t.get((s, x))
                cert = closure(pl, pr, blank_l, blank_r, cap=200000)
                if cert is not None:
                    # verify with kernel
                    from neverhalt.kernel import check, Reject
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
    return None