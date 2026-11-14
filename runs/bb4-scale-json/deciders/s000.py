import sys
sys.setrecursionlimit(10000)
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: "counter-bounce CPS" -- CPS certificates whose left/right automata
# are counters (bounded or periodic) instead of n-gram windows. The remaining
# holdouts show machines that grow a 1-block and then ping-pong forever, so we
# try automata that count the number of 1s in each half-tape up to a bound,
# with a periodic wrap, plus a small n-gram fallback. We also try translated
# cycle certificates on the first 200000 steps with several lap lengths.

MAX_STEPS = 200000


def _run_steps(tm, n):
    # run up to n steps, return (halted, steps, state, pos, tape, seen)
    # use neverhalt run with max_steps=n; if not halted, state/pos/tape are at n
    return run(tm, n)


def _build_cycle_certs(tm):
    res = []
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return res
    for T in range(0, 3000):
        for P in range(1, 200):
            if T + P > MAX_STEPS:
                break
            try:
                h1, s1, st1, p1, t1 = run(tm, T)
                if h1:
                    break
                h2, s2, st2, p2, t2 = run(tm, T + P)
                if h2:
                    continue
                # state at T and T+P
                if st1 != st2:
                    continue
                # tape equality with shift d = p2-p1
                d = p2 - p1
                # gather tape union
                keys = set(t1.keys()) | set(t2.keys())
                if d > 0:
                    ok = True
                    for y in keys:
                        v1 = t1.get(y, 0)
                        v2 = t2.get(y + d, 0)
                        if v1 != v2:
                            ok = False
                            break
                    if ok:
                        # check cells right of max position in t1 are blank in t2
                        hi = max(list(t1.keys()) + [p1])
                        for y in range(hi + 1, hi + 500):
                            if t2.get(y, 0) != 0:
                                ok = False
                                break
                    if ok:
                        cert = {"kind": "cycle", "t": T, "p": P}
                        try:
                            check(tm, cert)
                            res.append(cert)
                        except Reject:
                            pass
                elif d < 0:
                    ok = True
                    for y in keys:
                        v2 = t2.get(y, 0)
                        v1 = t1.get(y + (-d), 0)
                        if v1 != v2:
                            ok = False
                            break
                    if ok:
                        lo = min(list(t1.keys()) + [p1])
                        for y in range(lo - 500, lo):
                            if t2.get(y, 0) != 0:
                                ok = False
                                break
                    if ok:
                        cert = {"kind": "cycle", "t": T, "p": P}
                        try:
                            check(tm, cert)
                            res.append(cert)
                        except Reject:
                            pass
                else:
                    # d = 0 plain cycle
                    if t1 == t2:
                        cert = {"kind": "cycle", "t": T, "p": P}
                        try:
                            check(tm, cert)
                            res.append(cert)
                        except Reject:
                            pass
            except Exception:
                continue
    return res


def _build_cps_certs(tm):
    # Try counter automata on both halves.
    # We enumerate a handful of small deterministic automata over {0,1}
    # that count up to bound B (with periodic wrap) and remember last n cells.
    res = []
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return res
    states = list(range(ns))
    # generate candidate half-tape automata
    cands = []
    # n-gram automata for n=1..6
    for n in range(1, 7):
        # states 0..2^n-1 representing last n cells read (far to near)
        # state 0 = all blank
        # transitions: reading symbol x shifts in x at the near end
        # We just build the table.
        size = 1 << n
        trans = [[None, None] for _ in range(size)]
        for st in range(size):
            # st bits: bit0 = nearest? define st = value of last n cells with bit0 = farthest
            for x in range(2):
                nst = ((st << 1) | x) & (size - 1)
                trans[st][x] = nst
        cands.append(trans)
    # counter automata: state = count of 1s seen mod B, plus blank flag
    for B in range(2, 12):
        size = B + 1
        trans = [[None, None] for _ in range(size)]
        for st in range(size):
            trans[st][0] = st
            trans[st][1] = (st + 1) % size
        cands.append(trans)
    # try all pairs (left automaton, right automaton) and BFS over contexts
    for lt in cands:
        for rt in cands:
            contexts = _bps(tm, lt, rt)
            if contexts is not None:
                cert = {"kind": "cps", "left": lt, "right": rt, "contexts": contexts}
                try:
                    check(tm, cert)
                    res.append(cert)
                except Reject:
                    pass
    return res


def _bps(tm, lt, rt):
    # BFS closure over contexts [l, q, s, r]
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    start = (0, 0, 0, 0)
    seen = set()
    stack = [start]
    seen.add(start)
    contexts = []
    while stack:
        l, q, s, r = stack.pop()
        contexts.append([l, q, s, r])
        # transition
        if q >= ns:
            return None
        key = (q, s)
        if key not in table:
            return None  # halting context
        w, move, q2 = table[key]
        if move > 0:
            # right move: push w onto left half-tape
            if w >= 2:
                return None
            l2 = lt[l][w]
            if l2 is None:
                return None
            # pop nearest cell s2 off right half-tape; all (r2, s2) with rt[r2][s2] == r
            for r2 in range(len(rt)):
                for s2 in range(2):
                    if rt[r2][s2] == r:
                        nxt = (l2, q2, s2, r2)
                        if nxt not in seen:
                            seen.add(nxt)
                            stack.append(nxt)
        else:
            # left move: mirror
            if w >= 2:
                return None
            r2 = rt[r][w]
            if r2 is None:
                return None
            for l2 in range(len(lt)):
                for s2 in range(2):
                    if lt[l2][s2] == l:
                        nxt = (l2, q2, s2, r2)
                        if nxt not in seen:
                            seen.add(nxt)
                            stack.append(nxt)
    return contexts


NAME = "counter bounce cps"


def decide(tm):
    res = _build_cycle_certs(tm)
    if res:
        return res[0]
    res = _build_cps_certs(tm)
    if res:
        return res[0]
    return None