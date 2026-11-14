from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def _table_of(tm):
    t, ns, nsm = parse(tm)
    return t, ns, nsm

def _contexts_for_pair(t, ns, nsm, L, R):
    # L: list of rows (left automaton), R: list of rows (right automaton)
    # Each row i is a list over symbols 0..1; entry None means unhandled.
    # states are ints 0..len(L)-1 and 0..len(R)-1
    Ls = len(L)
    Rs = len(R)
    # context: (l, q, s, r)
    start = (0, 0, 0, 0)
    seen = set()
    stack = [start]
    seen.add(start)
    contexts = []
    while stack:
        (l, q, s, r) = stack.pop()
        contexts.append((l, q, s, r))
        # transition of machine on (q, s); if halting -> reject
        key = (q, s)
        if key not in t:
            return None  # halting context
        (w, mv, q2) = t[key]
        if mv == 1:
            # push w on left: l2 = L[l][w]
            if l >= Ls or w >= 2 or L[l][w] is None:
                return None
            l2 = L[l][w]
            # pop from right: any (r2, s2) with R[r2][s2] == r
            for r2 in range(Rs):
                for s2 in range(2):
                    if r2 < Rs and s2 < 2 and R[r2][s2] == r:
                        nxt = (l2, q2, s2, r2)
                        if nxt not in seen:
                            seen.add(nxt)
                            stack.append(nxt)
        else:
            # mirror: pop from left, push on right
            if r >= Rs or w >= 2 or R[r][w] is None:
                return None
            r2 = R[r][w]
            for l2 in range(Ls):
                for s2 in range(2):
                    if l2 < Ls and s2 < 2 and L[l2][s2] == l:
                        nxt = (l2, q2, s2, r2)
                        if nxt not in seen:
                            seen.add(nxt)
                            stack.append(nxt)
    return contexts

def _emit_cps(t, ns, nsm, L, R, contexts):
    left = [list(row) for row in L]
    right = [list(row) for row in R]
    # replace None with null (kernel expects None -> Python null in JSON)
    left = [[(None if x is None else int(x)) for x in row] for row in left]
    right = [[(None if x is None else int(x)) for x in row] for row in right]
    return {"kind": "cps", "left": left, "right": right, "contexts": [[int(a), int(b), int(c), int(d)] for (a, b, c, d) in contexts]}

def _rows_to_idx(rows):
    # canonicalize rows for dedup
    return tuple(tuple(r) for r in rows)

def _enumerate_dfa_states(nstates, max_rows=12):
    # enumerate BFS-canonical deterministic automata with nstates states, 2 symbols,
    # state 0 loops on symbol 0 (blank tape state).
    # Each row: [a, b] where a in {0..nstates-1} or None, b likewise.
    # BFS by number of distinct rows used.
    # To keep the search small we enumerate row multisets then assign canonical ids.
    import itertools
    # possible row values: a in 0..nstates-1 or None, b in 0..nstates-1 or None
    vals = [v for v in range(nstates)] + [None]
    allrows = []
    for a in vals:
        for b in vals:
            if a is None and b is None:
                continue
            allrows.append((a, b))
    # state 0 must be 0 on symbol 0
    # enumerate assignments of rows to states 0..nstates-1 with row0[0]==0
    results = []
    n = nstates
    # choose row for state 0 first
    # BFS over partial assignments: index -> row index or None
    # simpler: enumerate all mappings of states to rows, canonicalize by BFS from state 0
    # Do a bounded enumeration via recursive assignment with canonicalization.
    best = []
    for combo in itertools.product(allrows, repeat=n):
        rows = list(combo)
        if rows[0][0] != 0:
            continue
        # BFS-canonical check: build reachable states, canonical ids
        # map state 0 -> 0; follow transitions
        canon = {}
        order = []
        dq = [0]
        canon[0] = 0
        while dq:
            st = dq.pop(0)
            order.append(st)
            row = rows[st]
            for sym in (0, 1):
                nxt = row[sym]
                if nxt is not None and nxt not in canon:
                    canon[nxt] = len(canon)
                    dq.append(nxt)
        if len(canon) < n:
            continue
        # canonical rows
        newrows = [None] * n
        for st in range(n):
            newrows[canon[st]] = rows[st]
        # check canonical: state 0 has smallest id and BFS order is by id
        ok = True
        for st in range(n):
            if canon[st] != st:
                ok = False
                break
        if not ok:
            continue
        results.append(tuple(tuple(r) for r in newrows))
        if len(results) >= max_rows:
            # keep only canonical representatives to avoid duplicates
            results = list(set(results))
            break
    # dedup
    seen = set()
    out = []
    for r in results:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out

def _make_rows(rows):
    return [list(r) for r in rows]

def decide(tm):
    try:
        t, ns, nsm = _table_of(tm)
    except Exception:
        return None
    # quick simulation to see if it halts; deciders should not waste time on halting machines
    try:
        halted, steps, state, pos, tape = run(tm, 10000)
        if halted:
            return None
    except Exception:
        pass
    # enumerate DFAs for left and right sides, 1..3 states first
    total_tried = 0
    for nL in (1, 2, 3):
        for nR in (1, 2, 3):
            Llist = _enumerate_dfa_states(nL, 4000)
            Rlist = _enumerate_dfa_states(nR, 4000)
            for L in Llist:
                Lr = _make_rows(L)
                for R in Rlist:
                    Rr = _make_rows(R)
                    total_tried += 1
                    ctx = _contexts_for_pair(t, ns, nsm, Lr, Rr)
                    if ctx is not None:
                        try:
                            cert = _emit_cps(t, ns, nsm, Lr, Rr, ctx)
                            check(tm, cert)
                            return cert
                        except Reject:
                            pass
                        except Exception:
                            pass
    return None
