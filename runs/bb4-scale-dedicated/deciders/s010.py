import sys
from itertools import product

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _eps(r):
    return None


def _build_context_closure(left, right, n_states):
    # left[i][x], right[i][x]: int or None. State 0 all-blank.
    left = [list(row) for row in left]
    right = [list(row) for row in right]
    nq = n_states
    contexts = set()
    work = []
    contexts.add((0, 0, 0, 0))
    work.append((0, 0, 0, 0))
    while work:
        l, q, s, r = work.pop()
        # transition
        try:
            w, mv, q2 = left_table[q][s]
        except Exception:
            return None
        if q2 < 0:
            # halting transition: context is halting -> reject
            return None
        if mv == 1:
            # right move: l2 = left[l][w] must exist
            l2 = left[l][w]
            if l2 is None:
                return None
            # for every (r2, s2) with right[r2][s2] == r
            found = False
            for r2 in range(len(right)):
                for s2 in range(2):
                    if right[r2][s2] == r:
                        found = True
                        ctx = (l2, q2, s2, r2)
                        if ctx not in contexts:
                            contexts.add(ctx)
                            work.append(ctx)
            if not found:
                return None
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            found = False
            for l2 in range(len(left)):
                for s2 in range(2):
                    if left[l2][s2] == l:
                        found = True
                        ctx = (l2, q2, s2, r2)
                        if ctx not in contexts:
                            contexts.add(ctx)
                            work.append(ctx)
            if not found:
                return None
    return contexts


def _make_tables(tm):
    # machine states are ints A=0..nq-1
    parsed = parse(tm)
    table, n_states, n_symbols = parsed
    # build transition function as dict (q, s) -> (w, mv, q2) or None for halt
    trans = {}
    for q in range(n_states):
        for s in range(2):
            trans[(q, s)] = table.get((q, s))
    return trans, n_states


def _emit_cert(tm, left, right, contexts, nq):
    left_tab = [[None, None] for _ in range(len(left))]
    right_tab = [[None, None] for _ in range(len(right))]
    used = set()
    for (l, q, s, r) in contexts:
        used.add(l)
        used.add(r)
    # keep only states reachable in the closure from state 0
    for i, row in enumerate(left):
        for x in range(2):
            v = row[x]
            if v is not None and v in used:
                left_tab[i][x] = v
    for i, row in enumerate(right):
        for x in range(2):
            v = row[x]
            if v is not None and v in used:
                right_tab[i][x] = v
    # contexts in kernel format: [l, q, s, r]
    ctx_list = [[l, q, s, r] for (l, q, s, r) in contexts]
    cert = {
        "kind": "cps",
        "left": left_tab,
        "right": right_tab,
        "contexts": ctx_list,
    }
    return cert


def decide(tm):
    # parse the machine once
    parsed = parse(tm)
    table, n_states, n_symbols = parsed
    # build transition table with q2 = -1 for halting
    trans = {}
    for (q, s), v in table.items():
        w, mv, q2 = v
        trans[(q, s)] = (w, mv, q2)

    # enumerate automata: 1, 2, 3 states per side
    # state 0 loops on symbol 0 (all-blank half-tape)
    def gen_automata(max_states):
        # each state: row [f(0), f(1)] with values in range(max_states) or None
        # state 0 must map 0 -> 0
        vals = list(range(max_states)) + [None]
        for nstates in range(1, max_states + 1):
            # canonical BFS order: enumerate all tables, dedupe by tuple
            seen = set()
            for tup in product(vals, repeat=2 * nstates):
                rows = [list(tup[2 * i:2 * i + 2]) for i in range(nstates)]
                if rows[0][0] != 0:
                    continue
                key = tuple(tuple(r) for r in rows)
                if key in seen:
                    continue
                seen.add(key)
                yield rows

    # try small automata
    for nq_target in (1, 2, 3):
        lefts = list(gen_automata(nq_target))
        for left in lefts:
            for right in lefts:
                # closure
                try:
                    ctx = _build_context_closure(left, right, n_states)
                except Exception:
                    ctx = None
                if ctx is None:
                    continue
                # if closure exists and no halting context (closure builder already rejects halting),
                # emit and let kernel verify
                cert = _emit_cert(tm, left, right, ctx, n_states)
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
                except Exception:
                    continue
    return None


if __name__ == "__main__":
    NAME = "small-cps-search"