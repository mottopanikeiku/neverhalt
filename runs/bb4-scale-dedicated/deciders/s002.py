"""Search small half-tape DFAs and closed-context fixpoints for the holdouts."""

from neverhalt.tm import parse, run
from neverhalt.kernel import Reject, check

import itertools


# ---------- machine tables ----------

def build(tm):
    table, ns, nsym = parse(tm)
    # table[(state, symbol)] = (write, move, next); absent => halt
    return table, ns, nsym


def step_cfg(table, q, s, pos, tape, nsym):
    key = (q, s)
    if key not in table:
        return None
    w, mv, q2 = table[key]
    return w, mv, q2


def apply_write(tape, pos, w):
    tape[pos] = w


def read_cell(tape, pos, nsym):
    return tape.get(pos, 0)


# ---------- DFA enumeration ----------

def enumerate_dfa_tables(n_states, nsym):
    """All deterministic tables where state 0 loops on symbol 0.
    table[i][x] = j (0..n-1) or None (dead) -- but we forbid None for now
    and later prune.  Return list of (n_states, tuple-of-rows)."""
    rows = []
    for combo in itertools.product(range(n_states), repeat=nsym):
        row = list(combo)
        # state 0 loops on symbol 0
        if row[0] != 0:
            continue
        rows.append(tuple(row))
    tables = []
    for t in itertools.product(rows, repeat=n_states):
        tables.append(t)
    return tables


def dfa_delta(table, state, sym):
    return table[state][sym]


# ---------- left half-tape push ----------
# When the head moves right, the written symbol w is pushed onto the left
# half-tape: the left automaton reads it as its next input symbol.
# We read the left half-tape from far away towards the head, so the *most
# recently written* cell is consumed first.  A push of w means: the new left
# automaton state is left[l][w].

def left_step(table_l, l, w):
    return table_l[l][w]


def right_pop_enumerate(table_r, r, s):
    """All pairs (r2, s2) with right[r2][s2] == r.  This is the pop: the
    current cell s2 sits right of the head and, after the head moves right,
    it becomes the new head symbol; the remainder of the right half-tape is
    summarised by r2."""
    out = []
    for r2 in range(len(table_r)):
        for s2 in range(len(table_r[0])):
            if table_r[r2][s2] == r:
                out.append((r2, s2))
    return out


# ---------- closed context fixpoint ----------

def closure(table, table_l, table_r, nsym, cap=200000):
    """Start from [0,0,0,0]; iterate the rule until stable.
    Returns the set of contexts, or None if a halting context is forced."""
    ctx = set()
    ctx.add((0, 0, 0, 0))
    frontier = [(0, 0, 0, 0)]
    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            key = (q, s)
            if key not in table:
                return None  # halting context forced
            w, mv, q2 = table[key]
            if mv > 0:
                l2 = table_l[l][w]
                if l2 is None:
                    return None
                for (r2, s2) in right_pop_enumerate(table_r, r, s):
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        ctx.add(c)
                        nxt.append(c)
            else:
                r2 = table_r[r][w]
                if r2 is None:
                    return None
                for (l2, s2) in left_pop_enumerate(table_l, l, s):
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        ctx.add(c)
                        nxt.append(c)
            if len(ctx) > cap:
                return None
        frontier = nxt
    return ctx


def left_pop_enumerate(table_l, l, s):
    out = []
    for l2 in range(len(table_l)):
        for s2 in range(len(table_l[0])):
            if table_l[l2][s2] == l:
                out.append((l2, s2))
    return out


# ---------- certificate construction ----------

def make_cps_cert(table, table_l, table_r, ctx):
    nf = len(table_l)
    nr = len(table_r)
    left = [[table_l[i][x] for x in range(len(table_l[0]))] for i in range(nf)]
    right = [[table_r[i][x] for x in range(len(table_r[0]))] for i in range(nr)]
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    return {"kind": "cps", "left": left, "right": right, "contexts": contexts}


# ---------- translated cycle fallback ----------

def try_tcycle(tm, max_steps=100000):
    table, ns, nsym = build(tm)
    # run and record snapshots
    tape = {}
    q = 0
    pos = 0
    snapshots = []
    try:
        for t in range(max_steps):
            # record
            snapshots.append((q, pos, dict(tape)))
            key = (q, tape.get(pos, 0))
            if key not in table:
                return None
            w, mv, q2 = table[key]
            tape[pos] = w
            pos += mv
            q = q2
    except Exception:
        return None
    # look for a lap T -> T+P with same state and matching window
    n = len(snapshots)
    for T in range(n):
        qT, pT, tT = snapshots[T]
        for P in range(1, n - T):
            qP, pP, tP = snapshots[T + P]
            if qT != qP:
                continue
            d = pP - pT
            # window of positions read during the lap
            lo = min(pT, pP)
            hi = max(pT, pP)
            ok = True
            for y in range(lo, hi + 1):
                if tP.get(y + d, 0) != tT.get(y, 0):
                    ok = False
                    break
            if not ok:
                continue
            if d > 0:
                for y in range(hi + 1, hi + 1 + d):
                    if tP.get(y, 0) != 0:
                        ok = False
                        break
            elif d < 0:
                for y in range(lo, lo - d):
                    if tP.get(y, 0) != 0:
                        ok = False
                        break
            if ok:
                return {"kind": "cycle", "t": T, "p": P}
    return None


# ---------- main ----------

def decide(tm):
    # quick translated-cycle scan first
    cert = try_tcycle(tm)
    if cert is not None:
        try:
            check(tm, cert)
            return cert
        except Reject:
            pass

    table, ns, nsym = build(tm)
    # candidate sizes
    for n in (1, 2, 3):
        # enumerate left tables
        for rows_l in enumerate_dfa_tables(n, nsym):
            for rows_r in enumerate_dfa_tables(n, nsym):
                # build tables with None where unused?  For simplicity use
                # full deterministic tables; the kernel allows null entries,
                # but we start with total tables and shrink later.
                tl = rows_l
                tr = rows_r
                ctx = closure(table, tl, tr, nsym)
                if ctx is not None:
                    # shrink: keep only used transitions
                    used_l = set()
                    used_r = set()
                    for (l, q, s, r) in ctx:
                        used_l.add(l)
                        used_r.add(r)
                    # verify kernel accepts
                    cert = make_cps_cert(table, tl, tr, ctx)
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
    return None


if __name__ == "__main__":
    import sys
    tm = sys.argv[1] if len(sys.argv) > 1 else "0RB0LA_1RC---_1LC1RD_1RB1LA"
    c = decide(tm)
    print(c if c is not None else "none")
