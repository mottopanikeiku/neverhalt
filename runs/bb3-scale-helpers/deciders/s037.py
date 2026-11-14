NAME = "bouncer_search"

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure


def _sym_states(tm):
    table, n_states, n_symbols = parse(tm)
    syms = range(n_symbols)
    return table, n_states, syms


def _trans(tm, q, s):
    table, n_states, _ = _sym_states(tm)
    t = table.get((q, s))
    if t is None:
        return None
    w, mv, q2 = t
    return w, mv, q2


def decide(tm):
    table, n_states, syms = parse(tm)

    # Precompute the full transition function for the machine.
    full = {}
    for (q, s), t in table.items():
        full[(q, s)] = t

    def push_left(state, symbol, left_table):
        return left_table.get((state, symbol))

    def push_right(state, symbol, right_table):
        return right_table.get((state, symbol))

    def build_tables(k):
        # For k states per side, enumerate all transition tables.
        # state 0 must loop on symbol 0 to be the blank state.
        # Also require push(blank, 0) == blank for both sides.
        syms = [0, 1]
        tables = []
        for state in range(k):
            for sym in syms:
                if state == 0 and sym == 0:
                    continue
                for nxt in range(k):
                    if state == 0 and sym == 0 and nxt != 0:
                        continue
                    tables.append((state, sym, nxt))
        # We generate all combos via recursive enumeration.
        base_entries = []
        for state in range(k):
            for sym in syms:
                if state == 0 and sym == 0:
                    base_entries.append((state, sym, 0))
                else:
                    base_entries.append((state, sym, None))
        # Enumerate assignments of the "free" entries.
        free_idx = []
        assigned0 = []
        for i, (st, sy, _) in enumerate(base_entries):
            if st == 0 and sy == 0:
                assigned0.append(0)
            else:
                free_idx.append(i)
        total = k ** len(free_idx)
        # To keep runtime bounded, cap enumeration count.
        if total > 200000:
            return None
        # Generate tables lazily by iterating in a structured order.
        for combo in range(total):
            vals = []
            c = combo
            for _ in free_idx:
                vals.append(c % k)
                c //= k
            tbl = {}
            for i, (st, sy, _) in enumerate(base_entries):
                if st == 0 and sy == 0:
                    tbl[(st, sy)] = 0
                else:
                    idx = free_idx.index(i) if i in free_idx else None
                    if idx is None:
                        tbl[(st, sy)] = None
                    else:
                        tbl[(st, sy)] = vals[idx]
            # Verify state 0 loops on 0 for both sides: tbl[(0,0)] == 0.
            if tbl.get((0, 0)) != 0:
                continue
            yield tbl

    def blank_state(tbl, k):
        # state 0 is blank; push(blank, 0) must return blank.
        if tbl.get((0, 0)) != 0:
            return None
        return 0

    def try_pair(left_tbl, right_tbl, k):
        # Build push functions for closure.
        def pl(state, symbol):
            return left_tbl.get((state, symbol))

        def pr(state, symbol):
            return right_tbl.get((state, symbol))

        blank_left = blank_state(left_tbl, k)
        blank_right = blank_state(right_tbl, k)
        if blank_left is None or blank_right is None:
            return None
        # Check blank_left loops on 0.
        if pl(blank_left, 0) != blank_left:
            return None
        if pr(blank_right, 0) != blank_right:
            return None
        cert = closure(pl, pr, blank_left, blank_right, cap=200000)
        if cert is None:
            return None
        return cert

    # Try small automata.
    for k in (1, 2, 3):
        # Enumerate left tables first into a list (may be large for k=3).
        # For k=1: 1 table. k=2: 2^2=4 free entries -> 16 tables. k=3: 2^4=16 free entries -> 3^16 huge -> cap.
        # We generate lazily and test pairs online.
        try:
            left_tables = list(build_tables(k))
        except MemoryError:
            break
        if not left_tables:
            continue
        # For k=3, left_tables is enormous; cap by taking a subset? Instead we try pairs
        # incrementally with early exit on first success.
        for lt in left_tables:
            for rt in left_tables:
                cert = try_pair(lt, rt, k)
                if cert is not None:
                    # cert is a cps certificate designed for the machine.
                    # Verify with kernel before returning.
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        continue
        # If we exhausted for this k, move on.
    return None
} 