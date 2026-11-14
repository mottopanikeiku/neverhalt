import json
from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

# Small helpers ---------------------------------------------------------------

def canon_bfs(table, n):
    # table[i][x] -> next state or None.  BFS-canonical labelling of
    # reachable states from 0.
    seen = {0: 0}
    order = [0]
    q = [0]
    while q:
        i = q.pop(0)
        for x in (0, 1):
            j = table[i][x]
            if j is None:
                continue
            if j not in seen:
                seen[j] = len(order)
                order.append(j)
                q.append(j)
    lab = [seen[i] for i in order]
    return lab

def reachable_count(table, n):
    seen = {0}
    q = [0]
    while q:
        i = q.pop()
        for x in (0, 1):
            j = table[i][x]
            if j is not None and j not in seen:
                seen.add(j)
                q.append(j)
    return len(seen)

# --------------------------- half-tape semantics ---------------------------
# We model a half-tape (say right of head) as a stack read far-to-head.
# Its language is the set of sequences of cells, read from far away towards
# the head, that can occur.  A DFA for it is a table dfa[s][x] -> s' or None
# (None means the sequence cannot occur).
#
# For the context fixpoint we need pairs (r2, s2) with right[r2][s2] == r.
# That is exactly the pair relation of the DFA: right[r][s] is the state
# reached after reading symbol s, and the "predecessor" pairs are those with
# right[r2][s2] == r.

def pairs_of(dfa, n):
    out = []
    for r in range(n):
        for s in (0, 1):
            r2 = dfa[r][s]
            if r2 is not None:
                out.append((r2, s, r))
    return out

# -------------------------- closed-context fixpoint --------------------------

def closed_contexts(tm, left, nl, right, nr, max_ctx=190000):
    # left/right are automaton tables; machine transitions from parse.
    table, ns, nsym = tm
    ctx = set()
    ctx.add((0, 0, 0, 0))
    frontier = [(0, 0, 0, 0)]
    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            if len(ctx) > max_ctx:
                return None
            tr = table.get((q, s))
            if tr is None:
                return None  # halting context => no certificate
            w, mv, q2 = tr
            if mv == 1:  # move right
                l2 = left[l][w]
                if l2 is None:
                    return None
                for (r2, s2, _rr) in pairs_of(right, nr):
                    pass
                # all pairs (r2,s2) with right[r2][s2] == r
                for r2 in range(nr):
                    for s2 in (0, 1):
                        if right[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                nxt.append(c)
            else:  # move left
                r2 = right[r][w]
                if r2 is None:
                    return None
                for l2 in range(nl):
                    for s2 in (0, 1):
                        if left[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                nxt.append(c)
        frontier = nxt
    return ctx

# -------------------------- DFA enumeration (canonical) --------------------------

def enumerate_dfas(max_states, max_tries=20000):
    """Yield canonical DFA tables of size up to max_states.  Each table is a
    list of [next0, next1] for states 0..n-1; state 0 loops on 0 (blank tape)."""
    tries = 0
    # start with 1-state
    for n in range(1, max_states + 1):
        # deterministic enumeration of tables with labels 0..n-1, canonical
        # BFS labelling
        def rec(states_done, table):
            nonlocal tries
            if tries > max_tries:
                return
            if states_done == n:
                tries += 1
                lab = canon_bfs(table, n)
                # canonical check: lab must be identity
                if lab == list(range(n)):
                    yield table
                return
            i = states_done
            # transitions to already-labelled states or new states
            choices = list(range(n)) + [n]
            for x0 in choices:
                for x1 in choices:
                    t = [row[:] for row in table]
                    if i < len(t):
                        t[i][0] = x0
                        t[i][1] = x1
                    else:
                        t.append([x0, x1])
                    # enforce: state 0 loops on 0
                    if i == 0:
                        t[0][0] = 0
                    # prune: canonical partial labelling must be possible
                    # (simple check: no state labelled before its predecessor)
                    rec(states_done + 1, t)
        table = []
        # iterative generation is complex; use recursion with mutable table
        # We generate rows in order 0..n-1.
        def gen(i, table):
            nonlocal tries
            if tries > max_tries:
                return
            if i == n:
                tries += 1
                lab = canon_bfs(table, n)
                if lab == list(range(n)):
                    yield table
                return
            choices = list(range(n)) + [n]
            for x0 in choices:
                for x1 in choices:
                    table.append([x0, x1])
                    if i == 0:
                        table[0][0] = 0
                    yield from gen(i + 1, table)
                    table.pop()
        yield from gen(0, [])

# -------------------------- backward reachability --------------------------

def halting_forced_blank(table, ns, nsym):
    """Return True if some state can reach a halting transition while reading
    only blank cells from the all-blank configuration.  We approximate by
    checking whether the blank tape (state 0 on symbol 0) can reach a halt
    using only symbols 0 along the way -- i.e. whether state 0 can halt on a
    tape that is all zeros.  This is exactly the blank-tape halting problem,
    which we cannot decide; instead we use a cheap heuristic: if the machine
    halts within a few hundred steps on the blank tape, reject the pair."""
    halt = False
    stack = [(0, 0, 0)]  # state, pos, steps
    seen = set()
    while stack and not halt:
        st, pos, steps = stack.pop()
        if steps > 400:
            return False
        if (st, pos) in seen:
            continue
        seen.add((st, pos))
        tr = table.get((st, 0))
        if tr is None:
            halt = True
            break
        w, mv, q2 = tr
        stack.append((q2, pos + mv, steps + 1))
    return halt

# -------------------------- decide --------------------------

NAME = "dfa-search-cps"

def decide(tm):
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    # Quick check: if it halts on blank tape within budget, no certificate.
    if halting_forced_blank(table, ns, nsym):
        return None
    # Enumerate DFAs for the left half-tape.
    for nleft in range(1, 5):
        for left in enumerate_dfas(nleft, max_tries=4000):
            # canonical: state 0 loops on 0
            if left[0][0] != 0:
                continue
            # Enumerate DFAs for the right half-tape.
            for nright in range(1, 5):
                for right in enumerate_dfas(nright, max_tries=4000):
                    if right[0][0] != 0:
                        continue
                    ctx = closed_contexts((table, ns, nsym), left, nleft,
                                          right, nright)
                    if ctx is not None and len(ctx) <= 200000:
                        cert = {
                            "kind": "cps",
                            "left": left,
                            "right": right,
                            "contexts": [list(c) for c in ctx],
                        }
                        try:
                            check(tm, cert)
                            return cert
                        except Reject:
                            pass
    return None
