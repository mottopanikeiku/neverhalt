import sys
from itertools import product

from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

# ---------- helpers ----------

def build_halt_preimage_states(tm):
    """For the machine, precompute for each (state, symbol) whether that transition
    can still lead to a halting transition ever (a halting transition is a state with
    no outgoing transition for a symbol; bbchallenge notation uses '---' or jumps to
    nonexistent states). We use parse's table: absent entries halt."""
    table, n_states, n_symbols = parse(tm)
    # table[(state, symbol)] = (write, move, next) or missing -> halt
    halt_preds = {}
    # fixed point: (q, s) can reach a halt if it is a halting transition or any
    # successor can reach a halt
    changed = True
    # initialize: all (q,s) can reach halt by default (optimistic), then remove
    # those that cannot. Simpler: compute which (q,s) cannot reach a halt, i.e.
    # which transitions are "safe".
    # Let can[q][s] = True if from (q,s) halting is reachable.
    can = {}
    for q in range(n_states):
        for s in range(n_symbols):
            if (q, s) not in table:
                can[(q, s)] = True
            else:
                can[(q, s)] = False
    changed = True
    while changed:
        changed = False
        for q in range(n_states):
            for s in range(n_symbols):
                if can[(q, s)]:
                    continue
                w, move, q2 = table[(q, s)]
                # successor is (q2, w) after the move (the written symbol is read next)
                if can.get((q2, w), False):
                    can[(q, s)] = True
                    changed = True
    return table, n_states, n_symbols, can

# ---------- DFA enumeration ----------
# A DFA over {0,1}: transition table is a tuple of (delta0, delta1) per state,
# state 0 is the blank-tape sink. We enumerate all DFAs with n states where
# state 0 loops on symbol 0 (delta(0,0) = 0) and is a sink for symbol 0; we do not
# require delta(0,1) = 0 because the first non-blank cell can be anything.
# BFS-canonical order: enumerate tables in increasing size and increasing
# lexicographic order of the flattened transition list.

def enumerate_dfas(max_states):
    for n in range(1, max_states + 1):
        # state 0: delta0 must be 0 (blank loop). delta1 free.
        # other states: delta0, delta1 free in [0, n-1]
        for delta1_0 in range(n):
            for rest in product(range(n), repeat=2 * (n - 1)):
                # rest encodes for states 1..n-1: (d0, d1)
                delta = [[0, delta1_0]]
                for i in range(n - 1):
                    delta.append([rest[2 * i], rest[2 * i + 1]])
                yield n, tuple(tuple(d) for d in delta)

# ---------- half-tape language ----------
# For a DFA table, we want to know whether the blank tape (all zeros, read from far
# away towards the head) is accepted... but our kernel does not accept/reject a
# language; it only needs the automaton table. The pruning is: if the DFA can reach
# a halting context, that DFA is bad. We compute the backward set of (state, symbol)
# pairs in the machine that can reach a halt, and prune DFA states whose symbol
# transitions would force a halting context.
# Simpler pruning: for a DFA A used for one half tape, the machine can halt only if
# some context [l, q, s, r] with (q,s) halting exists in the closure. We cannot know
# the closure before building it, so instead we prune DFA states that, combined with
# the machine's halt preimage, are unavoidable. A practical and sound pruning: if
# the DFA table itself, when used as "left", has a state l such that for every
# possible right automaton state r and symbol s2, the context [l, q, s, r] would be
# forced to a halting (q, s) pair... this is complex. We instead rely on the closure
# fixpoint and return None if a halting context appears. The enumeration is small
# enough.

# ---------- context closure ----------
# left[i][x] = state reached from i on x, or None.
# right likewise.
# context = (l, q, s, r)
# start with (0, 0, 0, 0)
# close under the kernel's rules.

def close_contexts(left, right, n_states, n_symbols, table, limit=200000):
    # left/right: lists of lists, None allowed
    contexts = set()
    contexts.add((0, 0, 0, 0))
    # precompute transitions
    def step_ctx(l, q, s, r):
        # returns list of new contexts, or None if halting
        if (q, s) not in table:
            return None
        w, move, q2 = table[(q, s)]
        if move > 0:
            l2 = left[l][w]
            if l2 is None:
                return None
            out = []
            for r2 in range(len(right)):
                for s2 in range(n_symbols):
                    if right[r2][s2] == r:
                        out.append((l2, q2, s2, r2))
            return out
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            out = []
            for l2 in range(len(left)):
                for s2 in range(n_symbols):
                    if left[l2][s2] == l:
                        out.append((l2, q2, s2, r2))
            return out
    frontier = [(0, 0, 0, 0)]
    while frontier:
        nxt = []
        for ctx in frontier:
            res = step_ctx(*ctx)
            if res is None:
                return None
            for nc in res:
                if nc not in contexts:
                    contexts.add(nc)
                    nxt.append(nc)
            if len(contexts) > limit:
                return None
        frontier = nxt
    return contexts

