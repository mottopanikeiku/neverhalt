from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def _stride_lap(tm):
    table, ns, nsym = parse(tm)
    snaps = []
    t = 0
    q, head = 0, 0
    tape = {}
    cap = 4000
    while t < cap:
        # sparse snapshot: store dense tape only for the last 512 steps
        if t % 512 == 0:
            snaps.append((t, q, head))
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
    # Enough to find the first lap; now do a focused re-simulation of up to 256 steps
    # around any repeated (state) anchor in the sparse list.
    # Return a verified lap by scanning a denser tail.
    snaps = []
    t = 0
    q, head = 0, 0
    tape = {}
    dense_from = 0
    while t < 350:
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
    # From the first cycle pattern onward, run a short window of length 240 further
    # and test a handful of plausible laps: p in {2..16}, t in {3..200}.
    for t0 in range(0, min(len(snaps), 400)):
        q0, h0, ta = snaps[t0][1], snaps[t0][2], snaps[t0][3]
        for p in range(1, 17):
            # quick pre-checks instead of a second simulation: head displacement
            if t0 + p > len(snaps):
                continue
            q1, h1 = snaps[t0 + p][1], snaps[t0 + p][2]
            if q0 != q1:
                continue
            cert = {"kind": "cycle", "t": t0, "p": p}
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    # Wider: many laps have longer stride for the same state pair.
    for t0 in range(0, min(len(snaps), 700)):
        q0, h0, ta = snaps[t0][1], snaps[t0][2], snaps[t0][3]
        for p in range(16, min(300, len(snaps) - t0)):
            q1, h1 = snaps[t0 + p][1], snaps[t0 + p][2]
            if q0 != q1:
                continue
            cert = {"kind": "cycle", "t": t0, "p": p}
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    return None

def decide(tm: str) -> dict | None:
    try:
        return _stride_lap(tm)
    except Exception:
        return None
