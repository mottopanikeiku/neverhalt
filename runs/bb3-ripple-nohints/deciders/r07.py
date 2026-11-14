from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

def _search(tm):
    table, ns, nsym = parse(tm)
    # Full-resolution run long enough to reach the repeating lap in every sample.
    cap = 40000
    snaps = []          # (t, state, head, head_symbol)
    t = 0
    q, head = 0, 0
    tape = {}
    while t < cap:
        hs = tape.get(head, 0)
        snaps.append((t, q, head, hs))
        tr = table.get((q, hs))
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

    n = len(snaps)
    # Equal state and equal head symbol; stride up to 3 * the observed period (40).
    for i in range(n):
        ti, qi, hi, hsi = snaps[i]
        for j in range(i + 1, min(n, i + 40)):
            tj, qj, hj, hsj = snaps[j]
            if qi != qj or hsi != hsj:
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
