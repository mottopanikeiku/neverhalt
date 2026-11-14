from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

# ---------------------------------------------------------------------------
# Decider: finite-automaton reduction for counter/bouncer machines.
#
# For a machine tm we build a certificate of kind "cps" (closed set of
# abstract contexts).  A context is (l, q, s, r): the left half-tape is
# summarised by a DFA in state l, the right half-tape by a DFA in state r,
# the machine state is q and the symbol under the head is s.
#
# The left DFA reads cells left of the head from far away towards the head.
# The right DFA reads cells right of the head, also from far away towards
# the head.  State 0 must be the all-blank half-tape, i.e. 0 loops on 0.
#
# For each candidate pair of DFAs (L, R) we compute the smallest closed set
# of contexts, starting from (0, 0, 0, 0).  If the closure contains no
# halting context (i.e. no (q, s) with a halting transition), the pair
# yields a certificate.
#
# Strategy
#   * enumerate DFAs for the left half-tape by size, up to L_MAX states,
#     in BFS-canonical order (deterministic, no unreachable state),
#   * for each left DFA, reverse-determinize the halting language of the
#     right half-tape into a far-to-head DFA (the NFA is the machine
#     stepping right from a halting state, read from the head outwards),
#   * close the context set and, if it never reaches a halting context,
#     emit the certificate.
#
# Only the transitions actually reachable in the closure are kept; the
# kernel requires every transition to be non-null where a context uses it,
# and null elsewhere is fine.
# ---------------------------------------------------------------------------


def _halting_pairs(table, n_states, n_symbols):
    """All (q, s) with a halting transition, as a set."""
    out = set()
    for q in range(n_states):
        for s in range(n_symbols):
            if (q, s) not in table:
                out.add((q, s))
    return out


def _step(table, q, s):
    """Returns (write, move, next) or None if the transition halts."""
    t = table.get((q, s))
    if t is None:
        return None
    w, move, nxt = t
    return w, move, nxt


def _determinize(machine_delta, start_set, n_states_out):
    """
    Determinize an NFA (machine_delta: set of (q, s) -> (w, move, q2))
    into a DFA reading symbols far away towards the head.

    We read the tape from far away towards the head, so the *last* symbol
    read is the one nearest the head.  The NFA state set is carried
    through; the DFA state is (frozenset of machine states, symbol-read-so-
    far summary).  To keep sizes small we canonicalise the DFA states by
    BFS order.

    Returns (delta, index) where delta is a dict (dfa_state, symbol) ->
    dfa_state and index maps canonical states to ints.  Null (absent)
    transitions mean "this symbol never happens in that state".
    """
    # We build the DFA lazily: states are frozensets of machine states.
    # Start: the machine is at its start state?  No: the NFA reads cells
    # that were written by right moves; the machine state is whatever the
    # machine is in when it moves right.  We start from the empty set and
    # let the caller seed it with the states we care about.
    #
    # Simpler and robust: build the DFA over the set of machine states
    # reachable by stepping right from any state, then canonicalise.
    #
    # Concretely: the NFA state set evolves as:
    #   from a set S and symbol x, go to the set of (q2) such that there is
    #   (q, x) in machine_delta with w == x and move == +1 and q in S.
    # (w is the symbol written; it must equal the symbol just read, since
    # we read the written symbol as we walk towards the head.)
    #
    # We use canonical BFS over frozensets.
    start = frozenset()
    index = {start: 0}
    order = [start]
    delta = {}
    i = 0
    while i < len(order):
        cur = order[i]
        i += 1
        for x in range(n_symbols_out):
            nxt = set()
            for q in cur:
                for (qq, ss), (w, move, q2) in machine_delta.items():
                    if qq == q and ss == x and move == 1 and w == x:
                        nxt.add(q2)
            if not nxt:
                continue
            key = frozenset(nxt)
            if key not in index:
                index[key] = len(order)
                order.append(key)
            delta[(index[cur], x)] = index[key]
    return delta, index


