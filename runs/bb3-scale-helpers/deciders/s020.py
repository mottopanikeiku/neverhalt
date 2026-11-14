from neverhalt.helpers import closure

def decide(tm):
    import itertools
    from neverhalt.tm import parse
    table, ns, nsym = parse(tm)
    # collect used states
    used = sorted({q for (q, s) in table} | {q2 for (_, _, q2) in table.values()})
    S = ns
    # enumerate automata with 1..3 states per side; state 0 loops on 0
    def automata(n):
        # transitions for symbols 0,1
        for cells in itertools.product([True, False], repeat=2 * n):
            # construct table
            tab = [[None, None] for _ in range(n)]
            tab[0][0] = 0
            for st in range(n):
                for sym in range(2):
                    if st == 0 and sym == 0:
                        continue
                    v = cells[st * 2 + sym]
                    tab[st][sym] = (st + 1) % n if v else (st - 1) % n
            yield tab
    for nl in range(1, 4):
        for nr in range(1, 4):
            for lt in automata(nl):
                for rt in automata(nr):
                    try:
                        cert = closure(tm, blank_left=0, blank_right=0,
                                       push_left=lambda st, sym, lt=lt: lt[st][sym],
                                       push_right=lambda st, sym, rt=rt: rt[st][sym])
                    except Exception:
                        cert = None
                    if cert is not None:
                        return cert
    return None
