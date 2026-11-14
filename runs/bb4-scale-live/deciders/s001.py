import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: look for translated cycles (tcycles) with larger laps, and also
# try to find a repeated (state, pos mod something, tape pattern) signature.
# We simulate up to 24000 steps and check all T in [0, n] with all P in a
# set of candidate lap lengths, using the kernel to accept.

def decide(tm):
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    try:
        halted, steps, state, pos, tape = run(tm, 0)
    except Exception:
        return None
    # simulate ourselves to get full trajectory
    import neverhalt.tm as tmmod
    try:
        # run with large max
        halted, steps, state, pos, tape = run(tm, 200000)
    except Exception:
        return None
    # We need trajectory snapshots; re-simulate manually using table.
    # table[(state, symbol)] = (write, move, next_state) or absent -> halt.
    # states are ints; symbol 0 or 1.
    def step(state, pos, tape):
        sym = tape.get(pos, 0)
        key = (state, sym)
        if key not in table:
            return None
        w, mv, nxt = table[key]
        if w != sym:
            tape[pos] = w
        # move: -1 left, +1 right? check convention
        # parse returns move as +1 or -1; assume +1 right, -1 left
        pos = pos + mv
        return nxt, pos
    # Reconstruct trajectory for up to N steps
    N = 12000
    state = 0
    pos = 0
    tape = {}
    snaps = []
    for i in range(N + 1):
        snaps.append((state, pos, dict(tape)))
        r = step(state, pos, tape)
        if r is None:
            break
        state, pos = r
    # try cycle certificates: pick T, find smallest P > 0 such that
    # state matches and tapes match after shift d.
    # We'll brute force over T and P.
    n = len(snaps) - 1
    # candidate d values: displacement over lap
    # first collect some (state, pos, tape) tuples
    # To keep time small, only consider T up to 8000 and P up to 3000.
    for T in range(0, min(n, 8000) + 1):
        st, p, tp = snaps[T]
        for P in range(1, min(3000, n - T) + 1):
            if T + P > n:
                break
            st2, p2, tp2 = snaps[T + P]
            if st2 != st:
                continue
            d = p2 - p
            # check tape match tp2[y+d] == tp[y] for y in range of tp keys
            ok = True
            for y, v in tp.items():
                if tp2.get(y + d, 0) != v:
                    ok = False
                    break
            if not ok:
                continue
            # extra condition when d>0: cells right of hi blank at T+P
            # hi = max position seen during lap; we need to compute that.
            # For simplicity, use hi = max(p, p2) and ensure all cells > hi blank at T+P.
            # Actually kernel checks; just try check().
            cert = {"kind": "cycle", "t": T, "p": P}
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    return None
