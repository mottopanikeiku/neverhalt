import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(100000)

# Automaton construction helpers for CPS certificates.
# We build automata that remember the last n cells of a half-tape (n-gram).
# left automaton reads cells from far away towards the head;
# right automaton reads cells from far away towards the head.

def build_gram_automaton(cells, n):
    # states: tuples of last n symbols read so far.
    # transitions: on symbol x, new state = (state + (x,))[-n:]
    # We use a dict mapping tuple -> index.
    table = {}
    idx = {}
    start = tuple([0] * n)
    idx[start] = 0
    table[0] = {}
    for x in range(2):
        ns = (start + (x,))[-n:]
        if ns not in idx:
            idx[ns] = len(idx)
            table[idx[ns]] = {}
        table[0][x] = idx[ns]
    for st, tup in list(idx.items()):
        if st == 0:
            continue
        for x in range(2):
            ns = (tup + (x,))[-n:]
            if ns not in idx:
                idx[ns] = len(idx)
                table[idx[ns]] = {}
            table[st][x] = idx[ns]
    # convert to list of dicts with None for missing
    return [table[i] for i in range(len(idx))]

# Generic n-gram CPS builder: for each context [l, q, s, r] we need:
#  - transition (q, s) -> (w, move, q2) exists
#  - right move: l2 = left[l][w] not None and for EVERY (r2, s2) with right[r2][s2] == r,
#    [l2, q2, s2, r2] is a context.
#  - left move: mirror image.
# We build the set of contexts by fixpoint iteration starting from [0,0,0,0].

