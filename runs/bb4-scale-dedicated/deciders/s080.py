import sys
sys.setrecursionlimit(100000)

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _transitions(tm):
    table, ns, nsym = parse(tm)
    tr = {}
    for st in range(ns):
        for sym in range(nsym):
            tr[(st, sym)] = table[(st, sym)]
    return tr, ns, nsym


def decide(tm):
    try:
        tr, ns, nsym = _transitions(tm)
    except Exception:
        return None

    # Try every pair of half-tape automata of size up to 3 (1, 2, 3 states total),
    # where state 0 is the blank half-tape and must loop on symbol 0.
    # We enumerate all deterministic tables for each side with the constraint
    # automaton[0][0] == 0, then close the context set and reject halting contexts.
    best = None
    ctx_count = 0

    def close(left, right, nL, nR):
        # context = (l, q, s, r)
        start = (0, 0, 0, 0)
        seen = {start}
        stack = [start]
        while stack:
            l, q, s, r = stack.pop()
            if (q, s) not in tr:
                return None  # halting context
            w, mv, q2 = tr[(q, s)]
            if mv == +1:
                if w not in (0, 1):
                    return None
                l2 = left[l][w] if l < nL and w < 2 else None
                if l2 is None:
                    return None
                for r2 in range(nR):
                    for s2 in (0, 1):
                        if right[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in seen:
                                seen.add(c)
                                stack.append(c)
            else:
                if w not in (0, 1):
                    return None
                r2 = right[r][w] if r < nR and w < 2 else None
                if r2 is None:
                    return None
                for l2 in range(nL):
                    for s2 in (0, 1):
                        if left[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in seen:
                                seen.add(c)
                                stack.append(c)
        if len(seen) > 200000:
            return None
        return seen

    # enumerate tables: list of rows, each row is (dst0, dst1) with dst in range(n) or None
    def enum_tables(n):
        rows = []
        for d0 in range(n):
            if n == 1 and d0 != 0:
                continue
            for d1 in range(n):
                rows.append((d0, d1))
        # cartesian product
        out = []
        def rec(i, cur):
            if i == n:
                out.append(tuple(cur))
                return
            for row in rows:
                # state 0 must loop on symbol 0
                if i == 0 and row[0] != 0:
                    continue
                rec(i + 1, cur + [row])
        rec(0, [])
        return out

    for nL in (1, 2, 3):
        for nR in (1, 2, 3):
            for L in enum_tables(nL):
                for R in enum_tables(nR):
                    left = [list(row) for row in L]
                    right = [list(row) for row in R]
                    seen = close(left, right, nL, nR)
                    if seen is not None:
                        # minimal tables: keep only transitions used
                        def minimize(tab, n):
                            used = [set() for _ in range(n)]
                            for (l, q, s, r) in seen:
                                if tab is left:
                                    used[l].add(s)
                                else:
                                    used[r].add(s)
                            new = []
                            for i in range(n):
                                row = []
                                for s in (0, 1):
                                    if s in used[i]:
                                        row.append(tab[i][s])
                                    else:
                                        row.append(None)
                                new.append(row)
                            return new
                        left_m = minimize(left, nL)
                        right_m = minimize(right, nR)
                        cert = {
                            "kind": "cps",
                            "left": left_m,
                            "right": right_m,
                            "contexts": [[l, q, s, r] for (l, q, s, r) in seen],
                        }
                        try:
                            check(tm, cert)
                            return cert
                        except Reject:
                            pass
                        except Exception:
                            pass
    return None
