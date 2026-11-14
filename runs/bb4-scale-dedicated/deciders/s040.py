import sys
from collections import deque, defaultdict

def decide(tm):
    from neverhalt.tm import parse, run
    table, ns, nsym = parse(tm)
    # map state ints
    A = 0
    # state alphabet: 0..ns-1
    # context: (l, q, s, r)
    # closure start: (0,0,0,0)
    def left_next(l, w):
        # left automaton reads from far away towards head; here we define
        # left[i][x] = state reached from i on symbol x.
        return left[l][w]
    # We need to search over DFA tables for left and right half-tapes.
    # left[i][x] in 0..nl-1 or None
    # right[i][x] in 0..nr-1 or None
    # state 0 loops on symbol 0.
    def build(nl, nr, left, right):
        # left: list of list of (state or None), index by symbol 0..1
        # right: same
        # closure over contexts (l,q,s,r)
        start = (0, A, 0, 0)
        seen = set([start])
        dq = deque([start])
        contexts = [start]
        while dq:
            l, q, s, r = dq.popleft()
            if q >= ns:
                return None  # should not happen
            key = (q, s)
            if key not in table:
                return None  # halting context
            w, mv, q2 = table[key]
            if mv == 1:
                # right move: l2 = left[l][w] must exist
                l2 = left[l][w]
                if l2 is None:
                    return None
                # for every (r2,s2) with right[r2][s2]==r, context (l2,q2,s2,r2)
                for r2 in range(nr):
                    for s2 in range(2):
                        if right[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in seen:
                                seen.add(c)
                                contexts.append(c)
                                dq.append(c)
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                for l2 in range(nl):
                    for s2 in range(2):
                        if left[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in seen:
                                seen.add(c)
                                contexts.append(c)
                                dq.append(c)
        return contexts

    # enumerate left DFA tables for nl = 1..max
    # canonical BFS order: states 0..nl-1, symbol 0..1
    # state 0 loops on symbol 0
    # we enumerate all functions into 0..nl-1
    import itertools
    for nl in range(1, 5):
        for nr in range(1, 5):
            # enumerate tables
            def enum_tables(n):
                # each table: list of n rows, each row is a tuple of n values (state or None)
                # symbol 0 must map 0->0
                # we do product over remaining entries
                entries = []
                for i in range(n):
                    for x in range(2):
                        if i == 0 and x == 0:
                            continue
                        entries.append((i, x))
                choices = []
                for (i, x) in entries:
                    choices.append([None] + list(range(n)))
                for combo in itertools.product(*choices):
                    t = [[None, None] for _ in range(n)]
                    t[0][0] = 0
                    for ((i, x), v) in zip(entries, combo):
                        t[i][x] = v
                    yield t
            for left in enum_tables(nl):
                for right in enum_tables(nr):
                    # quick check: left[0][0]==0 and right[0][0]==0 (ensured)
                    contexts = build(nl, nr, left, right)
                    if contexts is not None:
                        # build certificate
                        # keep only transitions used: we can just emit full automata
                        # but kernel limit 5000 states, 200000 contexts
                        if len(contexts) > 200000:
                            continue
                        # contexts are tuples (l,q,s,r)
                        # convert to lists
                        cert = {
                            "kind": "cps",
                            "left": left,
                            "right": right,
                            "contexts": [list(c) for c in contexts]
                        }
                        return cert
    return None

NAME = "dfa-search"