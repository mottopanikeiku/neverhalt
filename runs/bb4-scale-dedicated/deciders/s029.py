import sys
sys.setrecursionlimit(100000)

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---------- helpers on the parsed table ----------

def transitions(tm):
    table, ns, nsym = parse(tm)
    return table, ns, nsym

def halt_set(table, ns):
    H = set()
    for q in range(ns):
        for s in (0, 1):
            if (q, s) not in table:
                H.add((q, s))
    return H

# ---------- DFA enumeration for one half-tape ----------

def enumerate_dfa(ns, H, max_states, budget):
    """Yield DFA transition tables (list of lists, index = state, entries 0/1 or None)
    in BFS-canonical order with size 1..max_states. State 0 loops on symbol 0.
    Pruning: a partial table is rejected if the set of tape-states that can reach a
    halting transition (computed backwards) is forced to include the blank tape 0.
    """
    results = []
    # state 0: 0-signal must stay in 0
    for size in range(1, max_states + 1):
        # enumerate all assignments of transitions for states 1..size-1 on symbols 0,1
        others = size - 1
        total = (size * size) ** (2 * others)
        if total > budget:
            continue
        # iterate lexicographically over transition choices for states 1..size-1
        idx = 0
        while idx < total:
            # decode idx into per-state (t0, t1)
            rem = idx
            tbl = [[0, 0] for _ in range(size)]
            ok = True
            for st in range(1, size):
                a = rem % size
                rem //= size
                b = rem % size
                rem //= size
                tbl[st][0] = a
                tbl[st][1] = b
            # pruning: backward reachability to halting transitions must not include 0
            forced = backward_forced(tbl, ns, H)
            if 0 not in forced:
                results.append(tbl)
            idx += 1
        if results:
            return results
    return []

def backward_forced(tbl, ns, H):
    """Compute the set of half-tape states that can force a halt.
    A context is (l, q, s, r). We only track the l-component here for a partial
    pruning: a state is 'bad' if from it a half-tape can reach a halting transition.
    Simple conservative approximation: walk the automaton from each state; if from
    any reachable state (including 0) the machine can be in a halting transition
    with any q,s, the state is bad. We approximate by: if any state in the
    reachable closure of 0 (under the partial table) can reach a halting
    (q,s) - we use the machine's halting set - then 0 is bad.
    """
    # reachable set from 0
    seen = {0}
    stack = [0]
    while stack:
        u = stack.pop()
        for x in (0, 1):
            v = tbl[u][x]
            if v is not None and v not in seen:
                seen.add(v)
                stack.append(v)
    # if any reachable state can reach a halting (q,s) through any q,s, mark bad.
    # We approximate the machine side with the full halt set.
    if any((q, s) in H for q in range(ns) for s in (0, 1)):
        # a reachable state could be in a context whose (q,s) halts; conservative:
        # state 0 is bad unless the table is the trivial single state looping on 0
        # (which we explicitly allow but do not prune here).
        return set(seen)
    return set()

# ---------- NFA construction for the other half-tape ----------

def build_nfa(table, ns, H):
    """Build an NFA over the half-tape alphabet {0,1} whose states are the machine
    states q plus an accept marker. Transitions correspond to stepping the machine
    while reading cells from far away towards the head.
    We model the half-tape as a finite word; the NFA accepts words that can appear
    as the read half-tape in a non-halting play.
    Simplification: build NFA states (q, dir) with dir in {0,1}; reading symbol x
    from far away: the machine in state q on symbol x moves; the cell is consumed.
    This is a rough but sound starting point; the closed-context fixpoint will do
    the real work.
    """
    # states: q in 0..ns-1 ; start state 0 ; we reverse-determinize later.
    # transitions: for each (q,x) -> (w, move, q2) in table, the half-tape reads x
    # and the machine state becomes q2. For a right move, the written symbol w is
    # pushed onto the left half-tape; for a left move the symbol under the head is
    # consumed from the right half-tape.
    # We only need the raw relation: delta(q, x) contains q2.
    delta = {}
    for q in range(ns):
        for x in (0, 1):
            if (q, x) in table:
                w, mv, q2 = table[(q, x)]
                delta.setdefault((q, x), set()).add(q2)
    return delta

