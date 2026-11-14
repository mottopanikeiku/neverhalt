from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

def _search(tm):
    table, ns, nsym = parse(tm)
    # Full-resolution trace with a modest cap; these remaining holdouts settle
    # within a few thousand steps and the lap is short enough to verify.
    cap = 20000
    snaps = []
    t = 0
    q, head = 0, 0
    tape = {}
    while t < cap:
        snaps.append((t, q, head, dict(tape)))
        tr = table.get((q, tape.get(head, 0)))
        if tr is None:
            return None
        w, mv, q2 = tr
        if w:
            tape[head] = w
        else:
            tape.pop(head, None)
        head += mv
        q = q2
        t += 1

    # Find pairs (i, j) with equal state/symbol at the same *relative* tape shape.
    # Quick pre-filter: same state and same tape region up to a small margin.
    n = len(snaps)
    for i in range(n):
        ti, qi, hi, ta = snaps[i]
        for j in range(i + 1, min(n, i + 64)):
            tj, qj, hj, tb = snaps[j]
            if qi != qj:
                continue
            # Same head symbol is required for a translated-cycle lap.
            if ta.get(hi, 0) != tb.get(hj, 0):
                continue
            cert = {"kind": "cycle", "t": ti, "p": tj - ti}
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    return None

def decide(tm: str) -> dict | None:
    try:
        return _search(tm)
    except Exception:
        return None
