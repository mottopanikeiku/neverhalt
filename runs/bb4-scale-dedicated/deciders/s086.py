from neverhalt.tm import parse

# ---------- helpers ------------------------------------------------------

def blank_table(hash_=None):
    return {}

def canonical_dfa(states, trans):
    # trans: dict (state,sym) -> state or None ; sym in {0,1}
    # BFS-canonical relabeling starting from 0
    parent = {}
    order = []
    seen = {0}
    queue = [0]
    while queue:
        s = queue.pop(0)
        order.append(s)
        for x in (0, 1):
            t = trans.get((s, x))
            if t is not None and t not in seen:
                seen.add(t)
                parent[t] = s
                queue.append(t)
    lab = {}
    for s in order:
        lab[s] = len(lab)
    out = {}
    for s in order:
        for x in (0, 1):
            t = trans.get((s, x))
            out[(lab[s], x)] = None if t is None else lab[t]
    return out

def dfa_from_rows(rows):
    # rows: list of [on0, on1] with None allowed
    trans = {}
    for i, row in enumerate(rows):
        for x in (0, 1):
            if row[x] is not None:
                trans[(i, x)] = row[x]
    return trans

def dfa_size(trans):
    seen = set()
    stack = [0]
    while stack:
        s = stack.pop()
        if s in seen:
            continue
        seen.add(s)
        for x in (0, 1):
            t = trans.get((s, x))
            if t is not None:
                stack.append(t)
    return len(seen)

# ---------- half-tape DFAs ------------------------------------------------

def enumerate_dfas(max_states, limit=4000):
    """Yield (trans, size) for all BFS-canonical DFAs with 1..max_states states."""
    seen = set()
    out = []
    # 1 state
    for t0 in (0, None):
        tr = dfa_from_rows([[t0, 0]])
        out.append(tr)
        seen.add((tuple(sorted(tr.items())),))
    # build incrementally: for n states, extend canonical DFAs of n-1
    frontier = list(out)
    for n in range(2, max_states + 1):
        new = []
        for base in frontier:
            # add state n-1, keep canonical: 0 loops on 0
            for a in (None, n - 1):
                for b in (None, n - 1):
                    tr = dict(base)
                    tr[(n - 1, 0)] = a
                    tr[(n - 1, 1)] = b
                    # canonical check via relabel
                    can = canonical_dfa(n, tr)
                    key = tuple(sorted(can.items()))
                    if key in seen:
                        continue
                    # require state 0 loops on 0 (all-blank half-tape)
                    if can.get((0, 0)) != 0:
                        continue
                    seen.add(key)
                    new.append(can)
        # dedupe by canonical key, keep first
        ded = []
        dseen = set()
        for tr in new:
            k = tuple(sorted(tr.items()))
            if k in dseen:
                continue
            dseen.add(k)
            ded.append(tr)
        out.extend(ded)
        frontier = ded
        if len(out) > limit:
            break
    return out

def rows_of(trans, n):
    rows = []
    for i in range(n):
        rows.append([trans.get((i, 0)), trans.get((i, 1))])
    return rows

# ---------- context closure ----------------------------------------------

def context_closure(left, right, table, n_states, max_ctx=200000):
    """left/right: dict (state,sym)->state|None. table: (state,sym)->(w,move,next).
    Returns (contexts, halted) where contexts is a set of (l,q,s,r)."""
    ctx = set()
    ctx.add((0, 0, 0, 0))
    if (0, 0) in table:
        w, move, q2 = table[(0, 0)]
        l2 = left.get((0, w))
        if l2 is None:
            return ctx, True
        # context (l2,q2,?,r) for every r with right[r][s2]==r
        # we add a placeholder list of (l2,q2) pairs with all r
        # handled in the loop below
    # worklist
    work = list(ctx)
    while work:
        l, q, s, r = work.pop()
        if (q, s) not in table:
            return ctx, True
        w, move, q2 = table[(q, s)]
        if move == 1:
            l2 = left.get((l, w))
            if l2 is None:
                return ctx, True
            # find all (r2,s2) with right[r2][s2] == r
            for (r2, s2), rr in right.items():
                if rr == r:
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        ctx.add(c)
                        work.append(c)
                        if len(ctx) > max_ctx:
                            return ctx, True
        else:
            r2 = right.get((r, w))
            if r2 is None:
                return ctx, True
            for (l2, s2), ll in left.items():
                if ll == l:
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        ctx.add(c)
                        work.append(c)
                        if len(ctx) > max_ctx:
                            return ctx, True
    return ctx, False

# ---------- decider -------------------------------------------------------

NAME = "dfa-search"

_DFAS = None

def _get_dfas():
    global _DFAS
    if _DFAS is None:
        _DFAS = enumerate_dfas(4, limit=3000)
    return _DFAS

def decide(tm):
    from neverhalt.tm import parse as _p
    from neverhalt.kernel import check
    table, n_states, n_symbols = _p(tm)
    dfas = _get_dfas()
    tried = 0
    for lt in dfas:
        for rt in dfas:
            # both must have state 0 looping on 0
            if lt.get((0, 0)) != 0 or rt.get((0, 0)) != 0:
                continue
            tried += 1
            ctx, halted = context_closure(lt, rt, table, n_states)
            if halted:
                continue
            # build certificate
            left_rows = []
            right_rows = []
            # max state index
            maxl = max([k[0] for k in lt.keys()]) if lt.keys() else 0
            maxr = max([k[0] for k in rt.keys()]) if rt.keys() else 0
            for i in range(maxl + 1):
                left_rows.append([lt.get((i, 0)), lt.get((i, 1))])
            for i in range(maxr + 1):
                right_rows.append([rt.get((i, 0)), rt.get((i, 1))])
            contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
            cert = {"kind": "cps",
                    "left": [list(x) for x in left_rows],
                    "right": [list(x) for x in right_rows],
                    "contexts": contexts}
            try:
                check(tm, cert)
                return cert
            except Exception:
                continue
    return None

# trim: keep only transitions used by closure (null elsewhere) is handled by
# the kernel accepting any table; we return the full small tables.