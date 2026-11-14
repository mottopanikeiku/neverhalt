from neverhalt.tm import parse
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure


def _small_tables(n, cap=200000):
    blank = 0
    out = []
    total = (n) ** 2
    for mask in range(total):
        tbl = [[None, None] for _ in range(n)]
        tbl[blank][0] = blank
        for i in range(blank + 1, n):
            tbl[i][0] = (mask >> (2 * i)) & 3
            tbl[i][1] = (mask >> (2 * i + 1)) & 3
        out.append(tbl)
    return out


def _try_pair(tm, n, cap=200000):
    tables = _small_tables(n, cap)
    for lt in tables:
        for rt in tables:
            cert = closure(lt, rt, cap=cap)
            if cert is not None:
                try:
                    check(tm, cert)
                except Reject:
                    continue
                return cert
    return None


ATTEMPTS = 1


def decide(tm: str):
    for n in (1, 2, 3, 4, 5, 6):
        if _try_pair(tm, n, cap=200000):
            return _try_pair(tm, n, cap=200000)
    return None
