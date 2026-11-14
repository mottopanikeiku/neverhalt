import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# --- helpers ---------------------------------------------------------------

NIL = None


def build_cps(table, n_states, n_symbols):
    """Build the transition tables of the two half-tape automata from a spec.

    Spec: (left_trans, right_trans) where each is a list of rows
    row[state] = list over symbols of next-state or NIL.
    Returns (left, right) as lists of lists.
    """
    left = [list(r) for r in left_trans]
    right = [list(r) for r in right_trans]
    return left, right


def build_contexts(table, n_states, n_symbols, left, right):
    """Compute the smallest closed context set for (left, right).

    Context is (l, q, s, r). Start from (0, 0, 0, 0) and close under the
    kernel's rule. Returns None if a halting context is reached, else the
    list of contexts (as [l, q, s, r]).
    """
    n_q = n_states
    n_s = n_symbols
    # precompute contexts
    ctx = set()
    stack = [(0, 0, 0, 0)]
    ctx.add((0, 0, 0, 0))
    while stack:
        l, q, s, r = stack.pop()
        if q >= n_q or s >= n_s:
            continue
        if (q, s) not in table:
            return None  # halting context
        w, move, q2 = table[(q, s)]
        if move == 1:
            l2 = left[l][w]
            if l2 is NIL:
                return None
            # for every (r2, s2) with right[r2][s2] == r
            for r2 in range(len(right)):
                for s2 in range(n_s):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            stack.append(c)
        else:
            r2 = right[r][w]
            if r2 is NIL:
                return None
            for l2 in range(len(left)):
                for s2 in range(n_s):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            stack.append(c)
    if (0, 0, 0, 0) not in ctx:
        return None
    return [list(c) for c in ctx]


def minimal_tables(left, right, contexts):
    """Keep only transitions used by the closure; null elsewhere."""
    nl = len(left)
    nr = len(right)
    nl2 = [[NIL] * 2 for _ in range(nl)]
    nr2 = [[NIL] * 2 for _ in range(nr)]
    for l, q, s, r in contexts:
        # used transitions: none directly needed in certificate; keep all
        pass
    # Just make sure state 0 loops on 0
    for i in range(nl):
        nl2[i][0] = 0
    for i in range(nr):
        nr2[i][0] = 0
    return nl2, nr2


# --- automata enumeration --------------------------------------------------

def enum_tables(n_states, n_symbols, used_states):
    """Yield transition tables for an automaton with n_states.

    State 0 loops on symbol 0 (required by the kernel). Other entries are
    enumerated over next-states or NIL.
    """
    # enumerate rows
    rows = []
    for st in range(n_states):
        rows.append([NIL] * n_symbols)
    # state 0 must loop on 0
    rows[0][0] = 0
    # enumerate all assignments for the remaining entries
    idx = [st for st in range(n_states) for _ in range(n_symbols)]
    # positions: (st, sym) pairs except (0,0)
    positions = [(st, sym) for st in range(n_states) for sym in range(n_symbols)
                 if not (st == 0 and sym == 0)]
    npos = len(positions)
    # limit enumeration size
    if npos > 14:
        return
    total = (n_states + 1) ** npos
    for code in range(total):
        c = code
        table = [row[:] for row in rows]
        for (st, sym) in positions:
            v = c % (n_states + 1)
            c //= (n_states + 1)
            table[st][sym] = NIL if v == n_states else v
        yield table


def try_automata(table, n_states, n_symbols, tm):
    """Try all pairs of automata for the given machine."""
    # We start with the machine's own table to get n_q, n_s
    for n1 in (1, 2, 3):
        for n2 in (1, 2, 3):
            if n1 * n2 > 9:
                continue
            for lt in enum_tables(n1, n_symbols, n1):
                for rt in enum_tables(n2, n_symbols, n2):
                    ctx = build_contexts(table, n_states, n_symbols, lt, rt)
                    if ctx is None:
                        continue
                    # check via kernel
                    cert = {"kind": "cps", "left": lt, "right": rt,
                            "contexts": ctx}
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        continue
    return None


# --- driver ----------------------------------------------------------------

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # quick sanity: must be 4 states, 2 symbols for this run
    if n_states != 4 or n_symbols != 2:
        return None
    # First try the hint's small automata search (1..3 states per side)
    cert = try_automata(table, n_states, n_symbols, tm)
    if cert is not None:
        return cert
    return None


if __name__ == "__main__":
    import json
    import sys
    tm = sys.argv[1]
    c = decide(tm)
    if c:
        print(json.dumps(c))
    else:
        print("None")
