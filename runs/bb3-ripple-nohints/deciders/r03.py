from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def _staircase(tm):
    table, ns, nsym = parse(tm)
    # Snapshot the last N configurations at full resolution but keep the run short:
    # the repeating growth pattern appears well within 8 * 1024 steps.
    cap = 8 * 1024
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
    n = len(snaps)
    # Look for a lap where the same state and same head displacement occurs twice
    # and every cell between the head and the leftmost occupied cell has the same value.
    for i in range(n):
        ti, qi, hi, ta = snaps[i]
        for j in range(i + 1, min(n, i + 2048)):
            tj, qj, hj, tb = snaps[j]
            if qi != qj:
                continue
            d = hj - hi
            if d == 0:
                continue
            # Check overlap over the union of occupied cells plus a margin.
            keysa = set(ta.keys()) | {hi}
            keysa.update(range(hi, hi + 200))
            keysa.update(range(hi - 200, hi))
            keysb = set(tb.keys()) | {hj}
            keysb.update(range(hj, hj + 200))
            keysb.update(range(hj - 200, hj))
            ok = True
            for y in keysa:
                if ta.get(y) != tb.get(y + d):
                    ok = False
                    break
            if not ok:
                continue
            cert = {"kind": "cycle", "t": ti, "p": tj - ti}
            try:
                kind = check(tm, cert)
                if kind:
                    # verify it's a translated cycle certificate
                    return cert
            except Reject:
                pass
    return None

def decide(tm: str) -> dict | None:
    try:
        return _staircase(tm)
    except Exception:
        return None