def build_cps(tm, n, max_states, max_contexts):
    table, n_states, n_symbols = parse(tm)
    # n_symbols should be 2 (0 and 1)
    # Build left and right automata as n-gram automata over the two symbols.
    # Automaton state = tuple of last n symbols read.
    # We need the transition from a state on symbol x: append x, keep last n.
    # Represent states as tuples directly; use dict for indexing.
    left_states = {}
    right_states = {}
    start = tuple([0] * n)
    left_states[start] = 0
    right_states[start] = 0
    # We'll lazily add states.
    def next_state(states, tup, x):
        ns = (tup + (x,))[-n:]
        if ns not in states:
            states[ns] = len(states)
        return states[ns]
    # Build transition tables as list of dicts.
    # We'll grow them.
    left_tab = {}
    right_tab = {}
    # We must ensure state 0 is the all-blank state and left[0][0] == right[0][0] == 0.
    # The all-blank tuple is (0,)*n which is start, so state 0.
    # Transition on symbol 0 from start should stay in start (all zeros).
    # Actually if we append 0 to (0,)*n we get (0,)*n, so yes.
    # For symbol 1, we go to a new state.
    def get_tab(tab, states, tup, x):
        st = states[tup]
        if st not in tab:
            tab[st] = {}
        return tab[st]
    # Pre-populate transitions for all states we create.
    def ensure_state(states, tup, tab):
        if tup not in states:
            states[tup] = len(states)
            tab[states[tup]] = {}
        return states[tup]
    # We'll build the automata as we discover states during context expansion.
    # Fixpoint over contexts.
    # Context: (l, q, s, r) with l, r integers (automaton states), q state index, s symbol 0/1.
    # We need to know for each machine state q and symbol s the transition.
    # table[(q, s)] = (w, move, q2) or absent (halt).
    contexts = set()
    contexts.add((0, 0, 0, 0))
    # We also need to expand automata as needed.
    # To expand a context, we need:
    #  - for right move: for every (r2, s2) with right[r2][s2] == r, check [l2, q2, s2, r2].
    #    This requires enumerating all pairs (r2, s2) with transition to r.
    #    We can precompute reverse transitions of the automaton.
    #  - for left move: for every (l2, s2) with left[l2][s2] == l, check [l2, q2, s2, r2].
    # We'll maintain reverse transition lists.
    left_rev = {}  # state -> list of (prev_state, symbol)
    right_rev = {}
    def add_left_trans(prev_tup, x, next_tup):
        pi = ensure_state(left_states, prev_tup, left_tab)
        ni = ensure_state(left_states, next_tup, left_tab)
        left_tab[pi][x] = ni
        left_rev.setdefault(ni, []).append((pi, x))
    def add_right_trans(prev_tup, x, next_tup):
        pi = ensure_state(right_states, prev_tup, right_tab)
        ni = ensure_state(right_states, next_tup, right_tab)
        right_tab[pi][x] = ni
        right_rev.setdefault(ni, []).append((pi, x))
    # Initialize: state 0 on symbol 0 stays 0.
    add_left_trans(start, 0, start)
    add_right_trans(start, 0, start)
    # On symbol 1, need a state.
    # We'll create as needed.
    def get_or_create_left(tup):
        return ensure_state(left_states, tup, left_tab)
    def get_or_create_right(tup):
        return ensure_state(right_states, tup, right_tab)
    # Helper to compute next tuple after reading x.
    def step_tup(tup, x):
        return (tup + (x,))[-n:]
    # We'll do fixpoint iteration.
    # For each context, we need to check if it's valid and expand.
    # We'll maintain a worklist.
    work = list(contexts)
    # To check a context, we need the transition of (q, s). If missing -> halt -> reject context.
    # For each context we also need to ensure the automaton transitions l on w exist and r on w exist.
    # Actually the kernel checks: for right move, l2 = left[l][w] not null.
    # So we need to ensure left[l][w] exists for the context to be valid.
    # If it doesn't exist, the context is invalid (cannot be part of certificate).
    # Similarly for left move, right[r][w] must exist.
    # So during expansion we must add those transitions.
    # Let's define a function to validate and expand a context, returning list of new contexts.
    def expand_context(l, q, s, r):
        # Check transition exists.
        key = (q, s)
        if key not in table:
            return None  # halting transition -> context invalid
        w, move, q2 = table[key]
        new = []
        if move == 1:  # right move
            # Need left[l][w] exists.
            if l not in left_tab or w not in left_tab[l]:
                # We can try to add it if automaton can transition.
                # But automaton is deterministic: from state l, reading w should go to some state.
                # The state l corresponds to a tuple of last n symbols. Reading w gives next tuple.
                # We need to find the tuple for state l. We don't store reverse mapping.
                # Let's store a mapping from state index to tuple.
                pass
            # For now, we'll assume automaton is built on the fly and we can compute l2.
            l2 = left_tab[l].get(w)
            if l2 is None:
                return None
            # For every (r2, s2) with right[r2][s2] == r, add context (l2, q2, s2, r2).
            # We need right_rev[r] to list (r2, s2).
            if r not in right_rev:
                # r has no predecessors: but r must have been reached from something.
                # Actually r is a state; it may have no incoming transitions if it's start and never read.
                # But if r=0 (all blank), it has predecessors? The automaton reading from far away:
                # the far away is all blank, so the state is start. There is no "before" start.
                # So r=0 has no predecessors. That's fine: the condition is "for every (r2,s2) with right[r2][s2]==r".
                # If r=0, there are no such pairs, so the condition is vacuously true.
                pass
            for (r2, s2) in right_rev.get(r, []):
                new.append((l2, q2, s2, r2))
        else:  # left move (move == -1)
            r2 = right_tab[r].get(w)
            if r2 is None:
                return None
            if l not in left_rev:
                pass
            for (l2, s2) in left_rev.get(l, []):
                new.append((l2, q2, s2, r2))
        return new
    # We need to build automata on the fly. The state l is an index; we need to know the tuple
    # to compute next state on w. So we must store a map from state index to tuple.
    left_idx_to_tup = {0: start}
    right_idx_to_tup = {0: start}
    # When we create a new state, we add the tuple mapping.
    # Modify ensure_state to also record tuple.
    def ensure_state2(states, tup, tab, idx_to_tup):
        if tup not in states:
            states[tup] = len(states)
            tab[states[tup]] = {}
            idx_to_tup[states[tup]] = tup
        return states[tup]
    # Rebuild from scratch with this.
    # Let's restart cleanly.
    left_states = {}
    right_states = {}
    left_tab = {}
    right_tab = {}
    left_idx_to_tup = {}
    right_idx_to_tup = {}
    start = tuple([0] * n)
    left_states[start] = 0
    right_states[start] = 0
    left_tab[0] = {}
    right_tab[0] = {}
    left_idx_to_tup[0] = start
    right_idx_to_tup[0] = start
    left_rev = {}
    right_rev = {}
    def ensure_left(tup):
        if tup not in left_states:
            left_states[tup] = len(left_states)
            left_tab[left_states[tup]] = {}
            left_idx_to_tup[left_states[tup]] = tup
        return left_states[tup]
    def ensure_right(tup):
        if tup not in right_states:
            right_states[tup] = len(right_states)
            right_tab[right_states[tup]] = {}
            right_idx_to_tup[right_states[tup]] = tup
        return right_states[tup]
    # Initialize transitions on 0 from start.
    left_tab[0][0] = 0
    right_tab[0][0] = 0
    # For transitions on 1 from start, we create new states.
    def get_left_next(l, x):
        tup = left_idx_to_tup[l]
        nt = (tup + (x,))[-n:]
        ni = ensure_left(nt)
        left_tab[l][x] = ni
        left_rev.setdefault(ni, []).append((l, x))
        return ni
    def get_right_next(r, x):
        tup = right_idx_to_tup[r]
        nt = (tup + (x,))[-n:]
        ni = ensure_right(nt)
        right_tab[r][x] = ni
        right_rev.setdefault(ni, []).append((r, x))
        return ni
    # Now fixpoint.
    contexts = set()
    contexts.add((0, 0, 0, 0))
    work = list(contexts)
    while work:
        l, q, s, r = work.pop()
        if (l, q, s, r) in contexts:
            continue
        contexts.add((l, q, s, r))
        key = (q, s)
        if key not in table:
            # Halting transition: this context cannot be in a valid certificate.
            contexts.discard((l, q, s, r))
            continue
        w, move, q2 = table[key]
        new = []
        if move == 1:
            l2 = left_tab[l].get(w)
            if l2 is None:
                # Try to add transition.
                l2 = get_left_next(l, w)
            if r not in right_rev:
                # r has no predecessors; vacuous.
                pass
            for (r2, s2) in right_rev.get(r, []):
                new.append((l2, q2, s2, r2))
        else:
            r2 = right_tab[r].get(w)
            if r2 is None:
                r2 = get_right_next(r, w)
            for (l2, s2) in left_rev.get(l, []):
                new.append((l2, q2, s2, r2))
        for c in new:
            if c not in contexts:
                work.append(c)
    # After fixpoint, check if any context in the final set is invalid (halting).
    # Actually we discarded halting contexts, but they might be reachable from valid ones.
    # If a valid context expands to a halting context, then the certificate is invalid.
    # So we need to check: for every context in the final set, its expansion must stay in the set.
    # Our fixpoint only added contexts from valid expansions; halting contexts were discarded.
    # But if a context expands to a halting context, we discarded it, but the parent context
    # remains in the set. That would be an invalid certificate.
    # So we must verify: for every context in contexts, the expansion is subset of contexts.
    # Let's do a verification pass.
    valid = True
    for (l, q, s, r) in list(contexts):
        key = (q, s)
        if key not in table:
            valid = False
            break
        w, move, q2 = table[key]
        if move == 1:
            if l not in left_tab or w not in left_tab[l]:
                valid = False
                break
            l2 = left_tab[l][w]
            for (r2, s2) in right_rev.get(r, []):
                if (l2, q2, s2, r2) not in contexts:
                    valid = False
                    break
            if not valid:
                break
        else:
            if r not in right_tab or w not in right_tab[r]:
                valid = False
                break
            r2 = right_tab[r][w]
            for (l2, s2) in left_rev.get(l, []):
                if (l2, q2, s2, r2) not in contexts:
                    valid = False
                    break
            if not valid:
                break
    if not valid:
        return None
    # Build certificate.
    # Convert left_tab and right_tab to lists of lists with None for missing.
    def to_list(tab, n_states):
        res = []
        for i in range(n_states):
            row = [None, None]
            if i in tab:
                for x in range(2):
                    if x in tab[i]:
                        row[x] = tab[i][x]
            res.append(row)
        return res
    left_list = to_list(left_tab, len(left_states))
    right_list = to_list(right_tab, len(right_states))
    # Ensure state 0 transitions: left_list[0][0] == 0, right_list[0][0] == 0.
    if left_list[0][0] != 0 or right_list[0][0] != 0:
        return None
    ctx_list = [[l, q, s, r] for (l, q, s, r) in contexts]
    if len(left_list) > 5000 or len(right_list) > 5000 or len(ctx_list) > 200000:
        return None
    return {"kind": "cps", "left": left_list, "right": right_list, "contexts": ctx_list}

def decide(tm: str):
    # Try increasing n for n-gram CPS.
    for n in range(1, 5):
        cert = build_cps(tm, n, 5000, 200000)
        if cert is not None:
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    return None
}