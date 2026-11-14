import itertools
from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


def _symbols():
    return [0, 1]


def _build_left(n):
    # transitions[i][x] = j or None, state 0 loops on 0
    return [[None, None] for _ in range(n)]


def _closure(tm, table, n_states, n_symbols, left, right):
    # context: (l, q, s, r) with q state index, s symbol
    start = (0, 0, 0, 0)
    seen = set([start])
    stack = [start]
    while stack:
        l, q, s, r = stack.pop()
        if not (0 <= l < n_states and 0 <= q < 4 and 0 <= s < 2 and 0 <= r < n_states):
            return None
        tr = table[(q, s)]
        if tr is None:
            return None
        w, move, q2 = tr
        if move == 1:
            l2 = left[l][w]
            if l2 is None:
                return None
            for r2 in range(n_states):
                if right[r2][s] is None:
                    continue
                # right[r2][s] == r means reading s from state r2 lands in r
                # (mirror check: for a right move, the popped symbol s2 satisfies
                #  right[r][s2] == r2; equivalently r2 with right[r2][s2] == r)
                # We need: for every pair (r2, s2) with right[r2][s2] == r,
                # context [l2, q2, s2, r2] must be present.
            # find all (r2, s2) with right[r2][s2] == r
            for r2 in range(n_states):
                for s2 in range(2):
                    if right[r2][s2] == r:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(n_states):
                for s2 in range(2):
                    if left[l2][s2] == l:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
    return seen


def _make_automata(n):
    # enumerate deterministic transition tables with n states, state 0 loops on 0
    # each state has 2 entries, each entry None or 0..n-1, but 0->0 on symbol 0 fixed
    results = []
    # state 0: [0, x0]; other states arbitrary
    def rec(state, acc):
        if state == n:
            results.append([row[:] for row in acc])
            return
        if state == 0:
            acc.append([0, None])
            rec(state + 1, acc)
            acc.pop()
            return
        for a in [None] + list(range(n)):
            for b in [None] + list(range(n)):
                acc.append([a, b])
                rec(state + 1, acc)
                acc.pop()
    rec(0, [])
    return results


def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    if n_symbols != 2:
        return None
    if n_states > 5:
        return None
    maxn = 2
    for n in range(2, maxn + 1):
        lefts = _make_automata(n)
        rights = lefts
        for left in lefts:
            for right in rights:
                ctx = _closure(tm, table, n_states, n_symbols, left, right)
                if ctx is None:
                    continue
                # reject if any context halts
                ok = True
                for (l, q, s, r) in ctx:
                    if table.get((q, s)) is None:
                        ok = False
                        break
                if not ok:
                    continue
                # build certificate
                contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
                cert = {
                    "kind": "cps",
                    "left": left,
                    "right": right,
                    "contexts": contexts,
                }
                try:
                    check(tm, cert)
                except Reject:
                    continue
                except Exception:
                    continue
                return cert
    return None


if __name__ == "__main__":
    import sys
    from neverhalt.kernel import check
    for tm in sys.argv[1:]:
        c = decide(tm)
        if c is None:
            print(tm, "none")
        else:
            try:
                print(tm, "ok", check(tm, c))
            except Exception as e:
                print(tm, "REJECT", e)
