import sys
sys.setrecursionlimit(100000)

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def _sim_to(tm, T):
    table, ns, nsym = parse(tm)
    state = 0
    pos = 0
    tape = {}
    seen = []
    for _ in range(T):
        if (state, tape.get(pos, 0)) not in table:
            return None
        w, mv, nxt = table[(state, tape.get(pos, 0))]
        if w:
            tape[pos] = w
        pos += mv
        state = nxt
        seen.append((state, pos, dict(tape)))
    return (state, pos, tape, seen)

def _lap_state(seen, T, P):
    return seen[T][0], seen[T + P - 1][0], seen[T + P - 1][1] - seen[T - 1][1]

def decide(tm):
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    # Try translated cycles with a limited lap search
    for T in range(8, 60):
        r = _sim_to(tm, T)
        if r is None:
            break
        state, pos, tape, seen = r
        # find head range in first T steps
        positions = [s[1] for s in seen] + [pos]
        lo = min(positions)
        hi = max(positions)
        for P in range(1, 60):
            T2 = T + P
            r2 = _sim_to(tm, T2)
            if r2 is None:
                break
            st2, pos2, tape2, seen2 = r2
            if st2 != state:
                continue
            d = pos2 - pos
            ok = True
            for y in range(lo, hi + 1):
                if tape.get(y, 0) != tape2.get(y + d, 0):
                    ok = False
                    break
            if not ok:
                continue
            if d > 0:
                for y in range(hi + 1, hi + d + 1):
                    if tape2.get(y, 0) != 0:
                        ok = False
                        break
            elif d < 0:
                for y in range(lo + d, lo):
                    if tape2.get(y, 0) != 0:
                        ok = False
                        break
            if ok:
                try:
                    check(tm, {"kind": "cycle", "t": T, "p": P})
                    return {"kind": "cycle", "t": T, "p": P}
                except Reject:
                    pass
    return None

NAME = "translated-cycle search"
