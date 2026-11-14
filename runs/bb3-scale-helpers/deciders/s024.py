from neverhalt.tm import parse
from neverhalt.helpers import closure


def decide(tm):
    table, n_states, n_symbols = parse(tm)
    # Enumerate small automata for the left half-tape and right half-tape.
    def enum_automata(n):
        # states 0..n-1, blank state 0 loops on 0
        # transitions for states 1..n-1 on symbols {0,1}
        choices = [None, 0, 1] * (n - 1) * 2
        # build via product
        import itertools
        for combo in itertools.product([0, 1, None], repeat=(n - 1) * 2):
            trans = {}
            for i in range(1, n):
                for s in (0, 1):
                    trans[(i, s)] = combo[(i - 1) * 2 + s]
            # blank state 0 loops on 0
            trans[(0, 0)] = 0
            # state 0 on 1: also allow anything? The spec: left[0][0]==0. 0 on 1 can be None or state.
            # we set trans[(0,1)] = None for now; try both
            yield trans

    def make_push(trans, side):
        # push function: state, symbol -> new state
        def push(state, symbol):
            if symbol not in (0, 1):
                return None
            v = trans.get((state, symbol))
            return v
        return push

    for n in (1, 2, 3):
        for lt in enum_automata(n):
            for rt in enum_automata(n):
                # blank state 0 on 0 loops; also try 0 on 1 -> 0
                # build push functions
                def mk(trans):
                    def push(state, symbol):
                        if state == 0 and symbol == 0:
                            return 0
                        return trans.get((state, symbol))
                    return push
                lp = mk(lt)
                rp = mk(rt)
                cert = closure(lp, rp, table, table,
                               n_states, n_symbols,
                               cap=200000)
                if cert is not None:
                    return cert
    return None
