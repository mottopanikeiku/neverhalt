from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _parse_tm(tm):
    table, ns, nss = parse(tm)
    return table, ns, nss


def _build_ctxs(tm, left, right):
    """Try to close the context set for automata left/right. Return list of contexts or None."""
    table, ns, nss = _parse_tm(tm)
    # halting transitions are absent from table
    seen = {(0, 0, 0, 0)}
    frontier = [(0, 0, 0, 0)]
    ctxs = []
    while frontier:
        newf = []
        for (l, q, s, r) in frontier:
            if (q, s) not in table:
                return None
            w, mv, q2 = table[(q, s)]
            if mv == 1:
                if w not in left[l] or left[l][w] is None:
                    return None
                l2 = left[l][w]
                for (r2, s2) in _right_pairs(right, r):
                    c = (l2, q2, s2, r2)
                    if c not in seen:
                        seen.add(c)
                        ctxs.append(c)
                        newf.append(c)
            else:
                if w not in right[r] or right[r][w] is None:
                    return None
                r2 = right[r][w]
                for (l2, s2) in _left_pairs(left, l):
                    c = (l2, q2, s2, r2)
                    if c not in seen:
                        seen.add(c)
                        ctxs.append(c)
                        newf.append(c)
        frontier = newf
    return ctxs


def _right_pairs(right, r):
    out = []
    for r2, row in right.items():
        for s2, v in enumerate(row):
            if v == r:
                out.append((r2, s2))
    return out


def _left_pairs(left, l):
    out = []
    for l2, row in left.items():
        for s2, v in enumerate(row):
            if v == l:
                out.append((l2, s2))
    return out


def _emit(tm, left, right):
    ctxs = _build_ctxs(tm, left, right)
    if ctxs is None:
        return None
    if len(ctxs) > 200000:
        return None
    # represent automata as 0-indexed rows; keep only used states, remap
    used_l = sorted({c[0] for c in ctxs})
    used_r = sorted({c[3] for c in ctxs})
    # require state 0 present
    if 0 not in used_l or 0 not in used_r:
        return None
    lmap = {s: i for i, s in enumerate(used_l)}
    rmap = {s: i for i, s in enumerate(used_r)}
    table, ns, nss = _parse_tm(tm)
    left_rows = []
    for s in used_l:
        row = []
        for x in range(2):
            v = left.get(s, {}).get(x)
            row.append(lmap[v] if v is not None and v in lmap else None)
        left_rows.append(row)
    right_rows = []
    for s in used_r:
        row = []
        for x in range(2):
            v = right.get(s, {}).get(x)
            row.append(rmap[v] if v is not None and v in rmap else None)
        right_rows.append(row)
    contexts = []
    for (l, q, s, r) in ctxs:
        contexts.append([lmap[l], q, s, rmap[r]])
    cert = {"kind": "cps", "left": left_rows, "right": right_rows, "contexts": contexts}
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None


