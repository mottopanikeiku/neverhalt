from neverhalt.tm import parse
from neverhalt.kernel import check


def decide(tm):
    try:
        table, ns, nsy = parse(tm)
    except Exception:
        return None

    # A cheap general probe: simulate, and when the local window
    # configuration repeats, ask the kernel for a cycle / translated
    # cycle certificate over the lap in between.
    W = 3
    offs = list(range(-W, W + 1))
    tape = {}
    pos = 0
    state = 0
    occ = {}
    Tmax = 30000

    for t in range(Tmax):
        vals = tuple(tape.get(pos + k, 0) for k in offs)
        key = (state,) + vals
        lst = occ.get(key)
        if lst is not None:
            for (t0, p0) in lst:
                P = t - t0
                if P <= 0 or t0 + P > 90000:
                    continue
                cert = {"kind": "cycle", "t": t0, "p": P}
                try:
                    check(tm, cert)
                    return cert
                except Exception:
                    pass
        else:
            occ[key] = [(t, pos)]

        k = (state, tape.get(pos, 0))
        if k not in table:
            return None
        w, mv, nst = table[k]
        tape[pos] = w
        pos += mv
        state = nst

    return None
