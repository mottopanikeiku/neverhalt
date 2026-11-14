import sys
from collections import defaultdict
from neverhalt.tm import parse, run

# Decider: hunt for translated cycles (tcycle) and plain cycles (cycle) with
# moderate periods, plus a bounded-window induction (n-gram CPS) restricted to
# the machines that survive.  The expensive part is the cycle search, so we
# first look for small-period translated cycles in a window that grows with
# the machine's observed head span, then fall back to a bounded n-gram CPS.

MAX_T = 20000
MAX_P = 4000
MAX_NGRAM = 6


def _blank_match(tape, y, lo, hi, d, T, P, steps):
    # compare tape at time T and T+P over the window shifted by d
    for y in range(lo, hi + 1):
        a = tape.get(y, 0)
        b = tape.get(y + d, 0)
        if a != b:
            return False
    # cells entering from the far side must be blank at T+P
    if d > 0:
        for y in range(hi + 1, hi + d + 1):
            if tape.get(y, 0) != 0:
                return False
    elif d < 0:
        for y in range(lo + d, lo):
            if tape.get(y, 0) != 0:
                return False
    return True


def cycle_probe(tm):
    table, ns, syms = parse(tm)
    halted, steps, state, pos, tape = run(tm, 60000)
    if halted:
        return None
    # head displacement between two visits to the same state at the same
    # symbol, sampled over a reasonably long run
    states = {}
    for t in range(steps):
        pass
    # We cannot see intermediate states from run(); re-run ourselves.
    from neverhalt.tm import parse as _p
    # manual simulation
    tbl, ns, syms = parse(tm)
    tape = defaultdict(int)
    p = 0
    q = 0
    seen = []
    for step in range(60000):
        if (q, tape[p]) not in tbl:
            return None
        w, mv, q2 = tbl[(q, tape[p])]
        tape[p] = w
        p += mv
        q = q2
        seen.append((q, p, dict(tape)))
        if step > 60000:
            break
    # look for repeated (state, pos) pairs: plain cycle
    idx = {}
    for i, (q, p, _) in enumerate(seen):
        key = (q, p)
        if key in idx:
            T = idx[key]
            P = i - T
            if T + P <= 100000:
                # gather window positions
                lo = min(x[1] for x in seen[T: i + 1])
                hi = max(x[1] for x in seen[T: i + 1])
                d = 0
                # verify tape equality at T and T+P
                ok = True
                for y in range(lo, hi + 1):
                    if seen[T][2].get(y, 0) != seen[i][2].get(y, 0):
                        ok = False
                        break
                if ok:
                    return {"kind": "cycle", "t": T, "p": P}
        else:
            idx[key] = i
    # translated cycle: repeated state, displacement nonzero, tape shift matches
    first = {}
    for i, (q, p, _) in enumerate(seen):
        if q in first:
            j = first[q]
            P = i - j
            if 1 <= P <= MAX_P and j + P <= 100000:
                d = p - seen[j][1]
                if d != 0:
                    lo = min(x[1] for x in seen[j: i + 1])
                    hi = max(x[1] for x in seen[j: i + 1])
                    # window over the lap
                    ok = True
                    for y in range(lo, hi + 1):
                        if seen[j][2].get(y, 0) != seen[i][2].get(y + d, 0):
                            ok = False
                            break
                    if ok:
                        # far-side blank check
                        good = True
                        if d > 0:
                            for y in range(hi + 1, hi + d + 1):
                                if seen[i][2].get(y, 0) != 0:
                                    good = False
                                    break
                        else:
                            for y in range(lo + d, lo):
                                if seen[i][2].get(y, 0) != 0:
                                    good = False
                                    break
                        if good:
                            return {"kind": "cycle", "t": j, "p": P}
        else:
            first[q] = i
    return None


def ngram_cps(tm, n):
    tbl, ns, syms = parse(tm)
    # build automaton for last-n cells of a half tape
    states = [tuple([0] * n)]
    index = {states[0]: 0}
    trans = [[None, None] for _ in range(len(states))]
    for x in (0, 1):
        trans[0][x] = 0
    # state 0 is all blank
    i = 1
    while i < len(states):
        s = states[i]
        for x in (0, 1):
            ns_ = (x,) + s[:-1]
            if ns_ not in index:
                index[ns_] = len(states)
                states.append(ns_)
                trans.append([None, None])
            trans[i][x] = index[ns_]
        i += 1
    contexts = set()
    contexts.add((0, 0, 0, 0))
    changed = True
    while changed and len(contexts) <= 200000:
        changed = False
        cur = list(contexts)
        for (l, q, s, r) in cur:
            if s not in (0, 1):
                continue
            if (q, s) not in tbl:
                return None
            w, mv, q2 = tbl[(q, s)]
            if mv == 1:
                l2 = trans[l][w]
                if l2 is None:
                    return None
                for r2 in range(len(states)):
                    for s2 in (0, 1):
                        if trans[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in contexts:
                                contexts.add(c)
                                changed = True
            else:
                r2 = trans[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(states)):
                    for s2 in (0, 1):
                        if trans[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in contexts:
                                contexts.add(c)
                                changed = True
    if len(contexts) > 200000:
        return None
    left = [[trans[i][0], trans[i][1]] for i in range(len(states))]
    right = [row[:] for row in left]
    ctx = [[list(c) for c in contexts]]
    return {"kind": "cps", "left": left, "right": right, "contexts": ctx[0]}


def decide(tm):
    # try plain/translated cycle first: cheap and often decisive
    c = cycle_probe(tm)
    if c is not None:
        try:
            from neverhalt.kernel import check, Reject
            check(tm, c)
            return c
        except Exception:
            pass
    # bounded n-gram CPS
    for n in range(2, MAX_NGRAM + 1):
        cert = ngram_cps(tm, n)
        if cert is not None:
            try:
                from neverhalt.kernel import check, Reject
                check(tm, cert)
                return cert
            except Exception:
                continue
    return None