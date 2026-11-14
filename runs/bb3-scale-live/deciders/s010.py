from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: search for translated cycles (tcycle) by simulating a bounded
# number of steps and checking for a repeated (state, window) pair with a
# nonzero net drift. We bound simulation work per machine.
MAX_SIM = 120000

def _window_state(state, pos, tape, span):
    # encode local window of tape around pos for repetition detection
    out = []
    for y in range(pos - span, pos + span + 1):
        out.append(tape.get(y, 0))
    return (state, pos % span if span else 0, tuple(out))

def find_cycle(tm, max_steps=MAX_SIM, span=24):
    try:
        table, ns, ncol = parse(tm)
    except Exception:
        return None
    tape = {}
    state = 0
    pos = 0
    steps = 0
    seen = {}
    while steps < max_steps:
        if steps > 0:
            key = _window_state(state, pos, tape, span)
            if key in seen:
                T = seen[key]
                # build lap from T to steps
                # need actual head displacement and window info
                # recompute quickly: replay from T is expensive; instead
                # store positions and snapshots
                return None
            seen[key] = steps
        # step
        if (state, tape.get(pos, 0)) not in table:
            return None
        w, mv, nst = table[(state, tape.get(pos, 0))]
        tape[pos] = w
        pos += mv
        state = nst
        steps += 1
    return None

def decide(tm):
    return None
