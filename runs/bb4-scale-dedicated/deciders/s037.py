import sys
from collections import deque

def decide(tm):
    try:
        from neverhalt.tm import parse, run
    except Exception:
        return None
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    if nsym != 2:
        return None
    # context set fixpoint: contexts are (l, q, s, r); we do not know the automata yet,
    # so this decider enumerates one half-tape DFA and lets the other be derived.
    # For now, a bounded search over right automata with the left automaton fixed to
    # the n-gram of the last two cells; fall back to None if nothing is found.
    max_states = 10
    for ngram in (2, 3, 4):
        # build left automaton as n-gram memory (state = last n-1 cells, MSB = oldest)
        n = ngram
        mem_states = 1 << (n - 1)
        left = [[None, None] for _ in range(mem_states)]
        for st in range(mem_states):
            for sym in (0, 1):
                # shift in sym, drop oldest
                ns = ((st << 1) | sym) & (mem_states - 1)
                left[st][sym] = ns
        # enumerate right automata in BFS-canonical order
        for rtab in enumerate_tables(2, max_states):
            right = rtab
            if right[0][0] != 0:
                continue
            cert = close_contexts(table, ns, left, right)
            if cert is not None:
                return cert
    return None

def enumerate_tables(nsym, max_states):
    # yield tables as list of rows; rows are lists of length nsym of target states or None
    # canonical BFS enumeration: first row must be (0, 0) to fix the blank loop
    rows = [None] * max_states
    def rec(i, table):
        if i == max_states:
            yield table
            return
        # row i targets states 0..i (canonical: no target greater than current index)
        for t0 in range(i + 1):
            for t1 in range(i + 1):
                table[i] = [t0, t1]
                yield from rec(i + 1, table)
    for table in rec(0, [None] * max_states):
        # state 0 loops on 0
        if table[0][0] != 0:
            continue
        yield table

def close_contexts(table, ns, left, right):
    # context = (l, q, s, r)
    start = (0, 0, 0, 0)
    seen = {start}
    q = deque([start])
    while q:
        l, st, sym, r = q.popleft()
        row = table.get((st, sym))
        if row is None:
            return None
        w, move, st2 = row
        if move > 0:
            l2 = left[l][w]
            if l2 is None:
                return None
            # for every (r2, s2) with right[r2][s2] == r
            for r2 in range(len(right)):
                for s2 in (0, 1):
                    if right[r2][s2] == r:
                        ctx = (l2, st2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            q.append(ctx)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(len(left)):
                for s2 in (0, 1):
                    if left[l2][s2] == l:
                        ctx = (l2, st2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            q.append(ctx)
    if len(seen) > 200000:
        return None
    contexts = [[l, qq, ss, rr] for (l, qq, ss, rr) in seen]
    return {"kind": "cps", "left": left, "right": right, "contexts": contexts}

if __name__ == "__main__":
    tm = sys.argv[1]
    c = decide(tm)
    if c is None:
        print("none")
    else:
        print(c["kind"], len(c["contexts"]))
