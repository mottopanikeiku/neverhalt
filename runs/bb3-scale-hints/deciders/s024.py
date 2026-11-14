import sys
from itertools import product
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---- helpers ---------------------------------------------------------------
def table(tm):
    t, ns, nc = parse(tm)
    return t, ns, nc

def auto_loop_on_blank(ns):
    # transitions for symbols 0/1; state 0 loops on 0 by convention
    pass

# The certificate we emit is a cps certificate: two DFAs (left/right) over
# the half-tapes and a closed set of contexts.  We search for small DFAs
# whose closed context set contains no halting context.

def build_closure(left, right, nq, ntrans, max_ctx=200000):
    # left[r][x], right[r][x] in {0..n-1} or None
    # find smallest closed set of contexts [l,q,s,r]
    ctx = set()
    work = []
    if (0,0,0,0) not in ctx:
        ctx.add((0,0,0,0)); work.append((0,0,0,0))
    while work:
        l,q,s,r = work.pop()
        if (l,q,s,r) in ctx:
            continue
        ctx.add((l,q,s,r))
        if len(ctx) > max_ctx:
            return None
        w, mv, q2 = ntrans[q][s]
        if mv == 1:
            l2 = left[l][w]
            if l2 is None:
                return None
            for (r2, s2) in pairs_right(right, r):
                add = (l2, q2, s2, r2)
                if add not in ctx:
                    work.append(add)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for (l2, s2) in pairs_left(left, l):
                add = (l2, q2, s2, r2)
                if add not in ctx:
                    work.append(add)
    return ctx

def pairs_right(right, r):
    # all (r2, s2) with right[r2][s2] == r
    out = []
    for r2 in range(len(right)):
        for s2 in (0,1):
            if right[r2][s2] == r:
                out.append((r2, s2))
    return out

def pairs_left(left, l):
    out = []
    for l2 in range(len(left)):
        for s2 in (0,1):
            if left[l2][s2] == l:
                out.append((l2, s2))
    return out

# enumerate automata: list of transitions per state, each is (a,b) for 0/1
# DFA over {0,1} with n states, state 0 loops on 0 (blank tape).
def enumerate_autos(n, max_tables=40000):
    res = []
    for tbl in product(range(n), repeat=2*n):
        if tbl[0] != 0:  # state 0 on symbol 0 must go to 0
            continue
        auto = [[tbl[2*i], tbl[2*i+1]] for i in range(n)]
        res.append(auto)
        if len(res) >= max_tables:
            break
    return res

def decider_search(tm):
    t, ns, nc = parse(tm)
    # try n-gram style automata first (fast), then search
    sizes = [1,2,3,4]
    autos = {}
    for n in sizes:
        autos[n] = enumerate_autos(n, 20000)
    for n1 in sizes:
        for n2 in sizes:
            if n1*n2 > 16:
                continue
            for L in autos[n1]:
                if L[0][0] != 0:
                    continue
                for R in autos[n2]:
                    if R[0][0] != 0:
                        continue
                    ctx = build_closure(L, R, ns, t)
                    if ctx is None:
                        continue
                    if any(q == None for (l,q,s,r) in ctx):
                        # halting transition inside closure -> reject
                        continue
                    halted = False
                    for (l,q,s,r) in ctx:
                        if q >= ns:
                            halted = True
                            break
                        if (q,s) not in t:
                            halted = True
                            break
                    if halted:
                        continue
                    # emit certificate
                    cert = {
                        "kind": "cps",
                        "left": [[a,b] for a,b in L],
                        "right": [[a,b] for a,b in R],
                        "contexts": [[l,q,s,r] for (l,q,s,r) in ctx],
                    }
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        continue
    return None

def decide(tm):
    try:
        return decider_search(tm)
    except Exception:
        return None

NAME = "cps_search_small"

if __name__ == "__main__":
    tm = sys.argv[1] if len(sys.argv) > 1 else "1RB0LC_0LC1RA_---1LA"
    c = decide(tm)
    print("certificate" if c else "none")
