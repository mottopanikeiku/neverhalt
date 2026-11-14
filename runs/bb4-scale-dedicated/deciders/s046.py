import sys
from collections import deque
from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

def build_table(tm):
    table, ns, nsym = parse(tm)
    return table, ns, nsym

def run_machine(tm, steps):
    from neverhalt.tm import run
    return run(tm, steps)

def find_cycle(tm, max_steps=20000):
    # Look for small translated cycles: period-2 bouncing patterns.
    try:
        import neverhalt.tm as tm_mod
        table, ns, nsym = tm_mod.parse(tm)
    except Exception:
        return None
    # Simulate and look for a state+position repeat with matching tape window.
    from neverhalt.tm import run
    halted, steps, state, pos, tape = run(tm, max_steps)
    if halted:
        return None
    # Re-simulate recording configurations
    try:
        table2, ns2, nsym2 = parse(tm)
    except Exception:
        return None
    # manual simulation to record configs
    tape = {}
    st = 0
    p = 0
    configs = []
    for i in range(max_steps):
        configs.append((st, p, dict(tape)))
        key = (st, p)
        if key in [c[:2] for c in configs[:-1]]:
            pass
        try:
            w, mv, nxt = table2[(st, tape.get(p, 0))]
        except Exception:
            return None
        tape[p] = w
        p += mv
        st = nxt
        if st is None or st >= ns2:
            return None
    # search for translated cycle: state repeat with shift
    for i in range(len(configs)):
        for j in range(i+1, len(configs)):
            if configs[i][0] != configs[j][0]:
                continue
            d = configs[j][1] - configs[i][1]
            if d == 0:
                continue
            # check tape translation
            ti = configs[i][2]
            tj = configs[j][2]
            ok = True
            for y in range(min(ti.keys() + [-50]), max(ti.keys() + [50])):
                if ti.get(y, 0) != tj.get(y + d, 0):
                    ok = False
                    break
            if ok:
                T = i
                P = j - i
                if T + P <= 100000:
                    try:
                        cert = {"kind": "cycle", "t": T, "p": P}
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
    return None

def enumerate_dfas(max_states, nsym):
    # Yield transition tables: list of lists, index = state, table[state][sym] = next or None
    # State 0 loops on symbol 0.
    # Represent as tuple of tuples.
    results = []
    # BFS over partial tables
    def rec(table, nstates):
        # table is list of lists of length nsym
        if len(table) == nstates:
            results.append(tuple(tuple(row) for row in table))
            return
        # add a new state
        newrow = [None] * nsym
        rec(table + [newrow], nstates)
        # fill entries
        for s in range(nstates):
            for sym in range(nsym):
                if table[s][sym] is None:
                    for target in range(nstates + 1):
                        nt = [list(r) for r in table]
                        nt[s][sym] = target
                        if s == 0 and sym == 0 and target != 0:
                            continue
                        rec(tuple(tuple(r) for r in nt), nstates)
    # iterative generation up to max_states
    for n in range(1, max_states + 1):
        # generate all tables with n states
        def gen(n):
            out = []
            def rec2(table, filled):
                if len(table) == n:
                    out.append(tuple(tuple(r) for r in table))
                    return
                # next state to fill
                # simpler: fill row by row
                if filled == 0:
                    # first row: state 0, symbol 0 must be 0
                    # enumerate rest
                    def fill_row(state, sym, table):
                        if state == n:
                            out.append(tuple(tuple(r) for r in table))
                            return
                        if sym == nsym:
                            fill_row(state + 1, 0, table)
                            return
                        for target in range(n):
                            if state == 0 and sym == 0 and target != 0:
                                continue
                            nt = [list(r) for r in table]
                            nt[state][sym] = target
                            fill_row(state, sym + 1, nt)
                    t0 = [[None] * nsym for _ in range(n)]
                    t0[0][0] = 0
                    fill_row(0, 1, t0)
                    return
                return
            # use recursive fill
            table = [[None] * nsym for _ in range(n)]
            table[0][0] = 0
            def fill(state, sym):
                if state == n:
                    out.append(tuple(tuple(r) for r in table))
                    return
                if sym == nsym:
                    fill(state + 1, 0)
                    return
                for target in range(n):
                    if state == 0 and sym == 0 and target != 0:
                        continue
                    table[state][sym] = target
                    fill(state, sym + 1)
                    table[state][sym] = None
            fill(0, 1)
            return out
        for t in gen(n):
            yield t

