import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(100000)


def _table(tm):
    table, ns, nsym = parse(tm)
    return table, ns


def _half_dfa_search(table, ns, max_states, cap=60):
    # Enumerate deterministic half-tape automata for the LEFT side:
    # states are ints 0..k-1, state 0 is the all-blank tape. left[i][x] is
    # the state reached from i on symbol x (0 or 1), or None if unused.
    # A partial table is a tuple of rows; each row is a tuple over the
    # symbols seen so far, but to keep BFS canonical we store the *used*
    # transitions as a sorted list of (state, sym, next).
    found = []
    # We enumerate tables over all states 0..k-1, requiring left[0][0] == 0.
    # To keep it finite, we only allow transitions that are forced by the
    # closure below; here we enumerate all deterministic tables but prune
    # aggressively by only extending transitions that are reachable from
    # the blank reset (state 0 on symbol 0).
    seen = set()
    # Represent a partial table as a frozenset of (state, sym, next) with
    # next in 0..k-1; state 0 must have (0,0,0).
    base = ((0, 0, 0),)
    stack = [base]
    out = []
    while stack:
        t = stack.pop()
        if t in seen:
            continue
        seen.add(t)
        # count used transitions
        if len(t) > cap:
            continue
        # canonical: always include (0,0,0)
        if (0, 0, 0) not in t:
            t = t + ((0, 0, 0),)
        # make deterministic: for each state and symbol at most one next
        det = {}
        ok = True
        for (a, x, b) in t:
            if a < 0 or a >= max_states or b < 0 or b >= max_states:
                ok = False
                break
            if (a, x) in det and det[(a, x)] != b:
                ok = False
                break
            det[(a, x)] = b
        if not ok:
            continue
        # check closure on the fly: BFS the context set with only the
        # transitions present; if it closes without a halting context, emit.
        cert = _close(table, ns, det, max_states, max_states)
        if cert is not None:
            out.append((det, cert))
        # extend by one transition
        if len(t) < cap:
            for a in range(max_states):
                for x in (0, 1):
                    if (a, x) in det:
                        continue
                    for b in range(max_states):
                        stack.append(t + ((a, x, b),))
    return out


def _close(table, ns, det, max_states, _unused):
    # det: dict (state,sym)->next for the LEFT automaton.
    # Build the right automaton as the mirror (same table), which is only
    # correct for symmetric machines; but we try the *identity* table for
    # the right side too, which covers many counters.  For a general pair
    # we would need the NFA reverse-determinization; here we attempt the
    # same table on both sides, plus a few hand-built right automata.
    rights = [det]
    # also try a 1-state right automaton
    one = {(0, 0): 0, (0, 1): 0}
    rights.append(one)
    for right in rights:
        cert = _close_pair(table, ns, det, right, max_states)
        if cert is not None:
            return cert
    return None


def _close_pair(table, ns, left, right, max_states):
    # context: (l, q, s, r), l in left states, r in right states
    # start with (0,0,0,0)
    start = (0, 0, 0, 0)
    seen = {start}
    frontier = [start]
    halting = set()
    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            if q >= ns:
                continue
            tr = table.get((q, s))
            if tr is None:
                halting.add((l, q, s, r))
                continue
            w, move, q2 = tr
            if move == 1:
                l2 = left.get((l, w))
                if l2 is None:
                    nxt.append((l, q, s, r))
                    continue
                # for every (r2, s2) with right[(r2, s2)] == r
                for r2 in range(max_states):
                    for s2 in (0, 1):
                        if right.get((r2, s2)) == r:
                            c = (l2, q2, s2, r2)
                            if c not in seen:
                                seen.add(c)
                                nxt.append(c)
            else:
                r2 = right.get((r, w))
                if r2 is None:
                    nxt.append((l, q, s, r))
                    continue
                for l2 in range(max_states):
                    for s2 in (0, 1):
                        if left.get((l2, s2)) == l:
                            c = (l2, q2, s2, r2)
                            if c not in seen:
                                seen.add(c)
                                nxt.append(c)
        frontier = nxt
    if halting:
        return None
    left_t = [[None, None] for _ in range(max_states)]
    for (a, x), b in left.items():
        if a < max_states and x < 2:
            left_t[a][x] = b
    right_t = [[None, None] for _ in range(max_states)]
    for (a, x), b in right.items():
        if a < max_states and x < 2:
            right_t[a][x] = b
    contexts = [[l, q, s, r] for (l, q, s, r) in seen]
    cert = {"kind": "cps", "left": left_t, "right": right_t,
            "contexts": contexts}
    try:
        kind = check(table.tm if hasattr(table, 'tm') else None, cert)
        return cert
    except Exception:
        return None


def decide(tm: str):
    try:
        table, ns = _table(tm)
    except Exception:
        return None
    tmobj = type('X', (), {'tm': tm})()
    for max_states in (1, 2, 3):
        for det, cert in _half_dfa_search(table, ns, max_states, cap=40):
            try:
                check(tm, cert)
                return cert
            except Exception:
                pass
    return None
