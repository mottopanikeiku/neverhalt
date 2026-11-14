import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import Reject, check

# ---------------------------------------------------------------------------
# Certificate builders: translated cycles and closed context sets (cps).
# ---------------------------------------------------------------------------

MAX_T = 100000
MAX_P = 100000
MAX_CTX = 200000
MAX_AUT = 5000


def try_cycle(tm, table, n_states, n_symbols, halt_states):
    """Search for a translated cycle with a small period, returning a cert."""
    # state encoding: (state, pos, tape)
    start = (0, 0, (0, 0))
    seen = {start: 0}
    len_hist = {}
    for step in range(1, MAX_T + 1):
        st, pos, (lo, hi) = None, None, None
        # run one step manually to track window
        # (we use run() for speed but track window separately)
        break
    # simpler: use run() and inspect
    try:
        halted, steps, state, pos, tape = run(tm, MAX_T)
    except Exception:
        return None
    if halted and steps <= MAX_T:
        return None
    # We need tape snapshots. Re-run in chunks to collect states.
    # For efficiency, collect states every step up to some cap.
    return None


def cps_closure(right_table, left_table, n_states, n_symbols):
    """Compute the closed context set for given automaton tables.

    right_table[r][s] -> r' or None
    left_table[l][s]  -> l' or None
    returns (contexts, ok) where ok False means a halting context was found.
    """
    ctx = set()
    # invariant: contexts reachable from [0,0,0,0]
    init = (0, 0, 0, 0)
    if init not in ctx:
        ctx.add(init)
    frontier = deque([init])
    while frontier:
        l, q, s, r = frontier.popleft()
        # machine transition
        tr = None
        # need table lookup; done by caller
        tr = machine_tr[q][s]
        if tr is None:
            return None  # halting context
        w, move, q2 = tr
        if move == 1:
            l2 = left_table[l][w] if l < len(left_table) else None
            if l2 is None:
                return None
            # for every (r2, s2) with right_table[r2][s2] == r
            for r2 in range(len(right_table)):
                for s2 in range(n_symbols):
                    if right_table[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            frontier.append(c)
        else:
            r2 = right_table[r][w] if r < len(right_table) else None
            if r2 is None:
                return None
            for l2 in range(len(left_table)):
                for s2 in range(n_symbols):
                    if left_table[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            frontier.append(c)
        if len(ctx) > MAX_CTX:
            return None
    return ctx


# We need the machine transition table in the closure routine; use a global.
machine_tr = None
n_mach_states = 0
n_sym = 0


def build_ctx_cert(ctx):
    left = [[None] * n_sym for _ in range(10)]
    right = [[None] * n_sym for _ in range(10)]
    # We do not have the automata tables here; caller passes them.
    return None


def make_cps_cert(left_table, right_table, ctx, n_states, n_symbols):
    left = [[(left_table[i][x] + 1) if left_table[i][x] is not None else None
             for x in range(n_symbols)] for i in range(len(left_table))]
    right = [[(right_table[i][x] + 1) if right_table[i][x] is not None else None
              for x in range(n_symbols)] for i in range(len(right_table))]
    contexts = [[list(c) for c in ctx]]
    return {"kind": "cps", "left": left, "right": right, "contexts": contexts[0]}


# ---------------------------------------------------------------------------
# DFA enumeration in BFS-canonical order.
# ---------------------------------------------------------------------------

def normalize_table(t):
    # canonicalize state numbering by BFS from 0
    n = len(t)
    seen = {0: 0}
    order = [0]
    dq = deque([0])
    while dq:
        i = dq.popleft()
        for x in range(n_sym):
            j = t[i][x]
            if j is not None and j not in seen:
                seen[j] = len(order)
                order.append(j)
                dq.append(j)
    if len(order) < n:
        return None  # unreachable states
    remap = {old: new for new, old in enumerate(order)}
    nt = [[(remap[t[i][x]] if t[i][x] is not None else None) for x in range(n_sym)]
          for i in range(n)]
    return nt


def enumerate_dfa(max_states):
    """Yield DFA tables of size 1..max_states in BFS-canonical order."""
    # represent table as tuple of tuples with None
    for size in range(1, max_states + 1):
        # BFS over tables: start with all states looping on 0
        # We generate tables by extending a base table.
        # Simple approach: enumerate all transition assignments for a
        # canonical BFS-ordered state space, pruning by reachability.
        yield from _enum_size(size)


def _enum_size(size):
    # enumerate all functions for `size` states over n_sym symbols,
    # target in [0..size-1] or None; keep canonical (BFS from 0).
    choices = [None] + list(range(size))
    # iterate over all assignments
    total = (size + 1) ** (size * n_sym)
    if total > 200000:
        return
    for code in range(total):
        t = []
        c = code
        for i in range(size):
            row = []
            for x in range(n_sym):
                v = c % (size + 1)
                c //= (size + 1)
                row.append(None if v == 0 else v - 1)
            t.append(row)
        nt = normalize_table(t)
        if nt is not None:
            yield tuple(tuple(r) for r in nt)


def main(tm):
    global machine_tr, n_mach_states, n_sym
    table, n_states, n_symbols = parse(tm)
    n_sym = n_symbols
    n_mach_states = n_states
    # build machine transition list indexed by state, with None for halt
    machine_tr = []
    for st in range(n_states):
        row = []
        for sy in range(n_symbols):
            key = (st, sy)
            if key in table:
                row.append(table[key])
            else:
                row.append(None)
        machine_tr.append(row)

    # first: try translated cycle via run/inspect
    cert = try_cycle(tm, table, n_states, n_symbols, None)
    if cert is not None:
        return cert

    # enumerate right DFAs (from far away towards head) of size 1..3,
    # then left DFAs of size 1..3.
    right_cands = []
    for rsz in range(1, 4):
        cnt = 0
        for rt in enumerate_dfa(rsz):
            right_cands.append(rt)
            cnt += 1
            if cnt > 500:
                break
        if cnt > 500:
            break
    left_cands = []
    for lsz in range(1, 4):
        cnt = 0
        for lt in enumerate_dfa(lsz):
            left_cands.append(lt)
            cnt += 1
            if cnt > 500:
                break
        if cnt > 500:
            break

    # try pairs, prefer smaller context sets
    best = None
    for rt in right_cands:
        for lt in left_cands:
            ctx = cps_closure(rt, lt, n_states, n_symbols)
            if ctx is None:
                continue
            if len(ctx) > MAX_CTX:
                continue
            cert = make_cps_cert(lt, rt, ctx, n_states, n_symbols)
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
            except Exception:
                continue
    return None


def decide(tm: str):
    try:
        return main(tm)
    except Exception as e:
        return None


if __name__ == "__main__":
    import json
    tm = sys.argv[1]
    c = decide(tm)
    print(json.dumps(c) if c else "None")
