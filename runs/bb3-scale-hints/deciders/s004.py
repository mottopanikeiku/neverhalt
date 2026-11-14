import sys
sys.setrecursionlimit(1000000)

# ============================================================
# shared helpers
# ============================================================
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def analyze(tm):
    """Return (halted, steps, state, pos, tape) from a long simulation."""
    halted, steps, state, pos, tape = run(tm, 100000)
    return halted, steps, state, pos, tape

# ============================================================
# 1) translated cycle search
# ============================================================
def find_tcycle(tm, max_steps=6000):
    halted, steps, state, pos, tape = run(tm, max_steps + 120)
    if halted:
        return None
    # sample states at several times, look for a lap
    T = 1500
    for P in range(20, 1200, 1):
        if T + P > steps:
            break
        try:
            # capture snapshots
            h, s2, st2, po2, tape2 = run(tm, T + P)
            h0, s1, st1, po1, tape1 = run(tm, T)
            if h or h0:
                continue
            if st1 != st2 or po1 != po2:
                continue
            d = po2 - po1
            # window positions seen between T and T+P
            # we can approximate by the tape span at T+P
            lo = min(tape2.keys()) if tape2 else 0
            hi = max(tape2.keys()) if tape2 else 0
            if lo < -30:
                lo = -30
            if hi > 30:
                hi = 30
            ok = True
            for y in range(lo, hi + 1):
                v1 = tape1.get(y, 0)
                v2 = tape2.get(y + d, 0)
                if v1 != v2:
                    ok = False
                    break
            if ok:
                cert = {"kind": "cycle", "t": T, "p": P}
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
        except Exception:
            pass
    return None

# ============================================================
# 2) CPS with search over small DFAs
# ============================================================
def build_cps(tm, max_states=4):
    """Search over pairs of DFAs (left, right) of up to max_states states.
    State 0 loops on 0; transitions on 1 are chosen freely.
    For each pair compute the smallest closed context set and check for
    halting contexts. Return a certificate or None.
    """
    table, n_states, n_syms = parse(tm)

    # enumerate all DFAs of size k: transition table per state on symbol 0,1
    # state 0 must loop on 0 -> left[0][0] = right[0][0] = 0
    # For simplicity: enumerate all mappings for states 1..k-1 on symbol 1
    # onto {0..k-1}; symbol 0 maps deterministically: for state i>=1
    # we choose from {0..k-1} too, but state 0 maps 0->0.
    # To keep the search small, restrict: state i on symbol 0 maps to 0 or stays.
    import itertools

    def enumerate_dfas(k):
        # state 0: [0, a] where a in 0..k-1 (a = transition on 1)
        # states 1..k-1: (z, o) each in 0..k-1
        choices0 = list(range(k))
        per = list(itertools.product(range(k), repeat=2))
        for a0 in choices0:
            for rest in itertools.product(per, repeat=max(0, k - 1)):
                trans = [[0, a0]]
                for z, o in rest:
                    trans.append([z, o])
                yield trans

    # Precompute halting detection: a context is halting if (q, s) undefined.
    def is_halting_context(l, q, s, r):
        if q < n_states and s < n_syms:
            if (q, s) not in table:
                return True
        else:
            return True
        return False

    def closure(left, right, start=(0, 0, 0, 0)):
        """Compute smallest closed context set containing start."""
        # context = (l, q, s, r)
        seen = set()
        stack = [start]
        while stack:
            ctx = stack.pop()
            if ctx in seen:
                continue
            seen.add(ctx)
            l, q, s, r = ctx
            # must have a transition
            if (q, s) not in table:
                return seen, True  # halting context found
            w, move, q2 = table[(q, s)]
            if move == 1:
                # right move: l2 = left[l][w] must exist
                if w >= 2:
                    return seen, True
                l2 = left[l][w]
                if l2 is None:
                    return seen, True
                # for every pair (r2, s2) with right[r2][s2] == r
                for r2 in range(len(right)):
                    for s2 in range(2):
                        if right[r2][s2] == r:
                            nxt = (l2, q2, s2, r2)
                            if nxt not in seen:
                                stack.append(nxt)
            else:
                # left move: r2 = right[r][w] must exist
                if w >= 2:
                    return seen, True
                r2 = right[r][w]
                if r2 is None:
                    return seen, True
                for l2 in range(len(left)):
                    for s2 in range(2):
                        if left[l2][s2] == l:
                            nxt = (l2, q2, s2, r2)
                            if nxt not in seen:
                                stack.append(nxt)
        return seen, False

    for k in range(1, max_states + 1):
        dfas = list(enumerate_dfas(k))
        for left in dfas:
            for right in dfas:
                # quick check: start context not halting
                if is_halting_context(0, 0, 0, 0):
                    continue
                ctxs, halting = closure(left, right)
                if halting:
                    continue
                # build certificate
                left_tbl = []
                for row in left:
                    left_tbl.append([row[0] if row[0] < len(left) else None,
                                     row[1] if row[1] < len(left) else None])
                right_tbl = []
                for row in right:
                    right_tbl.append([row[0] if row[0] < len(right) else None,
                                      row[1] if row[1] < len(right) else None])
                contexts = []
                for (l, q, s, r) in ctxs:
                    contexts.append([l, q, s, r])
                cert = {
                    "kind": "cps",
                    "left": left_tbl,
                    "right": right_tbl,
                    "contexts": contexts,
                }
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
    return None

# ============================================================
# decider
# ============================================================
NAME = "cps_search"

def decide(tm: str):
    # quick translated cycle attempt
    c = find_tcycle(tm, 4000)
    if c:
        return c
    # CPS with searched DFAs
    c = build_cps(tm, max_states=4)
    if c:
        return c
    return None