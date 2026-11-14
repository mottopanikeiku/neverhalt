import sys
sys.setrecursionlimit(100000)

# --- helpers -------------------------------------------------------------
def parse_tm(tm):
    # returns (trans, nstates) ; trans[q][sym] = (w, mv, q2) or None
    rows = []
    i = 0
    while i < len(tm):
        if i + 2 < len(tm):
            rows.append((i // 3, tm[i:i + 3]))
            i += 3
        else:
            break
    # states: letters A.. (A=0)
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    n = 0
    for r in range(len(rows)):
        ch = chr(ord('A') + r)
        if ch in letters:
            n += 1
    trans = [[None, None], [None, None]]
    while len(trans) < n:
        trans.append([None, None])
    for r, row in enumerate(rows):
        if r >= n:
            break
        for sym in (0, 1):
            cell = row[sym]
            if cell == '-' or cell is None:
                continue
            w = 1 if cell[0] == '1' else 0
            mv = 1 if cell[1] == 'R' else -1
            nxt = cell[2]
            if nxt == 'Z' or nxt == '-':
                continue
            if nxt in letters:
                q2 = ord(nxt) - ord('A')
                if q2 < n:
                    trans[r][sym] = (w, mv, q2)
    return trans, n


def simulate_blank(trans, n, limit):
    # run from blank tape, return (halted, steps, states, tape)
    pos = 0
    q = 0
    tape = {}
    states = []
    for _ in range(limit):
        states.append(q)
        tr = trans[q][0]
        if tr is None:
            return True, len(states), states, tape
        w, mv, q2 = tr
        tape[pos] = w
        pos += mv
        q = q2
    return False, limit, states, tape


def run(tm, max_steps):
    trans, n = parse_tm(tm)
    # find head start symbol 0 always
    halted, steps, states, tape = simulate_blank(trans, n, max_steps)
    return halted, steps, states, tape


# --- automaton helpers ---------------------------------------------------
def build_cps(table, nstates, nsym, left, right, contexts):
    # contexts: list of (l,q,s,r)
    ctxset = set(contexts)
    # BFS closure
    frontier = list(ctxset)
    seen = set(ctxset)
    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            tr = table[q][s]
            if tr is None:
                # halting context -> reject
                return None
            w, mv, q2 = tr
            if mv > 0:
                l2 = left[l][w] if l < len(left) else None
                if l2 is None:
                    return None
                # for every (r2, s2) with right[r2][s2] == r
                found = False
                for r2 in range(len(right)):
                    for s2 in range(2):
                        if right[r2][s2] == r:
                            key = (l2, q2, s2, r2)
                            if key not in seen:
                                seen.add(key)
                                ctxset.add(key)
                                nxt.append(key)
                            found = True
                if not found:
                    return None
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                found = False
                for l2 in range(len(left)):
                    for s2 in range(2):
                        if left[l2][s2] == l:
                            key = (l2, q2, s2, r2)
                            if key not in seen:
                                seen.add(key)
                                ctxset.add(key)
                                nxt.append(key)
                            found = True
                if not found:
                    return None
        frontier = nxt
    return sorted(ctxset)


def emit_cps(tm, table, nstates, left, right, contexts):
    ctxs = build_cps(table, nstates, 2, left, right, contexts)
    if ctxs is None:
        return None
    if len(ctxs) > 200000 or len(left) > 5000 or len(right) > 5000:
        return None
    # encode
    left_enc = [[(left[i][x] if left[i][x] is not None else None) for x in range(2)] for i in range(len(left))]
    right_enc = [[(right[i][x] if right[i][x] is not None else None) for x in range(2)] for i in range(len(right))]
    ctx_enc = [[list(c) for c in ctx] for ctx in ctxs]
    return {"kind": "cps", "left": left_enc, "right": right_enc, "contexts": ctx_enc}


def ngram_automaton(k):
    # canonical k-gram automaton remembering last k symbols; state 0 = all blank
    # We'll just generate states by canonical BFS from blank history, transition on new symbol
    # state = tuple of up to k bits; but canonical labels needed.
    # simpler: enumerate all reachable states from () with symbols 0,1
    from collections import deque
    start = ()
    idx = {start: 0}
    order = [start]
    trans = []
    dq = deque([start])
    while dq:
        st = dq.popleft()
        row = []
        for sym in (0, 1):
            ns = (st + (sym,))
            if len(ns) > k:
                ns = ns[1:]
            if ns not in idx:
                idx[ns] = len(order)
                order.append(ns)
                dq.append(ns)
            row.append(idx[ns])
        trans.append(row)
    return trans, order


def try_gram(tm, table, nstates, k):
    # left and right automata (same ngram but right reads right side)
    L, _ = ngram_automaton(k)
    R, _ = ngram_automaton(k)
    # start context
    ctxs = [[0, 0, 0, 0]]
    cert = emit_cps(tm, table, nstates, L, R, ctxs)
    return cert


def decide(tm):
    # Parse and get table
    trans, nstates = parse_tm(tm)
    table = trans
    # First try ngram CPS with growing k
    for k in range(1, 13):
        try:
            cert = try_gram(tm, table, nstates, k)
        except Exception:
            cert = None
        if cert is not None:
            return cert
    # Try small custom automata by enumeration
    # Enumerate left automata with 1..3 states, right with 1..3, canonical
    # Build candidate tables: state 0 loops on 0 (blank tape). We'll enumerate
    # transitions for non-zero symbols and small state counts.
    from itertools import product
    for nL in (1, 2, 3):
        for nR in (1, 2, 3):
            # enumerate left table: each state i (0..nL-1), for sym 0: 0 (state 0 loops on 0)
            # for sym 1: any state or None (but state 0 on sym 0 must be 0)
            # We'll do a bounded enumeration.
            # Represent table as tuple of length nL*2, values in 0..nL-1 or -1 (None)
            # state 0 sym 0 fixed = 0
            cells = [(i, s) for i in range(nL) for s in (0, 1)]
            cells.remove((0, 0))
            choices = list(range(nL)) + [-1]
            # limit
            total = len(choices) ** len(cells)
            if total > 200000:
                continue
            for combo in product(choices, repeat=len(cells)):
                L = [[None, None] for _ in range(nL)]
                L[0][0] = 0
                for (i, s), v in zip(cells, combo):
                    L[i][s] = v if v >= 0 else None
                # right table similarly
                cellsR = [(i, s) for i in range(nR) for s in (0, 1)]
                cellsR.remove((0, 0))
                totalR = len(choices) ** len(cellsR)
                if totalR > 200000:
                    continue
                for comboR in product(choices, repeat=len(cellsR)):
                    R = [[None, None] for _ in range(nR)]
                    R[0][0] = 0
                    for (i, s), v in zip(cellsR, comboR):
                        R[i][s] = v if v >= 0 else None
                    ctxs = [[0, 0, 0, 0]]
                    try:
                        cert = emit_cps(tm, table, nstates, L, R, ctxs)
                    except Exception:
                        cert = None
                    if cert is not None:
                        return cert
    return None
