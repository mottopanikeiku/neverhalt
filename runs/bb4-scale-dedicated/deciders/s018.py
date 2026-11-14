import sys
from collections import deque
from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


def _halt_states(tm):
    table, ns, nsym = parse(tm)
    out = set()
    for (q, s), v in table.items():
        if v[2] == -1 or v[2] >= ns:
            out.add((q, s))
    return out, table, ns


def _backward_halt_pairs(tm):
    table, ns, nsym = parse(tm)
    pairs = set()
    for (q, s), v in table.items():
        w, mv, q2 = v
        if q2 == -1 or q2 >= ns:
            pairs.add((q, s))
            continue
        # one more step
        if mv == 1:
            pass
        pairs.add((q, s))
    return pairs


def _dfa_partial_states(n):
    # all functions from n states x 2 symbols to 0..n-1
    import itertools
    for vals in itertools.product(range(n), repeat=(n * 2)):
        yield vals


def _dfa_trie(n):
    # BFS-canonical enumeration of deterministic automata with n states
    # (state 0 loops on 0), represented as tuple of length n*2.
    import itertools
    seen = set()
    frontier = [tuple([0] * (n * 2))]
    while frontier:
        cur = frontier.pop(0)
        yield cur
        for i in range(n * 2):
            nxt = list(cur)
            nxt[i] += 1
            if nxt[i] >= n:
                continue
            nxt = tuple(nxt)
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)


def _far_to_head_table(dfa):
    # dfa: tuple of length n*2, index s*n + x
    n = 1
    # caller passes n; recompute from length: length = n*2
    return dfa


def _build_nfa_from_tm(tm):
    table, ns, nsym = parse(tm)
    # NFA over tape symbols (0/1), states = machine states
    # transitions on reading a cell (far to head, i.e. reversed order)
    # We approximate: read cells one at a time towards the head.
    tr = {}
    for (q, s), v in table.items():
        w, mv, q2 = v
        tr[(q, s)] = (q2, w)
    return tr, ns


def _reverse_determinize(tm, n_states_limit=10):
    # Build an NFA whose language is the set of half-tapes that can lead
    # to a halt when read far-to-head. Then determinize by subset
    # construction, using the reversed reading order.
    table, ns, nsym = parse(tm)
    # backward reachable machine states before a halt
    rev = {}
    for (q, s), v in table.items():
        w, mv, q2 = v
        if q2 >= ns or q2 < 0:
            rev.setdefault(q2, set()).add(q)
        else:
            rev.setdefault(q2, set()).add(q)
    # BFS from the halting "next states" backwards
    start = set()
    for (q, s), v in table.items():
        w, mv, q2 = v
        if q2 >= ns or q2 < 0:
            start.add(q)
    # delta: given a tape symbol x (the cell being consumed), which
    # machine state pairs map
    delta = {}
    for (q, s), v in table.items():
        w, mv, q2 = v
        # step: read s under head, write w
        delta[(q2, w)] = delta.get((q2, w), set()) | {q}
    # determinize
    alphabet = (0, 1)
    start_set = frozenset(start)
    dfa = {start_set: {0: start_set, 1: None}}
    # state 0 = all blank: read 0 -> stays
    queue = deque([start_set])
    while queue:
        cur = queue.popleft()
        for x in alphabet:
            nxt = set()
            for q in cur:
                for (qq, w), preds in delta.items():
                    if qq == q and w == x:
                        nxt |= preds
            nxt = frozenset(nxt)
            if nxt not in dfa:
                dfa[nxt] = {}
                queue.append(nxt)
            if dfa[cur].get(x) is None:
                dfa[cur][x] = nxt
    # canonicalize to a tuple indexed by a state order
    order = {}
    for st in dfa:
        if st not in order:
            order[st] = len(order)
    n = len(order)
    arr = [0] * (n * 2)
    for st, idx in order.items():
        for x in alphabet:
            tgt = dfa[st].get(x)
            if tgt is None:
                arr[idx * 2 + x] = -1
            else:
                arr[idx * 2 + x] = order[tgt]
    return arr, n


def _closure(tm, left, right, ns):
    table, nsm, nsym = parse(tm)
    # left/right: tuples length n*2 with entries -1 for null
    # find transitions
    trans = {}
    for q in range(nsm):
        for s in range(2):
            v = table.get((q, s))
            if v is None:
                continue
            w, mv, q2 = v
            if q2 < 0 or q2 >= nsm:
                continue
            trans[(q, s)] = (w, mv, q2)
    # start context
    start = (0, 0, 0, 0)
    ctx = set([start])
    changed = True
    while changed:
        changed = False
        for (l, q, s, r) in list(ctx):
            if (q, s) not in trans:
                continue
            w, mv, q2 = trans[(q, s)]
            if mv == 1:
                l2 = left[l * 2 + w]
                if l2 < 0:
                    continue
                for r2 in range(len(right) // 2):
                    for s2 in range(2):
                        if right[r2 * 2 + s2] == r:
                            nc = (l2, q2, s2, r2)
                            if nc not in ctx:
                                ctx.add(nc)
                                changed = True
            else:
                r2 = right[r * 2 + w]
                if r2 < 0:
                    continue
                for l2 in range(len(left) // 2):
                    for s2 in range(2):
                        if left[l2 * 2 + s2] == l:
                            nc = (l2, q2, s2, r2)
                            if nc not in ctx:
                                ctx.add(nc)
                                changed = True
    # check no halting context
    for (l, q, s, r) in ctx:
        if (q, s) not in trans:
            return None
    # build certificate
    left_cert = []
    right_cert = []
    nl = len(left) // 2
    nr = len(right) // 2
    for i in range(nl):
        row = []
        for x in range(2):
            v = left[i * 2 + x]
            row.append(v if v >= 0 else None)
        left_cert.append(row)
    for i in range(nr):
        row = []
        for x in range(2):
            v = right[i * 2 + x]
            row.append(v if v >= 0 else None)
        right_cert.append(row)
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    return {"kind": "cps", "left": left_cert, "right": right_cert, "contexts": contexts}


def decide(tm):
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    # Try to find a pair of half-tape DFAs.
    # First try a small handcrafted search over both sides using the
    # reverse-determinization routine for one side and a small
    # enumerated DFA for the other.
    # Because of the time budget, only try a few sizes.
    for n1 in range(1, 4):
        # enumerate a small DFA for the left side
        for arr in _dfa_trie(n1):
            for n2 in range(1, 4):
                for arr2 in _dfa_trie(n2):
                    cert = _closure(tm, arr, arr2, ns)
                    if cert is not None:
                        try:
                            check(tm, cert)
                            return cert
                        except Reject:
                            pass
    # Fallback: try reverse-determinized automata for both sides
    try:
        arr1, n1 = _reverse_determinize(tm)
        if n1 <= 10:
            for n2 in range(1, 4):
                for arr2 in _dfa_trie(n2):
                    cert = _closure(tm, arr1, arr2, ns)
                    if cert is not None:
                        try:
                            check(tm, cert)
                            return cert
                        except Reject:
                            pass
            for n2 in range(1, 4):
                for arr2 in _dfa_trie(n2):
                    cert = _closure(tm, arr2, arr1, ns)
                    if cert is not None:
                        try:
                            check(tm, cert)
                            return cert
                        except Reject:
                            pass
    except Exception:
        pass
    return None


if __name__ == "__main__":
    print(decide("0RB1RA_1LC---_1LD0RB_0RA0LC"))
