from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# This decider attempts to prove non-halting for the remaining 3-state, 2-symbol
# Turing machines by searching for a translated cycle certificate ("cycle") or a
# closed set of abstract configurations ("cps").  It is a self-contained search
# routine built on the kernel's accepted certificate formats.
#
# The strategy is to enumerate each machine's execution for up to T_max steps,
# then look for a repeated state with a consistent tape pattern shifted by d
# cells.  This is the translated-cycle certificate.  If no such cycle is found,
# we build a small n-gram CPS certificate by abstracting the last n cells on
# each side of the head.  Both attempts are bounded by the kernel limits.

def _simulate(tm, max_steps):
    table, n_states, n_symbols = parse(tm)
    tape = {}
    state = 0
    pos = 0
    steps = 0
    while steps < max_steps:
        if (state, tape.get(pos, 0)) not in table:
            return None
        w, mv, ns = table[(state, tape.get(pos, 0))]
        tape[pos] = w
        pos += mv
        state = ns
        steps += 1
    return (state, pos, tape)

def _try_cycle(tm, T_max=2000, P_max=500):
    # Simulate up to T_max steps, recording snapshots of state, pos, tape.
    table, n_states, n_symbols = parse(tm)
    tape = {}
    state = 0
    pos = 0
    snaps = []
    for t in range(T_max + 1):
        # save tape window around head: we need full tape for window checks
        snaps.append((state, pos, dict(tape)))
        if (state, tape.get(pos, 0)) not in table:
            return None
        w, mv, ns = table[(state, tape.get(pos, 0))]
        tape[pos] = w
        pos += mv
        state = ns
    # Look for a lap: same state at t and t+P, P in 1..P_max
    for T in range(T_max - P_max, T_max):
        for P in range(1, P_max + 1):
            T2 = T + P
            if T2 > T_max:
                break
            s1, p1, tape1 = snaps[T]
            s2, p2, tape2 = snaps[T2]
            if s1 != s2:
                continue
            d = p2 - p1
            # window [lo, hi] = positions seen during lap
            lo = min(p for _, p, _ in snaps[T:T2 + 1])
            hi = max(p for _, p, _ in snaps[T:T2 + 1])
            ok = True
            for y in range(lo, hi + 1):
                if tape2.get(y + d, 0) != tape1.get(y, 0):
                    ok = False
                    break
            if not ok:
                continue
            # far side blank
            if d > 0:
                for y in range(hi + 1, hi + 1 + d):
                    if tape2.get(y, 0) != 0:
                        ok = False
                        break
            elif d < 0:
                for y in range(lo - 1, lo - 1 + (-d), -1):
                    if tape2.get(y, 0) != 0:
                        ok = False
                        break
            if ok:
                try:
                    check(tm, {"kind": "cycle", "t": T, "p": P})
                    return {"kind": "cycle", "t": T, "p": P}
                except Reject:
                    pass
    return None

def _ngram_cps(tm, n=4):
    # Build n-gram automata for left and right half-tapes (reading from far
    # away towards the head).  We use a simple finite automaton that remembers
    # the last n cells seen.  Then close the set of contexts starting from
    # [0,0,0,0] and verify with the kernel.
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # left automaton: states are tuples of last n symbols read (from far away
    # towards head).  We only care about states reachable from blank.  We'll
    # build it lazily via BFS on the context closure instead of prebuilding.
    # For simplicity, use a bounded n-gram automaton where state = tuple of
    # last n symbols (0/1), and the automaton reads new symbols appended.
    def build_automaton(read_direction):
        # We'll represent automaton state as a tuple (history).  start = all zeros
        # but kernel requires state 0 to be the all-blank half-tape and
        # left[0][0] == right[0][0] == 0.
        # We'll use a canonical BFS over reachable n-gram states.
        # For left automaton, reading from far away towards head: we append
        # symbols to the front?  The kernel says left[i][x] is the state reached
        # from state i on symbol x.  We'll interpret state as a tuple of the last
        # n symbols in order from far to near.  On reading a new symbol x (the
        # next cell towards the head), the new state drops the oldest and appends x.
        start = tuple([0] * n)
        idx = {start: 0}
        trans = []
        queue = [start]
        while queue:
            st = queue.pop(0)
            i = idx[st]
            row = [None, None]
            for x in (0, 1):
                if len(st) < n:
                    # pad with zeros at the far end
                    newst = (0,) * (n - len(st)) + st + (x,)
                else:
                    newst = st[1:] + (x,)
                # For right automaton the order is mirrored, but for simplicity
                # we use the same construction; the kernel will verify.
                if newst not in idx:
                    idx[newst] = len(idx)
                    queue.append(newst)
                row[x] = idx[newst]
            trans.append(row)
        return trans
    left = build_automaton("left")
    right = build_automaton("right")
    # Ensure state 0 is all-blank: left[0][0] and right[0][0] should be 0.
    if left[0][0] != 0:
        left[0][0] = 0
    if right[0][0] != 0:
        right[0][0] = 0
    # Now close contexts: context = (l, q, s, r)
    contexts = set()
    contexts.add((0, 0, 0, 0))
    work = list(contexts)
    while work:
        l, q, s, r = work.pop()
        if (q, s) not in table:
            return None
        w, mv, q2 = table[(q, s)]
        if mv > 0:
            if w not in (0, 1):
                return None
            l2 = left[l][w]
            if l2 is None:
                return None
            # for every (r2, s2) with right[r2][s2] == r
            for r2 in range(len(right)):
                row = right[r2]
                for s2 in (0, 1):
                    if row[s2] == r:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in contexts:
                            contexts.add(ctx)
                            work.append(ctx)
        else:
            if w not in (0, 1):
                return None
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(len(left)):
                row = left[l2]
                for s2 in (0, 1):
                    if row[s2] == l:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in contexts:
                            contexts.add(ctx)
                            work.append(ctx)
    # Check kernel limit: at most 5000 states per automaton and 200000 contexts
    if len(left) > 5000 or len(right) > 5000 or len(contexts) > 200000:
        return None
    cert = {
        "kind": "cps",
        "left": left,
        "right": right,
        "contexts": [list(c) for c in contexts],
    }
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None

def decide(tm: str) -> dict | None:
    # First try translated cycles (fast and often sufficient for the small
    # remaining holdouts).
    cert = _try_cycle(tm)
    if cert is not None:
        return cert
    # Then try n-gram CPS with increasing n.
    for n in (2, 3, 4):
        cert = _ngram_cps(tm, n)
        if cert is not None:
            return cert
    return None

NAME = "cycle_and_ngram_cps"