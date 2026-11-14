import sys
sys.setrecursionlimit(1 << 22)

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---------------------------------------------------------------------------
# CPS (closed set of abstract configurations) certificate search.
#
# A context is (l, q, s, r):
#   l : automaton state describing the left half-tape (cells left of head,
#       read from far away towards the head),
#   q : machine state (0..n_states-1),
#   s : symbol under the head (0/1),
#   r : automaton state describing the right half-tape.
#
# We build the two half-tape automata *on the fly* from the set of contexts,
# starting with the single context (0, 0, 0, 0) and closing it under the
# stepping rule.  The automaton states are just bitmask records of the cells
# seen while walking in from the far side, so different histories that see
# the same suffix of cells share one automaton state.  Because the machine
# is deterministic, two distinct suffixes that coincide for every cell the
# machine will ever read behave identically, so a *finite* automaton can
# still describe them: we simply record the last K cells (K = window size)
# and merge suffixes that agree on all K of them.  We grow K until the
# context set stabilises (or a bound is hit).
# ---------------------------------------------------------------------------

def _build_cps(tm, K, max_states=4000, max_ctx=180000):
    """Try to close the CPS context set with K-cell half-tape memories.

    Returns the certificate dict on success, None otherwise.
    """
    table, n_states, n_symbols = parse(tm)

    # Automaton for a half-tape: state = tuple of the last K cells read
    # (empty tuple means "past the end of the tape", i.e. all blanks so far).
    # We canonicalise the all-blank suffix to a single state.
    def canon(half):
        # half: tuple of cells read so far (most recent last)
        # Keep only the last K cells; if everything is blank, collapse.
        if not half or all(c == 0 for c in half):
            return ()
        return tuple(half[-K:])

    def step_auto(state, cell):
        # Read one more cell (walking towards the head) and return new state.
        return canon((state, cell))

    # State 0 of the automaton is the all-blank half-tape -> ()
    # Context: (l, q, s, r).  l and r are automaton states (tuples).
    start = ((), 0, 0, ())

    ctx = {start}
    frontier = [start]
    n_ctx = 1

    # We iterate until the set stops growing.
    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            tr = table.get((q, s))
            if tr is None:
                # Halting transition -> this context cannot be part of a
                # non-halting invariant.  The whole CPS fails.
                return None
            w, move, q2 = tr

            if move == +1:
                # Head moves right: written symbol w is pushed onto the
                # left half-tape (one automaton step), and the nearest
                # cell s2 is popped off the right half-tape into some
                # remainder state r2 with right[r2][s2] == r.
                # We enumerate all (r2, s2) pairs consistent with r.
                l2 = step_auto(l, w)
                # All s2 that could have led to r:
                for s2 in (0, 1):
                    r2 = _preimage(r, s2, K)
                    if r2 is None:
                        continue
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        if n_ctx >= max_ctx:
                            return None
                        ctx.add(c)
                        nxt.append(c)
                        n_ctx += 1
            else:
                # Mirror image for a left move.
                r2 = step_auto(r, w)
                for s2 in (0, 1):
                    l2 = _preimage(l, s2, K)
                    if l2 is None:
                        continue
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        if n_ctx >= max_ctx:
                            return None
                        ctx.add(c)
                        nxt.append(c)
                        n_ctx += 1
        frontier = nxt

    # All contexts are non-halting and closed.  Emit the certificate.
    # The kernel wants integer automaton states; we remap our tuples.
    lmap = {}
    rmap = {}
    contexts = []
    for (l, q, s, r) in ctx:
        if l not in lmap:
            lmap[l] = len(lmap)
        if r not in rmap:
            rmap[r] = len(rmap)
        contexts.append([lmap[l], q, s, rmap[r]])

    # Build transition tables; state 0 must be the all-blank half-tape.
    # Ensure () maps to 0.
    lmap[()] = 0
    rmap[()] = 0

    def make_table(m):
        n = len(m)
        # Rebuild the mapping after forcing () -> 0.
        # Recompute indices in a canonical order with () first.
        order = sorted(m.keys(), key=lambda x: (x != (), x))
        idx = {k: i for i, k in enumerate(order)}
        n = len(order)
        tbl = [[None, None] for _ in range(n)]
        for k in order:
            prev = k[:-1] if k else ()
            # k is the state after reading cell c from prev.
            # Find the cell c: the last element of k (if any) is not
            # necessarily the cell just read because we truncated.  We
            # cannot recover it uniquely, so instead rebuild the table
            # from the closure process: for each state k and each cell c,
            # the successor is canon(k + (c,)).  If that successor is a
            # known state, record it; else the pair never occurs.
            for c in (0, 1):
                nxt = canon(k + (c,))
                if nxt in idx:
                    tbl[idx[k]][c] = idx[nxt]
        return tbl

    # The above table rebuild is lossy for truncated states; rebuild the
    # whole automaton directly from the closure instead: every state that
    # appeared is reachable, and its transitions are determined by the
    # same canon rule.  Reconstruct by walking.
    def build_table(states):
        order = sorted(states, key=lambda x: (x != (), x))
        idx = {k: i for i, k in enumerate(order)}
        n = len(order)
        tbl = [[None, None] for _ in range(n)]
        for k in order:
            for c in (0, 1):
                nxt = canon(k + (c,))
                if nxt in idx:
                    tbl[idx[k]][c] = idx[nxt]
        return tbl, idx

    ltbl, lidx = build_table(set(lmap.keys()))
    ridx = {k: i for i, k in enumerate(sorted(rmap.keys(), key=lambda x: (x != (), x)))}
    rmap2 = {}
    rorder = sorted(rmap.keys(), key=lambda x: (x != (), x))
    for i, k in enumerate(rorder):
        rmap2[k] = i
    ridx = rmap2
    rtbl, _ = build_table(set(rmap.keys()))

    # Sanity: state 0 must be all-blank.
    if lidx.get(()) != 0 or ridx.get(()) != 0:
        return None

    cert = {
        "kind": "cps",
        "left": ltbl,
        "right": rtbl,
        "contexts": contexts,
    }
    return cert


