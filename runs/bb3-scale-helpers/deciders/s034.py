import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure


def _cands(n):
    # enumerate deterministic transition tables on n states with symbols 0/1
    # state 0 must loop on symbol 0 (all-blank half-tape fixed point requirement)
    # left table: left[i][x] = next state, or None
    out = []
    # we enumerate functions i in range(n), x in (0,1) -> value in range(n) or None
    # state 0: on symbol 0 -> 0
    funcs = []
    def rec(i, cur):
        if i == n:
            funcs.append(list(cur))
            return
        if i == 0:
            cur.append(0)
            rec(1, cur)
            cur.pop()
            return
        for v in range(n):
            cur.append(v)
            rec(i + 1, cur)
            cur.pop()
        cur.append(None)
        rec(i + 1, cur)
        cur.pop()
    rec(0, [])
    for f in funcs:
        out.append(f)
    return out


def _table_to_automaton(f):
    # f is list of n entries per state? Wait we built one value per state, not per symbol.
    # We need per (state, symbol). Rebuild properly.
    pass


def _generate(n):
    # produce list of tables: table[i] = [next_on_0, next_on_1]
    res = []
    def rec(i, cur):
        if i == n:
            res.append([list(x) for x in cur])
            return
        if i == 0:
            # state 0 loops on 0
            for v1 in range(n):
                cur.append((0, v1))
                rec(i + 1, cur)
                cur.pop()
            return
        for v0 in range(n):
            for v1 in range(n):
                cur.append((v0, v1))
                rec(i + 1, cur)
                cur.pop()
        cur.append((None, None))
        rec(i + 1, cur)
        cur.pop()
    rec(0, [])
    return res


def decide(tm):
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    # order by table size: small first
    for n in range(1, 4):
        for L in _generate(n):
            for R in _generate(n):
                # blank states must be fixed by symbol 0
                if L[0][0] != 0 or R[0][0] != 0:
                    continue
                try:
                    cert = closure(
                        push_left=lambda s, x: L[s][x] if L[s][x] is not None else None,
                        push_right=lambda s, x: R[s][x] if R[s][x] is not None else None,
                        blank_left=0,
                        blank_right=0,
                    )
                except Exception:
                    continue
                if cert is None:
                    continue
                try:
                    kind = check(tm, cert)
                except Reject:
                    continue
                return cert
    return None