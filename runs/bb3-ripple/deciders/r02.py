from neverhalt.tm import parse, run
from neverhalt.kernel import check


def decide(tm):
    try:
        table, ns, nsy = parse(tm)
    except Exception:
        return None

    tape = {}
    pos = 0
    state = 0
    low, high = 0, 0

    # first pass: gather a reasonably long simulation, tracking only
    # configurations in a compact window around the head
    W = 3
    off = list(range(-W, W + 1))
    occ = {}
    Tmax = 20000

    for t in range(Tmax):
        cells = tuple(tape.get(pos + k, 0) for k in off)
        sig = (state,) + cells
        lst = occ.get(sig)
        if lst is not None:
            # repeated local window: try cycle from each earlier occurrence
            for (t0, p0) in lst:
                P = t - t0
                if P <= 0 or t0 + P > 50000:
                    continue
                cert = {"kind": "cycle", "t": t0, "p": P}
                try:
                    check(tm, cert)
                    return cert
                except Exception:
                    pass
        else:
            occ[sig] = [(t, pos)]
            if len(occ) > 300000:
                return None

        key = (state, tape.get(pos, 0))
        if key not in table:
            return None
        w, mv, nst = table[key]
        tape[pos] = w
        pos += mv
        state = nst
        if pos < low:
            low = pos
        if pos > high:
            high = pos

    return None
