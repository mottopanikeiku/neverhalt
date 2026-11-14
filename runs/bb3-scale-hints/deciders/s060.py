import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

HALT = object()  # placeholder, never used


def _cells_of_tunnel(tm, steps=400):
    """Return (see_l, see_r) closure patterns around the head for a run.

    We simulate and, at each step, record the symbol under the head and the
    head direction.  For tunnel machines we only need the *tail* information
    that is consumed while the head is away from cell 0.
    """
    table, ns, nsym = parse(tm)
    _, _, state, pos, tape = run(tm, steps)
    return state, pos, tape


def _build_ngram_cps(tm, n=4, max_steps=250):
    """Try n-gram CPS certificates with n up to 4.

    Automata remember the last n cells of each half-tape.  states of each
    automaton are the n-grams (with a leading blank), so at most 2^n states.
    """
    table, ns, nsym = parse(tm)
    if ns > 3:
        return None

    # n-gram automaton: state is a tuple of the last n cells read from far
    # away towards the head, i.e. the *closest* cell is last.  Transition
    # state -> (cell) appends the cell.
    def ngram_auto(n):
        allstates = []
        for mask in range(1 << n):
            tup = tuple((mask >> k) & 1 for k in range(n))  # far->near
            allstates.append(tup)
        auto = {}
        for tup in allstates:
            for c in (0, 1):
                # drop the farthest, append c as the new nearest
                nt = (tup[1:], c)
                auto[(tup, c)] = nt
        return allstates, auto

    Lstates, L = ngram_auto(n)
    Rstates, R = ngram_auto(n)

    # Base state is the all-blank half-tape.
    blankL = tuple([0] * n)
    blankR = tuple([0] * n)

    # Contexts [l, q, s, r]
    contexts = set()
    contexts.add((blankL, 0, 0, blankR))

    # Fixpoint
    for _ in range(200000):
        new = set(contexts)
        for (l, q, s, r) in contexts:
            if q >= ns or s >= nsym:
                continue
            tr = table.get((q, s))
            if tr is None:
                continue
            w, move, q2 = tr
            if move == +1:
                l2 = L.get((l, w))
                if l2 is None:
                    continue
                # pop the nearest right cell s2 -> r2 with R[(r2, s2)] == r
                for s2 in (0, 1):
                    for r2 in Rstates:
                        if R.get((r2, s2)) == r:
                            new.add((l2, q2, s2, r2))
            else:
                r2 = R.get((r, w))
                if r2 is None:
                    continue
                for s2 in (0, 1):
                    for l2 in Lstates:
                        if L.get((l2, s2)) == l:
                            new.add((l2, q2, s2, r2))
        if len(new) == len(contexts):
            contexts = new
            break
        contexts = new
        if len(contexts) > 200000:
            return None

    # Check for halting contexts
    for (l, q, s, r) in contexts:
        if q >= ns or s >= nsym:
            return None
        if table.get((q, s)) is None:
            return None

    # Emit certificate; also trim automata to used states/transitions.
    used_L = set()
    used_R = set()
    for (l, q, s, r) in contexts:
        used_L.add(l)
        used_R.add(r)
    # find all transitions used
    Lmap = {}
    Rmap = {}
    for (l, q, s, r) in contexts:
        tr = table.get((q, s))
        w, move, q2 = tr
        if move == +1:
            l2 = L.get((l, w))
            Lmap[(l, w)] = l2
        else:
            r2 = R.get((r, w))
            Rmap[(r, w)] = r2
    # build full maps over used states
    Lfull = {}
    for l in used_L:
        Lfull[l] = []
        for c in (0, 1):
            if (l, c) in Lmap:
                Lfull[l].append(Lmap[(l, c)])
            else:
                Lfull[l].append(None)
    Rfull = {}
    for r in used_R:
        Rfull[r] = []
        for c in (0, 1):
            if (r, c) in Rmap:
                Rfull[r].append(Rmap[(r, c)])
            else:
                Rfull[r].append(None)

    # Remap states to 0..k-1 with blank state equal to index 0
    def remap(states, blank):
        order = [blank] + [s for s in states if s != blank]
        idx = {s: i for i, s in enumerate(order)}
        return order, idx

    Lorder, Lidx = remap(used_L, blankL)
    Rorder, Ridx = remap(used_R, blankR)
    assert Lidx[blankL] == 0 and Ridx[blankR] == 0

    Lout = []
    for l in Lorder:
        row = []
        for c in (0, 1):
            v = Lfull.get(l, [None, None])[c]
            row.append(Lidx[v] if v is not None else None)
        Lout.append(row)
    Rout = []
    for r in Rorder:
        row = []
        for c in (0, 1):
            v = Rfull.get(r, [None, None])[c]
            row.append(Ridx[v] if v is not None else None)
        Rout.append(row)

    ctx = []
    for (l, q, s, r) in contexts:
        ctx.append([Lidx[l], q, s, Ridx[r]])

    cert = {"kind": "cps", "left": Lout, "right": Rout, "contexts": ctx}
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None


def decide(tm: str) -> dict | None:
    # First try n-gram CPS for n = 1..4
    for n in (1, 2, 3, 4):
        cert = _build_ngram_cps(tm, n)
        if cert is not None:
            return cert
    return None
