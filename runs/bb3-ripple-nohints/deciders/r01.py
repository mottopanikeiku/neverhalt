from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def _find_cycle(tm, max_t=60, max_p=4000, cap=50000):
    # Run far enough for a lap to close, then search for a translated/plain cycle.
    stopped, steps, state, pos, tape = run(tm, cap)
    if stopped:
        return None
    # table of (state, pos, sorted tape region) states is too big; instead use the kernel
    # on the raw trace: find a lap of period p such that the windowed tape matches.
    # Reconstruct the whole trace is too expensive; do it stepwise.
    table, ns, nsym = parse(tm)
    # Simulate and record snapshots sparsely to bound memory.
    # Snapshot format: dict pos->symbol for nonzero cells.
    snaps = []
    t, q, head = 0, 0, 0
    tape = {}
    step = 0
    while step <= max_t + max_p and len(snaps) <= (max_t + max_p) // 64 + 2:
        if len(snaps) == 0 or (step % 64 == 0 and (len(snaps) == 0 or step // 64 > len(snaps) - 1)):
            snaps.append((step, q, head, dict(tape)))
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
        step += 1
    # We need full-resolution data; re-simulate with snapshots every step up to cap,
    # but cap memory by only keeping up to 500 snapshots around the tail region.
    if cap > 5000:
        cap = 5000
    snaps = []
    t, q, head = 0, 0, 0
    tape = {}
    step = 0
    while step <= cap:
        snaps.append((step, q, head, dict(tape)))
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
        step += 1
    # Search for a translated cycle: same state at step A and B, and windows match.
    for A in range(min(max_t, cap // 2)):
        for B in range(A + 1, min(cap, A + max_p)):
            sa, qa, ha, ta = snaps[A]
            sb, qb, hb, tb = snaps[B]
            if qa != qb:
                continue
            # find displacement d such that windows shifted by d match.
            d = hb - ha
            # Determine the span of nonzero cells in ta relative to head.
            keys = sorted(ta.keys())
            if not keys:
                # all blank tape, plain cycle
                cert = {"kind": "cycle", "t": A, "p": B - A}
                try:
                    kind = check(tm, cert)
                    return cert
                except Reject:
                    pass
                continue
            lo = min(k for k in keys if k < ha) if any(k < ha for k in keys) else ha
            hi = max(k for k in keys if k >= ha) if any(k >= ha for k in keys) else ha - 1
            # extend by 64 on each side to cover entering cells
            lo -= 64
            hi += 64
            ok = True
            for y in range(lo + d, hi + 1):
                # cell y at B must equal cell y-d at A
                if tb.get(y) != ta.get(y - d):
                    ok = False
                    break
            if not ok:
                continue
            # Check translation lag condition: cells right of hi at B must be blank
            # (for d > 0) or left of lo for d < 0.
            if d > 0:
                far = [k for k in tb.keys() if k > hi]
            else:
                far = [k for k in tb.keys() if k < lo]
            if far:
                continue
            cert = {"kind": "cycle", "t": A, "p": B - A}
            try:
                kind = check(tm, cert)
                return cert
            except Reject:
                pass
    return None

def decide(tm: str) -> dict | None:
    try:
        return _find_cycle(tm)
    except Exception:
        return None