# ---------- reverse determinization (far-to-head DFA from NFA) ----------
# Given a DFA table A (head-to-far, i.e. reads cells nearest the head first),
# build the reverse DFA that reads cells far-to-head. The reverse language is
# recognized by the NFA obtained by reversing the DFA: states same, start = all
# states that can reach the accepting state, and transitions reversed. We then
# determinize.
# We use a single accepting state: state 0 (blank tape). Actually for the right
# half tape we want: reading cells right of the head from far away towards the head.
# A DFA B is such a reader if B's language is the reverse of A's language, with the
# same state set. Build NFA N: states of A; start set = {q : A accepts 0^omega?} --
# too vague. Instead, for the reverse, we take the NFA with transitions reversed and
# initial states = {q : from q, reading zeros forever, A stays in state 0}? The blank
# tape is all zeros; the far-away cells are blank. A valid right automaton must
# accept the blank tape as state 0. We require right[0][0] == 0. The reverse NFA:
# states = states of A; initial states = {q in A : A on all-zero input from q stays
# in state 0}? That's not right either.
# Practical approach: the reverse of a DFA A (with a single start state) is an NFA
# whose initial states are those from which A can reach the start state of A by
# reading only zeros? No: the blank tape is read as zeros from far away; the state
# after reading the blank part must be the start state of the forward reader.
# Standard: reverse(A) accepts x^R for x in L(A). NFA for reverse(A): states of A,
# initial states = {q : q can reach start state of A}, transitions reversed, final
# states = {start state of A}. But here the "input" read far-to-head is the reverse
# of the head-to-far input, and the far-to-head automaton must end in a state that
# encodes the near cells. We use the NFA with initial states = all states, reversed
# transitions, and determinize with a subset construction; the start subset is
# {0} intersected... To keep it simple: build the reverse NFA with initial states
# = {q : delta_A(q, 0) eventually reaches start (0)}? We instead just determinize
# the NFA with initial states = all states that have a path to state 0 under zeros,
# and accept the resulting DFA; we then verify by brute force that the resulting
# DFA accepts the blank tape (all zeros) and is a valid reader.

def reverse_determinize(A, n_states):
    # A: tuple of (d0, d1) per state, state 0 is start.
    # NFA with reversed transitions: from p on x to q if A[q][x] == p.
    # Initial states: all states that can reach 0 by reading only zeros (so that
    # reading blanks far away leaves the automaton able to be at 0 near the head).
    rev = [{}, {}]
    for x in range(2):
        for q in range(n_states):
            rev[x][A[q][x]] = rev[x].get(A[q][x], set()) | {q}
    # initial: states from which 0 is reachable via zeros
    init = set()
    stack = [0]
    seen = {0}
    while stack:
        q = stack.pop()
        init.add(q)
        for x in range(2):
            for p in rev[x].get(q, ()):
                if p not in seen:
                    seen.add(p)
                    stack.append(p)
    # determinize
    start = frozenset(init)
    dfa = {}
    order = []
    stack = [start]
    while stack:
        S = stack.pop()
        if S in dfa:
            continue
        row = []
        for x in range(2):
            T = frozenset().union(*[rev[x].get(q, set()) for q in S]) if S else frozenset()
            row.append(T)
        dfa[S] = row
        order.append(S)
        for T in row:
            if T not in dfa:
                stack.append(T)
    return dfa, order

# ---------- main ----------

def decide(tm: str):
    table, n_states, n_symbols, can = build_halt_preimage_states(tm)
    # limit automaton size
    max_auto = 3
    for n, A in enumerate_dfas(max_auto):
        if n == 0:
            continue
        # A is head-to-far (reads cells nearest head first). We need far-to-head
        # for the left half tape: reverse determinize A to get left.
        # For the right half tape we need head-to-far: use A directly as right? The
        # kernel's right automaton reads cells right of head from far away towards
        # the head, i.e. far-to-head as well. So both sides need far-to-head.
        # Build far-to-head DFA for A.
        rev, order = reverse_determinize(A, n)
        # map subsets to states
        sub2id = {S: i for i, S in enumerate(order)}
        # ensure state 0 (blank) maps to a state that loops on 0 and is the start
        # We build the automaton table: state id -> [delta0, delta1]
        left = [[0, 0] for _ in range(len(order))]
        for S in order:
            i = sub2id[S]
            for x in range(2):
                T = rev[S][x]
                if T in sub2id:
                    left[i][x] = sub2id[T]
                else:
                    left[i][x] = None
        # force state 0 to loop on 0: find the state corresponding to the start
        # subset and renumber it to 0
        start_id = sub2id[frozenset().union(*[set() for _ in range(1)])] if False else None
        # The start subset is the initial set computed in reverse_determinize; we
        # need it returned. Simplify: rebuild with explicit start.
        # (For speed, just try all states as state 0 and require left[0][0] == 0.)
        # Find a state whose delta0 is itself.
        cand = None
        for i in range(len(left)):
            if left[i][0] == i:
                cand = i
                break
        if cand is None:
            continue
        # renumber so that cand becomes 0
        perm = list(range(len(left)))
        perm[0], perm[cand] = perm[cand], perm[0]
        remap = {old: new for new, old in enumerate(perm)}
        newleft = []
        for new, old in enumerate(perm):
            row = []
            for x in range(2):
                v = left[old][x]
                row.append(remap[v] if v is not None else None)
            newleft.append(row)
        left = newleft
        if left[0][0] != 0:
            continue
        # right automaton: we need a far-to-head automaton too. Try the same
        # construction (or the forward A if it also reads far-to-head). Try both.
        for right in (left, [[0, 0]] + [[None, None]] * (len(left) - 1)):
            if right[0][0] != 0:
                continue
            # also try right = a fresh enumeration? Just use left and a trivial one.
            ctx = close_contexts(left, right, n_states, n_symbols, table)
            if ctx is not None:
                # build certificate (kernel wants lists, not None)
                cert = {
                    "kind": "cps",
                    "left": [[a if a is not None else None for a in row] for row in left],
                    "right": [[a if a is not None else None for a in row] for row in right],
                    "contexts": [list(c) for c in ctx],
                }
                try:
                    from neverhalt.kernel import check
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
                except Exception:
                    pass
    return None

if __name__ == "__main__":
    print(decide(sys.argv[1]))
