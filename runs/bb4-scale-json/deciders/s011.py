from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from itertools import product

def decide(tm: str) -> dict | None:
    table, nstates, nsym = parse(tm)
    # Broad translated-cycle search with large lap window and both directions.
    for T in range(0, 20000):
        try:
            halted, steps, state, pos, tape = run(tm, 40000)
        except Exception:
            return None
        if halted:
            return None
        # Try laps from the current state at time T to a later time.
        for P in range(1, 30000 - T):
            try:
                # Re-run from scratch to time T+P; expensive but bounded.
                h, s, st, ps, tp = run(tm, T + P)
            except Exception:
                return None
            if h:
                return None
            # Compare window [lo, hi] over lap.
            lo = min(pos, ps) - 2
            hi = max(pos, ps) + 2
            d = ps - pos
            ok = True
            if state != st:
                ok = False
            if ok:
                for y in range(lo, hi + 1):
                    v1 = tape.get(y, 0)
                    v2 = tp.get(y + d, 0)
                    if v1 != v2:
                        ok = False
                        break
            if ok and d != 0:
                if d > 0:
                    for y in range(hi + 1, pos + 100):
                        if tp.get(y, 0) != 0:
                            ok = False
                            break
                else:
                    for y in range(hi - 100, lo):
                        if tp.get(y, 0) != 0:
                            ok = False
                            break
            if ok:
                try:
                    check(tm, {"kind": "cycle", "t": T, "p": P})
                    return {"kind": "cycle", "t": T, "p": P}
                except Reject:
                    pass
    return None