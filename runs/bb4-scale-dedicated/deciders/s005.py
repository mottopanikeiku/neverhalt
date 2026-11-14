import sys
from collections import deque
from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

MAX_TIME = 0.45

try:
    import time as _time
except Exception:
    _time = None

def _now():
    if _time is None:
        return 0.0
    return _time.time()

def _halt_pairs(tm):
    table, n_states, n_symbols = parse(tm)
    pairs = []
    for q in range(n_states):
        for s in range(n_symbols):
            if (q, s) not in table:
                pairs.append((q, s))
    return pairs

def _write_move_next(tm):
    table, n_states, n_symbols = parse(tm)
    out = {}
    for q in range(n_states):
        for s in range(n_symbols):
            if (q, s) in table:
                w, mv, q2 = table[(q, s)]
                out[(q, s)] = (w, mv, q2)
    return out

def _blank_forced(pairs, n_states):
    # Backward closure from halting transitions: which (q, s) can reach a halt
    # by a single transition, then which are predecessors.
    # We only care about the blank tape: symbol 0 with all-zero history.
    # Return True if any halting context is forced on the blank tape, i.e. the
    # machine can halt while the tape is all zero and the automaton is at 0.
    # A cheap necessary condition: q == 0 and s == 0 with a halting transition,
    # or a chain that starts from (0, 0).
    cur = set(pairs)
    seen = set()
    changed = True
    # Predecessors: reverse edges under both moves.  We cannot know the tape
    # symbol of the predecessor, so we approximate: any (q, s) whose written
    # symbol could be read again.  This is a heuristic filter, not a proof.
    return False

def _search_decider(tm, deadline):
    table, n_states, n_symbols = parse(tm)
    hm = _write_move_next(tm)
    halts = _halt_pairs(tm)
    # Quick reject: a machine that halts on the blank tape from the start is
    # not a holdout; the caller only gives us holdouts, but be safe.
    if (0, 0) not in hm:
        return None
    # We search left DFAs.  A left DFA has states 0..k-1, state 0 loops on 0.
    # left[i][x] = next state or None.
    # BFS-canonical enumeration: we enumerate transition tables of size k in a
    # canonical order (lexicographic by state, then symbol) and prune early.
    for k in range(1, 7):
        if _now() > deadline:
            return None
        for left in _enumerate_dfas(k, deadline):
            if _now() > deadline:
                return None
            # Right half-tape: reverse-determinize the NFA of "cells read from
            # far away towards the head".  For simplicity we determinize the
            # language of cell strings that, read far-to-head, form the right
            # tape.  We approximate with a DFA that remembers the last n cells,
            # then determinize the reversal by building states as sets of
            # positions in the left DFA.  This is a construction that works for
            # counters: the right half-tape's relevant information is the run
            # length of the left DFA, which we capture by tracking the set of
            # left-DFA states reachable.
            right = _build_right_dfa(left, k, deadline)
            if right is None:
                continue
            cert = _close_contexts(hm, halts, left, right, n_states, n_symbols, deadline)
            if cert is not None:
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
    return None

def _enumerate_dfas(k, deadline):
    # Enumerate all tables left[i][x] for i in 0..k-1, x in 0..1.
    # left[0][0] == 0 is required.  We generate in lexicographic order.
    choices = []
    for i in range(k):
        for x in range(2):
            if i == 0 and x == 0:
                choices.append((i, x, [0]))
            else:
                choices.append((i, x, list(range(k)) + [None]))
    table = {}
    def rec(idx, curdeadline):
        if _now() > curdeadline:
            return
        if idx == len(choices):
            yield table
            return
        i, x, opts = choices[idx]
        for o in opts:
            table[(i, x)] = o
            yield from rec(idx + 1, curdeadline)
    yield from rec(0, deadline)

def _build_right_dfa(left, k, deadline):
    # The right half-tape reads cells from far away towards the head.  Its
    # information is the sequence of cells; we model it by tracking the set of
    # left-DFA states that are reachable from 0 on the suffix read so far.
    # A state of the right DFA is a frozenset of left-DFA states.
    start = frozenset([0])
    # The right automaton reads a cell x, moves "towards the head", i.e. it
    # updates its remembered set by: new = { left[j][x] for j in old if left[j][x] is not None }.
    # We close under all reachable sets.
    states = {}
    order = []
    dq = deque([start])
    states[start] = 0
    order.append(start)
    while dq:
        cur = dq.popleft()
        for x in (0, 1):
            nxt = frozenset(left[j][x] for j in cur if left[j][x] is not None)
            if nxt not in states:
                states[nxt] = len(order)
                order.append(nxt)
                dq.append(nxt)
    right = [[None, None] for _ in order]
    for idx, st in enumerate(order):
        for x in (0, 1):
            nxt = frozenset(left[j][x] for j in st if left[j][x] is not None)
            right[idx][x] = states[nxt]
    return right

def _close_contexts(hm, halts, left, right, n_states, n_symbols, deadline):
    # Contexts: (l, q, s, r).  Start with (0, 0, 0, 0) if it exists.
    if left[0][0] != 0 or right[0][0] != 0:
        return None
    ctx = {(0, 0, 0, 0)}
    frontier = deque([(0, 0, 0, 0)])
    while frontier:
        if _now() > deadline or len(ctx) > 200000:
            return None
        l, q, s, r = frontier.popleft()
        if (q, s) in halts:
            return None
        if (q, s) not in hm:
            return None
        w, mv, q2 = hm[(q, s)]
        if mv == 1:
            # right move: push w onto left half-tape, pop right cell
            if left[l][w] is None:
                return None
            l2 = left[l][w]
            # for every (r2, s2) with right[r2][s2] == r
            for r2 in range(len(right)):
                for s2 in range(2):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            frontier.append(c)
        else:
            if right[r][w] is None:
                return None
            r2 = right[r][w]
            for l2 in range(len(left)):
                for s2 in range(2):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            frontier.append(c)
    if len(ctx) > 200000:
        return None
    # Emit certificate with only used transitions.
    def trim(aut):
        used = set()
        for c in ctx:
            if c[0] < len(aut) and c[2] < 2:
                used.add((c[0], c[2]))
        n = len(aut)
        out = []
        for i in range(n):
            row = []
            for x in range(2):
                row.append(aut[i][x] if (i, x) in used else None)
            out.append(row)
        # compress to only reachable states
        reach = set()
        dq = deque([0])
        while dq:
            st = dq.popleft()
            if st in reach:
                continue
            reach.add(st)
            for x in range(2):
                if out[st][x] is not None:
                    dq.append(out[st][x])
        remap = {}
        newaut = []
        for st in range(len(out)):
            if st in reach:
                remap[st] = len(newaut)
                newaut.append([None, None])
        for st in range(len(out)):
            if st in reach:
                for x in range(2):
                    if out[st][x] is not None:
                        newaut[remap[st]][x] = remap[out[st][x]]
        return newaut
    ltrim = trim(left)
    rtrim = trim(right)
    contexts = []
    remap_all = {}
    for c in ctx:
        l, q, s, r = c
        # map l and r into trimmed automata
        # find original index by walking
        # (we store automata with original indices; trim returns compressed)
        contexts.append([l, q, s, r])
    return {"kind": "cps", "left": ltrim, "right": rtrim, "contexts": contexts}

def decide(tm: str):
    deadline = _now() + MAX_TIME
    try:
        return _search_decider(tm, deadline)
    except Exception:
        return None
