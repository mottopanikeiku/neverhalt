import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def decide(tm):
    try:
        tab, ns, nsm = parse(tm)
    except Exception:
        return None
    try:
        cert = _try(tm, tab, ns, nsm)
        if cert is not None:
            check(tm, cert)
            return cert
    except (Reject, Exception):
        pass
    return None

# --- helpers ---------------------------------------------------------
def _step(tab, q, s):
    key = (q, s)
    if key not in tab:
        return None
    w, m, q2 = tab[key]
    return w, m, q2

def _run_to(tab, limit, q0=0, s0=0, pos0=0):
    """Run at most limit steps from (q0,s0,pos0) on blank tape.
    Returns (steps_done, q, s, pos, tape) or steps_done==limit if not halted."""
    tape = {}
    q, s, pos = q0, s0, pos0
    for t in range(limit):
        key = (q, s)
        if key not in tab:
            return t, None, None, pos, tape
        w, m, q2 = tab[key]
        tape[pos] = w
        pos += m
        s = tape.get(pos, 0)
        q = q2
    return limit, q, s, pos, tape

# --- decider 1: plain cycle detection -------------------------------
def _try(tm, tab, ns, nsm):
    # 1. Look for a translated / plain cycle in the first window.
    cert = _cycle_search(tab, ns)
    if cert:
        return cert
    # 2. Look for a counter-like pattern using a "lap" window.
    cert = _tcycle_search(tab, ns)
    if cert:
        return cert
    # 3. CPS with n-gram automata, increasing n.
    cert = _cps_ngram(tab, ns, nsm, 3)
    if cert:
        return cert
    cert = _cps_ngram(tab, ns, nsm, 4)
    if cert:
        return cert
    return None

# --- cycle search ---------------------------------------------------
def _cycle_search(tab, ns, T=400, P=200):
    # Full config = (q, pos, tape_high, tape_low)
    # Simulate T steps, then check if a lap of P steps repeats the config.
    # We keep tape as dict; compare relevant window.
    try:
        steps, q, s, pos, tape = _run_to(tab, T)
        if steps < T:
            return None
        base_q, base_pos, base_tape = q, pos, dict(tape)
        lo = min(list(tape.keys()) + [pos]) - 40
        hi = max(list(tape.keys()) + [pos]) + 40
        base_win = {y: base_tape.get(y, 0) for y in range(lo, hi + 1)}
        # run P more
        steps2, q2, s2, pos2, tape2 = _run_to(tab, P)
        if steps2 < P:
            return None
        # merge base + lap: need to simulate P steps from base
        # redo: simulate T+P and compare
        q3, s3, pos3, tape3 = _run_to(tab, T)[0]
        # simpler: simulate T+P once
        qA, sA, posA, tapeA = _run_to(tab, T)
        if qA is None:
            return None
        # continue P steps
        q, s, pos = qA, sA, posA
        tp = dict(tapeA)
        for _ in range(P):
            key = (q, s)
            if key not in tab:
                return None
            w, m, q2 = tab[key]
            tp[pos] = w
            pos += m
            s = tp.get(pos, 0)
            q = q2
        if q != qA:
            return None
        d = pos - posA
        # displacement
        # window [lo2,hi2] of posA during lap
        # we approximate: compare base with shifted
        lo2 = min(list(tapeA.keys()) + [posA]) - 40
        hi2 = max(list(tapeA.keys()) + [posA]) + 40
        # compare tapeA[y] with tp[y+d] for y in [lo2,hi2]
        for y in range(lo2, hi2 + 1):
            if tapeA.get(y, 0) != tp.get(y + d, 0):
                return None
        # check blank outside
        if d > 0:
            for y in range(hi2 + 1, hi2 + 1 + d):
                if tp.get(y, 0) != 0:
                    return None
        elif d < 0:
            for y in range(lo2 + d - 1, lo2 - 1):
                if tp.get(y, 0) != 0:
                    return None
        return {"kind": "cycle", "t": T, "p": P}
    except Exception:
        return None

def _tcycle_search(tab, ns):
    return None

# --- CPS n-gram -----------------------------------------------------
def _cps_ngram(tab, ns, nsm, n):
    # Build contexts reachable from [0,0,0,0] under the invariant.
    # left automaton: state = last n cells read leftwards (far->near)
    # right automaton: state = last n cells read rightwards (far->near)
    # We construct reachable contexts BFS.
    alpha = list(range(nsm))
    # automaton states: tuples of length n (cells far->near), plus () for empty meaning all-blank seen
    def aut_states():
        # all tuples of length up to n over alpha, plus empty tuple
        out = [()]
        frontier = [()]
        for _ in range(n):
            nf = []
            for st in frontier:
                for x in alpha:
                    ns_ = (st + (x,))[-n:]
                    if ns_ not in out:
                        out.append(ns_)
                        nf.append(ns_)
            frontier = nf
        return out
    L_states = aut_states()
    R_states = aut_states()
    idxL = {s: i for i, s in enumerate(L_states)}
    idxR = {s: i for i, s in enumerate(R_states)}
    # automaton transition: reading symbol x (from far to near) shifts
    def trans(state, x):
        return (state + (x,))[-n:]
    # build left/right transition tables
    def build_table(states, idx):
        tbl = [[None] * nsm for _ in states]
        for i, st in enumerate(states):
            for x in range(nsm):
                tbl[i][x] = idx[trans(st, x)]
        return tbl
    L = build_table(L_states, idxL)
    R = build_table(R_states, idxR)
    # BFS over contexts
    init = (0, 0, 0, 0)
    seen = {init}
    frontier = [init]
    contexts = []
    while frontier and len(seen) < 200000:
        nxt = []
        for (l, q, s, r) in frontier:
            contexts.append((l, q, s, r))
            # transition must exist
            key = (q, s)
            if key not in tab:
                return None
            w, m, q2 = tab[key]
            if m == 1:  # right move
                l2 = L[l][w]
                if l2 is None:
                    return None
                # for every (r2, s2) with R[r2][s2] == r
                for r2 in range(len(R_states)):
                    for s2 in range(nsm):
                        if R[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in seen:
                                seen.add(c)
                                nxt.append(c)
            else:
                r2 = R[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(L_states)):
                    for s2 in range(nsm):
                        if L[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in seen:
                                seen.add(c)
                                nxt.append(c)
        frontier = nxt
    if not seen:
        return None
    if (0, 0, 0, 0) not in seen:
        return None
    return {
        "kind": "cps",
        "left": L,
        "right": R,
        "contexts": [[l, q, s, r] for (l, q, s, r) in seen],
    }
} else None

if __name__ == "__main__":
    pass