def _enumerate_dfas(n_states, n_symbols, max_states, budget):
    """
    Enumerate deterministic automata with 1..max_states states, canonical
    BFS order, state 0 = all-blank half-tape (0 loops on 0).

    Yields (delta, n) where delta is a dict (state, symbol) -> state or
    None (null = never happens) and n is the number of states actually
    used.

    We enumerate all functions delta: states x symbols -> states that keep
    state 0 on symbol 0 (blank tape loops), then keep only reachable and
    canonical (renumber by BFS from 0) tables.  To bound work we limit the
    number of tables emitted.
    """
    # All functions from (n x symbols) to n, with 0 -> 0 on symbol 0.
    # n_symbols includes 0 (blank).  We require delta[0][0] == 0.
    import itertools

    emitted = 0
    for n in range(1, max_states + 1):
        cells = [(q, x) for q in range(n) for x in range(n_symbols)]
        # fix delta[0][0] = 0
        rest = [c for c in cells if c != (0, 0)]
        # BFS canonical: we generate all tables, canonicalise, and skip
        # duplicates.  For n up to 3 and 2 symbols this is at most 3^5=243
        # tables, fine.  For larger n we cap the count.
        for vals in itertools.product(range(n), repeat=len(rest)):
            if emitted >= budget:
                return
            d = {(0, 0): 0}
            for (q, x), v in zip(rest, vals):
                d[(q, x)] = v
            # canonicalise: BFS from 0
            seen = {0: 0}
            order = [0]
            canon = {}
            i = 0
            ok = True
            while i < len(order):
                q = order[i]
                i += 1
                for x in range(n_symbols):
                    r = d.get((q, x))
                    if r is None:
                        continue
                    if r not in seen:
                        seen[r] = len(order)
                        order.append(r)
            # canonical numbering by BFS order
            newd = {}
            for q in order:
                for x in range(n_symbols):
                    r = d.get((q, x))
                    if r is None:
                        newd[(seen[q], x)] = None
                    else:
                        newd[(seen[q], x)] = seen[r]
            # skip if not all states reachable
            if len(order) != n:
                continue
            key = tuple(sorted((q, x, newd[(q, x)]) for q in range(len(order)) for x in range(n_symbols)))
            if getattr(_enumerate_dfas, "_seen", None) is None:
                _enumerate_dfas._seen = set()
            if key in _enumerate_dfas._seen:
                continue
            _enumerate_dfas._seen.add(key)
            emitted += 1
            yield newd, len(order)
            if emitted >= budget:
                return


def _close_contexts(table, n_states, n_symbols, L, R, halting, max_contexts):
    """
    Close the context set for the pair (L, R).

    L, R: dicts (state, symbol) -> state or None.
    Returns (contexts, closed) where contexts is a set of
    (l, q, s, r) tuples and closed is True iff the closure contains no
    halting context.
    """
    # (0, 0, 0, 0) must be a context: blank tape, state A, symbol 0 under
    # the head, blank half-tapes.
    start = (0, 0, 0, 0)
    ctx = {start}
    frontier = [start]
    while frontier:
        if len(ctx) > max_contexts:
            return None, False
        nxt = []
        for (l, q, s, r) in frontier:
            t = table.get((q, s))
            if t is None:
                # halting context -> closure is not closed
                return ctx, False
            w, move, q2 = t
            if move == 1:
                # right move: push w onto left half-tape
                l2 = L.get((l, w))
                if l2 is None:
                    return ctx, False
                # pop the nearest cell s2 off the right half-tape:
                # for every (r2, s2) with R[(r2, s2)] == r
                for r2 in range(len(R) and (max(R.keys(), key=lambda k: k[0])[0] + 1)):
                    for s2 in range(n_symbols):
                        if R.get((r2, s2)) == r:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                nxt.append(c)
            else:
                # left move: mirror image
                r2 = R.get((r, w))
                if r2 is None:
                    return ctx, False
                maxl = max(L.keys(), key=lambda k: k[0])[0] + 1
                for l2 in range(maxl):
                    for s2 in range(n_symbols):
                        if L.get((l2, s2)) == l:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                nxt.append(c)
        frontier = nxt
    return ctx, True


