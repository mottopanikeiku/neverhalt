import sys

try:
    from neverhalt.tm import parse, run
    from neverhalt.kernel import Reject
except Exception:
    parse = None
    run = None
    Reject = Exception


def _get(table, q, s):
    try:
        return table[(q, s)]
    except KeyError:
        return None


def _left_closure(table, nq, nstates, lr, rr, start_ctx, lr_states, rr_states):
    # context = (l, q, s, r)
    seen = {start_ctx: True}
    work = [start_ctx]
    while work:
        l, q, s, r = work.pop()
        tr = _get(table, q, s)
        if tr is None:
            return None
        w, move, q2 = tr
        if move == +1:
            l2 = lr[l][w]
            if l2 is None:
                return None
            # pop from right: need r2 such that rr[r2][s2] == r for every s2
            for r2 in range(len(rr)):
                row = rr[r2]
                for s2 in (0, 1):
                    if row[s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen[c] = True
                            work.append(c)
        else:
            r2 = rr[r][w]
            if r2 is None:
                return None
            for l2 in range(len(lr)):
                row = lr[l2]
                for s2 in (0, 1):
                    if row[s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen[c] = True
                            work.append(c)
    return seen


def _emit(tm):
    table, nq, ns = parse(tm)
    # half-tape automaton: state 0 loops on 0; enumerate transition tables
    # for sizes 1..3 states, then 4..6 roughly limited by time budget.
    import itertools
    cands = []
    for n in (1, 2, 3, 4):
        # each non-zero state has 4 possible rows over symbols 0/1
        rows = []
        for st in range(1, n):
            for a in range(n):
                for b in range(n):
                    rows.append((a, b))
        # generate all assignments of rows to non-zero states
        # too many for n=4; restrict for n>=3 by using a canonical BFS order later
        if n <= 2:
            cnt = 0
            for combo in itertools.product(rows, repeat=n - 1):
                lr = [[0, 0]]
                ok = True
                for st, (a, b) in enumerate(combo, start=1):
                    lr.append([a, b])
                # check reachability from 0 only includes state 0 for symbol 0
                # (state 0 must loop on 0: lr[0][0] == 0 by construction)
                cands.append(lr)
                cnt += 1
                if cnt > 200:
                    break
            continue
        else:
            # small random-ish enumeration via BFS canonical form is expensive;
            # just try the n-gram style automaton: state i remembers last i bits
            lr = [[0, 0]]
            for i in range(1, n):
                lr.append([(i - 1) % n, i % n])
            cands.append(lr)
    # also try the "all states loop except symbol-1 chain" patterns
    for n in (1, 2, 3):
        lr = [[0, 0]]
        for i in range(1, n):
            lr.append([(i - 1) % n, i % n])
        cands.append(lr)

    for lr in cands:
        # build rr with same shape (mirror)
        # prune: state 0 must loop on 0
        if lr[0][0] != 0:
            continue
        # try rr = lr, and rr derived by mirroring
        for rr in (lr, [[0, 0]] + [[(i - 1) % len(lr), (i + 1) % len(lr)] for i in range(1, len(lr))]):
            if rr[0][0] != 0:
                continue
            # check every state has valid entries
            for a in (lr, rr):
                for st in range(len(a)):
                    for s in (0, 1):
                        if not (0 <= a[st][s] < len(a)):
                            break
            # start context (0,0,0,0)
            ctxs = _left_closure(table, nq, ns, lr, rr, (0, 0, 0, 0), len(lr), len(rr))
            if ctxs is None:
                continue
            if len(ctxs) > 200000:
                continue
            # emit
            left = [[a, b] for a, b in lr]
            right = [[a, b] for a, b in rr]
            contexts = [[l, q, s, r] for (l, q, s, r) in ctxs]
            # sanity: kernel check
            cert = {
                "kind": "cps",
                "left": left,
                "right": right,
                "contexts": contexts,
            }
            try:
                from neverhalt.kernel import check
                check(tm, cert)
                return cert
            except Reject:
                continue
            except Exception:
                continue
    return None


def decide(tm):
    try:
        return _emit(tm)
    except Exception:
        return None
