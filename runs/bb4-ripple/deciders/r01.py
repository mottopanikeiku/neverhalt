from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

NAME = "window-repeat cycles"


def decide(tm):
    table, n_states, n_symbols = parse(tm)

    for W, LIMIT in ((30, 3500), (60, 2200), (95, 1300)):
        win_len = 2 * W
        window = [0] * win_len
        tape = {}
        state = 0
        pos = 0
        seen = {}
        cands = []
        t = 0
        while t < LIMIT:
            key = (state, bytes(window))
            prev = seen.get(key)
            if prev is None:
                seen[key] = t
            else:
                cands.append((prev, t - prev))
                if len(cands) >= 14:
                    break
            sym = tape.get(pos, 0)
            tr = table.get((state, sym))
            if tr is None:
                break
            w, mv, ns = tr
            if ns is None:
                break
            tape[pos] = w
            window[W] = w
            if mv == 1 or mv == 'R':
                nc = tape.get(pos + W, 0)
                pos += 1
                window = window[1:]
                window.append(nc)
            else:
                nc = tape.get(pos - W - 1, 0)
                pos -= 1
                window = [nc] + window[:win_len - 1]
            state = ns
            t += 1

        for t0, p in cands[:8]:
            if p <= 0:
                continue
            cert = {"kind": "cycle", "t": t0, "p": p}
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
            except Exception:
                continue
    return None