def _emit_certificate(tm, L, R, ctx, n_states, n_symbols):
    """Convert (L, R, ctx) into a kernel certificate of kind cps."""
    # strip to used states
    lmax = max(l for (l, q, s, r) in ctx) + 1
    rmax = max(r for (l, q, s, r) in ctx) + 1
    left = []
    for q in range(lmax):
        row = []
        for x in range(n_symbols):
            v = L.get((q, x))
            if v is None or v >= lmax:
                row.append(None)
            else:
                row.append(v)
        left.append(row)
    right = []
    for q in range(rmax):
        row = []
        for x in range(n_symbols):
            v = R.get((q, x))
            if v is None or v >= rmax:
                row.append(None)
            else:
                row.append(v)
        right.append(row)
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    cert = {"kind": "cps", "left": left, "right": right, "contexts": contexts}
    return cert


def decide(tm: str):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None

    halting = _halting_pairs(table, n_states, n_symbols)

    # Build the right-move NFA used for reverse-determinization: from a
    # machine state q on symbol x, a right move writes w and goes to q2.
    machine_delta = {}
    for (q, s), (w, move, q2) in table.items():
        if move == 1:
            machine_delta[(q, s)] = (w, move, q2)

    # Budget: 500 ms per machine.  Enumerate left DFAs of size 1..3 first
    # (cheap), then larger if time remains.
    import time
    t0 = time.time()
    deadline = t0 + 0.45

    tried = 0
    for max_states in (1, 2, 3, 4):
        # enumerate left DFAs
        for L, nl in _enumerate_dfas(n_states, n_symbols, max_states, 4000):
            if time.time() > deadline:
                return None
            tried += 1
            # determinize the right half-tape language from the machine
            # states reachable by right moves
            # The NFA start set: all machine states (we are lazy and let
            # the closure drive it).  We determinize over all states.
            # Build the DFA over the set of machine states, canonical.
            delta, index = _determinize(machine_delta, frozenset(), n_symbols)
            # map DFA states to ints; we need a DFA reading far-to-head.
            # The determinized automaton above reads symbols x and tracks
            # the set of machine states that could be at the head after
            # reading x.  We use it as the right DFA R: DFA state -> set.
            # For the kernel we need R as a table (state, symbol) -> state.
            # We renumber DFA states 0..k-1 with 0 = empty set.
            R = {}
            for (a, x), b in delta.items():
                R[(a, x)] = b
            Rn = len(index)
            # quick check: does the closure stay finite and halt-free?
            ctx, closed = _close_contexts(table, n_states, n_symbols, L, R, halting, 200000)
            if ctx is None:
                continue
            if closed:
                # verify with the kernel before returning
                cert = _emit_certificate(tm, L, R, ctx, n_states, n_symbols)
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
    return None


DECIDERS = [decide]
NAME = "fa-reduction-search"


if __name__ == "__main__":
    import sys
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        c = decide(line)
        print(c if c is not None else None)
        break
    else:
        print(None)
}


# End of module
}

# Note: the above is the module body.  The JSON payload's "code" field
# contains exactly this text.
}


# The JSON object must be emitted as the final reply.  Below is the
# compact form with the code embedded.  (This text is not part of the code.)
"notes": "The holdouts are counters and bouncers: the head walks out one side, reverses at a far marker and walks back, leaving a growing diagonal stripe of ones, so a fixed recent-cell window is far too little. I will stop using hand-picked counters and instead run the finite-automaton reduction itself: enumerate small DFAs for one half-tape, reverse-determinize the other half-tape's language into a far-to-head DFA, then close the context set and emit a certificate if the closure contains no halting context.", "code": "from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


def _halting_pairs(table, n_states, n_symbols):
    out = set()
    for q in range(n_states):
        for s in range(n_symbols):
            if (q, s) not in table:
                out.add((q, s))
    return out


def _determinize(machine_delta, start_set, n_symbols_out):
    start = frozenset()
    index = {start: 0}
    order = [start]
    delta = {}
    i = 0
    while i < len(order):
        cur = order[i]
        i += 1
        for x in range(n_symbols_out):
            nxt = set()
            for q in cur:
                for (qq, ss), (w, move, q2) in machine_delta.items():
                    if qq == q and ss == x and move == 1 and w == x:
                        nxt.add(q2)
            if not nxt:
                continue
            key = frozenset(nxt)
            if key not in index:
                index[key] = len(order)
                order.append(key)
            delta[(index[cur], x)] = index[key]
    return delta, index


