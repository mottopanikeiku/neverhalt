NAME = "cps_enumerate"

def decide(tm: str):
    from neverhalt.tm import parse
    from neverhalt.helpers import closure

    table, n_states, n_symbols = parse(tm)
    q0 = 0

    # Automaton states: 0 = all-blank (loop on 0). For n in 1..3 additional states.
    # Transitions: state -> symbol -> state or None (never happens).
    def make_push(n):
        # states 0..n ; state 0 loops on symbol 0, and on symbol 1 goes to state 1.
        # non-blank states: on any symbol go to some state (we enumerate).
        return n

    import itertools

    best = None

    for n_left in (1, 2, 3):
        for n_right in (1, 2, 3):
            if best is not None:
                return best
            # enumerate transition tables for each side
            # side has states 0..n; transitions: for state 0: on 0 -> 0 (fixed), on 1 -> 1
            # for states 1..n: on 0 -> any of 0..n, on 1 -> any of 0..n
            # but also allow None (never happens) -> we encode None as n+1
            NONE = n_left + 1 + n_right + 1

            # enumerate left table
            for lt in itertools.product(range(n_left + 1), repeat=(n_left) * 2):
                # build push_left
                def push_left_blank(x):
                    return 0
                def blank_left():
                    return 0
                # left automaton: states 0..n_left
                # table: for state i in 0..n_left, symbol 0 and 1
                # state 0: on 0 -> 0, on 1 -> 1
                # states 1..n_left: on 0 -> lt[2*(i-1)], on 1 -> lt[2*(i-1)+1]
                def push_left(state, symbol):
                    if state == 0:
                        return 0 if symbol == 0 else 1
                    idx = 2 * (state - 1) + symbol
                    return lt[idx]
                def blank_left():
                    return 0
                # right table
                for rt in itertools.product(range(n_right + 1), repeat=(n_right) * 2):
                    def push_right(state, symbol):
                        if state == 0:
                            return 0 if symbol == 0 else 1
                        idx = 2 * (state - 1) + symbol
                        return rt[idx]
                    def blank_right():
                        return 0
                    try:
                        cert = closure(push_left, push_right, blank_left, blank_right, cap=200000)
                    except Exception:
                        cert = None
                    if cert is not None:
                        return cert

    return None
