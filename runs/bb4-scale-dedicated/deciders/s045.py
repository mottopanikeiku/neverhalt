import sys
sys.setrecursionlimit(100000)

def parse(tm):
    rows = tm.split('_')
    table = {}
    n = 0
    for row in rows:
        for k in range(0, len(row), 3):
            chunk = row[k:k+3]
            if chunk == '---':
                continue
            w, m, ns = chunk[0], chunk[1], chunk[2]
            move = 1 if m == 'R' else -1
            try:
                nxt = ord(ns) - 65
                if nxt >= len(rows):
                    nxt = None
            except Exception:
                nxt = None
            table[(n, int(w))] = (int(w), move, nxt)
        n += 1
    return table, n, 2

def step(table, q, s):
    t = table.get((q, s))
    if t is None:
        return None
    w, m, q2 = t
    return w, m, q2

def build_automaton(nstates, trans):
    # trans: dict (state, sym) -> nextstate or None
    left = []
    for i in range(nstates):
        row = []
        for x in range(2):
            row.append(trans.get((i, x)))
        left.append(row)
    return left

def close_contexts(left, right, nq, table):
    # left/right: automaton tables, rows lists of len 2 with int or None
    # nq: number of machine states
    # BFS from (0,0,0,0)
    seen = set()
    stack = [(0, 0, 0, 0)]
    seen.add((0, 0, 0, 0))
    contexts = []
    while stack:
        (l, q, s, r) = stack.pop()
        contexts.append([l, q, s, r])
        t = table.get((q, s))
        if t is None:
            return None
        w, m, q2 = t
        if m == 1:
            l2 = left[l][w]
            if l2 is None:
                return None
            # for every (r2,s2) with right[r2][s2]==r
            for r2 in range(len(right)):
                row = right[r2]
                for s2 in range(2):
                    if row[s2] == r:
                        cx = (l2, q2, s2, r2)
                        if cx not in seen:
                            seen.add(cx)
                            stack.append(cx)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(len(left)):
                row = left[l2]
                for s2 in range(2):
                    if row[s2] == l:
                        cx = (l2, q2, s2, r2)
                        if cx not in seen:
                            seen.add(cx)
                            stack.append(cx)
    return contexts

def decide(tm):
    table, nq, ns = parse(tm)
    # enumerate automata of size 1..3 per side
    sizes = [1, 2, 3]
    for n1 in sizes:
        for n2 in sizes:
            # enumerate all transition tables for left of size n1
            # state 0 loops on 0
            for lt in gen_tables(n1):
                for rt in gen_tables(n2):
                    if n1 == 1 and n2 == 1:
                        # quick skip maybe
                        pass
                    ctx = close_contexts(lt, rt, nq, table)
                    if ctx is not None:
                        return {"kind": "cps", "left": lt, "right": rt, "contexts": ctx}
    return None

def gen_tables(n):
    # generate all deterministic tables size n x 2 with entries in range(n),
    # state 0 on symbol 0 -> 0
    results = []
    # each of n*2 entries, but (0,0) fixed to 0
    entries = []
    for i in range(n):
        for x in range(2):
            if i == 0 and x == 0:
                continue
            entries.append((i, x))
    total = n ** len(entries)
    for code in range(total):
        c = code
        trans = {}
        trans[(0, 0)] = 0
        for (i, x) in entries:
            trans[(i, x)] = c % n
            c //= n
        results.append(build_automaton(n, trans))
    return results

if __name__ == '__main__':
    import sys
    tm = sys.argv[1]
    print(decide(tm))
