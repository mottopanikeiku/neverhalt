import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: "farwall-reflect"
# Strategy: run the machine for a bounded horizon, then look for machines whose
# head is bouncing between two fixed walls: the tape outside a moving window is
# permanently blank. If we can find two times T < T+P such that the whole
# visible tape is blank outside the visited window, the state sequence repeats,
# and the window contents repeat (possibly translated), then the cycle
# certificate applies. We try many (T, P) pairs, preferring small P, and return
# the first certificate the kernel accepts.

MAX_STEPS = 200000

def _try_cycle(tm, T, P):
    # Simulate T+P steps from scratch (we do not trust cached state).
    # We need tape at T and at T+P, plus the head positions seen in (T, T+P].
    table, ns, nsym = parse(tm)
    n = T + P
    if n > MAX_STEPS:
        return None
    # tape[i][j] is a list of (write, move, next) for cell j; we store the tape
    # as a dict position -> symbol at each time we need it. To save memory we
    # only keep snapshots at T and T+P.
    from collections import defaultdict
    tape = defaultdict(int)
    q = 0
    pos = 0
    snapT = None
    lo = hi = None
    for step in range(n + 1):
        if step == T:
            snapT = dict(tape)
        if step == T + P:
            snapEnd = dict(tape)
            break
        if step < T:
            # fast forward: just step
            pass
        if step >= T:
            if lo is None:
                lo = hi = pos
            else:
                if pos < lo: lo = pos
                if pos > hi: hi = pos
        tr = table.get((q, tape[pos]))
        if tr is None:
            return None
        w, mv, q2 = tr
        tape[pos] = w
        pos += mv
        q = q2
    else:
        return None
    # q is state at step T+P (we stepped n times total)
    # We need state at T and T+P: recompute cheaply by rerunning to T.
    # (The loop above already stepped; to get state at T we rerun.)
    return None

# The above is too clumsy; use neverhalt.run to get states/tape at a time.
def _snapshot(tm, T):
    table, ns, nsym = parse(tm)
    # run gives state,pos,tape at max_steps; use it directly.
    halted, steps, state, pos, tape = run(tm, T)
    return state, pos, tape

def decide(tm):
    # Try to find a cycle certificate by brute force over a window.
    for T in range(0, 4000, 1):
        st, pos, tape = _snapshot(tm, T)
        for P in range(1, 3000, 1):
            if T + P > 20000:
                break
            st2, pos2, tape2 = _snapshot(tm, T + P)
            # check no halt: run returns halted flag
            h1, _, st1, p1, t1 = run(tm, T)
            if h1:
                T += 1
                break
            h2, _, st2b, p2b, t2b = run(tm, T + P)
            if h2:
                break
            if st1 != st2b:
                continue
            # translate d = p2b - p1
            d = p2b - p1
            # We need head positions seen during the lap and matching tape.
            # Re-simulate the lap to collect positions and compare.
            table, ns, nsym = parse(tm)
            from collections import defaultdict
            tape = defaultdict(int)
            q = st1
            p = p1
            lo = hi = p
            ok = True
            for _ in range(P):
                tr = table.get((q, tape[p]))
                if tr is None:
                    ok = False
                    break
                w, mv, q2 = tr
                tape[p] = w
                p += mv
                q = q2
                if p < lo: lo = p
                if p > hi: hi = p
            if not ok:
                continue
            if q != st2b:
                continue
            # match tape window with translation d
            for y in range(lo, hi + 1):
                a = tape[y]
                b = t2b.get(y + d, 0)
                if a != b:
                    ok = False
                    break
            if not ok:
                continue
            if d > 0:
                # every cell right of hi must be blank at T+P
                for y in range(hi + 1, hi + 1 + abs(d) + 50):
                    if t2b.get(y, 0) != 0:
                        ok = False
                        break
            elif d < 0:
                for y in range(lo - 1 - abs(d) - 50, lo):
                    if t2b.get(y, 0) != 0:
                        ok = False
                        break
            if not ok:
                continue
            cert = {"kind": "cycle", "t": T, "p": P}
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    return None