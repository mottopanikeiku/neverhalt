from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

N_ST = 3
N_SY = 2
H = 5000

# ---------------- helpers ----------------

def tab(g):
    return tuple(g.get(k, None) for k in range(len(g)))

def sign(x):
    return 1 if x >= 0 else 0

# ---------------- small automata enumeration ----------------

def enum_automata(max_states, allow_blank_loop=True):
    """Yield automata as tuples of rows [row for state i], each row a tuple of
    length N_SY with entries in 0..max_states-1 or None."""
    # We enumerate rows for states 0..max_states-1 independently, but we want
    # the automaton to be *reachable* from state 0 and to be deterministic.
    # To keep the count small we only allow transitions out of reachable
    # states; unreachable states are filled with None.
    # For each state, its row is an arbitrary tuple of N_SY entries in
    # [0..max_states-1] U {None}. We enumerate all combinations where state 0
    # loops on 0 (blank) -> row for state 0 has entry[0] == 0.
    import itertools
    choices = list(range(max_states)) + [None]
    # enumerate rows for states 1..max_states-1 freely, row 0 fixed on symbol 0.
    if max_states == 1:
        # only state 0, must loop on 0
        for c1 in choices:
            yield ((0, c1),)
        return
    # symbol 0 of state 0 must be 0 (blank loop); symbol 1 free
    for c1_0 in choices:
        # actually enforce blank loop only if allow_blank_loop
        pass
    # full enumeration with pruning on reachability is done by caller; here
    # we just enumerate all rows.
    # We restrict: state 0 on symbol 0 must be 0 (per hint).
    # Enumerate rows for states 1..max_states-1.
    n_other = max_states - 1
    total = (len(choices)) ** (n_other * N_SY + 1)  # +1 for state0 sym1
    # too big for max_states=3? 4^(2*2+1)=4^5=1024 fine.
    # state0 row: (0, x) where x in choices
    # states 1..n_other rows: each N_SY entries
    for s0x in choices:
        base_rows = [(0, s0x)]
        for rows in itertools.product(choices, repeat=n_other * N_SY):
            full = list(base_rows)
            for i in range(n_other):
                full.append((rows[i * N_SY], rows[i * N_SY + 1]))
            yield tuple(full)
            # optional early pruning: skip if unreachable states used? skip.

def reach_rows(rows):
    """Return set of reachable states from 0."""
    reach = {0}
    stack = [0]
    while stack:
        i = stack.pop()
        for x in range(N_SY):
            v = rows[i][x]
            if v is not None and v not in reach:
                reach.add(v)
                stack.append(v)
    return reach

def minimal_rows(rows):
    """Restrict automaton to reachable states, renumbering."""
    reach = reach_rows(rows)
    if 0 not in reach:
        reach.add(0)
    new_idx = {s: i for i, s in enumerate(sorted(reach))}
    out = [None] * len(reach)
    for s in reach:
        out[new_idx[s]] = tuple((new_idx[rows[s][x]] if rows[s][x] is not None else None) for x in range(N_SY))
    return tuple(out)

def canonical_key(rows):
    return tab(rows)

# ---------------- closure computation ----------------

def compute_contexts(tm, left_rows, right_rows):
    """Compute the smallest closed context set; return list of contexts or None
    if it contains a halting context (then no certificate)."""
    table, n_states, n_syms = parse(tm)
    # context: (l, q, s, r)
    contexts = set()
    # start from (0,0,0,0)
    contexts.add((0, 0, 0, 0))
    changed = True
    while changed and len(contexts) < 200000:
        changed = False
        cur = list(contexts)
        for (l, q, s, r) in cur:
            tr = table.get((q, s))
            if tr is None:
                return None  # halting context -> cannot prove
            w, mv, q2 = tr
            if mv == 1:
                l2 = left_rows[l][w]
                if l2 is None:
                    return None
                # for every pair (r2, s2) with right_rows[r2][s2] == r
                for r2 in range(len(right_rows)):
                    for s2 in range(N_SY):
                        if right_rows[r2][s2] == r:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                contexts.add(ctx)
                                changed = True
            else:
                r2 = right_rows[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(left_rows)):
                    for s2 in range(N_SY):
                        if left_rows[l2][s2] == l:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                contexts.add(ctx)
                                changed = True
    if len(contexts) >= 200000:
        return None
    return contexts

def build_cert(tm, contexts):
    """Turn a context set into a certificate dict; prune automata to used states."""
    # find used left states and right states
    used_l = set()
    used_r = set()
    ctx_list = []
    for (l, q, s, r) in contexts:
        used_l.add(l)
        used_r.add(r)
        ctx_list.append([l, q, s, r])
    # We keep automata as given but ensure rows for unused states are None-filled
    # (kernel only requires states 0..n-1 exist; unused can be all-null rows).
    # Build left table: for each state i, row of length N_SY with values or None.
    # We don't have the original rows here; instead reconstruct by requiring
    # the certificate's automata to be *consistent* with the contexts. But the
    # kernel checks closure, not that automata are minimal. We need actual rows.
    # So we must pass the rows in. This function is a thin wrapper.
    # Instead, compute contexts with the rows and return cert directly.
    return None

# ---------------- main search ----------------

def decide(tm: str):
    # First try small automata enumeration for both halves simultaneously,
    # but that is huge. Instead: enumerate left automata; for each compute
    # closure with a *canonical* right automaton derived from left? No.
    # Strategy: enumerate left automata up to 3 states. For each left, we need
    # a right automaton. We enumerate right automata too but prune by the
    # closure: incremental search.
    # Simpler: enumerate pairs (left, right) with sizes 1..3, using the hint's
    # canonical minimal rows.
    seen = set()
    # cache parsed machine
    table, n_states, n_syms = parse(tm)

    def try_pair(lr, rr):
        # canonicalize
        lrm = minimal_rows(lr)
        rrm = minimal_rows(rr)
        key = (tab(lrm), tab(rrm))
        if key in seen:
            return None
        seen.add(key)
        # quick reject: if lrm[0][0] != 0 or rrm[0][0] != 0 -> kernel requires 0
        if lrm[0][0] != 0 or rrm[0][0] != 0:
            return None
        ctx = compute_contexts(tm, lrm, rrm)
        if ctx is None:
            return None
        cert = {"kind": "cps",
                "left": [list(row) for row in lrm],
                "right": [list(row) for row in rrm],
                "contexts": [list(c) for c in ctx]}
        return cert

    max_states = 3
    # enumerate left automata
    left_candidates = []
    for lr in enum_automata(max_states):
        left_candidates.append(minimal_rows(lr))
    # dedupe
    left_uniq = []
    lseen = set()
    for lr in left_candidates:
        k = tab(lr)
        if k not in lseen:
            lseen.add(k)
            left_uniq.append(lr)

    right_candidates = []
    for rr in enum_automata(max_states):
        right_candidates.append(minimal_rows(rr))
    right_uniq = []
    rseen = set()
    for rr in right_candidates:
        k = tab(rr)
        if k not in rseen:
            rseen.add(k)
            right_uniq.append(rr)

    # Try pairs; prioritize small sizes
    def size(a):
        return len(a)
    left_uniq.sort(key=size)
    right_uniq.sort(key=size)

    count = 0
    for lr in left_uniq:
        for rr in right_uniq:
            count += 1
            if count > 200000:
                return None
            c = try_pair(lr, rr)
            if c is not None:
                try:
                    check(tm, c)
                    return c
                except Reject:
                    continue
    return None
