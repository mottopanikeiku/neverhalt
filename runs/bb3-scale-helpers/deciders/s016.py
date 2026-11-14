from neverhalt.tm import parse
from neverhalt.helpers import closure

def _enumerate_tables(n, cap=200000):
    # Table: list of lists, table[state][symbol] = next_state or None.
    # State 0 loops on 0. Other transitions chosen from {0,1,...,n-1} or None.
    # We enumerate lazily to keep memory sane.
    from itertools import product
    vals = list(range(n)) + [None]
    # state 0: table[0][0] = 0 fixed; table[0][1] free
    # other states: both symbols free
    free = []
    free.append((0, 1))  # (state, symbol) for state 0, symbol 1
    for q in range(1, n):
        free.append((q, 0))
        free.append((q, 1))
    for combo in product(vals, repeat=len(free)):
        table = [[None, None] for _ in range(n)]
        table[0][0] = 0
        for (q, x), v in zip(free, combo):
            table[q][x] = v
        yield tuple(tuple(row) for row in table)

def decide(tm):
    table, n_states, n_symbols = parse(tm)
    # For each side we need push functions: push(state, symbol) -> next state.
    # Our automaton table maps (state, symbol) -> state or None.
    # Blank half-tape state is 0.
    def make_push(t):
        def push(state, symbol):
            v = t[state][symbol]
            if v is None:
                return None
            return v
        return push
    # Enumerate pairs of small automata.
    for n in (1, 2, 3):
        # Generate all candidate tables for left and right.
        # To keep time bounded, iterate pairs but break early.
        tables = list(_enumerate_tables(n))
        m = len(tables)
        # Try to be smarter: many machines only need one side to be a counter.
        # First try identical tables on both sides, then all pairs.
        for i in range(m):
            tl = tables[i]
            # quick self-pair first
            cands = [tables[i]]
            if i != 0:
                cands.append(tables[0])
            for j in range(m):
                cands.append(tables[j])
                for tr in cands:
                    cert = closure(
                        make_push(tl), make_push(tr),
                        0, 0, cap=200000,
                    )
                    if cert is not None:
                        # Verify before returning.
                        try:
                            from neverhalt.kernel import check
                            kind = check(tm, cert)
                            return cert
                        except Exception:
                            pass
        # If nothing found with size n, try larger.
    return None
  