import json
from neverhalt.tm import parse, run
from neverhalt.kernel import Reject

# ---- machine helpers -------------------------------------------------------

def _table(tm):
    t, ns, nsym = parse(tm)
    return t, ns, nsym

def _step(t, ns, nsym, q, s):
    """Return (w, move, q2) or None if halting."""
    tr = t.get((q, s))
    if tr is None:
        return None
    return tr

def _halt_states(t, ns, nsym):
    """States q such that (q, s) is undefined for some s that can be read.
    We treat all undefined transitions as halting."""
    hs = set()
    for q in range(ns):
        for s in range(nsym):
            if (q, s) not in t:
                hs.add(q)
    return hs

# ---- DFA enumeration -------------------------------------------------------

def _enumerate_dfa_states(n_states, nsym):
    """Yield transition tables as tuples of rows; row i is a tuple of length nsym
    with -1 for 'undefined' (trap)."""
    rows = []
    # enumerate all functions [n_states x nsym] -> [0, n_states-1] or -1
    # too many: 1+.. use itertools.product over choices per cell
    import itertools
    choices = list(range(n_states)) + [-1]
    for combo in itertools.product(choices, repeat=n_states * nsym):
        rows.append(combo)
    return rows

def _build_dfa(combo, n_states, nsym):
    """combo -> table list of rows. Row i is list of targets."""
    return [list(combo[i * nsym:(i + 1) * nsym]) for i in range(n_states)]

def _dfa_step(tbl, state, sym):
    if tbl is None:
        return None
    v = tbl[state][sym]
    return None if v < 0 else v

# ---- context closure -------------------------------------------------------

def _closure_contexts(t, ns, nsym, left, right, max_ctx=200000):
    """left/right: tables (list of rows) or None. Compute smallest closed set of
    contexts [l, q, s, r] containing [0,0,0,0], or None if a halting context is
    forced."""
    if left is None or right is None:
        return None
    ctx = set()
    ctx.add((0, 0, 0, 0))
    stack = [(0, 0, 0, 0)]
    while stack:
        (l, q, s, r) = stack.pop()
        tr = _step(t, ns, nsym, q, s)
        if tr is None:
            # halting context: reject
            return None
        w, move, q2 = tr
        if move > 0:
            # right move: l2 = left[l][w]; r2 ranges over pairs with right[r2][s2]==r
            l2 = _dfa_step(left, l, w)
            if l2 is None:
                return None
            # find all (r2, s2) with right[r2][s2] == r
            pairs = []
            for r2 in range(len(right)):
                row = right[r2]
                for s2 in range(nsym):
                    if row[s2] == r:
                        pairs.append((r2, s2))
            for (r2, s2) in pairs:
                c = (l2, q2, s2, r2)
                if c not in ctx:
                    if len(ctx) >= max_ctx:
                        return None
                    ctx.add(c)
                    stack.append(c)
        else:
            r2 = _dfa_step(right, r, w)
            if r2 is None:
                return None
            pairs = []
            for l2 in range(len(left)):
                row = left[l2]
                for s2 in range(nsym):
                    if row[s2] == l:
                        pairs.append((l2, s2))
            for (l2, s2) in pairs:
                c = (l2, q2, s2, r2)
                if c not in ctx:
                    if len(ctx) >= max_ctx:
                        return None
                    ctx.add(c)
                    stack.append(c)
    return ctx

def _cert_from_ctx(ctx):
    left_tbl = {}
    right_tbl = {}
    # infer automata from contexts: for each context, the transition used.
    # We need the actual automata; reconstruct from the context set by tracking
    # transitions. Simpler: return contexts and let decide() rebuild tables from
    # the search bookkeeping.
    return ctx

# ---- certificate emission --------------------------------------------------

def _emit_cps(ctx, left, right, nsym):
    left_out = []
    right_out = []
    for tbl, out in ((left, left_out), (right, right_out)):
        if tbl is None:
            return None
        for row in tbl:
            out.append([(-1 if v < 0 else v) for v in row])
    # convert -1 to None
    def conv(rows):
        return [[(None if v < 0 else v) for v in row] for row in rows]
    contexts = []
    for (l, q, s, r) in ctx:
        contexts.append([l, q, s, r])
    return {
        "kind": "cps",
        "left": conv(left_out),
        "right": conv(right_out),
        "contexts": contexts,
    }

# ---- decider ---------------------------------------------------------------

NAME = "dfa-search-small"

def decide(tm):
    try:
        t, ns, nsym = _table(tm)
    except Exception:
        return None
    if nsym != 2:
        return None
    # halting states: any state with an undefined transition is a potential halt.
    # We only need automata that never force a halting context.
    # Enumerate small DFAs on each side, state 0 must loop on symbol 0 (blank).
    # For each pair, try closure.
    max_states = 3
    for nleft in range(1, max_states + 1):
        for nright in range(1, max_states + 1):
            # enumerate left DFAs
            for lc in _enumerate_dfa_states(nleft, nsym):
                lt = _build_dfa(lc, nleft, nsym)
                if lt[0][0] != 0:
                    continue
                for rc in _enumerate_dfa_states(nright, nsym):
                    rt = _build_dfa(rc, nright, nsym)
                    if rt[0][0] != 0:
                        continue
                    ctx = _closure_contexts(t, ns, nsym, lt, rt)
                    if ctx is not None:
                        cert = _emit_cps(ctx, lt, rt, nsym)
                        if cert is not None:
                            return cert
    return None
