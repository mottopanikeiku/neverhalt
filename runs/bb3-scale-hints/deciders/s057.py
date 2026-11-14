import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# --- helpers -------------------------------------------------------------

def get_table(tm):
    table, n_states, n_symbols = parse(tm)
    trans = {}
    for (q, s), (w, mv, q2) in table.items():
        trans[(q, s)] = (w, mv, q2)
    return trans, n_states

# --- simple cycle search (cheap, catches short laps) ---------------------

def find_cycle(tm, max_steps=120000):
    table, n_states = get_table(tm)
    # simulate, record (state, pos) snapshots and tape snapshots
    tape = {}
    state = 0
    pos = 0
    steps = 0
    seen = {}
    # store (state,pos) -> (step, tape_snapshot)
    while steps <= max_steps:
        if (state, pos) in seen and steps - seen[(state, pos)][0] <= 100000:
            t0, snap0 = seen[(state, pos)]
            P = steps - t0
            # displacement: we need head displacement over lap; approximate by
            # re-simulating from t0 and tracking positions
            # we cannot rewind tape easily; instead re-simulate from scratch
            # to t0 and then P more steps, recording head positions.
            try:
                return _cycle_cert(tm, t0, P)
            except Exception:
                pass
            break
        seen[(state, pos)] = (steps, dict(tape))
        if (state, pos) not in trans_of(tm):
            break
        key = (state, pos)
        if key in trans_of(tm):
            w, mv, q2 = trans_of(tm)[key]
            tape[pos] = w
            pos += mv
            state = q2
            steps += 1
        else:
            break
    return None

def trans_of(tm):
    return get_table(tm)[0]

def _cycle_cert(tm, t0, P):
    table, n_states = get_table(tm)
    tape = {}
    state, pos = 0, 0
    steps = 0
    # simulate to t0
    while steps < t0:
        key = (state, pos)
        if key not in table:
            return None
        w, mv, q2 = table[key]
        tape[pos] = w
        pos += mv
        state = q2
        steps += 1
    # record snapshot and positions
    snap0 = dict(tape)
    positions = []
    state_t = state
    pos_t = pos
    # simulate P more, tracking positions and final tape
    lo = pos
    hi = pos
    while steps < t0 + P:
        key = (state, pos)
        if key not in table:
            return None
        w, mv, q2 = table[key]
        tape[pos] = w
        positions.append(pos)
        lo = min(lo, pos)
        hi = max(hi, pos)
        pos += mv
        state = q2
        steps += 1
    positions.append(pos)
    lo = min(lo, min(positions))
    hi = max(hi, max(positions))
    if state != state_t:
        return None
    d = pos - pos_t
    # check tape equality over [lo,hi]
    for y in range(lo, hi + 1):
        if tape.get(y, 0) != snap0.get(y + d, 0):
            return None
        if tape.get(y + d, 0) != snap0.get(y, 0):
            return None
    if d > 0:
        for y in range(hi + 1, hi + d + 1):
            if tape.get(y, 0) != 0:
                return None
    if d < 0:
        for y in range(lo + d, lo):
            if tape.get(y, 0) != 0:
                return None
    return {"kind": "cycle", "t": t0, "p": P}

# --- CPS construction ----------------------------------------------------

def build_cps(tm):
    table, n_states = get_table(tm)
    # right automaton: remembers up to K cells right of head, read far->near
    # left automaton: remembers up to K cells left of head, read far->near
    K = 3
    # automaton state 0 = blank (empty) tape; states 1..2^K represent
    # last K cells read (as an int with bits). Reading symbol x transitions
    # by shifting in x at the near end.
    # We'll build automata that remember K cells (bits).
    def build_auto(K):
        # state encodes the K most recent cells read (bit i = i-th from far)
        # state 0 is reserved: all blank
        size = 1
        for _ in range(K):
            size = size * 2
        # remap: 0 -> blank state; other states 1..size-1
        trans = [[None, None] for _ in range(size)]
        # state 0 loops on 0, and on 1 goes to state encoding [1] at far end?
        # Simplify: states are just bitmasks of length K (0..2^K-1), where bit 0
        # is the farthest-read cell, bit K-1 is the most recent.
        # blank tape state = 0.
        # transition on reading x: shift left by 1, insert x at bit K-1.
        for st in range(size):
            for x in (0, 1):
                ns = ((st << 1) | x) & (size - 1)
                trans[st][x] = ns
        return trans
    # In CPS notation automaton state 0 must loop on symbol 0: our state 0
    # does: trans[0][0] = 0. Good.
    left = build_auto(K)
    right = build_auto(K)
    # context: [l, q, s, r]
    nA = len(left)
    contexts = set()
    contexts.add((0, 0, 0, 0))
    changed = True
    while changed:
        changed = False
        cur = list(contexts)
        for (l, q, s, r) in cur:
            if (q, s) not in table:
                # halting context: would make certificate invalid -> fail
                return None
            w, mv, q2 = table[(q, s)]
            if mv == 1:  # right move
                l2 = left[l][w]
                if l2 is None:
                    return None
                # for every (r2, s2) with right[r2][s2] == r
                for r2 in range(nA):
                    for s2 in (0, 1):
                        if right[r2][s2] == r:
                            new = (l2, q2, s2, r2)
                            if new not in contexts:
                                contexts.add(new)
                                changed = True
            else:  # left move
                r2 = right[r][w]
                if r2 is None:
                    return None
                for l2 in range(nA):
                    for s2 in (0, 1):
                        if left[l2][s2] == l:
                            new = (l2, q2, s2, r2)
                            if new not in contexts:
                                contexts.add(new)
                                changed = True
    # check limit
    if len(contexts) > 200000:
        return None
    # emit certificate
    cert = {
        "kind": "cps",
        "left": left,
        "right": right,
        "contexts": [list(c) for c in contexts],
    }
    return cert

# --- main decider --------------------------------------------------------

def decide(tm: str):
    # 1) try cycle certificate
    try:
        c = find_cycle(tm)
        if c:
            try:
                check(tm, c)
                return c
            except Reject:
                pass
    except Exception:
        pass
    # 2) try small n-gram CPS
    for K in (2, 3, 4):
        try:
            c = build_cps(tm, K) if False else build_cps(tm)
            if c:
                try:
                    check(tm, c)
                    return c
                except Reject:
                    pass
        except Exception:
            pass
    return None