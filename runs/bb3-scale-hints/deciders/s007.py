import json

# ---------------------------------------------------------------
# Decider: finite-automaton search for CPS certificates.
#
# Strategy (per the hint): enumerate DFA transition tables for one
# half-tape in BFS-canonical order (states 0..k-1, state 0 loops on 0),
# grow k from 1 to 10, and for each DFA run the closed-context fixpoint
# against the machine's transition table.  If the closure is finite and
# contains no halting context, emit a CPS certificate using the DFA for
# both sides (the left half-tape reads far-to-head; the right half-tape
# is the same language read far-to-head, which is exactly what a DFA
# over the reversed alphabet realizes for its own half-tape).
#
# We prune aggressively: any DFA that cannot be completed to a finite
# closed context set is discarded, and we stop at the first success.
# ---------------------------------------------------------------

from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

# Parse the machine once; expose the raw transition table for our own use.
# table[(state, symbol)] = (write, move, next_state); halting transitions
# are absent.


def _machine_tables(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states, n_symbols


def _closure(tm, left, right):
    """Compute the closed context set for the given pair of half-tape
    automata.  Returns a list of (l, q, s, r) contexts, or None if the
    closure is empty (impossible) or unbounded (detected by a step cap)."""
    table, n_states, n_symbols = _machine_tables(tm)

    start = (0, 0, 0, 0)
    seen = {start}
    frontier = [start]
    steps = 0
    cap = 200000

    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            steps += 1
            if steps > cap:
                return None
            tr = table.get((q, s))
            if tr is None:
                # halting context: fail this pair
                return None
            w, move, q2 = tr
            if move == 1:
                l2 = left[l][w] if l < len(left) and w < len(left[l]) else None
                if l2 is None:
                    return None
                for r2 in range(len(right)):
                    row = right[r2]
                    if len(row) > 0 and row[s if s < len(row) else 0] == r:
                        # find all (r2, s2) with right[r2][s2] == r
                        pass
                # enumerate pairs (r2, s2) with right[r2][s2] == r
                for r2 in range(len(right)):
                    row = right[r2]
                    for s2 in range(2):
                        if s2 < len(row) and row[s2] == r:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in seen:
                                seen.add(ctx)
                                nxt.append(ctx)
            else:
                r2 = right[r][w] if r < len(right) and w < len(right[r]) else None
                if r2 is None:
                    return None
                for l2 in range(len(left)):
                    row = left[l2]
                    for s2 in range(2):
                        if s2 < len(row) and row[s2] == l:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in seen:
                                seen.add(ctx)
                                nxt.append(ctx)
        frontier = nxt
    return sorted(seen)


def _emit(tm, left, right, contexts):
    """Build the certificate dict.  We keep only the automaton entries
    exercised by the closure (null elsewhere)."""
    used_left = set()
    used_right = set()
    ctx_list = []
    for (l, q, s, r) in contexts:
        used_left.add(l)
        used_right.add(r)
        ctx_list.append([l, q, s, r])

    # We store the automata as full tables (all states) but with null for
    # unused entries; the kernel only needs the contexts to be consistent.
    n_left = len(left)
    n_right = len(right)
    L = [[None, None] for _ in range(n_left)]
    R = [[None, None] for _ in range(n_right)]
    for l in used_left:
        for s in range(2):
            if s < len(left[l]) and left[l][s] is not None:
                L[l][s] = left[l][s]
    for r in used_right:
        for s in range(2):
            if s < len(right[r]) and right[r][s] is not None:
                R[r][s] = right[r][s]

    return {
        "kind": "cps",
        "left": L,
        "right": R,
        "contexts": ctx_list,
    }


def _enumerate_dfa_tables(max_states, max_states_per_symbol):
    """Yield DFA tables (list of rows, row = list of length 2) for k
    states, k = 1..max_states.  State 0 loops on symbol 0.  Canonical BFS
    order: at each state, try transitions on symbol 0 then symbol 1."""
    import itertools

    for k in range(1, max_states + 1):
        # transitions for states 1..k-1; state 0 fixed to (0, 0).
        # Each state has up to 2 transitions; we enumerate all assignments
        # in lexicographic order.
        for combo in itertools.product(range(k), repeat=2 * (k - 1)):
            table = [[0, 0]]
            ok = True
            for i in range(1, k):
                a = combo[2 * (i - 1)]
                b = combo[2 * (i - 1) + 1]
                table.append([a, b])
            yield table


def decide(tm):
    """Return a certificate for tm, or None."""
    table, n_states, n_symbols = _machine_tables(tm)

    # Quick pre-check: no halting transition reachable from the start
    # context?  Actually the closure itself handles this.  Just run it.

    # Symmetry: try the DFA as the left automaton and as the right
    # automaton; both sides use the same machine table here because the
    # kernel's convention is symmetric enough for our construction.
    # We search one table and use it for both sides first.

    max_states = 10
    for left in _enumerate_dfa_tables(max_states, 2):
        # State 0 loops on 0 already; also require that unused symbols
        # default to a "sink" that is itself.  Our tables are total.
        # Try using the same table for both sides (simplest first).
        right = [row[:] for row in left]
        ctxs = _closure(tm, left, right)
        if ctxs is None:
            continue
        cert = _emit(tm, left, right, ctxs)
        # Verify before returning; never guess.
        try:
            check(tm, cert)
        except Reject:
            continue
        return cert

    # If no same-table pair worked, try all pairs of distinct tables.
    tables = list(_enumerate_dfa_tables(max_states, 2))
    for i, left in enumerate(tables):
        for j, right in enumerate(tables):
            if i == j:
                continue
            ctxs = _closure(tm, left, right)
            if ctxs is None:
                continue
            cert = _emit(tm, left, right, ctxs)
            try:
                check(tm, cert)
            except Reject:
                continue
            return cert

    return None