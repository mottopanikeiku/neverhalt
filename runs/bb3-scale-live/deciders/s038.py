from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: combined cycle search + ngram CPS fallback.
# Strategy: first attempt to prove non-halting with a translated-cycle
# certificate found by a bounded search over laps (this catches the
# machines whose diagrams show a drifting repeating pattern).  If a
# cycle is found, return it.  Otherwise fall back to a CPS certificate
# built from n-gram memories of both half-tapes, extended with a few
# hand-picked context-closing heuristics (adding contexts only when the
# closure rule demands them).

def _cycle_search(tm, max_t=3000, max_p=3000):
    table, n_states, n_symbols = parse(tm)
    # simulate once, recording configurations
    halted, steps, state, pos, tape = run(tm, max_t + max_p)
    # re-run step by step recording (state, pos, tape snapshot) at each time
    cfgs = []
    # simulate manually
    s, p, tp = 0, 0, {}
    for t in range(max_t + max_p):
        cfgs.append((t, s, p, dict(tp)))
        if (s, 0 if p not in tp else 1) not in table:
            return None
        w, mv, ns = table[(s, 0 if p not in tp else 1)]
        if w:
            tp[p] = w
        else:
            tp.pop(p, None)
        p += mv
        s = ns
    # try all (T, P) pairs within budget: T + P <= 100000
    # but we only have cfgs up to max_t+max_p
    limit = min(max_t + max_p, 100000)
    for T in range(0, limit):
        if T >= len(cfgs):
            break
        tT, sT, pT, tpT = cfgs[T]
        for P in range(1, limit - T):
            if T + P >= len(cfgs):
                break
            t2, s2, p2, tp2 = cfgs[T + P]
            if s2 != sT:
                continue
            d = p2 - pT
            # window: positions seen during lap
            lo = min(pT, p2)
            hi = max(pT, p2)
            # collect positions actually visited in the lap
            visited = [cfgs[k][2] for k in range(T, min(T + P + 1, len(cfgs)))]
            lo = min(visited)
            hi = max(visited)
            ok = True
            for y in range(lo, hi + 1):
                # tape_T[y] is tpT.get(y, 0); tape_{T+P}[y+d]
                vT = tpT.get(y, 0)
                v2 = tp2.get(y + d, 0)
                if vT != v2:
                    ok = False
                    break
            if not ok:
                continue
            # blank outside condition
            if d > 0:
                for y in range(hi + 1, hi + d + 1):
                    if tp2.get(y, 0) != 0:
                        ok = False
                        break
            elif d < 0:
                for y in range(lo + d, lo):
                    if tp2.get(y, 0) != 0:
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


def _ngram_cps(tm, n=6):
    table, n_states, n_symbols = parse(tm)
    # Build left and right automata remembering last n cells (read from far
    # away towards the head).  Symbol alphabet {0,1}.
    # Automaton states: tuples of length up to n (the cells read so far, from
    # far to near).  State 0 = all-blank empty memory.
    # left[i][x]: reading x pushes x (newest cell) and keeps last n.
    # We represent states canonically as strings of length <= n.
    def build_auto():
        trans = {}
        trans[""] = {0: "0", 1: "1"}
        for length in range(1, n + 1):
            for bits in range(1 << length):
                key = format(bits, "0%db" % length)
                row = {}
                for x in (0, 1):
                    if length == n:
                        newkey = key[1:] + str(x)
                    else:
                        newkey = key + str(x)
                    row[x] = newkey
                trans[key] = row
        return trans
    left_auto = build_auto()
    right_auto = build_auto()
    # Map state strings to indices; 0 reserved for empty/blank.
    def index_auto(auto):
        idx = {"": 0}
        for k in auto:
            if k not in idx:
                idx[k] = len(idx)
        return idx
    li = index_auto(left_auto)
    ri = index_auto(right_auto)
    # convert to index tables
    left_tbl = []
    for k in li:
        row = []
        for x in (0, 1):
            row.append(li[left_auto[k][x]])
        left_tbl.append(row)
    right_tbl = []
    for k in ri:
        row = []
        for x in (0, 1):
            row.append(ri[right_auto[k][x]])
        right_tbl.append(row)
    # contexts [l, q, s, r]; start from [0,0,0,0]
    start = (0, 0, 0, 0)
    seen = {start}
    stack = [start]
    contexts = []
    while stack:
        l, q, s, r = stack.pop()
        contexts.append([l, q, s, r])
        if (q, s) not in table:
            return None  # halting context -> cannot close
        w, mv, q2 = table[(q, s)]
        if mv > 0:
            # right move: l2 = left[l][w]; for every (r2, s2) with right[r2][s2] == r
            l2 = left_tbl[l][w]
            # find all (r2, s2) pairs mapping to r in right automaton
            pairs = []
            for r2 in range(len(right_tbl)):
                for s2 in (0, 1):
                    if right_tbl[r2][s2] == r:
                        pairs.append((r2, s2))
            for r2, s2 in pairs:
                c = (l2, q2, s2, r2)
                if c not in seen:
                    seen.add(c)
                    stack.append(c)
        else:
            r2 = right_tbl[r][w]
            pairs = []
            for l2 in range(len(left_tbl)):
                for s2 in (0, 1):
                    if left_tbl[l2][s2] == l:
                        pairs.append((l2, s2))
            for l2, s2 in pairs:
                c = (l2, q2, s2, r2)
                if c not in seen:
                    seen.add(c)
                    stack.append(c)
    if len(seen) > 200000:
        return None
    cert = {
        "kind": "cps",
        "left": left_tbl,
        "right": right_tbl,
        "contexts": [list(c) for c in contexts],
    }
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None


def decide(tm: str):
    # Try translated-cycle search first (fast for drifting patterns).
    c = _cycle_search(tm, max_t=1200, max_p=1200)
    if c is not None:
        return c
    # Fall back to ngram CPS with increasing memory.
    for n in (4, 5, 6, 7, 8):
        c = _ngram_cps(tm, n=n)
        if c is not None:
            return c
    return None