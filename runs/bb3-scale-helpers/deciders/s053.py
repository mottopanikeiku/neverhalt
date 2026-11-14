import sys
from neverhalt.tm import parse
from neverhalt.helpers import closure
from neverhalt.kernel import check, Reject


def build_push(table, n_states, n_symbols, n_mem, side):
    """Enumerate all transition tables for a half-tape automaton with n_mem
    states (state 0 is blank, loops on symbol 0 -> 0).  For each candidate
    return (push, blank) where push(state, symbol) is the next automaton state.

    For side == 'left' the automaton reads cells towards the head, i.e. when
    the machine moves right and writes a symbol, that symbol is pushed onto
    the left half-tape, so push_left(prev_state, written_symbol).
    Symmetric for the right side.
    """
    candidates = []
    # symbol alphabet is 0..n_symbols-1
    for code in range((n_mem ** (n_symbols * n_mem))):
        tbl = [[0] * n_symbols for _ in range(n_mem)]
        c = code
        ok = True
        for st in range(n_mem):
            for sy in range(n_symbols):
                tbl[st][sy] = c % n_mem
                c //= n_mem
        # state 0 must loop on symbol 0
        if tbl[0][0] != 0:
            continue
        push = {}
        for st in range(n_mem):
            for sy in range(n_symbols):
                push[(st, sy)] = tbl[st][sy]
        blank = 0
        candidates.append((push, blank))
    return candidates


def make_push_fn(cand):
    push, blank = cand
    def f(state, symbol):
        return push[(state, symbol)]
    return f, blank


def decide(tm):
    table, n_states, n_symbols = parse(tm)
    # try small half-tape automata, 1 then 2 then 3 states
    for n_mem in (1, 2, 3):
        try:
            lefts = build_push(table, n_states, n_symbols, n_mem, 'left')
            rights = build_push(table, n_states, n_symbols, n_mem, 'right')
        except Exception:
            continue
        for lp, lb in lefts:
            for rp, rb in rights:
                cert = closure(lp, lb, rp, rb)
                if cert is not None:
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        continue
    return None


def _unused(*a, **k):
    return None


DECIDER = decide

if __name__ == '__main__':
    tm = sys.argv[1]
    c = decide(tm)
    print(c)
