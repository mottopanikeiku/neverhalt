import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(1000000)

HALT = None

# ---------- helpers for building certificate structures ----------

def id_of(x):
    return x

# ---------- BFS over machines to find small translated cycles ----------

def find_cycle(tm, budget=60000):
    """Try to find a translated cycle by simulating and looking for a state
    repetition where the tape window has shifted by a constant d and the
    content outside the window is blank. Returns cert or None."""
    table, ns, nsym = parse(tm)
    # states: 0..ns-1 ; symbols 0/1
    # simulate step by step, remember configurations
    pos = 0
    state = 0
    tape = {}
    seen = {}
    # configuration key: (state, pos, tuple(sorted(tape.items()))) -- too big;
    # instead remember (state, pos) plus a bounded window snapshot.
    # We search for a pair (T, T+P) with same state, displacement d != 0
    # and window content shifted by d, blanks outside.
    # Simpler: look for a repeated state at same pos (d=0 cycle) or a
    # repeated state with constant displacement across a window.
    # We'll simulate, recording for each step the state and pos and the
    # tape content in a window [pos-40, pos+40].
    W = 40
    hist = []
    t = 0
    while t <= budget:
        hist.append((state, pos, tuple(sorted(tape.items()))))
        # step
        key = (state, tape.get(pos, 0))
        if key not in table:
            return None
        w, mv, q2 = table[key]
        tape[pos] = w
        pos += mv
        state = q2
        t += 1
    # search pairs (T, T+P) with same state, P >= 1
    n = len(hist)
    # index by state -> list of times
    by_state = {}
    for i, (st, p, _) in enumerate(hist):
        by_state.setdefault(st, []).append(i)
    for st, times in by_state.items():
        if len(times) < 2:
            continue
        for ii in range(len(times)):
            T = times[ii]
            for jj in range(ii + 1, len(times)):
                TP = times[jj]
                if TP - T > budget:
                    continue
                P = TP - T
                stT, pT, tapeT = hist[T]
                stTP, pTP, tapeTP = hist[TP]
                d = pTP - pT
                if d == 0:
                    # plain cycle: tape must be identical
                    if tapeT == tapeTP:
                        lo = min([x for x, _ in tapeT] + [pT])
                        hi = max([x for x, _ in tapeT] + [pT])
                        cert = {"kind": "cycle", "t": T, "p": P}
                        try:
                            check(tm, cert)
                            return cert
                        except Reject:
                            pass
                    continue
                # translated: check window content
                # window [lo,hi] must contain all nonzero cells read during lap
                # We'll just take a generous window around pos range.
                # Reconstruct tape at T and TP: tapeT is dict of nonzero.
                # For y in [lo,hi] where lo = min(pos over lap, min tape key) etc.
                # Simpler: verify certificate directly with kernel after building.
                # Build window from tapeT and tapeTP.
                keys = [x for x, _ in tapeT] + [x for x, _ in tapeTP] + [pT, pTP]
                lo = min(keys)
                hi = max(keys)
                ok = True
                for y in range(lo, hi + 1):
                    if tapeTP.get(y + d, 0) != tapeT.get(y, 0):
                        ok = False
                        break
                if not ok:
                    continue
                # blanks outside: every cell right of hi (left of lo) blank at TP
                # we check that all nonzero keys of tapeTP are within [lo+d, hi+d]
                for x, v in tapeTP.items():
                    if x < lo + d or x > hi + d:
                        ok = False
                        break
                if not ok:
                    continue
                cert = {"kind": "cycle", "t": T, "p": P}
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
    return None

# ---------- CPS with automata search ----------

def build_cps(tm, max_states=4, max_contexts=200000):
    table, ns, nsym = parse(tm)
    # left and right automata: list of transition tables.
    # We enumerate automata with n states, state 0 loops on 0.
    # Each automaton: list of length nsym of dicts state->next or None.
    def enumerate_automata(n):
        # transitions per state: for symbol 0 and 1, choose target 0..n-1 or None
        # but require automaton 0 on symbol 0 = 0.
        # To limit, we require symbol 0 transitions: state i on 0 -> 0 for all i (memory of zeros resets)
        # Actually hint says "state 0 loops on symbol 0". We'll require state 0 -> 0 on 0.
        # Enumerate all functions for symbol 1 only, and symbol 0 goes to 0.
        # That's (n+1)^n possibilities. For n=3: 4^3=64. n=4: 5^4=625.
        for mask in range((n + 1) ** n):
            auto = [dict() for _ in range(n)]
            for i in range(n):
                # symbol 0 -> 0
                auto[i][0] = 0
            m = mask
            for i in range(n):
                auto[i][1] = m % (n + 1)
                m //= (n + 1)
                if auto[i][1] == n:
                    auto[i][1] = None
            yield auto

    def closure(left, right):
        # contexts: set of (l, q, s, r)
        init = (0, 0, 0, 0)
        ctx = {init}
        frontier = {init}
        while frontier:
            new = set()
            for (l, q, s, r) in frontier:
                key = (q, s)
                if key not in table:
                    return None  # halting context
                w, mv, q2 = table[key]
                if mv == 1:
                    l2 = left[l].get(w)
                    if l2 is None:
                        return None
                    # for every (r2, s2) with right[r2][s2] == r
                    for r2 in range(len(right)):
                        for s2 in range(2):
                            if right[r2].get(s2) == r:
                                c = (l2, q2, s2, r2)
                                if c not in ctx:
                                    ctx.add(c)
                                    new.add(c)
                else:
                    r2 = right[r].get(w)
                    if r2 is None:
                        return None
                    for l2 in range(len(left)):
                        for s2 in range(2):
                            if left[l2].get(s2) == l:
                                c = (l2, q2, s2, r2)
                                if c not in ctx:
                                    ctx.add(c)
                                    new.add(c)
            frontier = new
            if len(ctx) > max_contexts:
                return None
        return ctx

    seen_pairs = set()
    for n in range(1, max_states + 1):
        for left in enumerate_automata(n):
            for right in enumerate_automata(n):
                # canonical: both automata, but we allow asymmetric
                key = (tuple(tuple(sorted(a.items())) for a in left),
                       tuple(tuple(sorted(a.items())) for a in right))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                ctx = closure(left, right)
                if ctx is None:
                    continue
                # build certificate
                contexts = []
                ok = True
                for (l, q, s, r) in ctx:
                    if (q, s) not in table:
                        ok = False
                        break
                    contexts.append([l, q, s, r])
                if not ok:
                    continue
                left_tab = []
                for a in left:
                    row = []
                    for x in range(2):
                        row.append(a.get(x))
                    left_tab.append(row)
                right_tab = []
                for a in right:
                    row = []
                    for x in range(2):
                        row.append(a.get(x))
                    right_tab.append(row)
                cert = {"kind": "cps", "left": left_tab, "right": right_tab,
                        "contexts": contexts}
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
    return None

def decide(tm: str):
    # First try translated cycle search
    c = find_cycle(tm, budget=40000)
    if c is not None:
        return c
    # Then CPS search
    c = build_cps(tm, max_states=3, max_contexts=200000)
    if c is not None:
        return c
    c = build_cps(tm, max_states=4, max_contexts=200000)
    if c is not None:
        return c
    return None
