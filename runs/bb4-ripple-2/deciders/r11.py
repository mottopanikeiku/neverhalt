from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


def decide(tm):
    table, ns, nsym = parse(tm)
    tr = [[None] * nsym for _ in range(ns)]
    for (st, sym), ent in table.items():
        tr[st][sym] = ent

    # find a short cycle of states in any symbol-supported order
    cyc = _find_cycle(tr, ns, nsym)
    if cyc is None:
        return None

    # a cycle automaton with count offset, plus its own non-halting check
    cert = _cycle_cert(tr, ns, cyc)
    if cert is not None:
        try:
            check(tm, cert)
            return cert
        except Reject:
            pass
    return None


def _find_cycle(tr, ns, nsym):
    # 5-state loop: try state order 0->1->2->3->4->0 within the table
    order = None
    for start in range(ns):
        chain = []
        cur = start
        seen = set()
        for _ in range(8):
            chain.append(cur)
            seen.add(cur)
            if cur == start and len(chain) > 1:
                order = chain
                break
            cur = (cur + 1) % ns
            if cur in seen:
                break
    if order is None:
        return None
    # require that each transition exists for some symbol
    for i in range(len(order) - 1):
        ok = False
        for x in range(nsym):
            if tr[order[i]][x] is not None:
                w, mv, q2 = tr[order[i]][x]
                if q2 == order[i + 1]:
                    ok = True
                    break
        if not ok:
            return None
    return order


def _cycle_cert(tr, ns, cyc):
    # cycle automaton: state 0 loops on 0; states 1..k are count-offset states
    k = len(cyc)
    left = [[0] * nsym for _ in range(k + 1)]
    right = [[0] * nsym for _ in range(k + 1)]
    contexts = set()
    # seeds: start with machine in any state, offset 0, blank half-tapes
    for q in cyc:
        contexts.add((0, q, 0, 0))
    for q in cyc:
        contexts.add((0, q, 1, 0))
    seen = True
    guard = 0
    while seen:
        seen = False
        guard += 1
        if guard > 60000:
            return None
        for (l, q, s, r) in list(contexts):
            ent = tr[q][s]
            if ent is None:
                return None
            w, mv, q2 = ent
            nq = cyc[(cyc.index(q) + 1) % len(cyc)]
            nxt = (l, nq, w, r)
            if nxt not in contexts:
                contexts.add(nxt)
                seen = True
    if len(contexts) > 200000:
        return None
    for (l, q, s, r) in contexts:
        if tr[q][s] is None:
            return None
    return {
        "kind": "cps",
        "left": left,
        "right": right,
        "contexts": [[l, q, s, r] for (l, q, s, r) in contexts],
    }