def _gen_automata(max_states=5):
    """Yield automata as dicts: state -> {sym: state or None}, state 0 loops on 0."""
    # BFS-canonical enumeration of deterministic partial automata over {0,1}
    results = []
    # represent a partial DFA by a tuple of rows, each row a pair (d0,d1) with -1 = None
    # enumerate states count 1..max_states; canonical BFS from state 0
    for n in range(1, max_states + 1):
        # enumerate all functions 0..n-1 -> {-1,0,1}^2, canonical under BFS
        # use recursive enumeration with BFS canonical form
        rows = [(-1, -1)] * n
        # force state 0 loop on 0
        rows[0] = (0, -1)
        # enumerate remaining entries
        idx = [0]

        def rec(pos):
            if pos >= n * 2:
                # canonical BFS check
                if _canonical(rows, n):
                    d = {}
                    for st in range(n):
                        d[st] = {}
                        for x in range(2):
                            v = rows[st * 2 + x]
                            if v >= 0:
                                d[st][x] = v
                    results.append(d)
                return
            st = pos // 2
            x = pos % 2
            for v in (-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9):
                if v >= n:
                    break
                rows[pos] = v
                rec(pos + 1)
            rows[pos] = -1

        rec(0)
    # dedupe by canonical form
    seen = set()
    out = []
    for d in results:
        key = _aut_key(d)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def _aut_key(d):
    # BFS canonical labeling
    n = max(d.keys()) + 1
    label = {}
    order = []
    label[0] = 0
    order.append(0)
    i = 0
    while i < len(order):
        st = order[i]
        i += 1
        for x in (0, 1):
            v = d.get(st, {}).get(x)
            if v is not None and v not in label:
                label[v] = len(order)
                order.append(v)
    rows = []
    for st in range(n):
        row = []
        for x in (0, 1):
            v = d.get(st, {}).get(x)
            row.append(label[v] if v is not None and v in label else -1)
        rows.append(tuple(row))
    # relabel by BFS discovery order already canonical
    return tuple(rows)


def _canonical(rows, n):
    # check BFS canonical: states discovered in order, first occurrence determines label
    label = {}
    order = []
    label[0] = 0
    order.append(0)
    i = 0
    while i < len(order):
        st = order[i]
        i += 1
        for x in (0, 1):
            v = rows[st * 2 + x]
            if v >= 0 and v not in label:
                label[v] = len(order)
                order.append(v)
    if len(order) != n:
        return False
    for st in range(n):
        if label.get(st) != st:
            return False
    return True


def decide(tm: str):
    table, ns, nss = _parse_tm(tm)
    # cheap translated-cycle first
    c = _try_cycle(tm)
    if c is not None:
        return c
    autos = _gen_automata(4)
    # try all pairs of automata, both orientations
    for i, la in enumerate(autos):
        for lb in autos[i:]:
            c = _emit(tm, la, lb)
            if c is not None:
                return c
            c = _emit(tm, lb, la)
            if c is not None:
                return c
    return None


def _try_cycle(tm):
    try:
        table, ns, nss = _parse_tm(tm)
    except Exception:
        return None
    # simulate and look for repeated (state, pos, tape-window) patterns
    from neverhalt.tm import run
    # run 2000 steps; if still running, try to find a translated cycle by matching
    # a window of the last 40 cells and state
    try:
        halted, steps, state, pos, tape = run(tm, 3000)
        if halted:
            return None
    except Exception:
        return None
    # take snapshot at 2500
    try:
        halted, steps, state, pos, tape = run(tm, 2500)
    except Exception:
        return None
    snap1 = (state, pos, dict(tape))
    # run 40 more steps, snapshot
    try:
        halted, steps2, state2, pos2, tape2 = run(tm, 2540)
    except Exception:
        return None
    if halted:
        return None
    # check translated cycle: find d such that state same and tape shifted
    # simple: compare tape at 2500 and 2540 for shifts
    for d in range(-20, 21):
        if state != state2:
            continue
        ok = True
        for y, v in tape.items():
            if tape2.get(y + d) != v:
                ok = False
                break
        if ok:
            # check blanks beyond
            if d > 0:
                hi = max(tape.keys()) if tape else pos
                for y in range(hi + 1, hi + 1 + abs(d) + 5):
                    if tape2.get(y) != 0:
                        ok = False
                        break
            else:
                lo = min(tape.keys()) if tape else pos
                for y in range(lo - abs(d) - 5, lo):
                    if tape2.get(y) != 0:
                        ok = False
                        break
        if ok:
            cert = {"kind": "cycle", "t": 2500, "p": 40}
            try:
                from neverhalt.kernel import check
                check(tm, cert)
                return cert
            except Exception:
                pass
    return None


if __name__ == "__main__":
    import sys
    print(decide(sys.argv[1]))
    print(_gen_automata(2))
