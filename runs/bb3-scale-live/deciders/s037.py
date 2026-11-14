from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: "cps_half" — half-tape automaton CPS with bounded cell memory.
# Builds, for each half-tape, a DFA that remembers the last n cells
# (n-gram), then searches for a closed context set containing
# [0,0,0,0] where every context has a total transition.

def _build_ngram(n):
    # states: tuples of length n, with None meaning "start of half-tape" (blank run)
    # We model this as: state = last n cells as a string of length n over {'0','1'},
    # with a special state for "fewer than n cells seen" represented by leading
    # state index 0 meaning blank-prefix. Simpler: represent state as tuple
    # where the first element is a flag (0 = prefix of blanks not yet filled).
    # For simplicity, we use the standard n-gram construction where the
    # automaton state is the last min(n, seen) cells and the "blank run" is
    # encoded by an initial state that loops on 0.
    # left[i][x] = state after reading symbol x (moving away from head).
    # We index states as: 0 = initial (all blank seen so far), then states are
    # tuples of length n over {0,1}; state for "read k < n cells" is tuple of
    # (n-k) 0s followed by the k actual cells read. That is the same as the
    # n-gram state of the last n cells (with implicit blanks before).
    # So: state = (n-k zeros) + (cells read so far). Reading x appends x and
    # drops the first element.
    # Reading 0 from the initial state stays initial.
    states = [None]  # placeholder
    idx = {}
    def mk(cells):
        if cells not in idx:
            idx[cells] = len(states)
            states.append(cells)
        return idx[cells]
    mk(())
    # initial state 0: all-zero string of length n? For "far away" semantics we
    # need the automaton to have seen blanks. Use state () meaning "no cells
    # yet", and reading 0 keeps it at () because leading blanks are indistinguishable
    # from the initial state. So left[0][0] = 0.
    table = {}
    for i, cells in enumerate(states):
        for x in (0, 1):
            if cells is None:
                continue
            if cells == () and x == 0:
                table[(i, x)] = 0
            else:
                new = (cells + (x,))[-n:]
                table[(i, x)] = mk(new)
    return table, len(states), mk

def _context_closure(left, right, n_left, n_right, n_states, n_symbols):
    # BFS over contexts [l, q, s, r]
    start = (0, 0, 0, 0)
    seen = {start}
    stack = [start]
    contexts = []
    while stack:
        l, q, s, r = stack.pop()
        contexts.append([l, q, s, r])
        trans = table[(q, s)] if (q, s) in table else None
        if trans is None:
            return None
        w, move, q2 = trans
        if move == 1:
            l2 = left.get((l, w))
            if l2 is None:
                return None
            for (rr, ss), rr2 in right.items():
                if rr == r and (rr2, ss) in right:
                    c = (l2, q2, ss, rr2)
                    if c not in seen:
                        seen.add(c)
                        stack.append(c)
        else:
            r2 = right.get((r, w))
            if r2 is None:
                return None
            for (ll, xx), ll2 in left.items():
                if ll == l:
                    # mirror: the right automaton pops s2, left pushes w
                    c = (ll2, q2, xx, r2)
                    if c not in seen:
                        seen.add(c)
                        stack.append(c)
    return contexts

def decide(tm):
    global table, n_states, n_symbols
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    if n_states > 3 or n_symbols != 2:
        return None
    # try several n-gram window sizes
    for n in range(0, 7):
        ltab, nL, _ = _build_ngram(n)
        rtab, nR, _ = _build_ngram(n)
        left = {}
        right = {}
        for i in range(nL):
            for x in (0, 1):
                if (i, x) in ltab:
                    left[(i, x)] = ltab[(i, x)]
                else:
                    left[(i, x)] = None
        for i in range(nR):
            for x in (0, 1):
                if (i, x) in rtab:
                    right[(i, x)] = rtab[(i, x)]
                else:
                    right[(i, x)] = None
        # context closure
        start = (0, 0, 0, 0)
        seen = {start}
        stack = [start]
        contexts = []
        ok = True
        while stack and ok:
            l, q, s, r = stack.pop()
            contexts.append([l, q, s, r])
            if (q, s) not in table:
                ok = False
                break
            w, move, q2 = table[(q, s)]
            if move == 1:
                l2 = left.get((l, w))
                if l2 is None:
                    ok = False
                    break
                for (rr, ss), rr2 in list(right.items()):
                    if rr == r and rr2 is not None:
                        c = (l2, q2, ss, rr2)
                        if c not in seen:
                            seen.add(c)
                            stack.append(c)
            else:
                r2 = right.get((r, w))
                if r2 is None:
                    ok = False
                    break
                for (ll, xx), ll2 in list(left.items()):
                    if ll == l and ll2 is not None:
                        c = (ll2, q2, xx, r2)
                        if c not in seen:
                            seen.add(c)
                            stack.append(c)
        if ok and len(contexts) <= 200000 and nL <= 5000 and nR <= 5000:
            cert = {
                "kind": "cps",
                "left": [[ltab.get((i, x), None) for x in (0, 1)] for i in range(nL)],
                "right": [[rtab.get((i, x), None) for x in (0, 1)] for i in range(nR)],
                "contexts": contexts,
            }
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    return None
