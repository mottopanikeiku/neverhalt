import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(100000)

# ---- helpers ---------------------------------------------------------------

def parse_table(tm):
    table, ns, nsym = parse(tm)
    return table, ns, nsym

def blank_pos(tape):
    return {p: v for p, v in tape.items() if v != 0}

def step_machine(tm, tape, pos, state, limit):
    """advance the machine, returning (halted, steps, state, pos, tape)"""
    return run(tm, limit)

# ---- DFA enumeration -------------------------------------------------------

def canonical_states(n):
    """BFS-canonical state numbering for a DFA with n states, state 0 = blank loop."""
    return list(range(n))

def enumerate_dfa_tables(n, max_halting_states=1):
    """Enumerate every transition table for a half-tape DFA with states 0..n-1.
    left[i][x] is the state reached from i on symbol x, or None if that never happens.
    State 0 must satisfy t[0][0] == 0 (blank tape loops on 0).
    Returns a list of tables (list of 2 lists, length 2 each)."""
    # BFS-canonical: order states by first time they are forced as a successor.
    # We enumerate all assignments t[i][x] in {None, 0..n-1}, subject to t[0][0]=0.
    # To avoid symmetric duplicates we require state 0 to be the unique "root"
    # reachable by reading zeros from state 0; we enforce t[0][1] != 0 when n > 1
    # only as a symmetry break (mere symmetry, not correctness).
    res = []
    total = (n + 1) ** (2 * n)
    for code in range(total):
        t = [[None, None] for _ in range(n)]
        c = code
        ok = True
        for i in range(n):
            for x in range(2):
                c, r = divmod(c, n + 1)
                if r == 0:
                    t[i][x] = None
                else:
                    t[i][x] = r - 1
        if t[0][0] != 0:
            continue
        if n > 1 and t[0][1] == 0 and t[0][0] == 0:
            continue
        res.append(t)
        if len(res) >= 400000:
            break
    return res

def reverse_determinize(nfa):
    """Reverse-determinize an NFA given as a table (list over states, each a list
    over symbols of sets of successor states) into a DFA reading from far away
    towards the head. Returns a DFA table with None for dead transitions."""
    # states of the DFA are frozensets of NFA states; start with the "far away"
    # set, which for a right half-tape read from far away towards the head is
    # the set of NFA states reachable after reading zeros forever, i.e. the
    # subset of NFA states on cycles of 0. We approximate with the state set of
    # the whole NFA: start = all states, and transitions are the reverse image.
    # This is a valid far-to-head DFA for the reversed language.
    allstates = set(range(len(nfa)))
    start = frozenset(allstates)
    idx = {start: 0}
    table = []
    stack = [start]
    while stack:
        cur = stack.pop()
        row = []
        for x in range(2):
            img = set()
            for st in cur:
                for nx in nfa[st][x]:
                    img.add(nx)
            fs = frozenset(img)
            if not fs:
                row.append(None)
            else:
                if fs not in idx:
                    idx[fs] = len(table)
                    stack.append(fs)
                row.append(idx[fs])
        table.append(row)
    return table

def prune_halting_forced(t, halt_states):
    """Return True if the blank tape state 0 can reach any halting state via
    the DFA's transitions (reading cells left of the head, far to near)."""
    seen = {0}
    stack = [0]
    while stack:
        cur = stack.pop()
        for x in range(2):
            nx = t[cur][x]
            if nx is None:
                continue
            if nx in halt_states:
                return True
            if nx not in seen:
                seen.add(nx)
                stack.append(nx)
    return False

# ---- context closure -------------------------------------------------------

def closure_contexts(table, ns, left, right, q0=0, s0=0):
    """Compute the closed set of contexts [l, q, s, r] starting from [0,0,0,0].
    Returns (contexts, halting_found)."""
    # context: (l, q, s, r). q in 0..ns-1, s in 0..1, l/r automaton states.
    # Note: halting transitions have no entry in table.
    start = (0, q0, s0, 0)
    seen = {start}
    stack = [start]
    halt = False
    while stack:
        (l, q, s, r) = stack.pop()
        tr = table.get((q, s))
        if tr is None:
            halt = True
            continue
        w, mv, q2 = tr
        if mv == +1:
            l2 = left[l][w]
            if l2 is None:
                continue
            # for every pair (r2, s2) with right[r2][s2] == r
            for r2 in range(len(right)):
                for s2 in range(2):
                    if right[r2][s2] == r:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
        else:
            r2 = right[r][w]
            if r2 is None:
                continue
            for l2 in range(len(left)):
                for s2 in range(2):
                    if left[l2][s2] == l:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
    return seen, halt

# ---- main decider ----------------------------------------------------------

def decide(tm: str) -> dict | None:
    try:
        table, ns, nsym = parse_table(tm)
    except Exception:
        return None
    if ns > 5:
        return None
    # halting transitions: any (q, s) not in table is halting.
    halt_states = set(range(ns))  # not exactly: halting depends on symbol
    # enumerate DFA tables of size 1..3
    for n in (1, 2, 3):
        for left in enumerate_dfa_tables(n):
            # quick prune: state 0 must not reach a halting state through
            # the blank-tape path; actually the closure check is the real one.
            for n2 in (1, 2, 3):
                for right in enumerate_dfa_tables(n2):
                    try:
                        ctxs, halt = closure_contexts(table, ns, left, right)
                    except Exception:
                        continue
                    if halt:
                        continue
                    if len(ctxs) > 200000:
                        continue
                    # build certificate
                    left_cert = [[left[i][0], left[i][1]] for i in range(n)]
                    right_cert = [[right[i][0], right[i][1]] for i in range(n2)]
                    contexts_cert = [[l, q, s, r] for (l, q, s, r) in ctxs]
                    cert = {
                        "kind": "cps",
                        "left": left_cert,
                        "right": right_cert,
                        "contexts": contexts_cert,
                    }
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        continue
    return None

if __name__ == "__main__":
    import sys
    for tm in sys.argv[1:]:
        c = decide(tm)
        print(tm, "->", "cert" if c else "None")
