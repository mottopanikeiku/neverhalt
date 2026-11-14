import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(100000)

# Held-out machines show a common pattern: a single active "wall" of #'s that the
# head walks back and forth along, with occasional extra 1-walls being swept out.
# We hunt for translated cycles directly: simulate up to a fixed horizon, look for
# a pair (T, P) where the head displacement d = pos[T+P] - pos[T] != 0 and the
# tape shifted by d matches on the visited window, using the kernel's own rules.

def find_cycle(tm, horizon=60000, extra=2000):
    table, ns, nsym = parse(tm)
    try:
        halted, steps, state, pos, tape = run(tm, horizon)
    except Exception:
        return None
    if halted:
        return None
    # We need detailed step history; run() doesn't give it, so re-simulate manually.
    cells = [0] * 4000
    cells[2000] = 0
    pos = 2000
    state = 0
    base = 0
    hist_pos = []
    hist_state = []
    hist_tape = []
    for step in range(horizon + extra):
        hist_pos.append(pos)
        hist_state.append(state)
        hist_tape.append((pos, cells[pos]))
        if (state, cells[pos]) not in table:
            return None
        w, mv, q2 = table[(state, cells[pos])]
        cells[pos] = w + 1
        pos += mv
        state = q2
        base = step
    # Try translated cycles: T around a period, P the lap length.
    # Search over a modest set of candidate laps: use head return times.
    # Build map (state, pos) -> list of times.
    from collections import defaultdict
    by_sp = defaultdict(list)
    for i in range(len(hist_pos)):
        by_sp[(hist_state[i], hist_pos[i])].append(i)
    # candidate laps: times i<j with same state, j-i = P, and pos[j]-pos[i]=d
    times = len(hist_pos)
    cands = []
    for (st, pp), ts in by_sp.items():
        for a in range(len(ts)):
            for b in range(a + 1, len(ts)):
                P = ts[b] - ts[a]
                if P < 3 or P > 3000:
                    continue
                T = ts[a]
                if T + P >= times:
                    continue
                d = hist_pos[T + P] - hist_pos[T]
                if d == 0:
                    continue
                cands.append((T, P, d))
    # sort by shortest lap
    cands.sort(key=lambda x: x[1])
    for (T, P, d) in cands[:400]:
        # window over steps T..T+P inclusive
        lo = min(hist_pos[T:T + P + 1])
        hi = max(hist_pos[T:T + P + 1])
        # check state matches
        if hist_state[T] != hist_state[T + P]:
            continue
        ok = True
        # tape at T+P: reconstruct by replaying? Instead use cells at end of T+P.
        # We stored only head cell values, not full tape history. Use the fact that
        # the only cells that matter in [lo,hi] at T are those visited; replay from
        # step T with a fresh tape copy is too expensive. Instead store full tape
        # snapshots sparsely every step would be too big; but the kernel itself can
        # verify. We can attempt T+P by re-simulating from scratch up to T+P.
        # Simpler: we already have cells after full run; but for arbitrary T we need
        # tape at T. Re-run from scratch up to T+P and compare to T.
        # Do it lazily for the first few candidates.
        try:
            c1 = [0] * 4000
            p1 = 2000
            st1 = 0
            tapeT = None
            tapeTP = None
            for step in range(T + P + 1):
                if step == T:
                    tapeT = (p1, list(c1))
                w, mv, q2 = table[(st1, c1[p1])]
                c1[p1] = w + 1
                p1 += mv
                st1 = q2
            tapeTP = (p1, list(c1))
        except Exception:
            continue
        if tapeT is None:
            continue
        # shift: tape_{T+P}[y + d] == tape_T[y] for y in [lo,hi]
        offT = tapeT[0]
        offTP = tapeTP[0]
        # absolute positions: at step T, base offset such that head pos hist_pos[T]
        # absolute = cell index. We stored cell index directly in hist_pos (2000-based).
        # So lo,hi are already absolute indices.
        for y in range(lo, hi + 1):
            vT = tapeT[1][y]
            vTP = tapeTP[1][y + d]
            if vT != vTP:
                ok = False
                break
        if not ok:
            continue
        # blank outside condition when d>0: cells right of hi blank at T+P
        if d > 0:
            for y in range(hi + 1, len(tapeTP[1])):
                if tapeTP[1][y] != 0:
                    ok = False
                    break
        elif d < 0:
            for y in range(0, lo):
                if tapeTP[1][y] != 0:
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

def decide(tm: str):
    try:
        return find_cycle(tm)
    except Exception:
        return None
