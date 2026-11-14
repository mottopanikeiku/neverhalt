import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---------- machine helpers ----------


def table_of(tm):
    t, ns, nsym = parse(tm)
    return t, ns, nsym


def blank_ok(t, ns):
    # all transitions on symbol 0 exist for every state (else machine may halt
    # immediately on the blank tape; a halting context would then be found)
    for q in range(ns):
        if (q, 0) not in t:
            return False
    return True


def trans(t, ns, q, s):
    # returns (w, move, q2) with move +1 / -1, or None (halting transition)
    if (q, s) not in t:
        return None
    w, mv, q2 = t[(q, s)]
    if mv == 1:
        m = 1
    else:
        m = -1
    return (w, m, q2)


# ---------- automaton helpers ----------


def mk_auto(n):
    # left[i][x] = next state or None; rows are lists of length 2
    return [[None, None] for _ in range(n)]


def complete_auto(auto, n):
    """Return a total transition table: for symbol 0, if entry is None,
    treat as a fresh non-accepting dead state appended?  Instead we keep
    None meaning 'this half-tape never occurs' - contexts never use it."""
    return auto


def enumerate_autos(max_states):
    """Yield (n, table) for n = 1..max_states.  State 0 loops on symbol 0.
    Other entries are arbitrary in {None} U {0..n-1}; but we normalise by
    BFS-canonical order: build reachable-partition representatives.  For
    small n we just enumerate all tables but deduplicate by the observable
    transition structure via canonical renaming of reachable states."""
    from itertools import product

    for n in range(1, max_states + 1):
        if n == 1:
            yield 1, [[0, None]]
            continue
        choices = [None] + list(range(n))
        # state 0 symbol 0 forced to 0
        for combo in product(choices, repeat=2 * n):
            tbl = [list(combo[2 * i:2 * i + 2]) for i in range(n)]
            tbl[0][0] = 0
            yield n, tbl


def canon(auto):
    n = len(auto)
    seen = {}
    order = []
    stack = [0]
    while stack:
        s = stack.pop()
        if s in seen:
            continue
        seen[s] = len(order)
        order.append(s)
        for x in (0, 1):
            e = auto[s][x]
            if e is not None and e not in seen:
                stack.append(e)
    if not order:
        return ()
    out = []
    for s in order:
        row = []
        for x in (0, 1):
            e = auto[s][x]
            row.append(seen.get(e, -1) if e is not None else -1)
        out.append(row)
    return tuple(map(tuple, out))


# ---------- context closure ----------


def close_contexts(t, ns, left, right, max_ctx=200000):
    """Closed set of contexts [l, q, s, r] (tuples).  Returns set or None if
    the closure exceeds the limit."""
    ctxs = set()
    if (0, 0, 0, 0) not in ctxs:
        ctxs.add((0, 0, 0, 0))
    work = list(ctxs)
    nl = len(left)
    nr = len(right)
    while work:
        l, q, s, r = work.pop()
        if l >= nl or r >= nr:
            continue
        tr = trans(t, ns, q, s)
        if tr is None:
            # halting context: reject
            return None
        w, mv, q2 = tr
        if mv == 1:
            # right move: l2 = left[l][w]; for every (r2,s2) with right[r2][s2]==r
            l2 = left[l][w]
            if l2 is None:
                return None
            for r2 in range(nr):
                for s2 in (0, 1):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctxs:
                            if len(ctxs) >= max_ctx:
                                return None
                            ctxs.add(c)
                            work.append(c)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(nl):
                for s2 in (0, 1):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctxs:
                            if len(ctxs) >= max_ctx:
                                return None
                            ctxs.add(c)
                            work.append(c)
    return ctxs


def cert_from_ctxs(t, ns, left, right, ctxs):
    """Build the certificate dict, keeping only transitions used."""
    used_l = set()
    used_r = set()
    out_l = []
    out_r = []
    # we emit automata of size len(left)/len(right) but trim unreachable
    # states by BFS from 0 to keep tables small; map old->new.
    def trim(auto):
        n = len(auto)
        mp = {}
        order = []
        st = [0]
        while st:
            s = st.pop()
            if s in mp:
                continue
            mp[s] = len(order)
            order.append(s)
            for x in (0, 1):
                e = auto[s][x]
                if e is not None and e not in mp:
                    st.append(e)
        new = [[None, None] for _ in range(len(order))]
        for s in order:
            for x in (0, 1):
                e = auto[s][x]
                new[mp[s]][x] = mp.get(e) if e is not None else None
        return new, mp

    nl2, mpl = trim(left)
    nr2, mpr = trim(right)
    # contexts are keyed by states of the original automata; map them
    remap = {}
    for (l, q, s, r) in ctxs:
        if l in mpl and r in mpr:
            remap[(l, q, s, r)] = (mpl[l], q, s, mpr[r])
    # dedupe
    newctx = set(remap.values())
    return {
        "kind": "cps",
        "left": nl2,
        "right": nr2,
        "contexts": [list(c) for c in newctx],
    }


# ---------- decider ----------


def decide(tm: str):
    t, ns, _ = table_of(tm)
    if not blank_ok(t, ns):
        return None
    # quick cycle check first (cheap, catches plain cycles)
    try:
        r = run(tm, 20000)
        if r[0]:
            return None
    except Exception:
        pass
    # enumerate automata sizes
    for maxn in (1, 2, 3):
        autos = []
        seen = set()
        for n, tbl in enumerate_autos(maxn):
            c = canon(tbl)
            if c in seen:
                continue
            seen.add(c)
            autos.append((n, tbl))
        for n1, a1 in autos:
            for n2, a2 in autos:
                ctxs = close_contexts(t, ns, a1, a2)
                if ctxs is None:
                    continue
                # verify with kernel before returning
                cert = cert_from_ctxs(t, ns, a1, a2, ctxs)
                try:
                    check(tm, cert)
                except Reject:
                    continue
                except Exception:
                    continue
                return cert
    return None


if __name__ == "__main__":
    import sys
    tm = sys.argv[1]
    c = decide(tm)
    if c is None:
        print("none")
    else:
        import json
        print(json.dumps(c)[:200])
