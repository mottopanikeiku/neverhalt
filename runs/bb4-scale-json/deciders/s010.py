import sys
sys.setrecursionlimit(100000)

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

NAME = "bounded-window-repeat search"

# We look for a cycle in the machine's configuration where the tape
# content within a window around the head repeats exactly, while the
# head displacement per lap is nonzero or zero. The kernel's cycle
# certificate accepts a window-repeat: simulate T steps, take a lap of
# P steps, require same state at both ends, and require that the tape
# content shifted by the lap displacement d matches on the window
# [lo, hi] seen during the lap, with the appropriate blank outside
# condition when d != 0.
#
# Here we search only over a *bounded* window: we require the window
# [lo, hi] to be small (at most WINDOW cells) so that the simulation
# and the check are cheap, and we require the outside cells to be
# blank at time T+P. This is a fast, memory-light variant aimed at
# machines whose long-running behavior is a small translated cycle
# and which were not caught by the "window-repeat cycles (replayed)"
# decider because the replay window was chosen differently.

WINDOW = 40
MAX_T = 6000
MAX_P = 6000

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # Simulate up to MAX_T + MAX_P steps, recording (state, pos) and
    # the tape at each step so we can extract windows.
    # We only need configuration snapshots at times T and T+P, so we
    # store the tape at each step in a compact dict-of-dicts.
    MAX = MAX_T + MAX_P
    from neverhalt.tm import run as _run
    # run() gives us only the final configuration; to get intermediate
    # ones we simulate ourselves. machine states are ints, A = 0.
    # parse gives table keyed (state, symbol) -> (write, move, next).
    # Undefined transitions are absent.
    # Tape as dict pos -> symbol (0 or 1), default 0.
    tape = {}
    pos = 0
    state = 0
    configs = []  # list of (state, pos, frozen tape)
    t = 0
    while t < MAX:
        if (state, tape.get(pos, 0)) not in table:
            return None  # halts, not a holdout
        w, mv, nxt = table[(state, tape.get(pos, 0))]
        if w:
            tape[pos] = w
        else:
            tape.pop(pos, None)
        pos += mv
        state = nxt
        t += 1
        # store snapshot at this time (t, after the step)
        configs.append((state, pos, dict(tape)))
        # early exit if we have enough
        if t >= MAX_T and t > MAX_T:
            break
    # Now search for T, P, d, window.
    # configs[i] is configuration after i+1 steps; time index i+1.
    # We want T and T+P both present.
    n = len(configs)
    # index by time: time = i+1
    # For speed, precompute per-time: state, pos, tape dict.
    # We'll iterate T from 0..MAX_T and P from 1..MAX_P.
    # To keep it fast, only try T in a sampled range and P sampled.
    # First, gather candidate (state, pos) pairs at times >= MAX_T.
    # Build dict: time -> (state, pos)
    times = {}
    for i, (st, p, tp) in enumerate(configs):
        times[i + 1] = (st, p)
    # Also store tape per time: we already have it in configs.
    # Iterate over T values where a snapshot exists, and P values.
    # To limit cost: for each T, we scan P from 1 upward until time
    # T+P exceeds n.
    # For each (T, P): same state, compute d = pos(T+P) - pos(T).
    # Determine window [lo, hi] as positions visited during the lap:
    # we need head positions from T to T+P inclusive. We approximate
    # by scanning configs from index T-1 to T+P-1 (careful with indexing).
    # Time k corresponds to configs[k-1] for k>=1.
    for idx in range(0, min(n, MAX_T)):
        T = idx + 1
        stT, posT, tapeT = configs[idx]
        # scan P
        for j in range(idx + 1, n):
            P = j - idx
            if P > MAX_P:
                break
            stP, posP, tapeP = configs[j]
            if stP != stT:
                continue
            d = posP - posT
            # window positions seen during lap: from configs[idx] to configs[j]
            lo = min(c[1] for c in configs[idx:j+1])
            hi = max(c[1] for c in configs[idx:j+1])
            if hi - lo > WINDOW:
                continue
            # check tape match: tapeP[y + d] == tapeT[y] for y in [lo, hi]
            ok = True
            for y in range(lo, hi + 1):
                a = tapeT.get(y, 0)
                b = tapeP.get(y + d, 0)
                if a != b:
                    ok = False
                    break
            if not ok:
                continue
            if d > 0:
                # every cell right of hi must be blank at T+P
                for y in range(hi + 1, hi + WINDOW + 1):
                    if tapeP.get(y, 0) != 0:
                        ok = False
                        break
                if not ok:
                    continue
            elif d < 0:
                for y in range(lo - WINDOW - 1, lo - 1):
                    if tapeP.get(y, 0) != 0:
                        ok = False
                        break
                if not ok:
                    continue
            if ok:
                cert = {"kind": "cycle", "t": T, "p": P}
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
    return None
} for everyone working on this problem: I think we can do better than this, but I want to see how far a bounded-window cycle search gets us before we invest in the heavier automaton-based approaches. The samples all look like they are expanding a filled triangle or a diagonal band, which is exactly the translated-cycle regime that this decider targets, so I expect a decent hit rate on the current holdouts. Let us see what the kernel says.