import heapq
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure

# Enumerate candidate push functions: automations described by transition tables.
# State 0 must loop on symbol 0 (blank). We try tables of size 1..N with
# transitions on symbols 0 and 1. push(s, x) = table[(s, x)], defaulting to
# a dead state that loops forever (never used by closure unless reachable).
def gen_pushes(n_states, default):
    # produce dict mapping (state, symbol) -> next_state
    # states 0..n_states-1, symbols 0,1. We enumerate all 2^(2*n_states) tables.
    out = []
    total = 2 * n_states
    for mask in range(1 << total):
        tbl = {}
        for i in range(n_states):
            for s in (0, 1):
                idx = i * 2 + s
                tbl[(i, s)] = (mask >> idx) & 1
        # state 0 must loop on 0
        if tbl.get((0, 0)) != 0:
            continue
        out.append(tbl)
    return out

SYMS = (0, 1)

def make_push(tbl, n_states, default_state):
    def push(state, symbol):
        if symbol not in SYMS:
            return state
        # unknown state: use default_state
        if state >= n_states:
            return default_state
        nxt = tbl.get((state, symbol))
        if nxt is None or nxt >= n_states:
            return default_state
        return nxt
    return push

def blank_ok(push, b):
    return push(b, 0) == b

# Try all pairs of automata up to n_states each.  We look for a pair whose
# closure has no halting context.  We use the helper's closure.
def build_cert(tm, n_states):
    tables = gen_pushes(n_states, None)
    n = len(tables)
    # Precompute push functions
    pushes = []
    for t in tables:
        pushes.append(make_push(t, n_states, n_states))
    blanks = set()
    for p in pushes:
        # find blank fixed point on 0: state 0 always loops on 0, so use 0
        pass
    # blank states are 0 for all (they loop on 0).  Use 0.
    # Try pairs; to limit work, first try pairs where blanks agree (both 0).
    # All of ours have blank 0, so all pairs are candidates.
    for i in range(n):
        for j in range(i, n):
            try:
                cert = closure(pushes[i], pushes[j], blank_left=0, blank_right=0)
            except Exception:
                cert = None
            if cert is not None:
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
    return None

def decide(tm):
    try:
        parse(tm)
    except Exception:
        return None
    # Fast reject: if it halts within a quick simulation, not our target.
    halted, _, _, _, _ = run(tm, 300)
    if halted:
        return None
    for n in (1, 2, 3):
        cert = build_cert(tm, n)
        if cert is not None:
            return cert
    return None
