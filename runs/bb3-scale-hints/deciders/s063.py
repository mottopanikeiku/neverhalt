from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

MAX_T = 20000
MAX_P = 80000

# ---------- helpers ----------

def _table(tm):
    t, ns, nsy = parse(tm)
    return t, ns

def _state_letter(n):
    return "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[n] if n < 26 else "?"

# ---------- 1. translated-cycle ("tcycle") search ----------

def _cycle_cert(tm, tmax=MAX_T, pmax=MAX_P):
    """Search for a translated cycle: T steps then P lap with head shift d != 0."""
    try:
        t, ns = _table(tm)
        halt, steps, state, pos, tape = run(tm, tmax + pmax + 10)
    except Exception:
        return None
    if halt:
        return None
    # We need snapshots at T and T+P for every candidate T.  Re-simulate per T
    # would be too slow, so we walk once and check laps ending at each step.
    # To keep memory bounded we only recall the tape at T and the head trace
    # for the lap: re-simulate the lap from the snapshot at T.
    from neverhalt.tm import run
    # First pass: record (state, pos, tape) at every T we might try.
    # Doing this for all T up to tmax is too expensive; instead sample T in
    # a coarse grid first, then refine.
    for T in range(0, tmax, max(1, tmax // 200)):
        halt1, s1, st1, p1, tp1 = run(tm, T)
        if halt1:
            continue
        # try laps of increasing size
        for P in (1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 30, 40, 60, 80,
                  120, 180, 260, 400, 600, 900, 1300, 1900, 2800, 4200,
                  6300, 9500, 14000, 21000, 32000, 49000, 75000):
            if T + P > tmax + pmax:
                break
            try:
                halt2, s2, st2, p2, tp2 = run(tm, T + P)
            except Exception:
                continue
            if halt2:
                break
            if st2 != st1:
                continue
            d = p2 - p1
            if d == 0:
                continue
            if abs(d) > 2000:
                continue
            # verify tape shift
            if d > 0:
                # right of hi must be blank at T+P
                hi = p2
                bad = False
                for y in range(hi + 1, hi + 1 + 0):
                    pass
                # collect window during lap: re-run lap and track positions
                try:
                    ok, lo, hi = _verify_shift(tm, T, P, tp1, p1, d, ns)
                except Exception:
                    ok = False
                if not ok:
                    continue
            else:
                try:
                    ok, lo, hi = _verify_shift(tm, T, P, tp1, p1, d, ns)
                except Exception:
                    ok = False
                if not ok:
                    continue
            cert = {"kind": "cycle", "t": T, "p": P}
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    return None

def _verify_shift(tm, T, P, tp1, p1, d, ns):
    """Re-simulate lap from snapshot (T, p1, tp1) tracking head positions."""
    from neverhalt.tm import run
    # Reconstruct tape as dict; simulate manually to track positions.
    t, _ = _table(tm)
    tape = dict(tp1)
    pos = p1
    state = None
    # get state at T
    halt, s, st, p, tp = run(tm, T)
    state = st
    pos = p
    lo = pos
    hi = pos
    for _ in range(P):
        key = (state, tape.get(pos, 0))
        if key not in t:
            return False, lo, hi
        w, mv, nxt = t[key]
        tape[pos] = w
        pos += mv
        state = nxt
        if pos < lo:
            lo = pos
        if pos > hi:
            hi = pos
    if state != st:
        return False, lo, hi
    if pos - p != d:
        return False, lo, hi
    # tape check: tape_{T+P}[y+d] == tape_T[y] for y in [lo,hi]
    # We need the original tape at T: tp1 is the dict at T (from run(tm,T)).
    for y in range(lo, hi + 1):
        a = tp1.get(y, 0)
        b = tape.get(y + d, 0)
        if a != b:
            return False, lo, hi
    if d > 0:
        # cells right of hi must be blank at T+P
        for y in range(hi + 1, hi + 1 + 50):
            if tape.get(y, 0) != 0:
                return False, lo, hi
    else:
        for y in range(lo - 50, lo):
            if tape.get(y, 0) != 0:
                return False, lo, hi
    return True, lo, hi

# ---------- 2. CPS via n-gram search ----------

def _ngram_cps(tm, nmax=3):
    """Enumerate n-gram DFAs for both half-tapes up to nmax, find closed context set."""
    t, ns = _table(tm)
    syms = [0, 1]
    for n in range(1, nmax + 1):
        # build left and right automata as n-gram counters
        left, right = _build_ngram(n)
        cert = _close_contexts(t, ns, left, right)
        if cert is not None:
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
    return None

def _build_ngram(n):
    """Automaton remembering last n cells; state 0 = all blank prefix."""
    # state index: bitmask of last n cells (0..2^n-1), read far->near.
    # state 0 loops on symbol 0.
    size = 1 << n
    table = [[None, None] for _ in range(size)]
    for s in range(size):
        for x in (0, 1):
            ns = ((s << 1) | x) & (size - 1)
            table[s][x] = ns
    # ensure state 0 loops on 0
    table[0][0] = 0
    return table, table

def _close_contexts(t, ns, left, right):
    """Compute smallest closed context set; return cert or None if halting context forced."""
    # context: (l, q, s, r)
    start = (0, 0, 0, 0)
    # BFS closure
    contexts = set([start])
    frontier = [start]
    while frontier:
        newf = []
        for (l, q, s, r) in frontier:
            key = (q, s)
            if key not in t:
                return None  # halting context
            w, mv, q2 = t[key]
            if mv == 1:
                l2 = left[l][w]
                if l2 is None:
                    return None
                # for every (r2, s2) with right[r2][s2] == r
                for r2 in range(len(right)):
                    for s2 in (0, 1):
                        if right[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in contexts:
                                contexts.add(c)
                                newf.append(c)
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(left)):
                    for s2 in (0, 1):
                        if left[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in contexts:
                                contexts.add(c)
                                newf.append(c)
        frontier = newf
    if len(contexts) > 200000:
        return None
    if len(left) > 5000 or len(right) > 5000:
        return None
    cert = {
        "kind": "cps",
        "left": [[x if x is not None else None for x in row] for row in left],
        "right": [[x if x is not None else None for x in row] for row in right],
        "contexts": [[l, q, s, r] for (l, q, s, r) in contexts],
    }
    return cert

# ---------- driver ----------

def decide(tm):
    # quick: translated cycle first
    try:
        c = _cycle_cert(tm)
        if c is not None:
            return c
    except Exception:
        pass
    # n-gram CPS
    try:
        c = _ngram_cps(tm, nmax=3)
        if c is not None:
            return c
    except Exception:
        pass
    return None