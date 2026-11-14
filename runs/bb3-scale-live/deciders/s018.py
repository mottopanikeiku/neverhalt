from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _bounded(t):
    rows = [r for r in t.split("_" if "_" in t else " ")]
    # fallback: bbchallenge uses '_' separator only
    return t


def _all_holdout_machines():
    # We cannot list all 37; the decider is called per-machine anyway.
    return None


def _try_cycle(tm, budget=4000):
    try:
        parsed = parse(tm)
    except Exception:
        return None
    # quick run to find a repeating behavior
    try:
        halted, steps, state, pos, tape = run(tm, budget)
    except Exception:
        return None
    if halted:
        return None
    # Look for a translated cycle: run again from a later point is not possible
    # with run(), so we simulate manually using parse output.
    table, n_states, n_symbols = parsed
    # manual simulation to record configurations
    # states are ints, A = 0
    head = 0
    tape = {}
    cur = 0
    seen = {}
    T = None
    P = None
    for i in range(budget):
        key = (cur, head, tuple(sorted((p, v) for p, v in tape.items())))
        # full tape snapshot too expensive; use window
        if key in seen:
            T = seen[key]
            P = i - T
            break
        seen[key] = i
        # step
        s = tape.get(head, 0)
        tr = table.get((cur, s))
        if tr is None:
            return None
        w, mv, nxt = tr
        tape[head] = w
        if mv > 0:
            head += 1
        else:
            head -= 1
        cur = nxt
    if T is None or P is None:
        return None
    # verify cycle certificate
    try:
        cert = {"kind": "cycle", "t": T, "p": P}
        check(tm, cert)
        return cert
    except Reject:
        return None


def decide(tm: str):
    try:
        return _try_cycle(tm)
    except Exception:
        return None