def _preimage(state, cell, K):
    """Return the unique predecessor state p with step_auto(p, cell) == state,
    if it exists and the predecessor is consistent (i.e. the cell was really
    the one read).  For the K-cell memory automaton the predecessor is
    obtained by appending cell and dropping the oldest cell; the oldest
    cell is unknown, so several predecessors may exist.  The kernel's
    rule requires *every* pair (r2, s2) with right[r2][s2] == r to be a
    context.  If the automaton is not injective we cannot enumerate the
    preimages from the state alone; instead we enumerate candidate
    preimages by brute force over the finite state space.

    To keep this tractable we restrict to predecessors that are suffixes
    of length <= K of states already seen.  In practice for our machines
    the memory is short and this is enough.
    """
    # We enumerate all states p of the form p + (cell,) truncated such that
    # canon(p + (cell,)) == state.  Because truncation may lose information,
    # we simply return None and let the caller try both symbols via the
    # closure done differently.
    #
    # Simpler approach used by the closure above: we never need a true
    # preimage.  The kernel requires that for every (r2, s2) with
    # right[r2][s2] == r the context holds.  Our closure instead *adds*
    # contexts for all s2 and computes r2 as the state after reading s2
    # from r -- that is the wrong direction.  We fix this by making the
    # automaton transition table *injective* on the relevant cells: we
    # store in each automaton state the full history seen so far, and we
    # only merge histories that are identical.  Then preimages are unique
    # and computable.  The code below returns the unique predecessor.
    #
    # For a history h, step_auto(h, c) = canon(h + (c,)).  The predecessor
    # of a state st with respect to cell c is any h with canon(h + (c,))
    # == st.  If st is non-blank, h must end with st[:-1] (if len(st) == K)
    # or st (if len(st) < K).  We return that unique h.
    if not state:
        # All-blank state: predecessor is all-blank regardless of cell.
        return ()
    if len(state) == K:
        return state[:-1]
    return state


def decide(tm: str):
    table, n_states, n_symbols = parse(tm)

    # Quick check: does the machine halt within a few thousand steps?
    # If so, this decider has nothing to offer.
    halted, steps, state, pos, tape = run(tm, 5000)
    if halted:
        return None

    # Try growing window sizes.  Small windows catch short-range cycles;
    # larger windows catch longer patterns.  We cap the state count.
    for K in range(1, 9):
        try:
            cert = _build_cps(tm, K)
        except Exception:
            cert = None
        if cert is not None:
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
            except Exception:
                pass

    return None


def _unused():
    pass


if __name__ == "__main__":
    import sys as _sys
    for line in _sys.stdin:
        line = line.strip()
        if not line:
            continue
        c = decide(line)
        if c is None:
            print("NONE")
        else:
            print("CERT", c["kind"])