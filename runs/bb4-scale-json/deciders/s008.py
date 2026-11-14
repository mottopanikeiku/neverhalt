from neverhalt.tm import parse, run
from neverhalt.kernel import Reject, check

# 1-gram CPS with a bounded number of live positions.
# Actually we implement a general "windowed CPS" decider: we try to detect a
# small repeating pattern in the tape head-positions and states, and if the
# pattern is a robust cycle under the 1-gram automaton abstraction we emit a
# certificate.

def _try_cycle(tm, max_steps=60000, lap_span=4000):
    try:
        halted, steps, state, pos, tape = run(tm, max_steps)
    except Exception:
        return None
    if halted:
        return None
    # We look for a repeated (state, pos, window) snapshot.
    # Snapshot includes state, head pos, and a window of the tape around the head.
    # A matched window is enough only if the window is large enough that all
    # future reads are covered -- the kernel's cycle certificate is the
    # rigorous way to test this.  So we just try to find a candidate lap and
    # let the kernel verify it.
    # We re-simulate step by step, keeping snapshots.
    from neverhalt.tm import parse as _parse
    (table, n_states, n_symbols) = _parse(tm)
    head = 0
    state = 0
    tape = {}
    snap = {}
    W = 12
    prev = (state, head, tuple((y, tape.get(y, 0)) for y in range(head - W, head + W + 1)))
    snap[prev] = 0
    for t in range(1, max_steps + 1):
        if (state, 1 - 0) not in table:
            pass
        key = (state, 1)
        if key not in table:
            return None
        w, mv, ns = table[key]
        old = tape.get(head, 0)
        tape[head] = w
        head += mv
        state = ns
        if not (-10**9 < head < 10**9):
            return None
        cur = (state, head, tuple((y, tape.get(y, 0)) for y in range(head - W, head + W + 1)))
        if cur in snap:
            T = snap[cur]
            P = t - T
            if T + P <= 100000:
                # try to emit a cycle certificate
                try:
                    # simulate T and T+P to build tape dicts
                    # (kernel will check anyway, so just try)
                    cert = {"kind": "cycle", "t": T, "p": P}
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
                except Exception:
                    pass
        snap[cur] = t
        if t > max_steps:
            break
    return None


def decide(tm: str):
    r = _try_cycle(tm)
    if r is not None:
        return r
    return None
