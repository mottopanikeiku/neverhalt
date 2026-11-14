import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _transitions(tm):
    table, n_states, n_symbols = parse(tm)
    tr = {}
    for st in range(n_states):
        for sy in range(n_symbols):
            if (st, sy) in table:
                tr[(st, sy)] = table[(st, sy)]
    return table, n_states, n_symbols, tr


def _blank_state_state(tm):
    table, n_states, n_symbols, tr = _transitions(tm)
    return table, n_states, n_symbols, tr


def _closure(tm, left, right):
    table, n_states, n_symbols, tr = _transitions(tm)
    contexts = set()
    ctxs = {}
    for l in range(len(left)):
        if left[l][0] is None:
            continue
        for r in range(len(right)):
            if right[r][0] is None:
                continue
            for q in range(n_states):
                for s in range(n_symbols):
                    if (q, s) not in tr:
                        continue
                    w, move, q2 = tr[(q, s)]
                    if move == +1:
                        l2 = left[l][w]
                        if l2 is None:
                            continue
                        for r2 in range(len(right)):
                            for s2 in range(n_symbols):
                                if right[r2][s2] != r:
                                    continue
                                contexts.add((l2, q2, s2, r2))
                    else:
                        r2 = right[r][w]
                        if r2 is None:
                            continue
                        for l2 in range(len(left)):
                            for s2 in range(n_symbols):
                                if left[l2][s2] != l:
                                    continue
                                contexts.add((l2, q2, s2, r2))
    return contexts


def _build_cps(tm):
    table, n_states, n_symbols, tr = _transitions(tm)
    syms = [0, 1]
    n = max(1, min(n_states, 4))
    for size in range(1, n + 1):
        for mask in range(1 << (size * 2)):
            left = [[None, None] for _ in range(size)]
            right = [[None, None] for _ in range(size)]
            ok = True
            for i in range(size):
                for x in range(2):
                    b = mask >> (i * 2 + x) & 1
                    v = b if b else None
                    left[i][x] = v
                    right[i][x] = v
            if left[0][0] != 0 or right[0][0] != 0:
                continue
            ctxs = _closure(tm, left, right)
            if not ctxs:
                continue
            if any((l, q, s, r) in ctxs for l in range(size) for q in range(n_states) for s in range(n_symbols) for r in range(size) if (q, s) not in tr):
                continue
            cert = {"kind": "cps", "left": left, "right": right,
                    "contexts": [[l, q, s, r] for (l, q, s, r) in sorted(ctxs)]}
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    return None


def decide(tm: str):
    cert = _build_cps(tm)
    if cert is not None:
        return cert
    return None
