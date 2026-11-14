import sys
from collections import deque
from neverhalt.tm import parse

try:
    from neverhalt.kernel import check, Reject
except Exception:
    check, Reject = None, Exception


def _to_table(rows):
    # rows: list of state strings, each row three chars per symbol
    n_syms = len(rows[0]) // 3
    tbl = {}
    nxt = {}
    k = 0
    for st in rows:
        for s in range(n_syms):
            w, m, ns = st[3 * s:3 * s + 3]
            if ns == '-':
                continue
            i = 0
            while chr(ord('A') + i) in st[:3 * s] or True:
                i += 1
                break
            # map state name to index
            if ns not in nxt:
                nxt[ns] = k
                k += 1
            idx = nxt[ns]
            tbl[(st, s)] = (w, 1 if m == 'R' else -1, idx)
    return tbl, nxt


def _states_of(tm):
    # tm is string of rows
    rows = tm.split('_')
    names = []
    for r in rows:
        if not r:
            continue
        names.append(r[:1])
    return rows, names


def _build(tm):
    rows, names = _states_of(tm)
    name_idx = {nm: i for i, nm in enumerate(names)}
    tbl = {}
    for r in rows:
        st = name_idx[r[:1]]
        for s in range(2):
            w, m, ns = r[3 * s:3 * s + 3]
            if ns == '-':
                continue
            if ns not in name_idx:
                continue
            tbl[(st, s)] = (1 if w == '1' else 0, 1 if m == 'R' else -1, name_idx[ns])
    return tbl, len(names)


def _close(tbl, ns, la, ra, maxlen=200000):
    # la: list of rows for DFA on left (each row 2 chars); ra likewise
    # state 0 loops on 0
    # la[i][x]: next state or None
    # Build context set
    # context (l, q, s, r)
    init = (0, 0, 0, 0)
    seen = {init}
    dq = deque([init])
    contexts = []
    while dq:
        l, q, s, r = dq.popleft()
        contexts.append((l, q, s, r))
        if len(contexts) > maxlen:
            return None
        if (q, s) not in tbl:
            return None  # halting context
        w, mv, q2 = tbl[(q, s)]
        if mv == 1:
            l2 = la[l][w]
            if l2 is None:
                return None
            # find all (r2, s2) with ra[r2][s2] == r
            for r2 in range(len(ra)):
                for s2 in range(2):
                    if ra[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            dq.append(c)
        else:
            r2 = ra[r][w]
            if r2 is None:
                return None
            for l2 in range(len(la)):
                for s2 in range(2):
                    if la[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            dq.append(c)
    if len(contexts) > 5000:
        return None
    # build cert
    return contexts


def _gen_dfa(n_states, sym=2, cap=3):
    # enumerate all deterministic transition tables with state 0 looping on 0
    # each state: tuple of next states for symbols 0..sym-1, None allowed
    import itertools
    # possible entries per state: sym choices from range(n_states) + None
    opts = [None] + list(range(n_states))
    tables = []
    # state 0 must loop on 0
    for combo in itertools.product(opts, repeat=sym * n_states):
        tbl = []
        for i in range(n_states):
            row = []
            for x in range(sym):
                v = combo[i * sym + x]
                row.append(v)
            tbl.append(row)
        if tbl[0][0] != 0:
            continue
        tables.append(tbl)
    return tables


def decide(tm: str):
    try:
        tbl, ns = _build(tm)
    except Exception:
        return None
    # Search over small automata on both sides
    # Try n_states 1..3 for both sides; maybe asymmetric 1 vs 2, 2 vs 1, 2 vs 2, 3 vs 3
    import itertools
    for n1 in (1, 2, 3):
        for n2 in (1, 2, 3):
            if n1 * n2 > 6:
                continue
            left_tables = _gen_dfa(n1)
            right_tables = _gen_dfa(n2)
            cnt = 0
            for la in left_tables:
                for ra in right_tables:
                    cnt += 1
                    if cnt > 40000:
                        break
                    contexts = _close(tbl, ns, la, ra)
                    if contexts is not None:
                        # Build cert
                        cert = {
                            "kind": "cps",
                            "left": [[x if x is not None else None for x in row] for row in la],
                            "right": [[x if x is not None else None for x in row] for row in ra],
                            "contexts": [[l, q, s, r] for (l, q, s, r) in contexts],
                        }
                        if check:
                            try:
                                check(tm, cert)
                            except Exception:
                                continue
                        return cert
                if cnt > 40000:
                    break
    return None
