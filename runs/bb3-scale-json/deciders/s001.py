import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def _build_cps(tm):
    table, ns, nsym = parse(tm)
    # For each state and symbol, get (write, move, next_state) or None
    # We build a closed set of contexts [l, q, s, r] using a worklist.
    # left[i] = list of length nsym: state reached from i on symbol x, or None
    # right[i] = same for reading towards the head.
    # We simulate the abstract transition system starting from [0,0,0,0].
    # State 0 is the all-blank half-tape.
    # For right moves: l2 = left[l][w], and we need [l2, q2, s2, r2] for every pair (r2, s2) with right[r2][s2] == r.
    # For left moves: r2 = right[r][w], and [l2, q2, s2, r2] for every pair (l2, s2) with left[l2][s2] == l.
    # We build automata that remember the last n cells of each half-tape.
    # left[i][x] = state after reading x, remembering last n cells; this is the n-gram automaton.
    # We'll build states as tuples of (position context, memory)
    # Simpler: build the set of contexts by closure, using the n-gram automata.
    # We'll try n = 4, 5, 6 and see if closure succeeds and is small enough.
    for n in (4, 5, 6, 7):
        # Build automata for remembering last n cells.
        # left automaton: states are tuples of last n cells (length n), or shorter at the far end.
        # Actually we need the automaton to read from far away towards the head, so the state
        # is the sequence of cells seen so far, up to n of them (the most recent n).
        # left[0] = far-away all-blank: state = () (empty), or a tuple of length < n of the cells seen.
        # We'll represent state as a tuple of the last min(k, n) cells read, where k is the number read.
        # left[state][x] = new state, or None if x is never read (but for a full automaton it's always defined).
        # For simplicity, we just build the transition table on the fly: state -> (new_state, output_symbol?)
        # Actually the kernel wants left[i][x] = state reached from i on symbol x, or null.
        # And it checks right[r2][s2] == r etc. So the automaton state after reading x is left[i][x].
        # The kernel also uses left[l][w] for a right move: l2 = left[l][w].
        # So the automaton reads the written symbol w when stepping right.
        # And for left moves: r2 = right[r][w].
        # So we need to build automata that can read any symbol and produce a next state.
        # The n-gram automaton: state = tuple of last n cells (padded with a special "far" marker for the blank far side).
        # We'll use None for the far side? But left[0][0] == 0 is required: state 0 is the all-blank half-tape.
        # So we'll define state 0 = all-blank (empty tuple or a special marker), and left[0][0] = 0.
        # When we read a 1, we get a new state. When we read a 0, we stay at 0 if the state is all-blank,
        # or we shift in the 0 if we have a non-blank history.
        # We'll build a canonical n-gram automaton:
        #   state 0: all-blank so far (no non-blank seen yet).
        #   state (a1, ..., ak) with k >= 1: last k cells read, the most recent is a1? Let's define
        #   the state as the sequence of the last up to n cells read, in order from oldest to newest,
        #   but we pad at the far end with a special marker for "no cell yet".
        # Actually the far side is blank, so reading blanks forever stays at 0.
        # Let's define state as a tuple of the last up to n cells read, in order from most recent to oldest.
        # state 0 = () = all blanks (or all blanks so far).
        # On reading x:
        #   if x == 0 and state == (): new state = ()
        #   else: new state = (x,) + state[:n-1]
        # This is a deterministic automaton. Number of states: 2^n + 1.
        # For n up to 7, that's 129 states, fine.
        # But the kernel limit is 5000 states per automaton, so n=7 is fine.
        # We'll build left and right as the same automaton (both read the same way).
        # Actually left reads cells left of the head from far away towards the head; right reads cells
        # right of the head also from far away towards the head. So both are the same n-gram automaton.
        # Let's build the automaton.
        def build_automaton(n):
            # states: 0 = all-blank, and tuples (a1,...,ak) with 1 <= k <= n, a1 most recent.
            # We'll map to ints.
            states = {(): 0}
            transitions = {}
            next_id = 1
            # BFS
            from collections import deque
            q = deque([()])
            while q:
                st = q.popleft()
                sid = states[st]
                row = []
                for x in (0, 1):
                    if st == () and x == 0:
                        nxt = ()
                    else:
                        nxt = (x,) + st[:n-1]
                    if nxt not in states:
                        states[nxt] = next_id
                        next_id += 1
                        q.append(nxt)
                    row.append(states[nxt])
                transitions[sid] = row
            return transitions, len(states)

        left, nleft = build_automaton(n)
        right, nright = build_automaton(n)
        # Now build the context closure.
        # Context: (l, q, s, r) where q is machine state (0..ns-1), s is 0 or 1.
        # Start with (0, 0, 0, 0) -- all blank, state A, symbol 0 under head, all blank right.
        # Wait: the initial tape is all zeros, head at 0, symbol 0 under head. So s = 0.
        # But the machine starts in state A = 0. So initial context is (0, 0, 0, 0).
        # We'll do a worklist closure.
        contexts = set()
        to_check = [(0, 0, 0, 0)]
        contexts.add((0, 0, 0, 0))
        # Precompute for each context the transition.
        # For a right move: l2 = left[l][w]; need [l2, q2, s2, r2] for every pair (r2, s2) with right[r2][s2] == r.
        # For a left move: r2 = right[r][w]; need [l2, q2, s2, r2] for every pair (l2, s2) with left[l2][s2] == l.
        # We need to find all pairs (r2, s2) with right[r2][s2] == r.
        # Since right is deterministic, for a given r and s2, r2 is the state that transitions to r on s2.
        # We can precompute the reverse: for each state r, and each symbol s2, find all r2 with right[r2][s2] == r.
        # Similarly for left.
        # Let's precompute reverse tables.
        nstates_left = nleft
        nstates_right = nright
        # reverse_right[r][s2] = list of r2 such that right[r2][s2] == r
        rev_right = [[[] for _ in range(2)] for _ in range(nstates_right)]
        for r2 in range(nstates_right):
            for s2 in range(2):
                rev_right[right[r2][s2]][s2].append(r2)
        rev_left = [[[] for _ in range(2)] for _ in range(nstates_left)]
        for l2 in range(nstates_left):
            for s2 in range(2):
                rev_left[left[l2][s2]][s2].append(l2)

        while to_check:
            ctx = to_check.pop()
            l, q, s, r = ctx
            # Find transition for (q, s). If absent, this context would halt -> fail.
            key = (q, s)
            if key not in table:
                return None
            w, move, q2 = table[key]
            # w is 0 or 1, move is +1 or -1
            if move == 1:
                # right move: l2 = left[l][w]
                if left[l][w] is None:
                    return None
                l2 = left[l][w]
                # need [l2, q2, s2, r2] for every pair (r2, s2) with right[r2][s2] == r
                # i.e., for every s2 in 0,1 and every r2 in rev_right[r][s2]
                for s2 in (0, 1):
                    for r2 in rev_right[r][s2]:
                        nctx = (l2, q2, s2, r2)
                        if nctx not in contexts:
                            contexts.add(nctx)
                            to_check.append(nctx)
            else:
                # left move: r2 = right[r][w]
                if right[r][w] is None:
                    return None
                r2 = right[r][w]
                # need [l2, q2, s2, r2] for every pair (l2, s2) with left[l2][s2] == l
                for s2 in (0, 1):
                    for l2 in rev_left[l][s2]:
                        nctx = (l2, q2, s2, r2)
                        if nctx not in contexts:
                            contexts.add(nctx)
                            to_check.append(nctx)

        # Check kernel limits: at most 5000 states per automaton and 200000 contexts.
        if nleft > 5000 or nright > 5000 or len(contexts) > 200000:
            continue
        # Build certificate.
        # contexts: list of [l, q, s, r]
        ctx_list = [list(c) for c in contexts]
        cert = {
            "kind": "cps",
            "left": left,
            "right": right,
            "contexts": ctx_list,
        }
        # Verify with kernel before returning.
        try:
            check(tm, cert)
            return cert
        except Reject:
            continue
        except Exception:
            continue
    return None

def decide(tm: str) -> dict | None:
    return _build_cps(tm)

NAME = "cps_ngram2"