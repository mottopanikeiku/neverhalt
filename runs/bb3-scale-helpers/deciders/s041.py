import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure


def decide(tm):
    table, n_states, n_symbols = parse(tm)
    n_states = len(table)
    # enumerate automata with up to 3 states per side, state 0 loops on 0
    def gen_automata(max_states):
        for k in range(1, max_states + 1):
            states = list(range(k))
            # transitions: list of tuples (write_symbol -> next_state or None)
            # each state has a mapping for symbols 0 and 1
            # enumerate all functions: for each state, for each symbol, choose target or None
            import itertools
            choices = [states + [None]]
            # product over (state, symbol)
            for combo in itertools.product(*([states + [None]] * (2 * k))):
                trans = {}
                ok = True
                for i in range(k):
                    for sym in range(2):
                        v = combo[2 * i + sym]
                        trans[(i, sym)] = v
                # state 0 must loop on symbol 0
                if trans[(0, 0)] != 0:
                    continue
                yield {i: (trans[(i, 0)], trans[(i, 1)]) for i in range(k)}

    # Precompute machine transitions
    mach = {}
    for q in range(n_states):
        for s in range(2):
            key = (q, s)
            if key in table:
                w, move, q2 = table[key]
                mach[key] = (w, move, q2)
            else:
                mach[key] = None

    blank_left = lambda st: 0 if st == 0 else None
    # push functions: state -> symbol -> new state or None
    def mk_push(trans):
        def push(st, sym):
            if st not in trans:
                return None
            return trans[st][sym]
        return push

    automata = []
    for automaton in gen_automata(3):
        automata.append(automaton)

    # try pairs
    for la in automata:
        for ra in automata:
            push_l = mk_push(la)
            push_r = mk_push(ra)
            try:
                cert = closure(mach, push_l, push_r, blank_left=lambda: 0, blank_right=lambda: 0, cap=200000)
            except Exception:
                cert = None
            if cert is None:
                continue
            try:
                kind = check(tm, cert)
                if kind:
                    return cert
            except Reject:
                continue
    return None


if __name__ == "__main__":
    tm = sys.argv[1]
    print(decide(tm))