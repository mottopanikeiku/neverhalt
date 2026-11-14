import sys
from collections import deque

MAX_STEPS = 200000

def parse(tm):
    rows = tm.split("_")
    n_states = len(rows)
    table = {}
    for si, row in enumerate(rows):
        for sym in range(2):
            idx = sym * 3
            if idx + 3 > len(row):
                continue
            w, mv, nxt = row[idx], row[idx+1], row[idx+2]
            if w == "-" or mv == "-" or nxt == "-":
                continue
            try:
                ns = int(ord(nxt) - ord('A'))
            except Exception:
                continue
            if ns < 0 or ns >= n_states:
                continue
            table[(si, sym)] = (int(w), 1 if mv == 'R' else -1, ns)
    return table, n_states

def run(tm, max_steps):
    table, n_states = parse(tm)
    tape = {}
    pos = 0
    state = 0
    for step in range(max_steps):
        sym = tape.get(pos, 0)
        key = (state, sym)
        if key not in table:
            return True, step + 1, state, pos, tape
        w, mv, ns = table[key]
        if w:
            tape[pos] = w
        else:
            tape.pop(pos, None)
        pos += mv
        state = ns
    return False, max_steps, state, pos, tape

def cps_from_tables(tm, left, right, q0=0):
    """left[i][x] -> j or None, right likewise. state 0 is blank half-tape.
    returns context list or None if a closing set cannot be built / halts."""
    table, n_states = parse(tm)
    nL = len(left)
    nR = len(right)
    # find halting (q, s) pairs
    def step_pairs():
        res = []
        for q in range(n_states):
            for s in range(2):
                if (q, s) not in table:
                    res.append((q, s))
        return res
    halting = step_pairs()
    # initial context
    init = (0, 0, 0, 0)
    # For efficiency, represent contexts as (l, q, s, r)
    # But closure can be huge; we need to be smart.
    # The kernel limit is 200000 contexts. We'll cap.
    ctxs = set([init])
    queue = deque([init])
    while queue:
        l, q, s, r = queue.popleft()
        key = (q, s)
        if key not in table:
            # halting context -> reject
            return None
        w, mv, q2 = table[key]
        if mv == 1:  # right move
            # left automaton steps on w
            l2 = left[l][w] if l < len(left) else None
            if l2 is None:
                return None
            # right pops: right[r][s2] == r for every s2 that can lead there
            for r2 in range(nR):
                for s2 in range(2):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctxs:
                            ctxs.add(c)
                            queue.append(c)
        else:  # left move
            r2 = right[r][w] if r < len(right) else None
            if r2 is None:
                return None
            for l2 in range(nL):
                for s2 in range(2):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctxs:
                            ctxs.add(c)
                            queue.append(c)
        if len(ctxs) > 199000:
            return None
    return sorted(ctxs)

def all_tables(n, nstates, fix0=True):
    """enumerate deterministic automata on alphabet {0,1} with nstates states.
    state 0 loops on 0 (blank). returns list of tables."""
    # each state has 2 transitions; total (nstates)^2 possibilities
    total = nstates ** 2
    out = []
    for mask in range(total):
        tab = []
        for i in range(nstates):
            row = []
            for x in range(2):
                row.append((mask >> (i * 2 + x)) & (nstates - 1))
            tab.append(row)
        if fix0 and tab[0][0] != 0:
            continue
        if fix0 and tab[0][1] != 0:
            # state 0 must loop on both symbols to be blank half-tape
            # Actually blank tape reads 0 forever, but 1 might appear; allow any
            pass
        out.append(tab)
    return out

def decide(tm):
    # quick halt check
    halted, steps, state, pos, tape = run(tm, 300)
    if halted:
        return None
    table, n_states = parse(tm)
    # enumerate automata for left and right sides
    for nL in range(1, 4):
        for nR in range(1, 4):
            # limit enumeration size
            if nL > 3 or nR > 3:
                continue
            # fix0: state 0 loops on 0; on 1 we allow anything but blank tape only reads 0
            # So state 0 on 0 must stay 0. On 1, the tape has a 1, so it's fine to be anything.
            for lt in all_tables(2, nL, fix0=True):
                # quick: ensure state 0 on 0 -> 0
                if lt[0][0] != 0:
                    continue
                for rt in all_tables(2, nR, fix0=True):
                    if rt[0][0] != 0:
                        continue
                    ctxs = cps_from_tables(tm, lt, rt)
                    if ctxs is not None:
                        # emit certificate; keep only used transitions
                        # prune unused states
                        # find used l, r, q, s, r2, s2, l2
                        used_l = set()
                        used_r = set()
                        for (l, q, s, r) in ctxs:
                            used_l.add(l)
                            used_r.add(r)
                        # prune transitions to unused states
                        def prune(tab, used, n):
                            remap = {}
                            newtab = []
                            for i in range(n):
                                if i in used:
                                    remap[i] = len(remap)
                            for i in range(n):
                                if i not in used:
                                    continue
                                row = []
                                for x in range(2):
                                    j = tab[i][x]
                                    row.append(remap.get(j))
                                newtab.append(row)
                            return newtab
                        # need to remap contexts
                        lp = prune(lt, used_l, nL)
                        rp = prune(rt, used_r, nR)
                        # build remap dicts
                        lmap = {}
                        for i in sorted(used_l):
                            lmap[i] = len(lmap)
                        rmap = {}
                        for i in sorted(used_r):
                            rmap[i] = len(rmap)
                        contexts = []
                        for (l, q, s, r) in ctxs:
                            contexts.append([lmap[l], q, s, rmap[r]])
                        cert = {
                            "kind": "cps",
                            "left": lp,
                            "right": rp,
                            "contexts": contexts,
                        }
                        return cert
    return None
