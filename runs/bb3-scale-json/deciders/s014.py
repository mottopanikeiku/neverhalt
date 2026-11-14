import sys

sys.setrecursionlimit(100000)

from neverhalt.tm import parse, run
from neverhalt.kernel import check


def _cert_cycle(tm, T, P):
    return {"kind": "cycle", "t": T, "p": P}


def _try_cycles(tm, limit=100000):
    try:
        table, _, _ = parse(tm)
    except Exception:
        return None
    seen = {}
    steps = 0
    state = 0
    pos = 0
    tape = {}
    try:
        while steps < limit:
            key = (state, pos, tuple(sorted(tape.items())))
            if key in seen:
                T = seen[key]
                P = steps - T
                if T + P <= 100000:
                    return _cert_cycle(tm, T, P)
            seen[key] = steps
            if (state, tape.get(pos, 0)) not in table:
                return None
            w, move, nxt = table[(state, tape.get(pos, 0))]
            tape[pos] = w
            pos += move
            state = nxt
            steps += 1
    except Exception:
        return None
    return None


def decide(tm):
    return _try_cycles(tm, 100000)