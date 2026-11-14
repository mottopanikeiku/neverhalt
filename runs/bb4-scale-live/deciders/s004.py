import sys
from neverhalt.tm import parse, run

def try_cycle(tm, max_steps=100000):
    halted, steps, state, pos, tape = run(tm, max_steps)
    if halted:
        return None
    # replay the trace to find a repeated (state, pos) pair, then verify with kernel
    try:
        from neverhalt.kernel import check
    except Exception:
        return None
    # re-simulate recording (state, pos, tape snapshot) to find candidate laps
    table, n_states, n_symbols = parse(tm)
    tape = {0: 0}
    state = 0
    pos = 0
    seen = {}
    trace = []
    for t in range(max_steps):
        trace.append((state, pos, dict(tape)))
        if (state, pos) in seen:
            T = seen[(state, pos)]
            # try a lap of length (t - T); general: try growing laps from here
            for lap in range(1, t - T + 1):
                pass
        seen[(state, pos)] = t
        key = (state, pos)
        if key in seen and len(trace) > 1:
            pass
        w, mv, ns = table[(state, tape.get(pos, 0))]
        tape[pos] = w
        pos += mv
        state = ns
        if state is None:
            break
    # Fallback: try standard cycle check via kernel on small laps
    # We simulate and look for a repeated full configuration (state,pos,tape)
    # then use kernel check with the lap.
    # Rebuild trace with tape snapshots but bounded memory.
    return None

def decide(tm):
    # Quick attempt: look for a translated or plain cycle in the trace.
    try:
        from neverhalt.kernel import check, Reject
    except Exception:
        return None
    table, n_states, n_symbols = parse(tm)
    tape = {}
    state = 0
    pos = 0
    seen = {}
    t = 0
    max_t = 100000
    # store snapshots as (state, pos, frozenset(tape.items()))
    while t < max_t:
        key = (state, pos, frozenset(tape.items()))
        if key in seen:
            T = seen[key]
            # try lap = t - T
            P = t - T
            if T + P <= 100000:
                try:
                    cert = {"kind": "cycle", "t": T, "p": P}
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
        seen[key] = t
        if state is None:
            return None
        w, mv, ns = table[(state, tape.get(pos, 0))]
        tape[pos] = w
        pos += mv
        state = ns
        t += 1
    return None
