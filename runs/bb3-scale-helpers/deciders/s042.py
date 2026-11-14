from neverhalt.helpers import closure
from neverhalt.tm import parse

def decide(tm):
    try:
        table, n_states, _ = parse(tm)
    except Exception:
        return None
    max_q = n_states
    pairs = []
    for ns in (1, 2, 3):
        for n in range(ns):
            pass
        for n in range(ns):
            pass
        for n in range(ns):
            pass
    # enumerate automata with ns states: state 0 loops on 0
    for ns in (1, 2, 3):
        for nt in range(ns):
            for bits in range(1 << (ns * 2)):
                def mk(bits, ns, nt):
                    left = [[None, None] for _ in range(ns)]
                    right = [[None, None] for _ in range(ns)]
                    ok = True
                    for i in range(ns):
                        for x in (0, 1):
                            idx = (i * 2 + x) * 2 * nt + nt
                            if idx >= (1 << (ns * 2)):
                                ok = False
                                break
                            left[i][x] = (bits >> (i * 2 + x)) & 1
                            right[i][x] = (bits >> (i * 2 + x + ns * 2)) & 1
                    return left, right
                left, right = mk(bits, ns, nt)
                # state 0 must loop on 0; blank states
                if left[0][0] != 0 or right[0][0] != 0:
                    continue
                try:
                    cert = closure(
                        tm,
                        lambda s, x: left[s][x] if left[s][x] is not None else None,
                        lambda s, x: right[s][x] if right[s][x] is not None else None,
                        0, 0, cap=200000,
                    )
                except Exception:
                    continue
                if cert is not None:
                    return cert
    return None