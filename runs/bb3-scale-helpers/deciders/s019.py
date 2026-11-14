from neverhalt.tm import parse, run
from neverhalt.helpers import closure

# Build a small pool of half-tape automata (push functions) and try every pair.
def _auto_pool(max_states):
    pool = []
    # states are ints; state 0 = all-blank, must loop on 0.
    for n in range(1, max_states + 1):
        states = list(range(n))
        # enumerate transition tables: left[i][x] for x in {0,1}, with left[0][0]==0
        for mask in range(1 << (2 * (n - 1))):
            L = [[None, None] for _ in states]
            L[0][0] = 0
            ok = True
            for i in range(1, n):
                a = (mask >> (2 * (i - 1))) & 1
                b = (mask >> (2 * (i - 1) + 1)) & 1
                L[i][0] = states[a] if a < n else None
                L[i][1] = states[b] if b < n else None
            # right automaton is built symmetrically later; here store L as 'left' candidate
            pool.append(tuple(tuple(L[i]) for i in range(n)))
    return pool

def _mk_left(L):
    def push_left(state, symbol):
        if state is None:
            return None
        row = L[state]
        if symbol < 2 and symbol < len(row):
            return row[symbol]
        return None
    return push_left

def _mk_right(L):
    def push_right(state, symbol):
        if state is None:
            return None
        row = L[state]
        if symbol < 2 and symbol < len(row):
            return row[symbol]
        return None
    return push_right

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # Try pairs of automata from a small pool.
    pool = _auto_pool(3)
    seen = set()
    for L in pool:
        keyL = L
        for R in pool:
            pair = (keyL, R)
            if pair in seen:
                continue
            seen.add(pair)
            try:
                cert = closure(
                    left=_mk_left(L),
                    right=_mk_right(R),
                    blank_left=0,
                    blank_right=0,
                    cap=200000,
                )
            except Exception:
                continue
            if cert is not None:
                return cert
    return None
