NAME = "dfa_search"

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

import itertools


def _build_trans_table(tm):
    table, ns, nsym = parse(tm)
    return table, ns, nsym


def _run_and_get(tm, max_steps):
    halted, steps, state, pos, tape = run(tm, max_steps)
    return halted, steps, state, pos, tape


def _make_rule_map(tm):
    table, ns, nsym = parse(tm)
    syms = sorted(set([s for (_q, s) in table.keys()]))
    return table, ns, nsym, syms


def _step_state_pos(tm, state, pos, tape):
    table, ns, nsym = parse(tm)
    sym = tape.get(pos, 0)
    if (state, sym) not in table:
        return None
    w, mv, nxt = table[(state, sym)]
    return (nxt, pos + mv, w)


def decide(tm: str):
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None

    # Try small n-gram automata first (fast path).
    for n in (1, 2, 3):
        cert = _try_ngram(tm, n)
        if cert is not None:
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
    return None


def _try_ngram(tm, n):
    table, ns, nsym = parse(tm)
    syms = sorted(set([s for (_q, s) in table.keys()]))

    # Build n-gram automaton states: tuples of last n symbols, read far->near.
    # State 0 = all blank half-tape.
    states = [tuple([0] * n)]
    index = {states[0]: 0}
    # Precompute transitions lazily.
    def automaton_step(sidx, x):
        pat = states[sidx]
        newpat = (pat + (x,))[-n:]
        if newpat not in index:
            index[newpat] = len(states)
            states.append(newpat)
        return index[newpat]

    def left_step(l, w):
        return automaton_step(l, w)

    def right_step(r, w):
        return automaton_step(r, w)

    # Contexts: (l, q, s, r). Start with (0, 0, 0, 0).
    start = (0, 0, 0, 0)
    contexts = {start}
    frontier = [start]
    while frontier:
        ctx = frontier.pop()
        l, q, s, r = ctx
        if (q, s) not in table:
            return None
        w, mv, q2 = table[(q, s)]
        if mv > 0:
            l2 = left_step(l, w)
            # For every (r2, s2) with right[r2][s2] == r
            for r2 in range(len(states)):
                for s2 in syms:
                    if right_step(r2, s2) == r:
                        nctx = (l2, q2, s2, r2)
                        if nctx not in contexts:
                            contexts.add(nctx)
                            frontier.append(nctx)
        else:
            r2 = right_step(r, w)
            for l2 in range(len(states)):
                for s2 in syms:
                    if left_step(l2, s2) == l:
                        nctx = (l2, q2, s2, r2)
                        if nctx not in contexts:
                            contexts.add(nctx)
                            frontier.append(nctx)

    if len(contexts) > 200000:
        return None
    if len(states) > 5000:
        return None

    left_tab = []
    right_tab = []
    for i in range(len(states)):
        row = []
        for x in syms:
            row.append(automaton_step(i, x))
        left_tab.append(row)
        right_tab.append(row)

    ctx_list = [[c[0], c[1], c[2], c[3]] for c in contexts]
    cert = {"kind": "cps", "left": left_tab, "right": right_tab, "contexts": ctx_list}
    return cert


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        tm = sys.argv[1]
        c = decide(tm)
        print(c if c is None else "cert")