from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: look for translated cycles (tcycle) in a window around the head,
# and for plain cycles after a bounded warm-up, using the kernel to validate.
def decide(tm: str):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # 1) search for a translated cycle over a sliding window
    cert = _find_tcycle(tm)
    if cert is not None:
        try:
            check(tm, cert)
            return cert
        except Reject:
            pass
    # 2) search for a plain cycle (d = 0) after warm-up
    cert = _find_cycle(tm)
    if cert is not None:
        try:
            check(tm, cert)
            return cert
        except Reject:
            pass
    return None


def _find_tcycle(tm, max_steps=40000, max_p=40000):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # simulate while remembering (state, position) -> step index
    seen = {}
    steps = []
    # steps[t] = (state, pos, tape_snapshot_of_window, lo, hi)
    # We simulate and keep a rolling record of head positions and window content.
    # Instead of storing full tape, store the dict of nonzero cells.
    from collections import defaultdict
    state = 0
    pos = 0
    tape = {}
    t = 0
    # We will record configurations at a coarse granularity to bound memory:
    # record every step for the first 20000, then every step up to 40000.
    # For pair matching we need exact state+pos; we store tape window lazily.
    # To keep memory sane we store tape as dict and copy the relevant window on demand.
    if not _tcycle_search(tm, table, n_states, n_symbols, state, pos, tape):
        return None
    return None


def _tcycle_search(tm, table, n_states, n_symbols, state, pos, tape):
    # Re-simulate with full control and try to find a repeated (state,pos) pair
    # within 20000 steps, then test whether the intervening lap satisfies the
    # translated-cycle condition: d != 0, tape_{T+P}[y+d] == tape_T[y] on [lo,hi],
    # and the far side beyond [lo,hi] is blank.
    from collections import defaultdict
    # first pass: find repeated (state,pos) pairs
    state = 0
    pos = 0
    tape = {}
    # record step -> (state, pos, frozenset of tape within +-50 of pos)
    first = {}
    history = []  # (state, pos, tape_snapshot)
    max_steps = 60000
    t = 0
    while t < max_steps:
        key = (state, pos)
        if key in first:
            T = first[key]
            P = t - T
            if P <= 0:
                break
            # candidate lap from T to t
            cert = _test_lap(tm, history, T, t)
            if cert is not None:
                return cert
        first.setdefault(key, t)
        history.append((state, pos, dict(tape)))
        # step
        halted = False
        try:
            s = table[(state, tape.get(pos, 0))]
        except KeyError:
            halted = True
        if halted:
            return None
        w, mv, ns = s
        tape[pos] = w
        pos += mv
        state = ns
        t += 1
    return None


def _test_lap(tm, history, T, t):
    # history[i] = (state, pos, tape_snapshot) at step i (before stepping i->i+1)
    # lap from T to t: we need state_T == state_t, and window content shifted.
    st_T, pos_T, tape_T = history[T]
    st_t, pos_t, tape_t = history[t]
    if st_T != st_t:
        return None
    P = t - T
    # d = pos_t - pos_T
    d = pos_t - pos_T
    if d == 0:
        return None
    # head positions seen during lap: pos_T .. pos_t along the path; we only
    # have endpoints. We need the window [lo,hi] of head positions during lap.
    # Reconstruct the head path from history.
    lo = pos_T
    hi = pos_T
    for i in range(T, t + 1):
        p = history[i][1]
        if p < lo:
            lo = p
        if p > hi:
            hi = p
    # condition: tape_{T+P}[y + d] == tape_T[y] for y in [lo,hi]
    # and cells beyond hi (if d>0) blank at T+P, or beyond lo (if d<0) blank.
    ok = True
    if d > 0:
        for y in range(lo, hi + 1):
            a = tape_T.get(y, 0)
            b = tape_t.get(y + d, 0)
            if a != b:
                ok = False
                break
        if ok:
            for y in range(hi + 1, hi + 1 + 200):
                if tape_t.get(y, 0) != 0:
                    ok = False
                    break
    else:
        for y in range(lo, hi + 1):
            a = tape_T.get(y, 0)
            b = tape_t.get(y + d, 0)
            if a != b:
                ok = False
                break
        if ok:
            for y in range(lo - 200, lo):
                if tape_t.get(y, 0) != 0:
                    ok = False
                    break
    if not ok:
        return None
    return {"kind": "cycle", "t": T, "p": P}


def _find_cycle(tm, max_steps=60000):
    # plain cycle: find (state,pos) repeat where the tape window content is
    # identical at both times (d=0 case handled by kernel as kind "cycle").
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    from collections import defaultdict
    state = 0
    pos = 0
    tape = {}
    seen = {}
    history = []
    t = 0
    while t < max_steps:
        key = (state, pos)
        if key in seen:
            T = seen[key]
            st_T, pos_T, tape_T = history[T]
            st_t, pos_t, tape_t = history[t]
            if st_T == st_t and pos_T == pos_t:
                # need window content identical. Use window +-100 around pos.
                lo = pos_T - 100
                hi = pos_T + 100
                same = True
                for y in range(lo, hi + 1):
                    if tape_T.get(y, 0) != tape_t.get(y, 0):
                        same = False
                        break
                if same:
                    # verify with kernel
                    cert = {"kind": "cycle", "t": T, "p": t - T}
                    try:
                        from neverhalt.kernel import check, Reject
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
        seen.setdefault(key, t)
        history.append((state, pos, dict(tape)))
        try:
            s = table[(state, tape.get(pos, 0))]
        except KeyError:
            return None
        w, mv, ns = s
        tape[pos] = w
        pos += mv
        state = ns
        t += 1
    return None