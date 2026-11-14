import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: detect translated cycles with a fast bitset-based search.
# We simulate the machine and periodically test for a translated cycle
# using the kernel's own definitions, but we do the search ourselves with
# a rolling hash of the window so we can test many candidate laps cheaply.

def _hash_window(tape, lo, hi, d, mod1, mod2):
    h1 = 0
    h2 = 0
    for y in range(lo, hi + 1):
        v = tape.get(y, 0) | (tape.get(y + d, 0) << 1)
        h1 = (h1 * 131 + v) % mod1
        h2 = (h2 * 137 + v + (y & 3)) % mod2
    return (h1, h2)

def _verify_cycle(tm, T, P):
    # Try to build a cycle certificate using the kernel itself.
    # We cannot call check with a certificate we haven't built; instead
    # build the certificate from simulation and let check validate it.
    try:
        halted, steps, state, pos, tape = run(tm, T + P + 10)
    except Exception:
        return None
    if halted:
        return None
    # We need the tape at time T and T+P. Re-run to capture snapshots.
    # Simpler: run step by step and record.
    from neverhalt.tm import parse as _parse
    table, n_states, n_symbols = _parse(tm)
    # manual step function to capture snapshots
    def step(state, pos, tape):
        s = tape.get(pos, 0)
        if (state, s) not in table:
            return None
        w, mv, ns = table[(state, s)]
        tape[pos] = w
        npos = pos + mv
        return ns, npos
    tape = {}
    st = 0
    p = 0
    snaps = {}
    for t in range(T + P + 1):
        if t == T or t == T + P:
            snaps[t] = (st, dict(tape))
        r = step(st, p, tape)
        if r is None:
            return None
        st, p = r
    if T not in snaps or (T + P) not in snaps:
        return None
    stT, tapeT = snaps[T]
    stP, tapeP = snaps[T + P]
    if stT != stP:
        return None
    # head displacement over lap
    # We need positions of head at T and T+P; recompute by tracking.
    # Instead, recompute head positions along with snapshots.
    # The above didn't track pos at snapshot time; redo quickly.
    st = 0
    p = 0
    tape = {}
    posT = posP = None
    for t in range(T + P + 1):
        if t == T:
            posT = p
        if t == T + P:
            posP = p
        r = step(st, p, tape)
        if r is None:
            return None
        st, p = r
    d = posP - posT
    # find window [lo, hi] of head positions during the lap
    st = 0
    p = 0
    tape = {}
    lo = hi = None
    for t in range(T + 1, T + P + 1):
        if lo is None or p < lo:
            lo = p
        if hi is None or p > hi:
            hi = p
        r = step(st, p, tape)
        if r is None:
            return None
        st, p = r
    if lo is None:
        return None
    # check tape condition: tape_{T+P}[y+d] == tape_T[y] for y in [lo,hi]
    # and outside window blank on far side when d != 0
    # We have tapeT and tapeP from earlier (at exact times).
    ok = True
    for y in range(lo, hi + 1):
        if tapeP.get(y + d, 0) != tapeT.get(y, 0):
            ok = False
            break
    if not ok:
        return None
    if d > 0:
        for y in range(hi + 1, hi + 64):
            if tapeP.get(y, 0) != 0:
                ok = False
                break
    elif d < 0:
        for y in range(lo - 64, lo):
            if tapeP.get(y, 0) != 0:
                ok = False
                break
    if not ok:
        return None
    cert = {"kind": "cycle", "t": T, "p": P}
    try:
        check(tm, cert)
    except Reject:
        return None
    return cert

def decide(tm: str):
    # Fast translated-cycle search. We simulate and look for a repeated
    # (state, pos mod small, tape hash) signature, then verify with kernel.
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # Manual fast simulation with tape dict.
    def step(state, pos, tape):
        s = tape.get(pos, 0)
        if (state, s) not in table:
            return None
        w, mv, ns = table[(state, s)]
        tape[pos] = w
        return ns, pos + mv
    tape = {}
    st = 0
    p = 0
    # We look for translated cycles: same state, same relative tape content
    # over a sliding window, head displacement d.
    # Use a simple approach: record (state, p, hash of tape in [p-40,p+40])
    # and if it repeats with same d = p2 - p1, try to build cert.
    MOD = 1000003
    seen = {}
    MAXSTEPS = 20000
    for t in range(MAXSTEPS + 1):
        if st == 0 and p == 0 and not tape and t > 0:
            # returned to start; try cycle with T=0? Not useful.
            pass
        # signature: state and tape window hash
        h = 0
        for y in range(p - 40, p + 41):
            h = (h * 131 + tape.get(y, 0)) % MOD
        sig = (st, h)
        if sig in seen:
            T0 = seen[sig]
            # candidate lap from T0 to t
            P = t - T0
            if P > 0 and P <= 50000:
                cert = _verify_cycle(tm, T0, P)
                if cert is not None:
                    return cert
        else:
            seen[sig] = t
        r = step(st, p, tape)
        if r is None:
            # halted; no certificate
            return None
        st, p = r
    return None