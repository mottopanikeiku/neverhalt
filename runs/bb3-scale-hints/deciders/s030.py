import json
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---- helpers ----

def table(tm):
    t, ns, nsl = parse(tm)
    return t, ns, nsl

def key(state, sym):
    return (state, sym)

def step(t, ns, nsl, st, sy):
    return t.get(key(st, sy))

# ---- basic simulation ----

def sim(tm, steps):
    t, ns, nsl = table(tm)
    tape = {}
    st = 0
    pos = 0
    hist = []
    for _ in range(steps):
        hist.append((st, pos, dict(tape)))
        tr = t.get(key(st, 0 if pos not in tape else tape[pos]))
        if tr is None:
            return hist, True
        w, mv, st = tr
        if w:
            tape[pos] = w
        pos += mv
    return hist, False

# ---- cycle certificate ----

def try_cycle(tm, max_steps=100000):
    t, ns, nsl = table(tm)
    tape = {}
    st = 0
    pos = 0
    states = []
    positions = []
    tapes = []
    for i in range(max_steps + 1):
        states.append(st)
        positions.append(pos)
        tapes.append(dict(tape))
        tr = t.get(key(st, 0 if pos not in tape else tape[pos]))
        if tr is None:
            return None
        w, mv, st = tr
        if w:
            tape[pos] = w
        pos += mv
    # look for repeated (state, pos) pairs
    seen = {}
    for i, (s, p) in enumerate(zip(states, positions)):
        if (s, p) in seen:
            j = seen[(s, p)]
            if i - j > 0:
                T = j
                P = i - j
                d = positions[i] - positions[j]
                lo = min(positions[j:i+1])
                hi = max(positions[j:i+1])
                # check tape shift condition
                ok = True
                for y in range(lo, hi + 1):
                    a = tapes[j].get(y, 0)
                    b = tapes[i].get(y + d, 0)
                    if a != b:
                        ok = False
                        break
                if ok:
                    if d > 0:
                        for y in range(hi + 1, hi + d + 1):
                            if tapes[i].get(y, 0) != 0:
                                ok = False
                                break
                    elif d < 0:
                        for y in range(lo + d, lo):
                            if tapes[i].get(y, 0) != 0:
                                ok = False
                                break
                if ok:
                    cert = {"kind": "cycle", "t": T, "p": P}
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
        seen[(s, p)] = i
    return None

# ---- CPS: ngram automata from the hint ----

def build_ngram(n):
    # states 0..n-1, state 0 loops on 0, others: any symbol -> 0? 
    # we build automaton that remembers last n cells (as value) 
    # state i means we have seen i cells; but we need deterministic 
    # transition: on symbol x, state = (state*2 + x) mod (2^n)? 
    # For simplicity: DFA over {0,1} with n bits, state 0 on loop 0.
    if n == 0:
        return [[None, None]]
    size = 2 ** n
    tab = []
    for s in range(size):
        row = []
        for x in range(2):
            if s == 0 and x == 0:
                row.append(0)
            else:
                row.append(((s << 1) | x) & (size - 1))
        tab.append(row)
    return tab

def build_1gram():
    # state 0 loop 0; on 1 -> state 1; state 1 on 0 -> 0, on 1 -> 1
    return [[0, 1], [0, 1]]

def build_2gram():
    # remember last 2 cells? simple: state = last cell value
    return [[0, 1], [0, 1]]

def build_3gram():
    # 2-bit shift register
    return build_ngram(2)

def build_4gram():
    return build_ngram(3)

def build_5gram():
    return build_ngram(4)

AUTOS = {
    1: build_1gram,
    2: build_2gram,
    3: build_3gram,
    4: build_4gram,
    5: build_5gram,
}

def cps_fixpoint(tm, left, right):
    t, ns, nsl = table(tm)
    # contexts: (l, q, s, r)
    contexts = set()
    start = (0, 0, 0, 0)
    contexts.add(start)
    frontier = [start]
    max_states = 5000
    max_ctx = 200000
    while frontier:
        if len(contexts) > max_ctx:
            return None
        new = []
        for (l, q, s, r) in frontier:
            tr = t.get(key(q, s))
            if tr is None:
                return None
            w, mv, q2 = tr
            if mv == 1:  # right move
                l2 = left[l][w] if w < len(left[l]) else None
                if l2 is None:
                    return None
                # for every (r2, s2) with right[r2][s2] == r
                for r2 in range(len(right)):
                    for s2 in range(len(right[r2])):
                        if right[r2][s2] == r:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                contexts.add(ctx)
                                new.append(ctx)
            else:  # left move
                r2 = right[r][w] if w < len(right[r]) else None
                if r2 is None:
                    return None
                for l2 in range(len(left)):
                    for s2 in range(len(left[l2])):
                        if left[l2][s2] == l:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                contexts.add(ctx)
                                new.append(ctx)
        frontier = new
        if len(contexts) > max_ctx:
            return None
    # convert to certificate
    left_tab = [row[:] for row in left]
    right_tab = [row[:] for row in right]
    # ensure state 0 loops on 0
    if left_tab[0][0] != 0:
        left_tab[0][0] = 0
    if right_tab[0][0] != 0:
        right_tab[0][0] = 0
    cert = {
        "kind": "cps",
        "left": left_tab,
        "right": right_tab,
        "contexts": [[l, q, s, r] for (l, q, s, r) in contexts],
    }
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None

def try_cps(tm):
    t, ns, nsl = table(tm)
    for n in range(1, 6):
        try:
            left = AUTOS[n]()
            right = AUTOS[n]()
            cert = cps_fixpoint(tm, left, right)
            if cert is not None:
                return cert
        except Exception:
            continue
    return None

# ---- main decider ----

def decide(tm: str):
    try:
        c = try_cycle(tm)
        if c is not None:
            return c
    except Exception:
        pass
    try:
        c = try_cps(tm)
        if c is not None:
            return c
    except Exception:
        pass
    return None