def _enumerate_dfas(n_states, n_symbols, max_states, budget):
    import itertools
    emitted = 0
    seen = set()
    for n in range(1, max_states + 1):
        cells = [(q, x) for q in range(n) for x in range(n_symbols)]
        rest = [c for c in cells if c != (0, 0)]
        for vals in itertools.product(range(n), repeat=len(rest)):
            if emitted >= budget:
                return
            d = {(0, 0): 0}
            for (q, x), v in zip(rest, vals):
                d[(q, x)] = v
            seen_local = {0: 0}
            order = [0]
            i = 0
            while i < len(order):
                q = order[i]
                i += 1
                for x in range(n_symbols):
                    r = d.get((q, x))
                    if r is not None and r not in seen_local:
                        seen_local[r] = len(order)
                        order.append(r)
            if len(order) != n:
                continue
            newd = {}
            for q in order:
                for x in range(n_symbols):
                    r = d.get((q, x))
                    newd[(seen_local[q], x)] = None if r is None else seen_local[r]
            key = tuple(sorted((q, x, newd[(q, x)]) for q in range(len(order)) for x in range(n_symbols)))
            if key in seen:
                continue
            seen.add(key)
            emitted += 1
            yield newd, len(order)
            if emitted >= budget:
                return


def _close_contexts(table, n_states, n_symbols, L, R, halting, max_contexts):
    start = (0, 0, 0, 0)
    ctx = {start}
    frontier = [start]
    while frontier:
        if len(ctx) > max_contexts:
            return None, False
        nxt = []
        for (l, q, s, r) in frontier:
            t = table.get((q, s))
            if t is None:
                return ctx, False
            w, move, q2 = t
            if move == 1:
                l2 = L.get((l, w))
                if l2 is None:
                    return ctx, False
                rmax = max((k[0] for k in R.keys()), default=-1) + 1
                for r2 in range(rmax):
                    for s2 in range(n_symbols):
                        if R.get((r2, s2)) == r:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                nxt.append(c)
            else:
                r2 = R.get((r, w))
                if r2 is None:
                    return ctx, False
                lmax = max((k[0] for k in L.keys()), default=-1) + 1
                for l2 in range(lmax):
                    for s2 in range(n_symbols):
                        if L.get((l2, s2)) == l:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                nxt.append(c)
        frontier = nxt
    return ctx, True


def _emit_certificate(L, R, ctx, n_symbols):
    lmax = max(l for (l, q, s, r) in ctx) + 1
    rmax = max(r for (l, q, s, r) in ctx) + 1
    left = []
    for q in range(lmax):
        row = []
        for x in range(n_symbols):
            v = L.get((q, x))
            row.append(None if v is None or v >= lmax else v)
        left.append(row)
    right = []
    for q in range(rmax):
        row = []
        for x in range(n_symbols):
            v = R.get((q, x))
            row.append(None if v is None or v >= rmax else v)
        right.append(row)
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    return {"kind": "cps", "left": left, "right": right, "contexts": contexts}


def decide(tm: str):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None

    machine_delta = {}
    for (q, s), (w, move, q2) in table.items():
        if move == 1:
            machine_delta[(q, s)] = (w, move, q2)

    import time
    t0 = time.time()
    deadline = t0 + 0.45

    for max_states in (1, 2, 3, 4):
        for L, nl in _enumerate_dfas(n_states, n_symbols, max_states, 3000):
            if time.time() > deadline:
                return None
            delta, index = _determinize(machine_delta, frozenset(), n_symbols)
            R = dict(delta)
            ctx, closed = _close_contexts(table, n_states, n_symbols, L, R, None, 200000)
            if ctx is None:
                continue
            if closed:
                cert = _emit_certificate(L, R, ctx, n_symbols)
                try:
                    from neverhalt.kernel import check, Reject
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
    return None


NAME = "fa-reduction-search"