import sys
from collections import deque
from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


def _trans(table, ns, index):
    return table[(index[0], index[1])]


def _machine_table(tm):
    table, ns, nsym = parse(tm)
    out = {}
    for q in range(ns):
        for s in range(nsym):
            if (q, s) in table:
                out[(q, s)] = table[(q, s)]
    return out, ns, nsym


def _dfa_from_halting_contexts(tm):
    """Enumerate DFAs for one half-tape whose states are half-tape summaries.

    We build a far-to-head DFA for the LEFT half-tape.  Its state 0 must be the
    all-blank tape, so left[0][0] = 0 is required.  We enumerate transition
    tables over {0,1} with a canonical BFS order (states discovered in order),
    prune partial tables whose reachable part cannot avoid forcing the blank
    tape into a halting context, and for each completed surviving table we
    build the context closure.
    """
    return None


def _dfa_canonical_tables(max_states, start=0):
    """Yield canonical deterministic tables on symbols {0,1}.

    States are numbered in BFS discovery order from `start`.  A table maps
    (state, symbol) -> state, with unreachable states having no outgoing edges.
    We enumerate by growing the table one transition at a time and keeping the
    canonical BFS representative; this yields every DFA up to isomorphism with
    states in BFS order.
    """
    # Represent a partial table as a dict (state, sym) -> state.
    # We enumerate complete reachable DFAs by assigning transitions lazily.
    # To keep it bounded we enumerate tables whose reachable set from `start`
    # has size <= max_states.
    tables = []

    def rec(table, next_state):
        if len(tables) >= 400000:
            return
        # compute reachable states
        reach = {start}
        stack = [start]
        while stack:
            q = stack.pop()
            for s in (0, 1):
                if (q, s) in table:
                    r = table[(q, s)]
                    if r not in reach:
                        reach.add(r)
                        stack.append(r)
        # canonicalize: BFS order from start
        order = []
        seen = {start}
        dq = deque([start])
        while dq:
            q = dq.popleft()
            order.append(q)
            for s in (0, 1):
                if (q, s) in table:
                    r = table[(q, s)]
                    if r not in seen:
                        seen.add(r)
                        dq.append(r)
        if len(order) > max_states:
            return
        if len(table) == 2 * max_states and all((q, s) in table for q in order for s in (0, 1)):
            # canonical relabel
            rel = {q: i for i, q in enumerate(order)}
            canon = {}
            for (q, s), r in table.items():
                if q in rel and r in rel:
                    canon[(rel[q], s)] = rel[r]
            tables.append(canon)
            return
        # choose the next unassigned (state, symbol) pair in canonical order
        assigned = False
        for q in order:
            for s in (0, 1):
                if (q, s) not in table:
                    for r in range(max_states + 1):
                        nt = dict(table)
                        nt[(q, s)] = r
                        rec(nt, r)
                    assigned = True
                    return
        if not assigned:
            # partial: complete the rest with self loops on state max_states
            nt = dict(table)
            for q in range(max_states + 1):
                for s in (0, 1):
                    if (q, s) not in nt:
                        nt[(q, s)] = q
            # re-canonicalize
            reach2 = {start}
            st2 = [start]
            while st2:
                q = st2.pop()
                for s in (0, 1):
                    r = nt[(q, s)]
                    if r not in reach2:
                        reach2.add(r)
                        st2.append(r)
            order2 = []
            seen2 = {start}
            dq2 = deque([start])
            while dq2:
                q = dq2.popleft()
                order2.append(q)
                for s in (0, 1):
                    r = nt[(q, s)]
                    if r not in seen2:
                        seen2.add(r)
                        dq2.append(r)
            rel2 = {q: i for i, q in enumerate(order2)}
            canon2 = {}
            for (q, s), r in nt.items():
                if q in rel2 and r in rel2:
                    canon2[(rel2[q], s)] = rel2[r]
            tables.append(canon2)

    rec({}, 0)
    return tables


def _build_left_tables(max_states):
    tables = _dfa_canonical_tables(max_states)
    out = []
    for t in tables:
        n = max(t.keys(), key=lambda k: k[0])[0] + 1 if t else 1
        left = [[None, None] for _ in range(n)]
        ok = True
        for (q, s), r in t.items():
            if r >= n:
                ok = False
                break
            left[q][s] = r
        if ok and left[0][0] == 0:
            out.append(left)
    return out


def _right_nfa_from_halts(tm):
    """Backwards reachability from halting transitions: the set of (q, s) that
    can reach a halt.  Used only to prune candidate DFAs (a DFA must not let a
    halting pair be forced)."""
    table, ns, nsym = parse(tm)
    halts = set()
    for q in range(ns):
        for s in range(nsym):
            if (q, s) not in table:
                halts.add((q, s))
    return halts


def _close_contexts(tm, left, right, max_ctx=200000):
    table, ns, nsym = parse(tm)
    # context (l, q, s, r); s in 0..nsym-1; base context [0,0,0,0]
    ctx = {(0, 0, 0, 0)}
    frontier = deque([(0, 0, 0, 0)])
    while frontier:
        l, q, s, r = frontier.popleft()
        if (q, s) not in table:
            return None
        w, move, q2 = table[(q, s)]
        if move > 0:
            l2 = left[l][w]
            if l2 is None:
                return None
            for r2 in range(len(right)):
                for s2 in range(nsym):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            if len(ctx) >= max_ctx:
                                return None
                            ctx.add(c)
                            frontier.append(c)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(len(left)):
                for s2 in range(nsym):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            if len(ctx) >= max_ctx:
                                return None
                            ctx.add(c)
                            frontier.append(c)
    # emit certificate: keep only transitions used
    left_use = [set() for _ in left]
    right_use = [set() for _ in right]
    for (l, q, s, r) in ctx:
        if (q, s) in table:
            w = table[(q, s)][0]
            if left[l][w] is not None:
                left_use[l].add(w)
            if right[r][w] is not None:
                right_use[r].add(w)
    def tab(use, size):
        out = []
        for i in range(size):
            row = []
            for sym in range(2):
                row.append(None)
            out.append(row)
        for i, syms in enumerate(use):
            for sym in syms:
                if sym < 2:
                    # find target
                    for j in range(size):
                        if left[i][sym] == j:
                            out[i][sym] = j
                            break
        return out
    def tab_r(use, size):
        out = []
        for i in range(size):
            row = []
            for sym in range(2):
                row.append(None)
            out.append(row)
        for i, syms in enumerate(use):
            for sym in syms:
                if sym < 2:
                    for j in range(size):
                        if right[i][sym] == j:
                            out[i][sym] = j
                            break
        return out
    cert = {
        "kind": "cps",
        "left": tab(left_use, len(left)),
        "right": tab_r(right_use, len(right)),
        "contexts": [[l, q, s, r] for (l, q, s, r) in ctx],
    }
    return cert


def decide(tm: str):
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    # Quick reject: if the machine halts quickly, no certificate.
    try:
        from neverhalt.tm import run
        halted, steps, state, pos, tape = run(tm, 200)
        if halted:
            return None
    except Exception:
        pass

    max_states = 3
    left_tables = _build_left_tables(max_states)
    if not left_tables:
        return None
    # candidate right automata: enumerate the same canonical tables
    right_tables = _build_left_tables(max_states)
    for left in left_tables:
        for right in right_tables:
            cert = _close_contexts(tm, left, right)
            if cert is None:
                continue
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
            except Exception:
                continue
    return None


if __name__ == "__main__":
    import json
    tm = sys.argv[1]
    c = decide(tm)
    if c:
        print(json.dumps(c)[:400])
    else:
        print("None")