def build_cps(tm, max_states=3):
    table2, ns2, nsym2 = parse(tm)
    # left DFA reads cells left of head from far away towards head (right to left in tape coords)
    # right DFA reads cells right of head from far away towards head (left to right in tape coords)
    # For CPS we need: left automaton on symbol w when moving right; right automaton on symbol w when moving left.
    # Try small DFAs for left; right derived from machine transitions.
    # Simplification: search over left automaton tables; right automaton must accept the
    # language of "cells to the right that lead back". Instead of full search, we try
    # n-gram style right automata too: right[r2][s2] = r means reading s2 from far right
    # towards head leads to state r2 from r.
    # We enumerate left and right DFAs jointly up to max_states each.
    for left_t in enumerate_dfas(max_states, 2):
        # right automaton: try n-gram DFA of size up to max_states
        # For a right move: l2 = left[l][w]; context [l2, q2, s2, r2] for every (r2,s2) with right[r2][s2]==r
        # For a left move: r2 = right[r][w]; context [l2, q2, s2, r2] for every (l2,s2) with left[l2][s2]==l
        # We'll try right automata as n-gram DFAs: state = last k cells, but bounded by max_states.
        # Simpler: enumerate right DFAs as well, but that is expensive. Instead, for each left DFA
        # we construct the minimal right DFA that accepts the "return" language by BFS.
        # Given time, try right = identity-ish DFA: right[r][x] = r for all x (memoryless), and
        # also right that remembers one symbol: right[i][x] = x (if x < max_states).
        right_candidates = []
        # memoryless
        right_candidates.append(tuple(tuple([0]*2) for _ in range(1)))
        # one-symbol memory: state = last symbol
        if max_states >= 2:
            right_candidates.append(tuple(tuple([0,1]) for _ in range(2)))
        if max_states >= 3:
            right_candidates.append(tuple(tuple([0,1,2]) for _ in range(3)))
        for right_t in right_candidates:
            cert = try_cps(tm, table2, ns2, left_t, right_t)
            if cert:
                return cert
    return None

def try_cps(tm, table2, ns2, left_t, right_t):
    nleft = len(left_t)
    nright = len(right_t)
    # context: (l, q, s, r)
    contexts = set()
    contexts.add((0, 0, 0, 0))
    changed = True
    while changed and len(contexts) <= 200000:
        changed = False
        new = set(contexts)
        for (l, q, s, r) in contexts:
            if q >= ns2:
                return None
            key = (q, s)
            if key not in table2:
                return None  # halting context -> reject
            w, mv, q2 = table2[key]
            if mv == 1:
                if l >= nleft or left_t[l][w] is None:
                    return None
                l2 = left_t[l][w]
                # for every (r2, s2) with right_t[r2][s2] == r
                for r2 in range(nright):
                    if r2 >= len(right_t):
                        continue
                    row = right_t[r2]
                    for s2 in range(len(row)):
                        if row[s2] == r:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in new:
                                new.add(ctx)
                                changed = True
            else:
                if r >= nright or right_t[r][w] is None:
                    return None
                r2 = right_t[r][w]
                for l2 in range(nleft):
                    if l2 >= len(left_t):
                        continue
                    row = left_t[l2]
                    for s2 in range(len(row)):
                        if row[s2] == l:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in new:
                                new.add(ctx)
                                changed = True
        contexts = new
    if len(contexts) > 200000:
        return None
    # check no halting context
    for (l, q, s, r) in contexts:
        if (q, s) not in table2:
            return None
    # build certificate
    left = [[None if x is None else int(x) for x in row] for row in left_t]
    right = [[None if x is None else int(x) for x in row] for row in right_t]
    ctx_list = [[int(l), int(q), int(s), int(r)] for (l, q, s, r) in contexts]
    cert = {"kind": "cps", "left": left, "right": right, "contexts": ctx_list}
    try:
        from neverhalt.kernel import check as kcheck
        kcheck(tm, cert)
        return cert
    except Exception:
        return None

def decide(tm: str):
    # quick cycle search first
    c = find_cycle(tm, 3000)
    if c:
        return c
    # CPS search
    try:
        cert = build_cps(tm, max_states=3)
        if cert:
            return cert
    except Exception:
        pass
    return None

NAME = "fsm-cps-search"
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(decide(sys.argv[1]))
