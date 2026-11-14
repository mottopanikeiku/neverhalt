from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
import itertools
from collections import deque


def _halting_steps(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states, n_symbols


def _halting_steps_set(tm):
    table, n_states, n_symbols = parse(tm)
    bad = set()
    for q in range(n_states):
        for s in range(n_symbols):
            if (q, s) not in table:
                bad.add((q, s))
    return table, n_states, n_symbols, bad


def _build_automaton(table, n_states, n_symbols, bad, side, max_states):
    # Enumerate DFA transition tables for one half-tape.
    # State 0 must be the all-blank half-tape: on symbol 0 it stays at 0.
    # We enumerate tables in BFS-canonical order with growing size.
    # For each candidate we compute the set of contexts (l, q, s, r) reachable
    # from the initial context (0, 0, 0, 0) under the machine transitions,
    # using the other side as an NFA (language of suffixes).
    # Instead of a full NFA construction we simply do a fixpoint over pairs
    # (l, r) with the automaton reading symbols one at a time.
    # Symbol 0 is blank, symbol 1 is non-blank.
    # The left automaton reads cells to the left of the head, far to near.
    # The right automaton reads cells to the right of the head, far to near.
    # For a right move, the machine writes w and moves right. The cell it
    # leaves behind (under the head) becomes the next symbol read by the
    # left automaton, and the cell it moves onto is popped from the right
    # automaton: the right automaton was in state r, and some symbol s2
    # with right[r][s2] == r2 is the next cell; all such (r2, s2) pairs
    # must be covered.
    # We build the left automaton by search and use the right automaton as
    # the dual: for each context we need the set of (r2, s2) reachable.
    # We approximate the right half-tape by a canonical DFA built from the
    # left automaton's language complement; for the fixpoint we just use
    # the actual right automaton built from the same enumeration.
    # Simpler and stronger: enumerate both automata simultaneously over a
    # small size, but that is too large. Instead we enumerate the left
    # automaton and construct the right one as the reverse-determinization
    # of the NFA of suffixes accepted by the left automaton's complement.
    # We implement a direct search over automata that are "prefix-closed"
    # in the following sense: we enumerate all DFAs up to max_states and
    # test closure.
    #
    # To keep it tractable we enumerate DFAs with at most max_states states
    # using BFS-canonical order (states discovered in order of first use).
    # We generate transition functions for symbols 0 and 1.
    # State 0 loops on 0.
    # We prune when the closure would contain a halting context.
    #
    # For a given left DFA we compute the set of contexts reachable from
    # (0, 0, 0, 0) where the right half-tape state r is represented as a
    # set of possible DFA states (a subset construction): we track the set
    # of right states reachable by reading the cells to the right.
    # Actually we do the fixpoint directly over (l, q, s, R) where R is a
    # frozenset of right automaton states.
    # For a right move: new left state l2 = left[l][w]; the new right state
    # set is { r2 : exists r in R, exists s2 with right[r][s2] == r2 }.
    # For a left move: new right state set is { r2 : exists r in R,
    # exists s2 with right[r][s2] == r2 } as well? No: for a left move the
    # machine pops a cell from the left half-tape, so the left state set
    # changes and the right state set is unchanged.
    # We track left as a single state l and right as a set R, but for a
    # left move the left automaton pops, so we need to track the set of
    # left states too. We do the full subset construction on both sides:
    # contexts are (L, q, s, R) with L, R frozensets of automaton states.
    # The certificate format only allows single states, so at the end we
    # determinize: if a context has |L| > 1 or |R| > 1 we cannot emit it
    # directly; but we can emit a DFA whose states are the subsets.
    # So we build the DFA states as the reachable subsets themselves.
    # That is exactly the subset construction; we then check that no
    # halting context appears and emit the resulting DFA tables.
    #
    # We do this for the left automaton; the right automaton is built the
    # same way from the mirror image of the machine (swap left/right moves
    # and reverse the tape). Then we run the closed-context fixpoint over
    # the pair of DFAs.
    #
    # This is the finite-automata reduction hinted at: enumerate DFAs in
    # BFS-canonical order with growing size, prune as soon as a halting
    # context is forced.
    #
    # We implement it as follows:
    # 1. Enumerate left DFA transition tables (state 0 loops on 0).
    # 2. For each, run the context closure with the right DFA obtained by
    #    the same enumeration but we only need one right DFA: we search
    #    over pairs (left, right) but to save time we first try the right
    #    DFA to be the mirror of the left DFA, then enumerate small right
    #    DFAs.
    # 3. Emit the first pair whose closure has no halting context and no
    #    context with a missing transition.
    #
    # We keep the search bounded by max_states and a step budget.
    #
    # Symbol encoding: 0 = blank, 1 = non-blank.
    # move: +1 for right, -1 for left.
    #
    # Let us write the core.

    # Enumerate DFA transition tables.
    # A table is a tuple of pairs (t0, t1) for each state, where ti is the
    # next state on symbol i, or None.
    # State 0 on symbol 0 must be 0.
    # We enumerate in BFS-canonical order: start with the one-state DFA
    # (0 on 0 -> 0, 0 on 1 -> 0 or None), then add states one by one,
    # requiring that new states are reachable and that the table is
    # canonical (states numbered by first discovery).
    #
    # We generate all tables up to max_states by recursive construction:
    # for each state we choose transitions to existing states or a new
    # state. To avoid duplicates we require that state indices are used
    # in order of first appearance.
    #
    # We do a simpler exhaustive enumeration over all functions from
    # states x symbols to states or None, with the constraint that the
    # number of states is exactly the number of states that are reachable
    # from 0, and state 0 loops on 0. For max_states = 3 this is small:
    # each state has 4 choices per symbol (0,1,2,None) -> 4^2 per state,
    # 4^6 = 4096 for 3 states, times reachability check. Fine.
    # For max_states = 4: 4^8 = 65536, still fine.
    # For max_states = 5: 4^10 = 1M, maybe too slow but we can prune.
    # We start with max_states = 3 and grow.

    def enumerate_dfas(max_states):
        # yield (n_states, table) where table[i] = (t0, t1)
        for n in range(1, max_states + 1):
            # enumerate all tables for n states
            # transitions: for each state, for each symbol, target in 0..n-1 or None
            # We encode None as n.
            choices = list(range(n + 1))  # n means None
            for combo in itertools.product(choices, repeat=2 * n):
                table = []
                ok = True
                for i in range(n):
                    t0 = combo[2 * i]
                    t1 = combo[2 * i + 1]
                    if i == 0 and t0 != 0:
                        ok = False
                        break
                    table.append((t0, t1))
                if not ok:
                    continue
                # check reachability from 0
                seen = {0}
                stack = [0]
                while stack:
                    st = stack.pop()
                    for sym in (0, 1):
                        t = table[st][sym]
                        if t is not None and t != n and t not in seen:
                            seen.add(t)
                            stack.append(t)
                if len(seen) != n:
                    continue
                yield n, table

    # Mirror the machine: swap left/right moves.
    def mirror(tm):
        table, n_states, n_symbols = parse(tm)
        new = {}
        for (q, s), (w, mv, q2) in table.items():
            new[(q, s)] = (w, -mv, q2)
        return new, n_states, n_symbols

    # Context closure.
    # A context is (l, q, s, r) where l, r are DFA states, q is the machine
    # state, s is the symbol under the head.
    # We start with (0, 0, 0, 0).
    # For each context we apply the machine transition (q, s) -> (w, mv, q2).
    # If no transition, this is a halting context -> reject.
    # If mv == +1 (right): l2 = left_table[l][w]; if None -> reject.
    #   For every (r2, s2) with right_table[r][s2] == r2, the context
    #   (l2, q2, s2, r2) must be in the set.
    #   Wait: the right automaton reads from far away towards the head, so
    #   the state r is the state after reading all cells to the right of
    #   the head. When the head moves right, it leaves the cell it was on
    #   (now containing w) and the new head is on the next cell to the
    #   right. The right automaton must pop the cell that is now under the
    #   head: the symbol s2 at the new head position. The right automaton
    #   was in state r; reading s2 from far away towards the head means
    #   the state r is the result of reading cells from far to near, so
    #   the nearest cell is read last. Thus the new right state r2 must
    #   satisfy: there exists a symbol s2 such that right_table[r][s2]
    #   == r2, and the context (l2, q2, s2, r2) must be present.
    #   Actually the kernel says: for a right move, l2 = left[l][w] is not
    #   null and [l2, q2, s2, r2] is a context for EVERY pair (r2, s2) with
    #   right[r2][s2] == r. Wait, re-read the kernel description:
    #   "for a right move, l2 = left[l][w] is not null and [l2, q2, s2, r2]
    #   is a context for EVERY pair (r2, s2) with right[r2][s2] == r"
    #   Hmm, that says right[r2][s2] == r, not right[r][s2] == r2.
    #   Let me re-read: "for a right move, l2 = left[l][w] is not null and
    #   [l2, q2, s2, r2] is a context for EVERY pair (r2, s2) with
    #   right[r2][s2] == r". So the right automaton state r is the state
    #   before reading s2? That means the right automaton reads from near
    #   to far? Let me re-read the whole description.
    #   "The left automaton reads the cells left of the head, from far away
    #   towards the head; the right automaton reads the cells right of the
    #   head, also from far away towards the head."
    #   So reading from far away towards the head: the last symbol read is
    #   the one nearest the head. So if the automaton is in state r after
    #   reading all cells to the right, then r = right[r_prev][s_nearest].
    #   When the head moves right, the cell that was under the head (now
    #   containing w) becomes part of the left half-tape, and the new head
    #   is on the next cell to the right. The right half-tape loses its
    #   nearest cell (the one now under the head). The new right state r2
    #   is the state after reading the remaining cells, so r2 is such that
    #   r = right[r2][s2] where s2 is the symbol of the cell now under the
    #   head. So indeed the kernel says: for every pair (r2, s2) with
    #   right[r2][s2] == r, the context (l2, q2, s2, r2) must be present.
    #   That matches the kernel description. Good.
    #   For a left move: mirror image: r2 = right[r][w]; for every pair
    #   (l2, s2) with left[l2][s2] == l, the context (l2, q2, s2, r2) must
    #   be present.
    #   Wait, the kernel says: "for a left move the mirror image: r2 =
    #   right[r][w] is not null and [l2, q2, s2, r2] is a context for EVERY
    #   pair (l2, s2) with left[l2][s2] == l". Yes.
    #   So the closure rule is as above.

    def closure(left_table, right_table, n_states, n_machine_states, bad):
        # left_table[i] = (t0, t1), right_table[i] = (t0, t1)
        # contexts: set of (l, q, s, r)
        start = (0, 0, 0, 0)
        seen = {start}
        stack = [start]
        while stack:
            (l, q, s, r) = stack.pop()
            if (q, s) in bad:
                return None  # halting context
            (w, mv, q2) = table[(q, s)]
            if mv == 1:
                l2 = left_table[l][w]
                if l2 is None:
                    return None
                # for every (r2, s2) with right_table[r2][s2] == r
                for r2 in range(len(right_table)):
                    for s2 in (0, 1):
                        if right_table[r2][s2] == r:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in seen:
                                seen.add(ctx)
                                stack.append(ctx)
            else:
                r2 = right_table[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(left_table)):
                    for s2 in (0, 1):
                        if left_table[l2][s2] == l:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in seen:
                                seen.add(ctx)
                                stack.append(ctx)
        return seen

    # Main search.
    def search(tm):
        table, n_states, n_symbols = parse(tm)
        bad = set()
        for q in range(n_states):
            for s in range(n_symbols):
                if (q, s) not in table:
                    bad.add((q, s))
        # The kernel's cps format wants left and right transition tables
        # as lists of [a, b] pairs, with null for missing.
        # We search over left and right DFAs.
        # To save time, we first try small sizes for both.
        # We enumerate left DFAs and right DFAs separately.
        # The context set size must be <= 200000.
        # We try sizes 1..3 first, then 4, etc.
        max_size = 4
        # Precompute all DFAs up to max_size.
        dfas = []
        for n, t in enumerate_dfas(max_size):
            dfas.append((n, t))
        # Sort by size.
        dfas.sort(key=lambda x: x[0])
        # Try pairs (left, right) in increasing total size.
        for nL, left in dfas:
            for nR, right in dfas:
                if nL + nR > 8:
                    continue
                ctx = closure(left, right, n_states, n_states, bad)
                if ctx is None:
                    continue
                # Check that the initial context is present (it is by construction)
                # and that no context has a missing transition (closure already ensures this).
                # Build the certificate.
                # left and right tables: convert None to null (None in Python).
                left_cert = [[t0 if t0 != nL else None, t1 if t1 != nL else None] for (t0, t1) in left]
                right_cert = [[t0 if t0 != nR else None, t1 if t1 != nR else None] for (t0, t1) in right]
                contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
                cert = {"kind": "cps", "left": left_cert, "right": right_cert, "contexts": contexts}
                # Verify with the kernel.
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
        return None

    return search(tm)


def decide(tm: str):
    try:
        cert = _decide_impl(tm)
        if cert is not None:
            return cert
    except Exception:
        pass
    return None


def _decide_impl(tm: str):
    from neverhalt.tm import parse
    from neverhalt.kernel import check, Reject
    import itertools

    table, n_states, n_symbols = parse(tm)
    bad = set()
    for q in range(n_states):
        for s in range(n_symbols):
            if (q, s) not in table:
                bad.add((q, s))

    def enumerate_dfas(max_states):
        for n in range(1, max_states + 1):
            choices = list(range(n + 1))
            for combo in itertools.product(choices, repeat=2 * n):
                table = []
                ok = True
                for i in range(n):
                    t0 = combo[2 * i]
                    t1 = combo[2 * i + 1]
                    if i == 0 and t0 != 0:
                        ok = False
                        break
                    table.append((t0, t1))
                if not ok:
                    continue
                seen = {0}
                stack = [0]
                while stack:
                    st = stack.pop()
                    for sym in (0, 1):
                        t = table[st][sym]
                        if t is not None and t != n and t not in seen:
                            seen.add(t)
                            stack.append(t)
                if len(seen) != n:
                    continue
                yield n, table

    def closure(left_table, right_table):
        start = (0, 0, 0, 0)
        seen = {start}
        stack = [start]
        while stack:
            (l, q, s, r) = stack.pop()
            if (q, s) in bad:
                return None
            (w, mv, q2) = table[(q, s)]
            if mv == 1:
                l2 = left_table[l][w]
                if l2 is None:
                    return None
                for r2 in range(len(right_table)):
                    for s2 in (0, 1):
                        if right_table[r2][s2] == r:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in seen:
                                seen.add(ctx)
                                stack.append(ctx)
            else:
                r2 = right_table[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(left_table)):
                    for s2 in (0, 1):
                        if left_table[l2][s2] == l:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in seen:
                                seen.add(ctx)
                                stack.append(ctx)
        return seen

    max_size = 4
    dfas = []
    for n, t in enumerate_dfas(max_size):
        dfas.append((n, t))
    dfas.sort(key=lambda x: x[0])
    for nL, left in dfas:
        for nR, right in dfas:
            if nL + nR > 8:
                continue
            ctx = closure(left, right)
            if ctx is None:
                continue
            if len(ctx) > 200000:
                continue
            left_cert = [[t0 if t0 != nL else None, t1 if t1 != nL else None] for (t0, t1) in left]
            right_cert = [[t0 if t0 != nR else None, t1 if t1 != nR else None] for (t0, t1) in right]
            contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
            cert = {"kind": "cps", "left": left_cert, "right": right_cert, "contexts": contexts}
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    return None