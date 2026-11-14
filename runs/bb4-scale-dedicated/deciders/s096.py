import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(100000)


def _transitions(table, n_states, n_symbols):
    out = []
    for q in range(n_states):
        row = []
        for s in range(n_symbols):
            t = table.get((q, s))
            if t is None:
                row.append(None)
            else:
                w, mv, q2 = t
                row.append((w, mv, q2))
        out.append(row)
    return out


def _enumerate_automata(max_states, n_symbols):
    """All DFA half-tape tables with 1..max_states states, state 0 loops on 0."""
    results = []
    for n in range(1, max_states + 1):
        for code in range((n_symbols * n) ** n):
            table = []
            for i in range(n):
                row = []
                for j in range(n_symbols):
                    row.append(code % n_symbols)
                    code //= n_symbols
                table.append(row)
            results.append(table)
            if len(results) > 4000000:
                break
        if len(results) > 4000000:
            break
    return results


def _closure(table, trans, n_states, n_symbols):
    """Smallest closed context set for one machine (parse result)."""
    # contexts: (l, q, s, r)
    start = (0, 0, 0, 0)
    seen = {start}
    stack = [start]
    contexts = set()
    while stack:
        l, q, s, r = stack.pop()
        if (l, q, s, r) in contexts:
            continue
        contexts.add((l, q, s, r))
        t = trans.get((q, s))
        if t is None:
            return None
        w, mv, q2 = t
        if mv == 1:
            if l >= n_states:
                return None
            l2 = table[l][w]
            if l2 is None:
                return None
            for r2 in range(n_states):
                for s2 in range(n_symbols):
                    if table[r2][s2] == r:
                        nxt = (l2, q2, s2, r2)
                        if nxt not in contexts:
                            stack.append(nxt)
        else:
            if r >= n_states:
                return None
            r2 = table[r][w]
            if r2 is None:
                return None
            for l2 in range(n_states):
                for s2 in range(n_symbols):
                    if table[l2][s2] == l:
                        nxt = (l2, q2, s2, r2)
                        if nxt not in contexts:
                            stack.append(nxt)
    return contexts


def _build_cert(tableL, tableR, contexts, nL, nR, n_symbols):
    left = [[None] * n_symbols for _ in range(nL)]
    right = [[None] * n_symbols for _ in range(nR)]
    for i in range(nL):
        for x in range(n_symbols):
            left[i][x] = tableL[i][x]
    for i in range(nR):
        for x in range(n_symbols):
            right[i][x] = tableR[i][x]
    cl = [[a, b] for (a, b) in sorted(contexts)]
    return {"kind": "cps", "left": left, "right": right, "contexts": [[l, q, s, r] for (l, q, s, r) in cl]}


def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    trans = {}
    for (q, s), (w, mv, q2) in table.items():
        trans[(q, s)] = (w, mv, q2)
    # halting transitions are absent from table: those q,s are halting
    # enumerate automata per side
    max_states = 3
    cands = _enumerate_automata(max_states, n_symbols)
    # filter: state 0 loops on 0
    cands = [t for t in cands if t[0][0] == 0]
    for tL in cands:
        nL = len(tL)
        for tR in cands:
            nR = len(tR)
            ctx = _closure(None, trans, nL, nR)
            if ctx is None:
                continue
            # require start present
            if (0, 0, 0, 0) not in ctx:
                continue
            cert = _build_cert(tL, tR, ctx, nL, nR, n_symbols)
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    return None
