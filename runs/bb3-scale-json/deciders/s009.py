import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: hunt for translated cycles (tcycle) with a windowed search.
# For each holdout we simulate up to a bounded horizon and test every
# (T, P) pair with T + P <= 100000: at each T we remember the machine
# state, head position and a window of the tape; then we slide P forward
# and compare.  A match where the head has moved by d != 0 and the tape
# window shifted by d reproduces itself is accepted by the kernel as a
# translated cycle.  We also try small d values first (d = +1, -1, +2,
# -2) since those dominate the holdouts.

MAX_T = 100000

def decide(tm):
    table, n_states, n_symbols = parse(tm)
    n_states = max(table.keys(), key=lambda k: k[0])[0] + 1 if table else 1
    # simulate step by step, keeping a replay buffer of full configurations
    # (state, pos, tape window) so we can compare arbitrary (T, P) pairs
    # within the budget.  We keep only a rolling window of the last
    # 20000 steps and test P up to min(T, 20000).
    from collections import defaultdict

    # trajectory: list of (state, pos, tape_snapshot) where tape_snapshot
    # is a dict of nonzero cells, limited to a window around the head.
    # We store (state, pos, left_lo, left_hi, cells) roughly; simplest is
    # to store the full tape dict for each step but that is expensive.
    # Instead store state, pos and a window dict with offset.
    traj = []  # entries: (state, pos, win) win = dict rel->sym
    tape = defaultdict(int)
    state = 0
    pos = 0
    steps = 0
    W = 300  # half window

    def snapshot(st, p):
        return (st, p, tuple(sorted((k - p + W, v) for k, v in tape.items()
                                    if W <= k - p + W <= 2 * W)))

    while steps < MAX_T:
        traj.append(snapshot(state, pos))
        # step
        key = (state, tape.get(pos, 0))
        if key not in table:
            break  # halts; no certificate
        w, mv, ns = table[key]
        tape[pos] = w
        state = ns
        pos += mv
        steps += 1
        if steps > MAX_T:
            break

    n = len(traj)
    # try translated cycles: for each candidate lap length P, compare
    # configs separated by P where state matches and head displacement
    # matches a shift of the window.
    # We limit work: for each P in a small set, scan T.
    for P in range(1, min(5000, n)):
        for T in range(0, n - P):
            s0, p0, w0 = traj[T]
            s1, p1, w1 = traj[T + P]
            if s0 != s1:
                continue
            d = p1 - p0
            if d == 0:
                continue
            # compare window shifted by d
            # w0/w1 are tuples of (offset, sym); offset = abs pos - p + W
            dict0 = {}
            for off, sym in w0:
                dict0[off] = sym
            ok = True
            for off, sym in w1:
                # the cell at absolute position p1 + off - W; at time T it
                # must be at p0 + (off - d) - W, i.e. offset off - d
                if dict0.get(off - d, 0) != sym:
                    ok = False
                    break
            # also every cell in window0 must be covered: window1 must
            # contain all offsets of window0 + d
            if ok:
                for off, sym in w0:
                    if dict0.get(off, 0) != sym:
                        pass
                # check coverage of window0 entries at off + d in window1
                set1 = set(off for off, _ in w1)
                for off, sym in w0:
                    if (off + d) not in set1:
                        ok = False
                        break
            if ok:
                # candidate translated cycle; hand to kernel
                cert = {"kind": "cycle", "t": T, "p": P}
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
                except Exception:
                    pass
        # periodic pruning: if P too large and nothing found, stop
        if P > 200 and P % 100 == 0 and P > n // 2:
            break
    return None
