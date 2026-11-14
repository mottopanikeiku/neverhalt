from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def _search(tm):
    table, ns, nsym = parse(tm)
    # Rolling snapshot store: keep steps from some low water mark L to current step.
    # Only full-resolution steps in the tail region, so memory stays bounded.
    L = 0
    snaps = []          # snaps[i] corresponds to step L + i
    def snap():
        return (q, head, dict(tape))
    # Step until we have seen enough to detect a lap, at most 20000 steps.
    max_steps = 20000
    t = 0
    q, head = 0, 0
    tape = {}
    while t < max_steps:
        snaps.append(snap())
        if len(snaps) > 5000:
            # drop oldest, advance L
            dropped = len(snaps) - 5000
            L += dropped
            del snaps[:dropped]
        if head < -200 or head > 200:
            # runaway: holdouts may still cycle, but a long tail search is worth it
            # only once; skip after 20000 steps total.
            pass
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
    # Now search the retained window for a lap A->B.
    base = L
    n = len(snaps)
    found = None
    for i in range(n):
        si = snaps[i]
        for j in range(i + 1, min(n, i + 4000)):
            sj = snaps[j]
            if si[0] != sj[0]:
                continue
            cert = {"kind": "cycle", "t": base + i, "p": j - i}
            try:
                kind = check(tm, cert)
                if kind:
                    return cert
            except Reject:
                pass
    return None

def decide(tm: str) -> dict | None:
    try:
        return _search(tm)
    except Exception:
        return None
