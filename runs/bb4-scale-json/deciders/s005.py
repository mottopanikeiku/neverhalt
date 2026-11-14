import sys
sys.setrecursionlimit(100000)

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None

    # Try a plain cycle certificate first (short lap).
    for T in range(0, 20000):
        try:
            halted, steps, state, pos, tape = run(tm, T + 4000)
        except Exception:
            return None
        if halted:
            return None
        if steps < T:
            return None
        # simulate the lap
        try:
            halted2, steps2, state2, pos2, tape2 = run(tm, T + 4000)
        except Exception:
            return None
        if halted2:
            return None
        if steps2 != T + 4000:
            return None
        # find lap boundary states
        # Instead of a full search, we look for a repeated state at equal tape
        # configuration modulo a shift over a window.
        # Simple approach: check for repeated (state, pos, tape-window) pairs.
        break

    # Direct approach: search for translated cycle over a window.
    held = 6000
    try:
        halted, steps, state, pos, tape = run(tm, held)
    except Exception:
        return None
    if halted:
        return None

    # Re-run and record configurations
    configs = []
    try:
        from neverhalt.tm import parse, run
    except Exception:
        return None

    # Manual simulation for flexibility
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None

    tape = {}
    pos = 0
    st = 0
    seen = {}
    snapshots = []
    for step in range(held):
        key = (st, pos)
        if key in seen:
            # possible lap
            T = seen[key]
            P = step - T
            if T + P > 100000:
                return None
            # get snapshots at T and step
            tT = snapshots[T]
            tP = snapshots[step]
            # check tape equality at T+P shifted by d = (pos at step - pos at T)
            d = tP['pos'] - tT['pos']
            if d == 0:
                if tP['tape'] == tT['tape']:
                    cert = {"kind": "cycle", "t": T, "p": P}
                    try:
                        r = check(tm, cert)
                        if r:
                            return cert
                    except Reject:
                        pass
            else:
                # translated cycle: need window
                loT, hiT = tT['lo'], tT['hi']
                loP, hiP = tP['lo'], tP['hi']
                # window at T+P is [loP - d, hiP - d] in T coordinates
                ok = True
                # check all cells in window at T
                for y in range(loT, hiT + 1):
                    need = tP['tape'].get(y + d, 0)
                    have = tT['tape'].get(y, 0)
                    if need != have:
                        ok = False
                        break
                if ok:
                    # check outside window blank at T+P on far side
                    if d > 0:
                        # cells right of hiP at T+P must be blank
                        for y in range(hiP + 1, hiP + 1):
                            pass
                        # check all positions > hiP in tape2 are blank
                        for y, v in tP['tape'].items():
                            if y > hiP and v != 0:
                                ok = False
                                break
                    elif d < 0:
                        for y, v in tP['tape'].items():
                            if y < loP and v != 0:
                                ok = False
                                break
                if ok:
                    cert = {"kind": "cycle", "t": T, "p": P}
                    try:
                        r = check(tm, cert)
                        if r:
                            return cert
                    except Reject:
                        pass
        if key not in seen:
            seen[key] = step
        snapshots.append({'st': st, 'pos': pos, 'tape': dict(tape),
                          'lo': min(tape.keys()) if tape else pos,
                          'hi': max(tape.keys()) if tape else pos})
        # step the machine
        w, mv, ns = table.get((st, tape.get(pos, 0)), (None, None, None))
        if w is None:
            return None
        tape[pos] = w
        pos += mv
        st = ns

    return None
