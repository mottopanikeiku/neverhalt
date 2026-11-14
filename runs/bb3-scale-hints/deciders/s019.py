import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(100000)

# ----- helpers -----------------------------------------------------------
def build_machine_tables(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states, n_symbols

def build_halting_pairs(tm):
    """Return set of (q, s) for which the transition exists (non-halting)."""
    table, n_states, n_symbols = parse(tm)
    nonhalt = set()
    for q in range(n_states):
        for s in range(n_symbols):
            if (q, s) in table:
                nonhalt.add((q, s))
    return nonhalt, n_states, n_symbols

def mov(delta):
    return -1 if delta < 0 else 1

def build_cps(tm, left_tbl, right_tbl, n_states, n_symbols):
    """Run closed-context fixpoint for given left/right automaton tables.

    left_tbl[i][x] = j or None
    right_tbl[i][x] = j or None
    State 0 must be all-blank: left_tbl[0][0] == right_tbl[0][0] == 0.
    """
    nonhalt, nst, nsym = build_halting_pairs(tm)
    # context -> (l, q, s, r)
    ctx = {(0, 0, 0, 0)}
    changed = True
    while changed:
        changed = False
        new = set()
        for (l, q, s, r) in ctx:
            if (q, s) not in nonhalt:
                return None
            w, md, q2 = None, None, None
            table, _, _ = parse(tm)
            w, md, q2 = table[(q, s)]
            if md > 0:
                # stepping right: push w onto left automaton
                l2 = left_tbl[l][w]
                if l2 is None:
                    return None
                # popping from right: for all (r2, s2) with right[r2][s2]==r
                for r2 in range(len(right_tbl)):
                    row = right_tbl[r2]
                    for s2 in range(len(row)):
                        if row[s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                new.add(c)
            else:
                r2 = right_tbl[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(left_tbl)):
                    row = left_tbl[l2]
                    for s2 in range(len(row)):
                        if row[s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                new.add(c)
        if new:
            ctx |= new
            changed = True
    # convert to certificate form
    lefts = [[row[i] for i in range(len(row))] for row in left_tbl]
    rights = [[row[i] for i in range(len(row))] for row in right_tbl]
    contexts = [[c[0], c[1], c[2], c[3]] for c in ctx]
    return {"kind": "cps", "left": lefts, "right": rights, "contexts": contexts}

def make_blank_loop(n):
    tbl = [[None] * n for _ in range(n)]
    tbl[0][0] = 0
    return tbl

def try_search(tm):
    """Enumerate small left automata; for each, determinize the reverse of
    the right half-tape language and run the fixpoint."""
    n_states, n_symbols = parse(tm)[1], parse(tm)[2]
    nonhalt, nst, nsym = build_halting_pairs(tm)

    # 1) enumerate tiny automata for the left half-tape
    for n in (1, 2, 3):
        # states 0..n-1, state 0 loops on symbol 0
        for tbl_flat in enumerate_tables(n, nsym):
            # check state 0 loops on 0
            if tbl_flat[0][0] != 0:
                continue
            # build right automaton candidate: reverse-determinize language of
            # the right half-tape. Approximate by determinizing from right_tbl
            # as a "far-to-head" DFA of the same size (search).
            for n2 in (1, 2, 3):
                for rflat in enumerate_tables(n2, nsym):
                    if rflat[0][0] != 0:
                        continue
                    cert = build_cps(tm, tbl_flat, rflat, nst, nsym)
                    if cert is not None:
                        try:
                            check(tm, cert)
                            return cert
                        except Reject:
                            pass
    return None

def enumerate_tables(n, nsym):
    """All transition tables n x nsym with entries in 0..n-1 or None."""
    choices = [list(range(n)) + [None] for _ in range(nsym)]
    out = []
    def rec(row):
        if row == n:
            yield []
            return
        for combo in choices:
            yield from rec_extend(row, combo)
    def rec_extend(row, combo):
        # build row-major via recursion over cells
        pass
    # simpler: product of (n+1) options per cell
    import itertools
    cells = n * nsym
    opts = list(range(n)) + [None]
    for combo in itertools.product(opts, repeat=cells):
        tbl = [[combo[r * nsym + c] for c in range(nsym)] for r in range(n)]
        yield tbl

# 2) direct cycle/tcycle search for machines whose head wanders
def try_cycles(tm):
    halted, steps, state, pos, tape = run(tm, 20000)
    if halted:
        return None
    # try small T, P values
    for T in range(0, 3000):
        for P in range(1, 800):
            cert = {"kind": "cycle", "t": T, "p": P}
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
    return None

NAME = "cps_search"

def decide(tm: str) -> dict | None:
    try:
        cert = try_search(tm)
        if cert is not None:
            return cert
    except Exception:
        pass
    try:
        cert = try_cycles(tm)
        if cert is not None:
            return cert
    except Exception:
        pass
    return None

def rec_extend(row, combo):
    pass

def rec(row):
    return []
} 