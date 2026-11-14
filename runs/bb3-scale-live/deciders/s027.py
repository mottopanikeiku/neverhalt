import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# --- helpers ---------------------------------------------------------------

def _halts_at(tm, T):
    """Return True if the machine halts at or before step T (inclusive)."""
    h, steps, *_ = run(tm, T + 1)
    return h


def _lap(tm, T, P):
    """Give the lap data for a cycle/tcycle certificate."""
    h, steps, state, pos, tape = run(tm, T + P)
    if h:
        return None
    return state, pos, tape


# --- attempt 1: plain / translated cycle ----------------------------------

def try_cycle(tm, max_steps=4000):
    """Search for a repeated configuration: try to find T < P such that the
    configuration at T+P equals the configuration at T (translated version
    included).  Cheap and effective for many machines."""
    n, _ = parse(tm)
    # run once, recording configurations (state, pos, tape snapshot)
    snapshots = []
    h, steps, state, pos, tape = run(tm, max_steps)
    if h:
        return None
    # re-run step by step to record configuration hashes
    try:
        from neverhalt.tm import parse as _p
    except Exception:
        return None
    # Simpler: do a manual step-by-step simulation.
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    # manual simulation
    tape = {}
    pos = 0
    st = 0
    seen = {}
    t = 0
    # initial config
    key = (st, pos, tuple(sorted(tape.items())))
    seen[key] = 0
    while t < max_steps:
        if (st, tape.get(pos, 0)) not in table:
            return None  # halted
        w, mv, nxt = table[(st, tape.get(pos, 0))]
        if w:
            tape[pos] = w
        else:
            tape.pop(pos, None)
        pos += mv
        st = nxt
        t += 1
        key = (st, pos, tuple(sorted(tape.items())))
        if key in seen:
            T = seen[key]
            P = t - T
            # build certificate
            cert = {"kind": "cycle", "t": T, "p": P}
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
        seen[key] = t
    return None


# --- attempt 2: small translated cycle via bounded window -----------------

def try_tcycle(tm, max_steps=3000):
    """Look for a translated cycle: configuration repeats after shifting by d
    cells, with blank surroundings."""
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    tape = {}
    pos = 0
    st = 0
    seen = {}
    t = 0
    while t < max_steps:
        if (st, tape.get(pos, 0)) not in table:
            return None
        w, mv, nxt = table[(st, tape.get(pos, 0))]
        if w:
            tape[pos] = w
        else:
            tape.pop(pos, None)
        pos += mv
        st = nxt
        t += 1
        # try translated repeats: same state, same local window shifted by d
        for d in range(-6, 7):
            if d == 0:
                continue
            # extract window around the head at time t
            lo = pos - 10
            hi = pos + 10
            win = tuple((y, tape.get(y, 0)) for y in range(lo, hi + 1))
            key = (st, d, win)
            if key in seen:
                T = seen[key]
                P = t - T
                cert = {"kind": "cycle", "t": T, "p": P}
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
            seen[key] = t
    return None


# --- attempt 3: ngram CPS --------------------------------------------------

def _build_ngram_cps(tm, n=6):
    """Build an n-gram CPS certificate: automata remember the last n cells of
    each half-tape (read from far away towards the head)."""
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    # automaton states: tuples of length n over {0,1} representing the last n
    # cells of the half-tape.  State 0 is the all-blank half-tape.
    def build_automaton():
        states = [tuple([0] * n)]
        index = {states[0]: 0}
        trans = [[None, None] for _ in states]

        def get_index(s):
            if s not in index:
                index[s] = len(states)
                states.append(s)
                trans.append([None, None])
            return index[s]

        # transitions: reading symbol x from far away towards the head
        # (i.e. we prepend x to the window, dropping the oldest cell)
        # state = last n cells in order (oldest .. newest)
        # reading x means a new cell closer to the head: window becomes
        # (window[1:], x)
        changed = True
        while changed:
            changed = False
            for i, s in enumerate(states):
                for x in (0, 1):
                    ns_ = (s[1:], x)
                    j = get_index(ns_)
                    if trans[i][x] != j:
                        trans[i][x] = j
                        changed = True
        return trans, index, states

    left_t, left_idx, left_states = build_automaton()
    right_t, right_idx, right_states = build_automaton()

    # contexts: (l, q, s, r)
    contexts = set()
    start = (left_idx[tuple([0] * n)], 0, 0, right_idx[tuple([0] * n)])
    contexts.add(start)
    frontier = [start]
    # precompute pairs
    def pairs_for_left(l):
        res = []
        for s2 in (0, 1):
            if left_t[l][s2] is not None:
                res.append((left_t[l][s2], s2))
        return res

    def pairs_for_right(r):
        res = []
        for s2 in (0, 1):
            if right_t[r][s2] is not None:
                res.append((right_t[r][s2], s2))
        return res

    while frontier:
        l, q, s, r = frontier.pop()
        if (q, s) not in table:
            return None  # halting context found
        w, mv, q2 = table[(q, s)]
        if mv == 1:
            if left_t[l][w] is None:
                return None
            l2 = left_t[l][w]
            for r2, s2 in pairs_for_right(r):
                c = (l2, q2, s2, r2)
                if c not in contexts:
                    contexts.add(c)
                    frontier.append(c)
        else:
            if right_t[r][w] is None:
                return None
            r2 = right_t[r][w]
            for l2, s2 in pairs_for_left(l):
                c = (l2, q2, s2, r2)
                if c not in contexts:
                    contexts.add(c)
                    frontier.append(c)

    cert = {
        "kind": "cps",
        "left": left_t,
        "right": right_t,
        "contexts": [list(c) for c in contexts],
    }
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None


# --- driver ----------------------------------------------------------------

def decide(tm: str):
    # try simple cycles first
    c = try_cycle(tm, 4000)
    if c is not None:
        return c
    c = try_tcycle(tm, 3000)
    if c is not None:
        return c
    # ngram cps of increasing size
    for n in (4, 5, 6, 7):
        c = _build_ngram_cps(tm, n)
        if c is not None:
            return c
    return None