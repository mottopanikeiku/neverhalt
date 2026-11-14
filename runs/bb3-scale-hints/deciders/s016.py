import json, sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Neverhalt kernel helpers (import as given)
try:
    from neverhalt.kernel import check as _check
except Exception:
    _check = None

# ---------- core machine helpers ----------
def machine_info(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states, n_symbols

# Build a transition function with explicit halting info.
def trans(table, n_states, q, s):
    # table[(q,s)] = (w, move, q2) or absent (halt)
    return table.get((q, s))

# ---------- bounded simulation for cycle search ----------
def simulate_trace(tm, max_steps):
    table, n_states, n_symbols = parse(tm)
    tape = {}
    q = 0
    pos = 0
    steps = 0
    trace = []
    while steps < max_steps:
        t = table.get((q, tape.get(pos, 0)))
        if t is None:
            return trace, steps, True
        w, mv, q2 = t
        tape[pos] = w
        pos += mv
        q = q2
        steps += 1
        trace.append((q, pos, dict(tape)))
    return trace, steps, False

# ---------- cycle detection (small lap) ----------
def find_cycle(tm, budget=100000):
    table, n_states, n_symbols = parse(tm)
    tape = {}
    q = 0
    pos = 0
    steps = 0
    # store seen (state, pos) with tape hash? too heavy. Use bounded replay.
    # Record positions of each (state,pos) with tape snapshot for candidate matches.
    seen = {}
    # We simulate and look for repeated (state, pos) with equal nearby tape.
    # Track full tape dict each step is heavy but budget <= 100000 and tape small.
    while steps < budget:
        t = table.get((q, tape.get(pos, 0)))
        if t is None:
            return None
        w, mv, q2 = t
        tape[pos] = w
        pos += mv
        q = q2
        steps += 1
        key = (q, pos)
        # naive: only check recent repeats to keep bounded
        if key in seen:
            T = seen[key]
            # replay T..steps to check tape equality
            if verify_lap(tm, T, steps - T):
                return (T, steps - T)
        seen[key] = steps
    return None

def verify_lap(tm, T, P):
    table, n_states, n_symbols = parse(tm)
    # simulate to T
    tape = {}
    q = 0
    pos = 0
    steps = 0
    while steps < T:
        t = table.get((q, tape.get(pos, 0)))
        if t is None:
            return False
        w, mv, q2 = t
        tape[pos] = w
        pos += mv
        q = q2
        steps += 1
    # snapshot
    snap1 = dict(tape)
    q1 = q
    p1 = pos
    lo = pos
    hi = pos
    # lap
    for _ in range(P):
        t = table.get((q, tape.get(pos, 0)))
        if t is None:
            return False
        w, mv, q2 = t
        tape[pos] = w
        pos += mv
        q = q2
        lo = min(lo, pos)
        hi = max(hi, pos)
    if q != q1:
        return False
    d = pos - p1
    # compare
    ok = True
    for y in range(lo, hi + 1):
        a = snap1.get(y, 0)
        b = tape.get(y + d, 0)
        if a != b:
            ok = False
            break
    if not ok:
        return False
    if d > 0:
        for y in range(hi + 1, hi + d + 1):
            if tape.get(y, 0) != 0:
                return False
    if d < 0:
        for y in range(lo + d, lo):
            if tape.get(y, 0) != 0:
                return False
    return True

# ---------- CPS construction ----------
def build_cps(tm, max_states=5000, max_ctx=200000):
    table, n_states, n_symbols = parse(tm)
    # states: 0..n_states-1
    # symbols: 0/1
    # For each (q,s) get (w, mv, q2) or halt.
    trans = {}
    halt = set()
    for q in range(n_states):
        for s in (0, 1):
            t = table.get((q, s))
            if t is None:
                halt.add((q, s))
            else:
                w, mv, q2 = t
                trans[(q, s)] = (w, mv, q2)

    contexts = set()
    # automata as dicts: left[l][x] = next or None
    # start with all-blank: state 0 loops on 0
    left = {0: {0: 0}}
    right = {0: {0: 0}}
    for x in (0, 1):
        left[0].setdefault(x, None)
        right[0].setdefault(x, None)
    left[0][0] = 0
    right[0][0] = 0

    init = (0, 0, 0, 0)
    contexts.add(init)
    changed = True
    while changed:
        changed = False
        new = set()
        for (l, q, s, r) in contexts:
            t = trans.get((q, s))
            if t is None:
                # halting context: reject
                return None
            w, mv, q2 = t
            if mv == 1:
                l2 = left[l].get(w)
                if l2 is None:
                    return None
                # every (r2,s2) with right[r2][s2] == r
                for r2 in list(right.keys()):
                    for s2 in (0, 1):
                        if right[r2].get(s2) == r:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                new.add(ctx)
            else:
                r2 = right[r].get(w)
                if r2 is None:
                    return None
                for l2 in list(left.keys()):
                    for s2 in (0, 1):
                        if left[l2].get(s2) == l:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                new.add(ctx)
        if new:
            contexts |= new
            changed = True
        if len(contexts) > max_ctx:
            return None
    # Build certificate
    left_tab = []
    for i in range(max(left.keys()) + 1):
        row = []
        for x in (0, 1):
            row.append(left[i].get(x))
        left_tab.append(row)
    right_tab = []
    for i in range(max(right.keys()) + 1):
        row = []
        for x in (0, 1):
            row.append(right[i].get(x))
        right_tab.append(row)
    ctx_list = [[a, b, c, d] for (a, b, c, d) in contexts]
    return {"kind": "cps", "left": left_tab, "right": right_tab, "contexts": ctx_list}

# ---------- n-gram CPS: automata remember last n cells ----------
def ngram_cps(tm, n, max_ctx=200000):
    table, n_states, n_symbols = parse(tm)
    # automaton state = tuple of last n bits (0..2^n-1), start = all zero
    def make_trans(n):
        size = 1 << n
        tab = []
        for st in range(size):
            row = []
            for x in (0, 1):
                # shift left, append x
                ns = ((st << 1) | x) & (size - 1)
                row.append(ns)
            tab.append(row)
        return tab, size
    ltab, lsz = make_trans(n)
    rtab, rsz = make_trans(n)

    contexts = set()
    init = (0, 0, 0, 0)
    contexts.add(init)
    changed = True
    while changed:
        changed = False
        new = set()
        for (l, q, s, r) in contexts:
            t = table.get((q, s))
            if t is None:
                return None
            w, mv, q2 = t
            if mv == 1:
                l2 = ltab[l][w]
                for r2 in range(rsz):
                    for s2 in (0, 1):
                        if rtab[r2][s2] == r:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                new.add(ctx)
            else:
                r2 = rtab[r][w]
                for l2 in range(lsz):
                    for s2 in (0, 1):
                        if ltab[l2][s2] == l:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                new.add(ctx)
        if new:
            contexts |= new
            changed = True
        if len(contexts) > max_ctx:
            return None
    ctx_list = [[a, b, c, d] for (a, b, c, d) in contexts]
    return {"kind": "cps", "left": ltab, "right": rtab, "contexts": ctx_list}

# ---------- main decider ----------
def decide(tm):
    # 1) cycle search
    try:
        lap = find_cycle(tm, 100000)
        if lap is not None:
            T, P = lap
            cert = {"kind": "cycle", "t": T, "p": P}
            try:
                check(tm, cert)
                return cert
            except Exception:
                pass
    except Exception:
        pass
    # 2) n-gram CPS for small n
    for n in (1, 2, 3, 4):
        try:
            cert = ngram_cps(tm, n)
            if cert is not None:
                try:
                    check(tm, cert)
                    return cert
                except Exception:
                    pass
        except Exception:
            pass
    # 3) search over small automata (1,2,3 states per side)
    cert = search_small_automata(tm)
    if cert is not None:
        return cert
    return None

# ---------- search over small automata ----------
def search_small_automata(tm, max_states=3, max_ctx=200000):
    table, n_states, n_symbols = parse(tm)
    # enumerate transition tables for a side with n states
    def all_tables(n):
        # each state has 2 transitions, each to one of n states or None (halt)
        results = []
        # encode: for each state, for each symbol, target in 0..n-1 or None
        choices = [list(range(n)) + [None] for _ in range(2 * n)]
        import itertools
        for combo in itertools.product(*choices):
            tab = [[combo[2 * i], combo[2 * i + 1]] for i in range(n)]
            # require state 0 loops on symbol 0
            if tab[0][0] != 0:
                continue
            results.append(tab)
        return results

    for n in range(1, max_states + 1):
        tabs = all_tables(n)
        for ltab in tabs:
            for rtab in tabs:
                # BFS canonical forms to reduce duplicates: use first-seen state order
                # simple: run closure directly
                contexts = set()
                init = (0, 0, 0, 0)
                contexts.add(init)
                ok = True
                changed = True
                while changed:
                    changed = False
                    new = set()
                    for (l, q, s, r) in contexts:
                        t = table.get((q, s))
                        if t is None:
                            ok = False
                            break
                        w, mv, q2 = t
                        if mv == 1:
                            l2 = ltab[l][w]
                            if l2 is None:
                                ok = False
                                break
                            for r2 in range(n):
                                for s2 in (0, 1):
                                    if rtab[r2][s2] == r:
                                        ctx = (l2, q2, s2, r2)
                                        if ctx not in contexts:
                                            new.add(ctx)
                        else:
                            r2 = rtab[r][w]
                            if r2 is None:
                                ok = False
                                break
                            for l2 in range(n):
                                for s2 in (0, 1):
                                    if ltab[l2][s2] == l:
                                        ctx = (l2, q2, s2, r2)
                                        if ctx not in contexts:
                                            new.add(ctx)
                    if not ok:
                        break
                    if new:
                        contexts |= new
                        changed = True
                    if len(contexts) > max_ctx:
                        ok = False
                        break
                if not ok:
                    continue
                # ensure init present and no halting context (already checked)
                ctx_list = [[a, b, c, d] for (a, b, c, d) in contexts]
                cert = {"kind": "cps", "left": ltab, "right": rtab, "contexts": ctx_list}
                try:
                    check(tm, cert)
                    return cert
                except Exception:
                    continue
    return None

if __name__ == "__main__":
    import sys
    tm = sys.argv[1]
    print(json.dumps(decide(tm)))
}
