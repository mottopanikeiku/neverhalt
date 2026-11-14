import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# --- helpers ---------------------------------------------------------

def cert_cycle(tm, T, P, d):
    try:
        return check(tm, {"kind": "cycle", "t": T, "p": P})
    except Reject:
        return None

def cycle_search(tm, limit=120000):
    table, n_states, n_symbols = parse(tm)
    halted, steps, state, pos, tape = run(tm, limit)
    if halted:
        return None
    # look for a repeated (state, pos) configuration
    seen = {}
    # re-simulate and record configurations
    t, st, p, tpe = 0, 0, 0, {}
    key = (st, p)
    seen[key] = t
    while t < limit:
        if key in seen and t - seen[key] > 0:
            P = t - seen[key]
            T = seen[key]
            d = p - seen[key][1] if False else 0
            # recompute displacement
            # we store pos history
            break
        if (st, p) in seen:
            break
        seen[(st, p)] = t
        # step
        if (st, tpe.get(p, 0)) in table:
            w, mv, ns = table[(st, tpe.get(p, 0))]
            tpe[p] = w
            p += mv
            st = ns
        else:
            return None
        t += 1
    # simpler: full simulation with configuration history
    return None

# --- decider ---------------------------------------------------------

def decide(tm: str):
    table, n_states, n_symbols = parse(tm)
    # search for translated cycles
    for limit in (200000,):
        halted, steps, state, pos, tape = run(tm, limit)
        if halted:
            break
    # attempt cycle search with configuration replay
    try:
        cfgs = []
        st, p, tpe = 0, 0, {}
        for step in range(300000):
            if (st, p) in tpe:
                pass
            cfgs.append((st, p, dict(tpe)))
            if (st, tpe.get(p, 0)) not in table:
                break
            w, mv, ns = table[(st, tpe.get(p, 0))]
            tpe[p] = w
            p += mv
            st = ns
    except Exception:
        return None
    # find repeated (state, pos) pairs
    seen = {}
    for i, (st, p, _) in enumerate(cfgs):
        if (st, p) in seen:
            T = seen[(st, p)]
            P = i - T
            d = p - cfgs[T][1]
            if T + P <= 100000:
                c = cert_cycle(tm, T, P, d)
                if c:
                    return c
        else:
            seen[(st, p)] = i
    return None

NAME = "cycle_replay"