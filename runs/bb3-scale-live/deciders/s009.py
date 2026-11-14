import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: CPS with k-gram automata over the two half-tapes.
# A "k-gram" automaton remembers the last k cells of that half-tape (as a
# tuple).  For small k the state space is tiny (2^k states), so we can build
# the full context set by a worklist fixpoint and let the kernel verify it.
# Two independent attempts are made: one small k (2..4) and one larger k (5)
# restricted to a bounded window, which is enough for the short-lived
# machines in the holdout sample.


def _build_tables(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states, n_symbols


def _aut(n):
    # automaton over n-grams of symbols, symbol 0 is blank.
    # state = tuple of last n symbols read (from far away towards head).
    # start state is the all-blank tuple.
    return n


def _kgram_contexts(tm, k):
    """Return a cps certificate dict or None (unverified)."""
    table, n_states, n_symbols = _build_tables(tm)
    blank = 0
    # symbols are 0/1; n_symbols should be 2.

    # states of the left automaton: tuples of length k (symbols read from
    # far away towards head).  state 0 convention in the kernel is the
    # all-blank half-tape; we use the all-blank tuple as index 0.
    def idx(t):
        # map tuple -> int id, blanks first.
        v = 0
        for s in t:
            v = (v << 1) | (1 if s else 0)
        return v

    # We represent the automaton transition: from state tuple t and new
    # symbol x (read next, i.e. the symbol now closest to the head), the new
    # state is ((t[1:] + (x,))).  left[i][x] is the state reached from i on x.
    # The kernel wants left[i][x] = index or null.
    n_left = idx((blank,) * k)
    n_right = n_left
    # We enumerate all reachable tuples lazily.
    left_states = {}

    def ensure(t):
        if t not in left_states:
            left_states[t] = len(left_states)
        return left_states[t]

    ensure((blank,) * k)

    # Build transitions lazily via BFS.
    from collections import deque
    dq = deque([(blank,) * k])
    left_tab = []          # list indexed by id
    right_tab = []
    while dq:
        t = dq.popleft()
        i = left_states[t]
        while len(left_tab) <= i:
            left_tab.append(None)
        row = [None, None]
        for x in range(n_symbols):
            t2 = (t[1:] + (x,))
            j = ensure(t2)
            while len(left_tab) <= j:
                left_tab.append(None)
            row[x] = j
            if t2 not in left_states:
                dq.append(t2)
        left_tab[i] = row

    # right automaton is the same table (symmetric problem).
    right_tab = [list(r) for r in left_tab]

    # Contexts: (l, q, s, r).  Start with (0,0,0,0).
    # Worklist closure:
    #   For a context (l,q,s,r) and transition (q,s)->(w,move,q2):
    #     if move is right (+1):  l2 = left[l][w]; must not be None.
    #       for every (r2,s2) with right[r2][s2] == r: add (l2,q2,s2,r2).
    #     if move is left (-1):   r2 = right[r][w]; must not be None.
    #       for every (l2,s2) with left[l2][s2] == l: add (l2,q2,s2,r2).
    # Halting transitions are rejected (no context added).
    contexts = []
    seen = set()

    def add(l, q, s, r):
        key = (l, q, s, r)
        if key in seen:
            return False
        seen.add(key)
        contexts.append(list(key))
        return True

    add(0, 0, 0, 0)
    # Precompute reverse maps: for each automaton state target, list of
    # (prev_state, symbol) that lead to it.
    def rev(tab):
        d = {}
        for i, row in enumerate(tab):
            for x in range(n_symbols):
                j = row[x]
                if j is not None:
                    d.setdefault(j, []).append((i, x))
        return d

    left_rev = rev(left_tab)
    right_rev = rev(right_tab)

    qi = 0
    while qi < len(contexts):
        l, q, s, r = contexts[qi]
        qi += 1
        tr = table.get((q, s))
        if tr is None:
            # Halting from a reachable context: cannot close.
            return None
        w, move, q2 = tr
        if move > 0:
            l2 = left_tab[l][w]
            if l2 is None:
                return None
            for (r2, s2) in right_rev.get(r, []):
                if not add(l2, q2, s2, r2):
                    pass
        else:
            r2 = right_tab[r][w]
            if r2 is None:
                return None
            for (l2, s2) in left_rev.get(l, []):
                if not add(l2, q2, s2, r2):
                    pass
    # Kernel requires left[0][0] == right[0][0] == 0.  Our all-blank tuple
    # is id 0, and the transition on 0 from it is itself -> 0.
    if left_tab[0][0] != 0 or right_tab[0][0] != 0:
        return None
    return {
        "kind": "cps",
        "left": [list(r) for r in left_tab],
        "right": [list(r) for r in right_tab],
        "contexts": contexts,
    }


def _try(tm, k):
    try:
        cert = _kgram_contexts(tm, k)
    except Exception:
        return None
    if cert is None:
        return None
    try:
        check(tm, cert)
    except Reject:
        return None
    except Exception:
        return None
    return cert


# A second, cheaper attempt: a translated-cycle search.  We look for a
# repeated local window in the run that could be certified by the kernel's
# cycle rule (T, P, d).  This catches machines whose head bounces in a
# small loop while the tape pattern translates by one cell per lap.
def _tcycle_search(tm, max_steps=4000, window=40):
    try:
        halted, steps, state, pos, tape = run(tm, max_steps)
    except Exception:
        return None
    if halted:
        return None
    # Re-simulate and record (state, pos, tape window) at each step.
    table, n_states, n_symbols = parse(tm)
    # We use run for the first pass only; a full re-simulation is cheap.
    try:
        halted, steps, state, pos, tape = run(tm, max_steps)
    except Exception:
        return None
    # Re-run with our own tracer to capture per-step snapshots.
    from neverhalt.tm import parse as _p
    tab, ns, nsym = _p(tm)
    t = {}
    head = 0
    st = 0
    snaps = []
    for step in range(max_steps):
        key = (st, head)
        if key not in tab:
            return None
        w, mv, nxt = tab[key]
        t[head] = w
        head += mv
        st = nxt
        # snapshot: state, head, tape values in a window around head
        lo = head - window
        hi = head + window
        win = tuple(t.get(y, 0) for y in range(lo, hi + 1))
        snaps.append((step, st, head, lo, win))
    # Look for a repeated (state, relative window) pair with a consistent
    # displacement.
    seen = {}
    for i in range(len(snaps)):
        step_i, st_i, head_i, lo_i, win_i = snaps[i]
        for j in range(i + 1, len(snaps)):
            step_j, st_j, head_j, lo_j, win_j = snaps[j]
            if st_i != st_j:
                continue
            if win_i != win_j:
                continue
            # Candidate lap: T = step_i, P = step_j - step_i, d = head_j - head_i
            T = step_i
            P = step_j - step_i
            d = head_j - head_i
            if T + P > 100000:
                continue
            if d == 0:
                # plain cycle: need state and tape at T and T+P equal.
                pass
            # Build candidate certificate and let the kernel verify.
            cert = {"kind": "cycle", "t": T, "p": P}
            try:
                check(tm, cert)
            except Reject:
                continue
            except Exception:
                continue
            return cert
    return None


def decide(tm: str):
    # First try the k-gram CPS with increasing k.
    for k in (2, 3, 4, 5):
        cert = _try(tm, k)
        if cert is not None:
            return cert
    # Then try the translated-cycle search.
    cert = _tcycle_search(tm)
    if cert is not None:
        return cert
    return None