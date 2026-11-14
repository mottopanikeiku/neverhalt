import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# State 0 = all-blank half-tape.  left[i][x] = next state reading symbol x,
# or None if that never happens.  We search small automata for one half-tape.
# A half-tape automaton is "good" for our purposes when its state 0 is the
# blank tape and it is deterministic on the cells it reads.

def canon_automaton(n, table, target):
    # BFS-canonical labelling of a DFA given as table[i][x] -> j (or None).
    # Returns a canonical tuple (dictionary) up to relabelling, or None if
    # the partial table is not consistent with reaching target from 0.
    seen = {0}
    order = []
    q = deque([0])
    while q:
        i = q.popleft()
        order.append(i)
        for x in range(2):
            j = table[i][x]
            if j is None:
                continue
            if j not in seen:
                seen.add(j)
                q.append(j)
    # BFS canonical labelling
    labels = {0: 0}
    cnt = 1
    canon = {0: (0, ordered_sig(table, 0, labels))}
    for i in order:
        for x in range(2):
            j = table[i][x]
            # label is assigned when node popped
    # simpler: assign labels in BFS order
    labels = {}
    lab_of = {}
    q = deque([0])
    labels[0] = 0
    while q:
        i = q.popleft()
        for x in range(2):
            j = table[i][x]
            if j is None:
                continue
            if j not in labels:
                labels[j] = len(lab_of)
                lab_of[labels[j]] = j
                q.append(j)
    return tuple(sorted((labels[i], tuple(labels[table[i][x]] if table[i][x] is not None else None for x in range(2))) for i in labels))

def ordered_sig(table, i, labels):
    return tuple(labels[table[i][x]] if table[i][x] is not None else None for x in range(2))

def enum_dfa(max_states):
    """Enumerate partial DFAs with states 0..max_states-1, state 0 looping on 0.
    Returns list of tables (list of lists) in order of (num_states, transitions).
    """
    out = []
    for n in range(1, max_states + 1):
        for bits in range((2 + 1) ** (2 * (n - 1))):
            table = [[0, 0] for _ in range(n)]
            table[0][0] = 0
            b = bits
            for i in range(1, n):
                for x in range(2):
                    d = b % 3
                    b //= 3
                    if d == 0:
                        table[i][x] = 0
                    elif d == 1:
                        table[i][x] = i
                    else:
                        table[i][x] = i + 1
            if table[n-1][1] == n:
                continue
            # skip tables where a transition to n (nonexistent) leaves state n
            if any(table[i][x] == n for i in range(n) for x in range(2)):
                continue
            out.append(table)
    return out

def build_automata(max_states):
    """All canonical partial DFAs over {0,1} with states 0..n-1, state 0 loops on 0."""
    result = []
    seen = set()
    for n in range(1, max_states + 1):
        for bits in range((2 + 1) ** (2 * (n - 1))):
            table = [[0, 0] for _ in range(n)]
            table[0][0] = 0
            b = bits
            ok = True
            for i in range(1, n):
                for x in range(2):
                    d = b % 3
                    b //= 3
                    if d == 0:
                        table[i][x] = 0
                    elif d == 1:
                        table[i][x] = i
                    else:
                        table[i][x] = i + 1
            if any(table[i][x] >= n for i in range(n) for x in range(2)):
                continue
            c = canon_automaton(n, table)
            if c in seen:
                continue
            seen.add(c)
            result.append(table)
    return result

def closure_contexts(tm, left, right):
    """Closed context set for pair (left, right).  Returns list of contexts [l,q,s,r]
    or None if a halting context is forced.  Also returns the halting flag."""
    table, n_states, _ = parse(tm)
    nQ = n_states
    nL = len(left)
    nR = len(right)
    start = (0, 0, 0, 0)
    ctx = set([start])
    frontier = deque([start])
    while frontier:
        (l, q, s, r) = frontier.popleft()
        tr = table.get((q, s))
        if tr is None:
            return None  # halting context
        w, mv, q2 = tr
        if mv > 0:
            l2 = left[l][w]
            if l2 is None:
                return None
            # for every (r2, s2) with right[r2][s2] == r
            for r2 in range(nR):
                for s2 in range(2):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            frontier.append(c)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(nL):
                for s2 in range(2):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            frontier.append(c)
    return ctx

def emit_cps(tm, left, right, ctx):
    left_t = [[left[i][x] for x in range(2)] for i in range(len(left))]
    right_t = [[right[i][x] for x in range(2)] for i in range(len(right))]
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    return {"kind": "cps", "left": left_t, "right": right_t, "contexts": contexts}

def decide(tm):
    try:
        table, n_states, _ = parse(tm)
    except Exception:
        return None
    # Try all pairs of small automata, one side fixed as the identity-ish loop.
    # We enumerate both sides up to 3 states first (cheap), then grow.
    max_states = 4
    auts = build_automata(max_states)
    # deduplicate by canonical form
    uniq = []
    seen = set()
    for a in auts:
        c = canon_automaton(len(a), a)
        if c not in seen:
            seen.add(c)
            uniq.append(a)
    for left in uniq:
        for right in uniq:
            ctx = closure_contexts(tm, left, right)
            if ctx is not None:
                cert = emit_cps(tm, left, right, ctx)
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
    return None