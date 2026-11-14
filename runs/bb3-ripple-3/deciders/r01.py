from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


def decide(tm):
    try:
        table, ns, nsy = parse(tm)
    except Exception:
        return None

    W = 5                       # window radius around the head
    ks = list(range(-W, W + 1))
    tape = {}
    pos = 0
    state = 0
    occ = {}                    # signature -> list of (time, head position)
    Tmax = 9000

    for t in range(Tmax):
        # local signature: state plus the cells just around the head
        vals = [tape.get(pos + k, 0) for k in ks]
        sig = (state,) + tuple(vals)

        lst = occ.get(sig)
        if lst is not None:
            # same local configuration seen before: try a cycle (or
            # translated cycle) certificate for the lap in between
            for (t0, p0) in lst:
                P = t - t0
                if P <= 0 or t0 + P > 100000:
                    continue
                cert = {"kind": "cycle", "t": t0, "p": P}
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
                except Exception:
                    pass
            if len(lst) < 3 and (t, pos) != lst[-1]:
                lst.append((t, pos))
        else:
            occ[sig] = [(t, pos)]

        # advance one step; a missing transition means halting, not our business
        key = (state, tape.get(pos, 0))
        if key not in table:
            return None
        tr = table[key]
        tape[pos] = tr[0]
        pos += tr[1]
        state = tr[2]

    return None
