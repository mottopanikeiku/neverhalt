import itertools, sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def decide(tm: str) -> dict | None:
    # Try to find a small translated cycle (tcycle).
    best = None
    for T in range(0, 300):
        for P in range(1, 60):
            if T + P > 350:
                break
            try:
                halted, steps, state, pos, tape = run(tm, T + P)
            except Exception:
                return None
            if halted:
                return None
            # Recompute tape at T and T+P
            try:
                h1, s1, st1, p1, t1 = run(tm, T)
                h2, s2, st2, p2, t2 = run(tm, T + P)
            except Exception:
                return None
            if h1 or h2:
                return None
            if st1 != st2:
                continue
            # head displacement over lap
            d = p2 - p1
            # find head positions during lap
            lo = p1; hi = p1
            for i in range(1, P + 1):
                # need head positions; approximate by simulating step by step
                pass
            # Simulate lap collecting head positions
            try:
                h, st, p, t = run(tm, T)
                positions = [p]
                for _ in range(P):
                    # step manually: we can just re-run T+i
                    pass
            except Exception:
                return None
            # Use a simple step-by-step simulation
            try:
                h, st, p, t = run(tm, T)
            except Exception:
                return None
            positions = [p]
            for i in range(P):
                # step one more
                try:
                    h, st, p, t = run(tm, T + i + 1)
                except Exception:
                    return None
                if h:
                    break
                positions.append(p)
            if h:
                return None
            lo = min(positions); hi = max(positions)
            # check tape match shifted
            ok = True
            for y in range(lo, hi + 1):
                v1 = t1.get(y, 0)
                v2 = t2.get(y + d, 0)
                if v1 != v2:
                    ok = False
                    break
            if not ok:
                continue
            if d > 0:
                # every cell right of hi is blank at T+P
                for y in range(hi + 1, hi + 200):
                    if t2.get(y, 0) != 0:
                        ok = False
                        break
            elif d < 0:
                for y in range(lo - 200, lo):
                    if t2.get(y, 0) != 0:
                        ok = False
                        break
            if not ok:
                continue
            cert = {"kind": "cycle", "t": T, "p": P}
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    return None
