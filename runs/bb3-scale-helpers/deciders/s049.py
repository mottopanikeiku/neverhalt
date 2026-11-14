from neverhalt.tm import parse
from neverhalt.helpers import closure

# Enumerate small deterministic automata for each half-tape.
# State 0 is the all-blank half-tape and must loop on blank: t[0][0] = 0.
# We enumerate transition tables with 1..3 states, transitions on {0,1}.

def enum_tables(max_states, cap=200000):
    import itertools
    for n in range(1, max_states + 1):
        # table[state][symbol] = next_state or None
        for bits in itertools.product(range(n + 1), repeat=2 * n):
            t = [[bits[2 * i], bits[2 * i + 1]] for i in range(n)]
            if t[0][0] != 0:
                continue
            yield n, t

def decide(tm):
    table, n_states, n_symbols = parse(tm)
    # push functions
    def make_push(t):
        def f(state, sym):
            v = t[state][sym]
            return v if v is not None else None
        return f
    for n, tl in enum_tables(3):
        for n2, tr in enum_tables(3):
            cert = closure(tl, tr, blank_left=0, blank_right=0, cap=200000)
            if cert is not None:
                # verify with the kernel before returning
                from neverhalt.kernel import check, Reject
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
    return None
