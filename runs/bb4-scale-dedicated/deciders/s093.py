import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _lap(tm, max_steps=20000):
    """Return (T, P, d, lo, hi) of a translated lap if one is found, else None."""
    table, n_states, n_symbols = parse(tm)
    tape = {}
    pos = 0
    state = 0
    seen = {}
    for step in range(max_steps):
        seen[(state, pos, tuple(sorted(tape.items())))] = step
        key = (state, pos)
        if key in seen and seen[key] < step:
            pass
        # single-step
        s = tape.get(pos, 0)
        if (state, s) not in table:
            return None
        w, mv, ns = table[(state, s)]
        tape[pos] = w
        pos += mv
        state = ns
        if step > 1000:
            # look for a lap: same state, tape shifted by d
            pass
    return None


def decide(tm):
    # try a translated lap search first: cheap and often enough
    lap = _lap(tm)
    if lap:
        T, P, d, lo, hi = lap
        cert = {"kind": "cycle", "t": T, "p": P}
        try:
            check(tm, cert)
            return cert
        except Reject:
            pass
    # finite automaton reduction
    table, n_states, n_symbols = parse(tm)
    try:
        return _dfa_reduction(tm, table, n_states, n_symbols)
    except Exception:
        return None


def _dfa_reduction(tm, table, n_states, n_symbols):
    # Enumerate DFAs for one half-tape: list of transitions trans[q][x] -> q' or None.
    # We search for a DFA A_left such that the required right-half-tape language is
    # realizable; then we build contexts.
    # For the purposes of this decider we enumerate DFAs up to 3 states and use the
    # kernel's cps certificate with a canonical n-gram automaton as a fallback.
    # (A full reduction is expensive; keep it bounded.)
    best = None
    # quick attempt: n-gram automata of size 1..4
    for n in range(1, 5):
        cert = _ngram(tm, n)
        if cert is not None:
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
    return None


def _ngram(tm, n):
    table, n_states, n_symbols = parse(tm)
    # build automata remembering last n cells (n-gram CPS)
    # left[i][x]: from n-gram state i on symbol x
    # context: (l, q, s, r)
    # We do a simple forward BFS over contexts.
    # n-gram state: tuple of last n cells (padded with 0 on the far side)
    def enc(t):
        return t
    # We will represent n-gram states as integers via canonicalization.
    # Build left automaton: reads cells from far away to head.
    # state = tuple of last n cells read, padded with 0.
    # transition: new = (state[1:] + (x,))
    # canonicalize with a dict.
    left_states = {}
    right_states = {}
    def canon(state, d):
        key = (state,)
        if key not in d:
            d[key] = len(d)
        return d[key]
    # initial state: all blanks
    init = tuple([0] * n)
    l0 = canon(init, left_states)
    r0 = canon(init, right_states)
    # transitions
    def trans(state, x, d):
        ns = (state[1:] + (x,))
        return canon(ns, d)
    # build context set by fixpoint
    contexts = set()
    contexts.add((l0, 0, 0, r0))
    frontier = deque([(l0, 0, 0, r0)])
    while frontier:
        l, q, s, r = frontier.popleft()
        if (q, s) not in table:
            return None
        w, mv, q2 = table[(q, s)]
        if mv > 0:
            # right move: left automaton consumes w
            l2 = trans((tuple([0] * n) if False else _state_of(l, left_states), w, left_states)
            # need actual state tuple; store mapping
            return None
        else:
            return None
    return None


def _state_of(idx, d):
    for k, v in d.items():
        if v == idx:
            return k[0]
    return tuple([0] * 4)