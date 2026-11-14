import json
import re
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _table(tm):
    t, ns, sy = parse(tm)
    return t, ns, sy


def _contexts_closure(left, right, ns, sy, tm_table):
    """Build the closed context set for automata left/right.

    Context = (l, q, s, r). Start from (0,0,0,0) and close under the kernel rule.
    Returns (contexts, halting_context_found).
    """
    # Precompute for each automaton state the successor symbol/state pairs.
    # For a right move: new l2 = left[l][w]; need contexts [l2,q2,s2,r2] for every
    # (r2,s2) with right[r2][s2] == r.
    # For a left move: new r2 = right[r][w]; need contexts [l2,q2,s2,r2] for every
    # (l2,s2) with left[l2][s2] == l.
    # We build reverse indices: for each automaton state X, list of (pre_state, symbol)
    # such that step(pre_state, symbol) == X.

    def rev_index(aut):
        n = len(aut)
        rev = [[] for _ in range(n)]
        for i in range(n):
            if i >= len(aut):
                continue
            row = aut[i]
            for x in range(len(row)):
                j = row[x]
                if j is not None:
                    rev[j].append((i, x))
        return rev

    rev_left = rev_index(left)
    rev_right = rev_index(right)

    ctx = set()
    todo = [(0, 0, 0, 0)]
    ctx.add((0, 0, 0, 0))
    halting = False
    while todo:
        (l, q, s, r) = todo.pop()
        if q >= len(tm_table) or s >= 2:
            halting = True
            continue
        tr = tm_table.get((q, s))
        if tr is None:
            # halting transition
            halting = True
            continue
        w, mv, q2 = tr
        if mv == 1:
            # right move: l2 = left[l][w]
            if l >= len(left) or w >= len(left[l]):
                halting = True
                continue
            l2 = left[l][w]
            if l2 is None:
                halting = True
                continue
            # need contexts [l2, q2, s2, r2] for every (r2, s2) with right[r2][s2] == r
            for (r2, s2) in rev_right[r]:
                st = (l2, q2, s2, r2)
                if st not in ctx:
                    ctx.add(st)
                    todo.append(st)
        else:
            # left move: r2 = right[r][w]
            if r >= len(right) or w >= len(right[r]):
                halting = True
                continue
            r2 = right[r][w]
            if r2 is None:
                halting = True
                continue
            for (l2, s2) in rev_left[l]:
                st = (l2, q2, s2, r2)
                if st not in ctx:
                    ctx.add(st)
                    todo.append(st)
    return ctx, halting


def _make_cps(tm, left, right):
    ctx, halting = _contexts_closure(left, right, None, None, _table(tm)[0])
    if halting:
        return None
    left_tbl = [[x for x in row] for row in left]
    right_tbl = [[x for x in row] for row in right]
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    return {
        "kind": "cps",
        "left": left_tbl,
        "right": right_tbl,
        "contexts": contexts,
    }


def _enum_automata(max_states, symbols=2):
    """Enumerate deterministic automata with up to max_states states.

    State 0 loops on symbol 0. Each state has a transition for each symbol,
    either to an existing state or null (dead). We enumerate tables.
    To keep the count manageable, we enumerate all functions from
    states x symbols to {0..max_states-1, None} with state 0 on symbol 0 = 0,
    then canonicalize by BFS from state 0.
    """
    out = []
    for n in range(1, max_states + 1):
        # enumerate assignments for states 1..n-1 and symbol 1, plus state 0 symbol 1
        # This is (n+1)^(2n) possibilities for n states: too many for n>=3 in general.
        # For n<=3 it is fine: n=3 -> 4^6=4096.
        if n > 3:
            continue
        targets = list(range(n)) + [None]
        # state 0: symbol 0 -> 0, symbol 1 -> targets[0]
        # we enumerate all rows
        import itertools
        rows = []
        # We'll enumerate row by row via product over (state, symbol) but fix row 0 sym 0 = 0.
        cells = []
        for st in range(n):
            for sym in range(2):
                if st == 0 and sym == 0:
                    continue
                cells.append((st, sym))
        for combo in itertools.product(targets, repeat=len(cells)):
            tbl = [[None, None] for _ in range(n)]
            tbl[0][0] = 0
            it = iter(combo)
            for (st, sym) in cells:
                tbl[st][sym] = next(it)
            out.append(tbl)
    return out


