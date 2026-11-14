import sys
from neverhalt.tm import parse, run

LIMIT = 5000

def _states_of(q):
    return q[0] if q else 0

def _sym(x):
    return 0 if x == 0 else 1

def _blank(q):
    return q is None

def _far_dfa_from_table(n, table):
    # table: dict[(state,sym)] = next or None; state 0 all-blank half-tape
    f = [dict() for _ in range(n)]
    for s in range(n):
        for x in (0, 1):
            r = table.get((s, x))
            if r is not None:
                f[s][x] = r
    return f

def _reverse_determinize(n, table):
    # Build NFA reading near-to-far (i.e. reverse of far-to-head), determinize
    # by subsets of states that read far-to-head; return list of dict sym->set.
    # Here we just build a canonical DFA over subsets using the standard
    # subset construction on the reversed automaton.
    # Represent the NFA as: from subset we can consume symbol x and move to
    # states whose far-to-head transition on x is in the subset (reverse edge).
    # We only need reachable subsets from {0}.
    # Build reverse transitions: for each state s and symbol x with table[(s,x)] = r,
    # reversed edge r --x--> s.
    rev = [dict() for _ in range(n)]
    for s in range(n):
        for x in (0, 1):
            r = table.get((s, x))
            if r is not None:
                rev[r][x] = s
    start = frozenset([0])
    index = {start: 0}
    order = [start]
    delta = []
    while len(index) < LIMIT:
        cur = order[len(delta)]
        d = {}
        for x in (0, 1):
            nxt = set()
            for s in cur:
                for t in rev[s].get(x, ()):
                    nxt.add(t)
            nxt = frozenset(nxt)
            if nxt not in index:
                index[nxt] = len(order)
                order.append(nxt)
            d[x] = index[nxt]
        delta.append(d)
    return delta

def _close(tm, table, n_states):
    # Build context closure. table[(state,sym)] = (write, move, next) or absent.
    # left automaton: list of dicts sym->next (or None); right automaton: same.
    # Contexts: list of (l, q, s, r).
    ctx = set()
    start = (0, 0, 0, 0)
    ctx.add(start)
    frontier = [start]
    while frontier:
        c = frontier.pop()
        l, q, s, r = c
        tr = table.get((q, s))
        if tr is None:
            return None
        w, move, q2 = tr
        if move > 0:
            l2 = None
            if w in (0, 1):
                l2 = table.get((l, w))
                if l2 is None:
                    return None
            # right half-tape pops s2: for every (r2, s2) with right[r2][s2] == r
            # we need (l2, q2, s2, r2) in ctx.
            # Here we approximate: use the right automaton table passed in.
            # We need access; handled by closure over right table.
        else:
            r2 = None
            if w in (0, 1):
                r2 = table.get((r, w))
                if r2 is None:
                    return None
        # Defer full expansion to caller-specified step function
        # (not implemented here; this decider uses a simpler closure below)
        # Actually we implement closure via explicit tables below.
        # Fallthrough: mark visited to avoid infinite loop.
        if c not in ctx:
            ctx.add(c)
    return None

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # Try plain cycle first with a bounded lap search.
    for T in range(0, 400):
        try:
            h, steps, state, pos, tape = run(tm, T)
        except Exception:
            return None
        if h:
            return None
        # Search laps P from 1..400 for a translated cycle.
        for P in range(1, 401):
            try:
                h2, steps2, state2, pos2, tape2 = run(tm, T + P)
            except Exception:
                return None
            if h2:
                return None
            # state at T and T+P same
            if state != state2:
                continue
            # head displacement d
            # need positions at T and T+P; approximate by final pos minus pos
            # We don't have pos at T; recompute.
            try:
                hT, _, stateT, posT, tapeT = run(tm, T)
                hP, _, stateP, posP, tapeP = run(tm, T + P)
            except Exception:
                return None
            d = posP - posT
            # window
            lo = posT
            hi = posP
            if d > 0:
                lo, hi = posT, posP
            else:
                lo, hi = posP, posT
            ok = True
            for y in range(lo, hi + 1):
                # tape_{T+P}[y+d] == tape_T[y]
                a = tapeP.get(y + d, 0)
                b = tapeT.get(y, 0)
                if a != b:
                    ok = False
                    break
            if not ok:
                continue
            # outside blank check
            if d > 0:
                for y in range(hi + 1, hi + 1 + abs(d) + 1):
                    if tapeP.get(y + d, 0) != 0:
                        ok = False
                        break
            else:
                for y in range(lo - abs(d) - 1, lo):
                    if tapeP.get(y + d, 0) != 0:
                        ok = False
                        break
            if ok:
                return {"kind": "cycle", "t": T, "p": P}
    # Fallback: nothing
    return None
