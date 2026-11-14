from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # simulate and record head positions and full tape snapshots as step count
    try:
        halted, steps, state, pos, tape0 = run(tm, 2000)
    except Exception:
        return None
    if halted:
        return None
    # re-simulate recording histories
    head = []
    states = []
    tape_hist = []
    try:
        # manual simulation with full dict copies for window checking
        from neverhalt.tm import parse as _parse
        # table: dict[(state,symbol)] = (write, move, next_state)
        st = 0
        p = 0
        tape = {}
        hist_head = []
        hist_state = []
        hist_tape = []
        for i in range(3000):
            hist_head.append(p)
            hist_state.append(st)
            hist_tape.append(dict(tape))
            sym = tape.get(p, 0)
            tr = table.get((st, sym))
            if tr is None:
                return None
            w, mv, ns = tr
            tape[p] = w
            if w == 0:
                tape.pop(p, None)
            p += mv
            st = ns
    except Exception:
        return None
    # search for translated cycle: state at T equals state at T+P, window content shifts
    N = len(hist_head)
    # limit search
    maxT = min(N - 1, 600)
    maxP = min(N - maxT - 1, 600)
    for T in range(maxT):
        sT = hist_state[T]
        for P in range(1, maxP + 1):
            if T + P >= N:
                break
            if hist_state[T + P] != sT:
                continue
            # compute displacement
            d = hist_head[T + P] - hist_head[T]
            if d == 0:
                continue
            # collect window positions during lap
            lo = min(hist_head[T:T + P + 1])
            hi = max(hist_head[T:T + 1])
            # window content at T+P shifted by d must equal at T for all y in [lo,hi]
            ok = True
            for y in range(lo, hi + 1):
                vT = hist_tape[T].get(y, 0)
                vP = hist_tape[T + P].get(y + d, 0)
                if vT != vP:
                    ok = False
                    break
            if not ok:
                continue
            # far side blankness
            if d > 0:
                for y in range(hi + 1, hi + 1 + abs(d)):
                    if hist_tape[T + P].get(y, 0) != 0:
                        ok = False
                        break
            else:
                for y in range(lo - abs(d), lo):
                    if hist_tape[T + P].get(y, 0) != 0:
                        ok = False
                        break
            if ok:
                cert = {"kind": "cycle", "t": T, "p": P}
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
    # try plain cycle d=0
    for T in range(maxT):
        for P in range(1, maxP + 1):
            if T + P >= N:
                break
            if hist_state[T + P] != hist_state[T]:
                continue
            # check tape same within head visited range
            lo = min(hist_head[T:T + P + 1])
            hi = max(hist_head[T:T + P + 1])
            ok = True
            for y in range(lo, hi + 1):
                if hist_tape[T].get(y, 0) != hist_tape[T + P].get(y, 0):
                    ok = False
                    break
            if ok:
                cert = {"kind": "cycle", "t": T, "p": P}
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
    return None
}  