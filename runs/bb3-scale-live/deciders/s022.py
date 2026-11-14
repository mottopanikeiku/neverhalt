import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# T-step translation invariant: if the window content repeats shifted by d
# while the head position stays bounded, the machine is in a translated cycle.
# We search T and P with a bounded window and verify with the kernel.

MAX_T = 4000
MAX_P = 4000

def decide(tm: str):
    try:
        halted, steps, state, pos, tape = run(tm, 400)
    except Exception:
        return None
    if halted:
        return None

    # try many (T, P) pairs, small first
    for T in range(1, MAX_T + 1, 1):
        try:
            h, st, sT, pT, tapeT = run(tm, T)
        except Exception:
            return None
        if h:
            return None
        for P in range(1, MAX_P + 1):
            try:
                h2, st2, sT2, pT2, tapeT2 = run(tm, T + P)
            except Exception:
                break
            if h2:
                return None
            d = pT2 - pT
            if d == 0:
                # plain cycle candidate
                lo = min(tapeT.keys()) if tapeT else pT
                hi = max(tapeT.keys()) if tapeT else pT
                if sT2 == sT and all(tapeT2.get(y + d) == tapeT.get(y) for y in range(lo, hi + 1)):
                    cert = {"kind": "cycle", "t": T, "p": P}
                    try:
                        return check(tm, cert)
                    except Reject:
                        pass
            else:
                # translated cycle; window from min to max of T window
                if sT2 == sT:
                    allpos = sorted(set(list(tapeT.keys()) + list(tapeT2.keys())))
                    if not allpos:
                        continue
                    lo = min(allpos) - abs(d) - 1
                    hi = max(allpos) + abs(d) + 1
                    ok = True
                    for y in range(lo, hi + 1):
                        if tapeT2.get(y + d) != tapeT.get(y):
                            ok = False
                            break
                    if ok:
                        # far side blank condition
                        if d > 0:
                            for y in range(hi + 1, hi + 1 + abs(d) + 1):
                                if tapeT2.get(y) not in (0, None):
                                    ok = False
                                    break
                        else:
                            for y in range(lo - abs(d) - 1, lo):
                                if tapeT2.get(y) not in (0, None):
                                    ok = False
                                    break
                        if ok:
                            cert = {"kind": "cycle", "t": T, "p": P}
                            try:
                                return check(tm, cert)
                            except Reject:
                                pass
    return None