def _canon(aut):
    """BFS-canonical form of a DFA from state 0 (with None as dead)."""
    n = len(aut)
    names = {}
    names[0] = 0
    order = [0]
    i = 0
    while i < len(order):
        st = order[i]
        i += 1
        for sym in range(2):
            j = aut[st][sym]
            if j is None:
                continue
            if j not in names:
                names[j] = len(names)
                order.append(j)
    # build canonical table restricted to reachable states
    reach = [names[s] for s in order]
    canon = [[None, None] for _ in range(len(order))]
    for new_i, old_i in enumerate(order):
        for sym in range(2):
            j = aut[old_i][sym]
            if j is None:
                canon[new_i][sym] = None
            else:
                canon[new_i][sym] = names[j]
    return canon


def _minimal(canon):
    """Remove unreachable and merge equivalent states (Moore)."""
    n = len(canon)
    # remove unreachable
    reach = [False] * n
    reach[0] = True
    stack = [0]
    while stack:
        st = stack.pop()
        for sym in range(2):
            j = canon[st][sym]
            if j is not None and not reach[j]:
                reach[j] = True
                stack.append(j)
    # Moore minimization
    part = [0 if reach[i] else -1 for i in range(n)]
    while True:
        sig = {}
        newpart = [0] * n
        nxt = 0
        for i in range(n):
            if part[i] == -1:
                newpart[i] = -1
                continue
            key = (part[i], part[canon[i][0]] if canon[i][0] is not None else -2,
                   part[canon[i][1]] if canon[i][1] is not None else -2)
            if key not in sig:
                sig[key] = nxt
                nxt += 1
            newpart[i] = sig[key]
        if newpart == part:
            break
        part = newpart
    # keep only reachable, renumber
    keep = [i for i in range(n) if part[i] != -1]
    m = len(keep)
    remap = {}
    for new_i, old_i in enumerate(keep):
        remap[old_i] = new_i
    out = [[None, None] for _ in range(m)]
    for new_i, old_i in enumerate(keep):
        for sym in range(2):
            j = canon[old_i][sym]
            if j is None:
                out[new_i][sym] = None
            else:
                out[new_i][sym] = remap[j]
    return out


def _all_halting_targets(table, ns, sy):
    """For each state, the set of symbols on which it halts."""
    res = []
    for q in range(ns):
        row = []
        for s in range(sy):
            row.append((q, s) not in table)
        res.append(row)
    return res


def _closure_ctx(left, right, table, ns, sy):
    return _contexts_closure(left, right, ns, sy, table)


def _try_pair(tm, left, right):
    table, ns, sy = _table(tm)
    ctx, halting = _contexts_closure(left, right, ns, sy, table)
    if halting:
        return None
    return {
        "kind": "cps",
        "left": [list(r) for r in left],
        "right": [list(r) for r in right],
        "contexts": [[l, q, s, r] for (l, q, s, r) in ctx],
    }


def decide(tm: str):
    table, ns, sy = _table(tm)
    # Quick check: if the machine halts, bail.
    halted, steps, st, pos, tape = run(tm, 100)
    if halted:
        return None
    # Enumerate automata up to 3 states on each side.
    autos = []
    for n in (1, 2, 3):
        import itertools
        targets = list(range(n)) + [None]
        cells = []
        for stt in range(n):
            for sym in range(2):
                if stt == 0 and sym == 0:
                    continue
                cells.append((stt, sym))
        for combo in itertools.product(targets, repeat=len(cells)):
            tbl = [[None, None] for _ in range(n)]
            tbl[0][0] = 0
            it = iter(combo)
            for (stt, sym) in cells:
                tbl[stt][sym] = next(it)
            autos.append(tbl)
    # Deduplicate by canonical form
    seen = set()
    uniq = []
    for a in autos:
        c = _minimal(_canon(a))
        key = json.dumps(c)
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    autos = uniq
    # Try pairs, smallest first
    autos_sorted = sorted(autos, key=lambda a: (len(a), json.dumps(a)))
    for li, left in enumerate(autos_sorted):
        for right in autos_sorted:
            # Symmetry: only one ordering needed? No, left/right roles differ.
            cert = _try_pair(tm, left, right)
            if cert is not None:
                try:
                    check(tm, cert)
                except Reject:
                    continue
                return cert
    return None