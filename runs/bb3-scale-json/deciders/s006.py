import sys
sys.setrecursionlimit(100000)

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _steps(tm, n):
    # Fast plain simulation for n steps, returning the raw state
    table, n_states, n_symbols = parse(tm)
    state = 0
    pos = 0
    tape = {}
    for _ in range(n):
        key = (state, tape.get(pos, 0))
        if key not in table:
            return None
        w, mv, ns = table[key]
        tape[pos] = w
        pos += mv
        state = ns
    return state, pos, tape


def _find_cycle(tm, max_t=30000, max_p=20000):
    """Look for a cycle or translated cycle.  We walk forward from the blank
    tape, remembering (state, head position, tape-window) snapshots at a
    modest number of positions, and try to close a lap between two of them."""
    table, n_states, n_symbols = parse(tm)
    state = 0
    pos = 0
    tape = {}
    # snapshot: (state, pos, tuple(sorted(tape.items())))
    snaps = {}
    for t in range(max_t):
        key = (state, pos)
        # store a windowed snapshot: only cells within +-60 of the head
        win = tuple(sorted((k, v) for (k, v) in tape.items() if abs(k - pos) <= 60))
        sig = (state, pos, win)
        if sig in snaps:
            t0 = snaps[sig]
            # candidate lap
            p = t - t0
            if p == 0:
                continue
            # verify with kernel
            try:
                cert = {"kind": "cycle", "t": t0, "p": p}
                check(tm, cert)
                return cert
            except Reject:
                pass
        snaps[sig] = t
        k = (state, tape.get(pos, 0))
        if k not in table:
            return None
        w, mv, ns = table[k]
        tape[pos] = w
        pos += mv
        state = ns
    return None


def _recorded_cycle(tm, max_steps=60000):
    """Run plain, then check a bunch of candidate (t,p) pairs by direct
    simulation of t+p steps and compare windows.  Also catches translated
    cycles where the window shifts."""
    table, n_states, n_symbols = parse(tm)
    # Simulate once, keeping a list of (state, pos, tape-copy) at sampled times.
    state = 0
    pos = 0
    tape = {}
    samples = []
    for t in range(max_steps):
        if t % 1 == 0 and len(samples) < 4000:
            samples.append((t, state, pos, dict(tape)))
        k = (state, tape.get(pos, 0))
        if k not in table:
            return None
        w, mv, ns = table[k]
        tape[pos] = w
        pos += mv
        state = ns
    # Try to find a repeat: for each sample i, look ahead for a later sample j
    # with same state and same relative window content (translated match).
    for i in range(len(samples)):
        ti, si, pi, tpi = samples[i]
        for j in range(i + 1, len(samples)):
            tj, sj, pj, tpj = samples[j]
            if sj != si:
                continue
            p = tj - ti
            if p == 0:
                continue
            # displacement
            d = pj - pi
            # window: cells that could matter
            lo_i = min(tpi.keys()) if tpi else pi
            hi_i = max(tpi.keys()) if tpi else pi
            lo_j = min(tpj.keys()) if tpj else pj
            hi_j = max(tpj.keys()) if tpj else pj
            # check translated equality over union of windows
            allk = set()
            for k in tpi:
                allk.add(k)
            for k in tpj:
                allk.add(k)
            ok = True
            for k in allk:
                if tpj.get(k + d, 0) != tpi.get(k, 0):
                    ok = False
                    break
            if not ok:
                continue
            # cells entering window on far side must be blank at tj
            if d > 0:
                for k in range(hi_j + 1, hi_j + 1 + 200):
                    if tpj.get(k, 0) != 0:
                        ok = False
                        break
            elif d < 0:
                for k in range(lo_j - 1, lo_j - 1 - 200, -1):
                    if tpj.get(k, 0) != 0:
                        ok = False
                        break
            if not ok:
                continue
            try:
                cert = {"kind": "cycle", "t": ti, "p": p}
                check(tm, cert)
                return cert
            except Reject:
                pass
    return None


def _cps_ngram(tm, n=8):
    """n-gram CPS: remember last n cells of each half-tape.
    Returns a certificate or None."""
    table, n_states, n_symbols = parse(tm)
    nctx = 0
    # left automaton states: tuples of up to n symbols (read far->near)
    # We'll index them by tuple.
    left_states = {(): 0}
    right_states = {(): 0}

    def get_left(s):
        if s not in left_states:
            left_states[s] = len(left_states)
        return left_states[s]

    def get_right(s):
        if s not in right_states:
            right_states[s] = len(right_states)
        return right_states[s]

    left_trans = {}
    right_trans = {}
    # state 0 = empty tuple
    for sym in (0, 1):
        left_trans[(0, sym)] = get_left((sym,))
        right_trans[(0, sym)] = get_right((sym,))
    for s, idx in list(left_states.items()):
        if len(s) >= n:
            continue
        for sym in (0, 1):
            ns = (sym,) + s
            left_trans[(idx, sym)] = get_left(ns)
    for s, idx in list(right_states.items()):
        if len(s) >= n:
            continue
        for sym in (0, 1):
            ns = (sym,) + s
            right_trans[(idx, sym)] = get_right(ns)

    contexts = set()
    contexts.add((0, 0, 0, 0))
    changed = True
    while changed:
        changed = False
        for (l, q, s, r) in list(contexts):
            nctx += 1
            if nctx > 200000:
                return None
            k = (q, s)
            if k not in table:
                return None
            w, mv, q2 = table[k]
            if mv == 1:
                # right move
                if w not in (0, 1):
                    continue
                l2 = left_trans.get((l, w))
                if l2 is None:
                    continue
                # s2 can be 0 or 1, r2 any with right_trans[(r2, s2)] == r
                found_any = False
                for r2 in list(right_states.values()):
                    for s2 in (0, 1):
                        if right_trans.get((r2, s2)) == r:
                            found_any = True
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                contexts.add(ctx)
                                changed = True
                if not found_any:
                    return None
            else:
                if w not in (0, 1):
                    continue
                r2 = right_trans.get((r, w))
                if r2 is None:
                    continue
                found_any = False
                for l2 in list(left_states.values()):
                    for s2 in (0, 1):
                        if left_trans.get((l2, s2)) == l:
                            found_any = True
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                contexts.add(ctx)
                                changed = True
                if not found_any:
                    return None

    if len(contexts) > 200000:
        return None
    cert = {
        "kind": "cps",
        "left": [[left_trans.get((i, x)) for x in (0, 1)] for i in range(len(left_states))],
        "right": [[right_trans.get((i, x)) for x in (0, 1)] for i in range(len(right_states))],
        "contexts": [[l, q, s, r] for (l, q, s, r) in contexts],
    }
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None


def decide(tm: str) -> dict | None:
    # 1) recorded cycle search
    c = _recorded_cycle(tm, max_steps=40000)
    if c:
        return c
    # 2) n-gram CPS with a few window sizes
    for n in (6, 8, 10, 12):
        c = _cps_ngram(tm, n=n)
        if c:
            return c
    return None