from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure

# --- helpers -------------------------------------------------------------

def _reach_cycles(tm, max_t=20000, max_p=60000):
    """Return a cycle or translated-cycle certificate by trying every
    (T, P) split of a long run that stays non-halting."""
    halted, steps, state, pos, tape = run(tm, max_t + max_p)
    if halted:
        return None
    # sample a bounded number of (T, P) pairs from the single run we did
    # (run() gave us only the final state, so re-run with tracing)
    return _cycle_search(tm, max_t, max_p)


def _cycle_search(tm, max_t, max_p):
    halted, steps, state, pos, tape = run(tm, max_t + max_p)
    if halted:
        return None
    return None  # traced search is too costly; rely on CPS


def _try_cycle(tm):
    """Look for a plain or translated cycle over a bounded trace."""
    TMAX = 4000
    PMAX = 4000
    halted, steps, state, pos, tape = run(tm, TMAX + PMAX)
    if halted:
        return None
    # rebuild a trace ourselves
    table, ns, nsym = parse(tm)
    head = 0
    tape = {}
    st = 0
    trace = []
    for step in range(TMAX + PMAX + 1):
        trace.append((st, head, dict(tape)))
        if (st, tape.get(head, 0)) not in table:
            return None
        w, mv, nxt = table[(st, tape.get(head, 0))]
        tape[head] = w
        head += mv
        st = nxt
    for T in range(0, TMAX + 1):
        for P in range(1, PMAX + 1):
            if T + P >= len(trace):
                break
            stT, hT, tapeT = trace[T]
            stP, hP, tapeP = trace[T + P]
            if stT != stP:
                continue
            d = hP - hT
            # collect window [lo, hi] of positions seen during the lap
            lo = hT
            hi = hT
            h = hT
            for k in range(T, T + P + 1):
                h = trace[k][1]
                lo = min(lo, h)
                hi = max(hi, h)
            ok = True
            for y in range(lo, hi + 1):
                if tapeP.get(y + d, 0) != tapeT.get(y, 0):
                    ok = False
                    break
            if not ok:
                continue
            if d > 0:
                for y in range(hi + 1, hi + d + 1):
                    if tapeP.get(y, 0) != 0:
                        ok = False
                        break
            elif d < 0:
                for y in range(lo + d, lo):
                    if tapeP.get(y, 0) != 0:
                        ok = False
                        break
            if ok:
                return {"kind": "cycle", "t": T, "p": P}
    return None


def _enumerate_automata(nstates, sym=2):
    """Every deterministic automaton with `nstates` states over {0,1} whose
    state 0 is the all-blank state (push(0,0) == 0).  Represent as a dict
    {(state, sym): next_state_or_None}; None means 'never happens'."""
    states = list(range(nstates))
    # a table assigns each (state, sym) either a state or None
    opts = list(states) + [None]
    import itertools
    for combo in itertools.product(opts, repeat=nstates * sym):
        tbl = {}
        for i, st in enumerate(states):
            tbl[(st, 0)] = combo[2 * i]
            tbl[(st, 1)] = combo[2 * i + 1]
        if tbl[(0, 0)] != 0:
            continue
        yield tbl


def _make_push(tbl):
    def push(state, symbol):
        nxt = tbl.get((state, symbol))
        return nxt
    return push


def _prune_automaton(tbl, used_states):
    """Keep only transitions the closure actually used; others become null."""
    pruned = {}
    for st in used_states:
        for sym in (0, 1):
            v = tbl.get((st, sym))
            pruned[(st, sym)] = v
    return pruned


def _try_cps_pair(tm, nleft, nright):
    table, ns, nsym = parse(tm)
    # state 0 must be the blank state of both half-tape automata
    count = 0
    for ltbl in _enumerate_automata(nleft):
        for rtbl in _enumerate_automata(nright):
            count += 1
            if count > 400000:
                return None
            lp = _make_push(ltbl)
            rp = _make_push(rtbl)
            try:
                cert = closure(lp, rp,
                               blank_left=0, blank_right=0,
                               cap=200000)
            except Exception:
                cert = None
            if cert is None:
                continue
            try:
                check(tm, cert)
            except Reject:
                continue
            return cert
    return None


def decide(tm: str):
    # 1) cheap direct cycle search
    try:
        c = _try_cycle(tm)
        if c is not None:
            check(tm, c)
            return c
    except Exception:
        pass
    # 2) CPS search over growing automata
    for nl in (1, 2, 3):
        for nr in (1, 2, 3):
            if nl + nr > 5:
                continue
            try:
                c = _try_cps_pair(tm, nl, nr)
            except Exception:
                c = None
            if c is not None:
                return c
    return None