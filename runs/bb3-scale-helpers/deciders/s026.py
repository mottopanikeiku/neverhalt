import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure


def _enumerate_tables(n, cap):
    # tables: list of list of (next_state or None) for states 0..n-1, symbols 0,1
    # state 0 loops on symbol 0 (blank_left requirement push(blank,0)==blank)
    # we enumerate all next states in 0..n-1 (None is not needed for push functions?)
    # Actually push functions should return states; None means "never happens" for
    # transitions not in the table. We'll allow any state in range(n) as next.
    results = []
    total = n * n
    for code in range(total ** n):
        tbl = []
        x = code
        for _ in range(n):
            row = []
            for _ in range(2):
                row.append(x % n)
                x //= n
            tbl.append(row)
        # enforce state 0 loops on symbol 0
        tbl[0][0] = 0
        results.append(tbl)
    return results


def _push_from_table(tbl):
    n = len(tbl)

    def push(state, symbol):
        if symbol not in (0, 1):
            return state
        return tbl[state][symbol]

    return push, 0


def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None

    # Try n-gram style automata first? We don't know the machine's states.
    # Instead, enumerate small automata pairs and use closure.
    for nside in (1, 2, 3):
        tables = _enumerate_tables(nside, 200000)
        for lt in tables:
            lpush, lblank = _push_from_table(lt)
            for rt in tables:
                rpush, rblank = _push_from_table(rt)
                try:
                    cert = closure(lpush, rpush, lblank, rblank, cap=200000)
                except Exception:
                    cert = None
                if cert is None:
                    continue
                try:
                    check(tm, cert)
                except Reject:
                    continue
                except Exception:
                    return None
                return cert
    return None
