import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(100000)

MACHINES = None

# ----- helpers -------------------------------------------------------------

def parse_table(tm):
    tbl, ns, nsym = parse(tm)
    return tbl, ns, nsym

def blank_macros():
    # one blank cell, at tape position 0
    return 0

def xtab_lookup(t, s):
    v = t.get((s, 0))
    return v

# ----- certificate emitters ----------------------------------------------

def emit_cycle(tm):
    try:
        halted, steps, state, pos, tape = run(tm, 200)
        if halted:
            return None
    except Exception:
        return None
    # find a repeated (state, pos) pair among recent steps
    tbl, ns, nsym = parse(tm)
    cfg = {}
    pos = 0
    tape = {}
    state = 0
    for i in range(0, 20000):
        if (state, pos) in cfg:
            T = cfg[(state, pos)]
            P = i - T
            if T + P <= 100000:
                # build a cycle certificate
                # simulate T and P
                halted, steps, st, p, tp = run(tm, T)
                if halted:
                    return None
                # snapshot
                snap = dict(tp)
                # simulate P more
                # construct by re-running
                try:
                    # re-run with tape snapshot
                    import copy
                    # use run for T then continue manually
                    def step(state, pos, tp):
                        v = tp.get(pos, 0)
                        if (state, v) not in tbl:
                            return None
                        w, mv, q2 = tbl[(state, v)]
                        if w:
                            tp[pos] = w
                        else:
                            tp.pop(pos, None)
                        pos += mv
                        return q2, pos, tp
                    cur_state, cur_pos, cur_tape = state, pos, dict(tape)
                    # resume from initial
                    st2, p2, tp2 = 0, 0, {}
                    for _ in range(T):
                        r = step(st2, p2, tp2)
                        if r is None:
                            return None
                        st2, p2, tp2 = r
                    if (st2, p2) != (state, pos):
                        return None
                    snap = dict(tp2)
                    lo = hi = p2
                    for _ in range(P):
                        r = step(st2, p2, tp2)
                        if r is None:
                            return None
                        st2, p2, tp2 = r
                        if p2 < lo: lo = p2
                        if p2 > hi: hi = p2
                    if (st2, p2) != (state, pos):
                        return None
                    # check tape relation
                    d = p2 - pos
                    for y in range(lo, hi + 1):
                        a = snap.get(y, 0)
                        b = tp2.get(y + d, 0)
                        if a != b:
                            return None
                    if d > 0:
                        for y in range(hi + 1, hi + 1 + 100):
                            if tp2.get(y, 0) != 0:
                                return None
                    if d < 0:
                        for y in range(lo - 100, lo):
                            if tp2.get(y, 0) != 0:
                                return None
                    return {"kind": "cycle", "t": T, "p": P}
                except Exception:
                    return None
        cfg[(state, pos)] = i
        r = step(state, pos, tape)
        if r is None:
            return None
        state, pos, tape = r
    return None

# ----- CPS search ----------------------------------------------------------
# enumerate small automata for one half-tape, canonical BFS order

def automata_gen(max_states, max_len=None):
    """yield (states, table) for deterministic automata over {0,1} where
    state 0 loops on 0. table: list of (t0, t1) with None possible."""
    # canonical BFS enumeration: build tables level by level
    # represent table as tuple of pairs
    out = []
    # start: single state looping on 0
    seen = set()
    frontier = [((0, 0),)]
    seen.add(frontier[0])
    while frontier:
        cur_level = frontier
        frontier = []
        for tab in cur_level:
            n = len(tab)
            if n > max_states:
                continue
            out.append(tab)
            # extend by one state
            new_tabs = []
            for a in (0, 1):
                for b in (0, 1):
                    if a == 0 and b == 0:
                        # state 0 loops on 0 already, but extension state 0 cannot be
                        # redefined; skip re-extension of state 0
                        continue
                    nt = tab + ((a, b),)
                    if nt in seen:
                        continue
                    seen.add(nt)
                    new_tabs.append(nt)
            # merge into frontier with dedup
            for nt in new_tabs:
                if nt not in frontier:
                    frontier.append(nt)
        if len(out) > 200000:
            break
    return out

def build_context_closure(tbl, ns, left, right):
    """closed set of contexts [l, q, s, r]. Returns set or None."""
    # state 0 of automata is blank half-tape
    # context: (l, q, s, r)
    ctx = {(0, 0, 0, 0)}
    changed = True
    while changed:
        changed = False
        new = set()
        for (l, q, s, r) in ctx:
            tr = tbl.get((q, s))
            if tr is None:
                return None  # halting context
            w, mv, q2 = tr
            if mv > 0:
                l2 = left[l][w]
                if l2 is None:
                    return None
                # for every (r2, s2) with right[r2][s2] == r
                for r2 in range(len(right)):
                    for s2 in (0, 1):
                        if right[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                new.add(c)
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(left)):
                    for s2 in (0, 1):
                        if left[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                new.add(c)
        if new:
            ctx |= new
            changed = True
    if len(ctx) > 200000:
        return None
    if len(ctx) > 5000:
        return None
    return ctx

def try_cps(tm):
    tbl, ns, nsym = parse(tm)
    # enumerate automata for left and right
    # try 1,2,3 states
    for nleft in (1, 2, 3):
        for nright in (1, 2, 3):
            # generate all tables for left with nleft states
            lefts = [tab for tab in automata_gen(nleft)]
            rights = [tab for tab in automata_gen(nright)]
            for lt in lefts:
                for rt in rights:
                    ctx = build_context_closure(tbl, ns, lt, rt)
                    if ctx is not None:
                        # check kernel limits
                        if len(ctx) > 200000 or len(lt) > 5000 or len(rt) > 5000:
                            continue
                        cert = {"kind": "cps",
                                "left": [[lt[i][0], lt[i][1]] for i in range(len(lt))],
                                "right": [[rt[i][0], rt[i][1]] for i in range(len(rt))],
                                "contexts": [[c[0], c[1], c[2], c[3]] for c in ctx]}
                        try:
                            check(tm, cert)
                            return cert
                        except Reject:
                            pass
    return None

# ----- main ---------------------------------------------------------------

def decide(tm: str):
    c = emit_cycle(tm)
    if c is not None:
        try:
            check(tm, c)
            return c
        except Reject:
            pass
    c = try_cps(tm)
    if c is not None:
        try:
            check(tm, c)
            return c
        except Reject:
            pass
    return None
