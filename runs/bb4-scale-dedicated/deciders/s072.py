import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _halting_from_blank_states(tm):
    table, ns, nsym = parse(tm)
    blank = 0
    # states from which a halting transition is reachable with all symbols blank
    bad = set()
    changed = True
    while changed:
        changed = False
        for q in range(ns):
            if q in bad:
                continue
            for s in range(nsym):
                t = table.get((q, s))
                if t is None:
                    bad.add(q)
                    changed = True
                    break
                w, mv, q2 = t
                # a transition to a non-halting state: if q2 bad we are bad
                if q2 in bad:
                    bad.add(q)
                    changed = True
                    break
    return bad


def _closure_contexts(tm, left, right, limit):
    table, ns, nsym = parse(tm)
    picked = [[0, 0, 0, 0]]
    seen = {(0, 0, 0, 0)}
    contexts = set()
    # BFS over contexts
    ctxs = [(0, 0, 0, 0)]
    while ctxs and len(seen) < limit:
        l, q, s, r = ctxs.pop()
        if (l, q, s, r) in seen:
            continue
        seen.add((l, q, s, r))
        t = table.get((q, s))
        if t is None:
            return None
        w, mv, q2 = t
        if mv > 0:
            l2 = left[l][w]
            if l2 is None:
                return None
            for (r2, s2) in right_pairs(right):
                if right[r2][s2] == r:
                    key = (l2, q2, s2, r2)
                    if key not in seen:
                        ctxs.append(key)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for (l2, s2) in left_pairs(left):
                if left[l2][s2] == l:
                    key = (l2, q2, s2, r2)
                    if key not in seen:
                        ctxs.append(key)
    if len(seen) > limit:
        return None
    return sorted(seen)


def right_pairs(right):
    out = []
    for r2 in range(len(right)):
        for s2 in range(len(right[r2])):
            out.append((r2, s2))
    return out


def left_pairs(left):
    out = []
    for l2 in range(len(left)):
        for s2 in range(len(left[l2])):
            out.append((l2, s2))
    return out


def _enumerate_dfa_tables(n_states, n_symbols, blank_loop=True):
    # BFS-canonical enumeration of deterministic tables where state 0 loops on 0
    # Only generate canonical representatives to save time.
    import itertools
    # first pass: choose row 0 fixed
    def canon(t):
        # canonicalize state labels by first appearance order in row-major
        order = []
        seen = {}
        for i in range(n_states):
            for x in range(n_symbols):
                t2 = t[i][x]
                if t2 is None:
                    continue
                if t2 not in seen:
                    seen[t2] = len(order)
                    order.append(t2)
        remap = {old: new for new, old in enumerate(order)}
        nt = [[remap[t[i][x]] if t[i][x] is not None else None for x in range(n_symbols)] for i in range(n_states)]
        return tuple(tuple(row) for row in nt)

    # generate all partial functions with row0 fixed to (0, 0) loop on 0
    rows = []
    for i in range(n_states):
        # each entry: None or target state
        if i == 0:
            # symbol 0 goes to 0
            choices = [(0,)+tuple(range(n_states)) for _ in [0]]
            # simpler: enumerate
            pass
        rows.append([tuple(range(n_states))]*n_symbols)
    # brute force for small sizes
    if n_states > 3:
        return
    # row 0: symbol 0 must be 0
    total = n_states ** (n_states*n_symbols - 1)
    if total > 200000:
        return
    seen = set()
    for idx in range(total):
        t = [[None]*n_symbols for _ in range(n_states)]
        t[0][0] = 0
        x = idx
        ok = True
        for i in range(n_states):
            for sym in range(n_symbols):
                if i == 0 and sym == 0:
                    continue
                t[i][sym] = x % (n_states+1)
                x //= (n_states+1)
                if t[i][sym] == n_states:
                    t[i][sym] = None
        c = canon(t)
        if c in seen:
            continue
        seen.add(c)
        yield [list(row) for row in c]


def decide(tm):
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    if nsym > 2:
        return None
    # quick cycle attempt
    try:
        r = run(tm, 2000)
        if r[0]:
            return None
    except Exception:
        return None
    # try tiny table pairs
    for na in range(1, 4):
        for nr in range(1, 4):
            for left in _enumerate_dfa_tables(na, 2):
                # right same enumeration
                for right in _enumerate_dfa_tables(nr, 2):
                    if (right[0][0] is None) or (left[0][0] is None):
                        continue
                    if left[0][0] != 0 or right[0][0] != 0:
                        continue
                    ctxs = _closure_contexts(tm, left, right, 5000)
                    if ctxs is None:
                        continue
                    cert = {
                        "kind": "cps",
                        "left": left,
                        "right": right,
                        "contexts": [[list(c) for c in ctx] for ctx in ctxs],
                    }
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        continue
                    except Exception:
                        continue
    return None


if __name__ == "__main__":
    import sys
    for line in sys.stdin:
        tm = line.strip()
        if not tm:
            continue
        c = decide(tm)
        print(tm, "->", "None" if c is None else c["kind"])