import sys
from neverhalt.tm import run

sys.setrecursionlimit(100000)

def decide(tm):
    # Try to find a translated cycle: simulate a bounded number of steps,
    # then look for a pair (T, T+P) with the same state and a window that
    # shifts by d = head displacement, reproducing the tape on the window.
    # We simulate once, storing states/positions/tapes at every step.
    max_steps = 4000
    try:
        halted, steps, state, pos, tape = run(tm, max_steps)
    except Exception:
        return None
    if halted:
        return None

    # Re-simulate collecting snapshots (positions, state, tape copy) at each step.
    # We use run() in chunks to capture the trace: easier to run stepwise.
    trace = []  # (state, pos, tape_dict)
    try:
        from neverhalt.tm import parse
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None

    # Manual simulation to keep trace.
    pos = 0
    state = 0
    tape = {}
    trace.append((state, pos, dict(tape)))
    for i in range(max_steps):
        key = (state, tape.get(pos, 0))
        if key not in table:
            return None  # halted -> not our decider's business
        w, move, ns = table[key]
        if w != tape.get(pos, 0):
            tape[pos] = w
        elif pos in tape and tape[pos] == 0:
            # keep zeros only when needed; store non-zero
            pass
        # normalize: keep only non-zero
        if w == 0:
            tape.pop(pos, None)
        pos += move
        state = ns
        trace.append((state, pos, dict(tape)))

    n = len(trace)
    # Look for translated cycles: for each T, for a set of P values, check state equality
    # and window consistency.
    # We need a window [lo, hi] and d such that tape_{T+P}[y+d] == tape_T[y] for y in window,
    # and outside window on the far side blank.
    # Simplification: take window = union of head positions in [T, T+P] plus one margin.
    # Then d = pos(T+P) - pos(T).
    max_P = n // 2
    results = []
    for T in range(0, n - 50, 1):
        st_T, pos_T, tape_T = trace[T]
        for P in range(1, max_P):
            st_P, pos_P, tape_P = trace[T + P]
            if st_T != st_P:
                continue
            d = pos_P - pos_T
            # window: positions visited in [T, T+P] plus margin 2
            lo = min(p for (_, p, _) in trace[T:T + P + 1]) - 2
            hi = max(p for (_, p, _) in trace[T:T + P + 1]) + 2
            # check window content shift
            ok = True
            for y in range(lo, hi + 1):
                a = tape_T.get(y, 0)
                b = tape_P.get(y + d, 0)
                if a != b:
                    ok = False
                    break
            if not ok:
                continue
            # check far side blank
            if d > 0:
                # cells right of hi must be blank at T+P
                for y in range(hi + 1, hi + 30):
                    if tape_P.get(y, 0) != 0:
                        ok = False
                        break
            elif d < 0:
                for y in range(lo - 30, lo):
                    if tape_P.get(y, 0) != 0:
                        ok = False
                        break
            else:
                # d == 0 plain cycle: also require tape unchanged on window
                pass
            if ok:
                return {"kind": "cycle", "t": T, "p": P}
    return None
