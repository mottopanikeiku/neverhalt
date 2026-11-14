import sys
sys.setrecursionlimit(1000000)
from neverhalt.tm import parse, run

# Try to find a cycle certificate (plain or translated) with a wider search
# than the earlier deciders.  We look for repeated (state, position) pairs
# with repeated window content, and for translated cycles by checking
# whether a later configuration is a shifted copy of an earlier one.

def find_cycle(tm, max_steps=20000):
    halted, steps, state, pos, tape = run(tm, max_steps)
    if halted:
        return None
    table, n_states, n_symbols = parse(tm)
    # collect configuration history (state, pos)
    seen = {}
    # We re-simulate step by step to record tape snapshots every K steps
    # for window comparison.
    K = 200
    confs = []
    snapshots = []
    try:
        h, st, s, p, t = run(tm, max_steps)
        # Re-run manually to capture history
        table, ns, nsym = parse(tm)
        tape = {}
        state = 0
        pos = 0
        step = 0
        history = []
        snap = []
        while step < max_steps:
            history.append((state, pos, step))
            if step % K == 0:
                snap.append(dict(tape))
            key = (state, pos)
            if key in seen:
                pass
            seen[key] = step
            # step
            if (state, tape.get(pos, 0)) not in table:
                return None
            w, mv, q2 = table[(state, tape.get(pos, 0))]
            old = tape.get(pos, 0)
            tape[pos] = w
            pos += mv
            state = q2
            step += 1
        # try plain cycles: find i<j with same (state,pos) and same window
        for i in range(len(history)):
            for j in range(i+1, len(history)):
                if history[i][0] == history[j][0] and history[i][1] == history[j][1]:
                    # window is all cells touched between i and j
                    lo = min(history[k][1] for k in range(i, j+1))
                    hi = max(history[k][1] for k in range(i, j+1))
                    ok = True
                    for y in range(lo, hi+1):
                        if tape.get(y,0) != tape.get(y,0):
                            pass
                    # need snapshot comparison across the lap
                    # approximate: assume plain cycle if same state/pos and window blank outside
                    # We'll return a certificate only if we can verify via kernel.
                    cert = {"kind":"cycle","t":history[i][2],"p":history[j][2]-history[i][2]}
                    from neverhalt.kernel import check, Reject
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
    except Exception:
        return None
    return None

def decide(tm):
    try:
        return find_cycle(tm)
    except Exception:
        return None
