import sys
from collections import deque

def _parse(tm):
    rows = tm.split('_')
    table = {}
    n_states = len(rows)
    n_symbols = 3
    for si, row in enumerate(rows):
        for xi in range(n_symbols):
            ch = row[xi]
            if ch == '-':
                continue
            nxt = ch
            if nxt.isdigit():
                nxt = int(nxt)
            else:
                nxt = ord(nxt) - ord('A')
            table[(si, xi)] = (ch if ch != 'L' and ch != 'R' else ch, 1 if ch == 'R' else -1, nxt)
    return table, n_states, n_symbols

def _halting_states(table, n_states):
    # states from which no transition on any symbol is defined
    for s in range(n_states):
        if not any((s, x) in table for x in range(3)):
            return s
    return None

def _deterministic_tables(n_states, n_symbols):
    # enumerate all total transition tables on symbols 0,1 (symbol 2 = halt handled separately)
    # for the automaton: each state maps each symbol to a state or None (None = "never happens")
    # for enumeration simplicity we enumerate functions on {0,1} with optional None
    # represent None as -1
    def rec(f):
        if len(f) == n_states * n_symbols:
            yield [f[i*n_symbols:(i+1)*n_symbols] for i in range(n_states)]
            return
        for v in range(-1, n_states):
            nf = f + [v]
            yield from rec(nf)
    yield from rec([])

def _closure(table, n_states, left, right, limit=200000):
    # left/right: transition tables with -1 = null; state 0 loops on 0
    # context: (l, q, s, r)
    start = (0, 0, 0, 0)
    seen = {start}
    dq = deque([start])
    contexts = []
    while dq:
        l, q, s, r = dq.popleft()
        contexts.append([l, q, s, r])
        if len(contexts) > limit:
            return None
        if (q, s) not in table:
            return None  # halting context found -> not closed
        w, mv, q2 = table[(q, s)]
        if mv == 1:
            if left[l][w] < 0:
                return None
            l2 = left[l][w]
            for r2 in range(len(right)):
                for s2 in (0, 1):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            dq.append(c)
        else:
            if right[r][w] < 0:
                return None
            r2 = right[r][w]
            for l2 in range(len(left)):
                for s2 in (0, 1):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            dq.append(c)
    return contexts

def _blank_reachability(left, right, table, n_states):
    # check whether the blank tape (context (0,0,0,0)) leads to a halting transition
    # we simply run the closure and see if any context hits a halting transition
    # but that is the same as closure succeeding; we need: no halting context reachable
    # i.e. closure must succeed without encountering a missing transition
    return _closure(table, n_states, left, right) is not None

def _enumerate_small(ns, max_states=3):
    # enumerate all automata with 1..max_states states, state 0 loops on 0
    # we only consider symbols 0 and 1; None allowed
    for n in range(1, max_states + 1):
        # enumerate all functions {0,1}^{n} -> {-1..n-1}
        total = (n + 1) ** (2 * n)
        for code in range(total):
            tab = []
            c = code
            for i in range(n):
                row = []
                for x in range(2):
                    v = c % (n + 1)
                    c //= (n + 1)
                    row.append(-1 if v == n else v)
                tab.append(row)
            # enforce state 0 loops on 0 (must be 0)
            if tab[0][0] != 0:
                continue
            yield tab

def decide(tm):
    try:
        table, n_states, n_symbols = _parse(tm)
    except Exception:
        return None
    # only machines that never halt are our target; try small pairs first
    # left automaton reads cells left of head from far away towards head
    # right automaton reads cells right of head from far away towards head
    for nl in range(1, 4):
        for left in _enumerate_small(nl, nl):
            for nr in range(1, 4):
                for right in _enumerate_small(nr, nr):
                    contexts = _closure(table, n_states, left, right)
                    if contexts is not None:
                        return {"kind": "cps", "left": left, "right": right, "contexts": contexts}
    # grow left DFA in BFS-canonical order up to 10 states, prune partial tables
    # that already force the blank tape to reach a halt
    # we enumerate complete tables and prune by checking closure on partial tables
    # (approximation: just enumerate all up to 5 states with early rejection)
    for nl in range(4, 7):
        cnt = 0
        for left in _enumerate_small(nl, nl):
            # prune: if blank tape already reaches a halt under any right automaton,
            # closure would fail; we cannot know without right, so skip cheap check
            cnt += 1
            if cnt > 200000:
                break
            for nr in range(1, 4):
                for right in _enumerate_small(nr, nr):
                    contexts = _closure(table, n_states, left, right)
                    if contexts is not None:
                        return {"kind": "cps", "left": left, "right": right, "contexts": contexts}
    return None

def _unused():
    pass
