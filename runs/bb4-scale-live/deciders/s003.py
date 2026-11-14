import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def dec_deciders():
    yield "ngram_cps"
    yield "tcycle"

def build_automaton(cells, maxlen):
    # cells: list of symbols 0/1, far to near
    states = [0]
    trans = [[None, None] for _ in range(1)]
    for c in cells:
        if c == 0:
            trans[0][0] = 0
        else:
            trans[0][1] = 0
    # only need state 0 if all blanks; but in general we build states for suffixes
    return None

def make_cps(tm, max_ctx=200000):
    table, n_states, n_symbols = parse(tm)
    # states are ints A=0..; transitions table[(state, sym)] = (write, move, next)
    # Build n-gram automata for each half-tape reading far->near, remembering last n cells.
    # State = tuple of last n cells read so far (or fewer if at boundary).
    def build_automaton(n, blank_sym=0):
        # states: frozensets/ tuples; we use ints via dict
        trans = {}
        def st(cells):
            key = tuple(cells)
            if key not in trans:
                trans[key] = [None, None]
            return key
        st(())
        # enumerate all reachable states up to length n
        from collections import deque
        dq = deque([st(())])
        while dq:
            cur = dq.popleft()
            for sym in range(n_symbols):
                if trans[cur][sym] is None:
                    # new cell prepended
                    new = (sym,) + cur
                    if len(new) > n:
                        new = new[:n]
                    trans[cur][sym] = st(new)
                    if trans[st(new)] is not None and st(new) not in [x for x in []]:
                        pass
                    if len(new) == n and new not in [k for k in trans if k == new]:
                        pass
                    # ensure enqueued
                    # simple: if state was just created and not seen
                    if st(new) not in [s for s in []] and True:
                        # avoid duplicates by checking if it was newly created
                        # We'll just enqueue if it's not already processed; approximate
                        pass
        # map to ints
        states = list(trans.keys())
        idx = {s: i for i, s in enumerate(states)}
        lt = [[None, None] for _ in states]
        for s in states:
            for sym in range(n_symbols):
                if trans[s][sym] is not None:
                    lt[idx[s]][sym] = idx[trans[s][sym]]
        return lt

    # Too slow/complex; skip. Instead return None.
    return None

def decide(tm: str):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # 1) Try cycle certificate by brute force simulation
    try:
        cert = try_cycle(tm)
        if cert is not None:
            return cert
    except Exception:
        pass
    # 2) Try short translated cycles
    try:
        cert = try_short_tcycle(tm)
        if cert is not None:
            return cert
    except Exception:
        pass
    return None

def try_cycle(tm):
    for T in range(0, 2000):
        for P in range(1, 2000):
            if T + P > 100000:
                return None
            try:
                h1, s1, st1, p1, tape1 = run(tm, T)
                if h1:
                    return None
                h2, s2, st2, p2, tape2 = run(tm, T + P)
                if h2:
                    return None
                if st1 != st2:
                    continue
                # d = p2 - p1
                d = p2 - p1
                if d == 0:
                    # plain cycle: tape unchanged everywhere
                    ok = True
                    for y in set(list(tape1.keys()) + list(tape2.keys())):
                        if tape1.get(y, 0) != tape2.get(y, 0):
                            ok = False
                            break
                    if ok:
                        return {"kind": "cycle", "t": T, "p": P}
                else:
                    # translated cycle: check window
                    # simulate to get positions seen during lap
                    # We need [lo, hi] of head positions during lap
                    _, _, _, _, _ = run(tm, T)
                    # redo simulation manually to track positions
                    from neverhalt.tm import run
                    # run returns final tape; we need trajectory. Use manual sim.
                    ok = manual_tcycle(tm, T, P)
                    if ok:
                        return {"kind": "cycle", "t": T, "p": P}
            except Exception:
                return None
    return None

def manual_tcycle(tm, T, P):
    table, n_states, n_symbols = parse(tm)
    # manual simulate T steps
    def sim(steps):
        tape = {}
        pos = 0
        state = 0
        positions = []
        for i in range(steps):
            positions.append(pos)
            sym = tape.get(pos, 0)
            key = (state, sym)
            if key not in table:
                return None
            w, mv, ns = table[key]
            tape[pos] = w
            pos += mv
            state = ns
        return tape, pos, state, positions
    r1 = sim(T)
    if r1 is None:
        return False
    tape1, pos1, state1, _ = r1
    # simulate lap
    tape = dict(tape1)
    pos = pos1
    state = state1
    lo = pos
    hi = pos
    for i in range(P):
        lo = min(lo, pos)
        hi = max(hi, pos)
        sym = tape.get(pos, 0)
        key = (state, sym)
        if key not in table:
            return False
        w, mv, ns = table[key]
        tape[pos] = w
        pos += mv
        state = ns
    if state != state1:
        return False
    d = pos - pos1
    # check window content shifted
    for y in range(lo, hi + 1):
        if tape.get(y + d, 0) != tape1.get(y, 0):
            return False
    # blank far side
    if d > 0:
        for y in range(hi + 1, hi + 1 + 0):
            pass
        # every cell right of hi must be blank at T+P
        # find max nonblank right of hi
        for y in list(tape.keys()):
            if y > hi and tape[y] != 0:
                return False
    elif d < 0:
        for y in list(tape.keys()):
            if y < lo and tape[y] != 0:
                return False
    return True

def try_short_tcycle(tm):
    # try small T, P for translated cycle
    for T in range(0, 500):
        for P in range(1, 500):
            if T + P > 100000:
                return None
            if manual_tcycle(tm, T, P):
                return {"kind": "cycle", "t": T, "p": P}
    return None

DECIDER_NAME = "cycle_bruteforce"