def reverse_determinize(delta, ns):
    """Determinize the reverse NFA into a DFA reading from far away towards the head.
    Returns a transition table indexed by frozensets of NFA states.
    """
    start = frozenset({0})
    dfa = {}
    order = [start]
    seen = {start}
    while order:
        cur = order.pop()
        row = [None, None]
        for x in (0, 1):
            nxt = set()
            for st in cur:
                if (st, x) in delta:
                    for t in delta[(st, x)]:
                        nxt.add(t)
            if nxt:
                f = frozenset(nxt)
                if f not in seen:
                    seen.add(f)
                    order.append(f)
                row[x] = f
        dfa[cur] = row
    return dfa

# ---------- closed-context fixpoint ----------

def closure_contexts(table, ns, left, right):
    """Compute the smallest closed context set containing [0,0,0,0].
    left/right are dict: state -> [next0 or None, next1 or None] (or list).
    Returns (contexts, halting) where contexts is a set of (l,q,s,r) and halting
    is True if any context has a halting (q,s).
    """
    def lstep(l, x):
        if l < len(left):
            v = left[l][x]
            return v
        return None
    def rstep(r, x):
        if r < len(right):
            v = right[r][x]
            return v
        return None
    ctx = set()
    ctx.add((0, 0, 0, 0))
    changed = True
    while changed:
        changed = False
        for (l, q, s, r) in list(ctx):
            if (q, s) not in table:
                return None, True  # halting context
            w, mv, q2 = table[(q, s)]
            if mv == 1:  # head moves right
                l2 = lstep(l, w)
                if l2 is None:
                    return None, True
                for r2 in range(len(right)):
                    if rstep(r2, s) == r:
                        c = (l2, q2, s, r2)
                        if c not in ctx:
                            ctx.add(c)
                            changed = True
            else:  # head moves left
                r2 = rstep(r, w)
                if r2 is None:
                    return None, True
                for l2 in range(len(left)):
                    if lstep(l2, s) == l:
                        c = (l2, q2, s, r2)
                        if c not in ctx:
                            ctx.add(c)
                            changed = True
    if len(ctx) > 200000:
        return None, False
    return ctx, False

def emit_cps(tm, left, right, ctx):
    return {
        "kind": "cps",
        "left": [list(row) for row in left],
        "right": [list(row) for row in right],
        "contexts": [[l, q, s, r] for (l, q, s, r) in ctx],
    }

# ---------- main decider ----------

NAME = "fa-reduction-cps"

def decide(tm: str) -> dict | None:
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    H = halt_set(table, ns)
    # For the certificate we need two automata. Try all small pairs.
    max_states = 3
    # enumerate left automata
    left_cands = enumerate_dfa(ns, H, max_states, 200000)
    if not left_cands:
        return None
    # right automata: use reverse-determinized NFA from the machine
    delta = build_nfa(table, ns, H)
    rd = reverse_determinize(delta, ns)
    # map frozensets to ints
    state_map = {s: i for i, s in enumerate(rd.keys())}
    right_cands = []
    for i, s in enumerate(rd.keys()):
        row = rd[s]
        right_cands.append([state_map.get(row[0], None), state_map.get(row[1], None)])
    if not right_cands:
        return None
    # try pairs; start with matching sizes
    for left in left_cands:
        for right in right_cands:
            if len(left) != len(right):
                continue
            ctx, bad = closure_contexts(table, ns, left, right)
            if ctx is None:
                continue
            cert = emit_cps(tm, left, right, ctx)
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    return None

if __name__ == "__main__":
    import sys
    tm = sys.argv[1]
    print(decide(tm))
