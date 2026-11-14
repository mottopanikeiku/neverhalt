from neverhalt.tm import parse
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure


def _all_tables(n_states, n_symbols=2):
    # left automaton reads cells from far away towards the head.
    # state 0 is the all-blank half-tape; it must loop on symbol 0.
    # each automaton state is an int 0..n_states-1
    # table[i][x] = next automaton state or None (never happens)
    # we enumerate all deterministic tables.
    choices = []
    for i in range(n_states):
        row = []
        for x in range(n_symbols):
            if i == 0 and x == 0:
                row.append(0)
            else:
                row.append(None)  # placeholder
        choices.append(row)
    # enumerate every assignment
    total = (n_states + 1) ** (n_states * n_symbols - 1) if n_states else 1
    for mask in range(total):
        table = [[None, None] for _ in range(n_states)]
        table[0][0] = 0
        m = mask
        for i in range(n_states):
            for x in range(n_symbols):
                if i == 0 and x == 0:
                    continue
                v = m % (n_states + 1)
                m //= (n_states + 1)
                table[i][x] = None if v == n_states else v
        yield table


def _blank_table(table):
    # blank[i][0] must loop on 0 for state 0; for other states we need
    # push(blank, 0) to return blank so all-blank half-tape is a fixed point.
    # We simply require the table restricted to symbol 0 to be a fixed point:
    # for every state i, table[i][0] must be 0? No: blank state is a single
    # state b such that push(b, 0) = b. In our encoding the all-blank half-tape
    # state is 0, so we need table[0][0] == 0 (already) and we must ensure
    # that from state 0 reading 0 we never leave 0. That is guaranteed.
    # For other states, table[i][0] can go anywhere; blank_left is just 0.
    return 0


def _try_pair(tm, n_states, cap):
    # precompute the machine transitions
    # parse(tm) -> table, n_states_m, n_symbols
    # table[(state, symbol)] = (write, move, next_state) ; halting transitions absent
    # We build push functions over automaton states.
    # For the left half-tape: it is read from far away towards the head.
    # When the head moves right, the cell it leaves is pushed onto the left
    # half-tape (nearest cell first, so push_left(state, symbol) is called
    # with the symbol just written at the cell the head leaves).
    # We enumerate deterministic automata tables and use closure() to test
    # the inductive invariant.
    #
    # The closure helper expects push functions that return the automaton
    # state after the half-tape grows by one cell next to the head.
    # We enumerate tables over states 0..n_states-1.
    mtab, n_m, n_s = parse(tm)
    # we only know the machine's transitions
    for lt in _all_tables(n_states):
        for rt in _all_tables(n_states):
            def push_left(state, symbol, _lt=lt):
                if symbol not in (0, 1):
                    return None
                return _lt[state][symbol]
            def push_right(state, symbol, _rt=rt):
                if symbol not in (0, 1):
                    return None
                return _rt[state][symbol]
            cert = closure(push_left, push_right,
                           blank_left=_blank_table(lt),
                           blank_right=_blank_table(rt), cap=cap)
            if cert is not None:
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
    return None


def decide(tm):
    for n_states in (1, 2, 3):
        # cap: number of contexts limit
        cap = 200000
        cert = _try_pair(tm, n_states, cap)
        if cert is not None:
            return cert
    return None