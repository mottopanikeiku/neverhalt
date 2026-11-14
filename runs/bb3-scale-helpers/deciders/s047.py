import sys
from neverhalt.tm import parse
from neverhalt.helpers import closure

def _states_to_table(pairs):
    # pairs: list of (from, sym, to) -> dict mapping (from,sym)->to, None for absent
    t = {}
    for (f, s, to) in pairs:
        t[(f, s)] = to
    return t

def _build(pairs, n_states, blank):
    # push functions: push(state, symbol) -> state or None
    def push(state, symbol):
        to = pairs.get((state, symbol))
        return to
    return push, blank

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # Build a canonical list of (state, symbol) transitions for the machine
    # used only for reference: we don't need them for the CPS closure of the
    # half-tapes.  We enumerate small half-tape automata.
    SYM = (0, 1)
    # enumerate automata with 1, 2, 3 states, state 0 loops on 0 and is blank
    def enumerate_tables(max_states):
        # table dict: {(from, sym): to_or_None}
        from itertools import product
        for n in range(1, max_states + 1):
            # each transition is either absent or maps to one of n states
            # number of transitions: n * 2 ; each can be None or 0..n-1
            choices = [None] + list(range(n))
            for combo in product(choices, repeat=n * 2):
                tbl = {}
                ok = True
                for i in range(n):
                    for s in (0, 1):
                        idx = i * 2 + s
                        v = combo[idx]
                        if v is None:
                            pass
                        else:
                            tbl[(i, s)] = v
                # state 0 must loop on 0
                if tbl.get((0, 0)) != 0:
                    continue
                # blank state must be fixed: push(blank, 0) == blank
                # (already enforced for state 0; we treat state 0 as blank)
                yield tbl

    def try_pair(left_tbl, right_tbl):
        blank = 0
        def push_left(state, symbol):
            return left_tbl.get((state, symbol))
        def push_right(state, symbol):
            return right_tbl.get((state, symbol))
        try:
            cert = closure(push_left, push_right, blank_left=blank, blank_right=blank, cap=200000)
        except Exception:
            return None
        if cert is None:
            return None
        return cert

    # Quick sanity: the machine itself; if it already halts within a short run,
    # we can just return None (the decider only needs to prove non-halting).
    # Enumerate pairs of small automata.
    max_states = 3
    count = 0
    for lt in enumerate_tables(max_states):
        for rt in enumerate_tables(max_states):
            count += 1
            if count > 400000:
                return None
            cert = try_pair(lt, rt)
            if cert is not None:
                # trim to used transitions: kernel does that, but we can pass as is
                return cert
    return None


if __name__ == "__main__":
    # Small self-test: nothing printed on import.
    pass
