import sys
from collections import deque

# ---- kernel-independent helpers -------------------------------------------
# We do not need the full table; only transitions of the machine.
def transitions(tm):
    """Return list of (state, symbol) -> (w, move, q2) for defined transitions."""
    # bbchallenge notation: one row per state, 3 chars per read symbol
    rows = tm.split('_')
    out = {}
    for i, row in enumerate(rows):
        for sym in (0, 1):
            c = row[3*sym:3*sym+3]
            if c == '---' or len(c) < 3:
                continue
            w = int(c[0])
            mv = +1 if c[1] == 'R' else -1
            ns = c[2]
            out[(i, sym)] = (w, mv, ns)
    return out

def state_index(ch):
    up = ch.upper()
    return ord(up) - ord('A')

def sym_of(ch):
    return 1 if ch.isupper() else 0

# ---- DFA enumeration for one half-tape ------------------------------------
def canon_states(trans, n):
    """trans: dict (state, sym) -> next state. Assign canonical ids in BFS order."""
    start = 0
    seen = {start: 0}
    order = [start]
    q = deque([start])
    while q:
        s = q.popleft()
        for sym in (0, 1):
            t = trans.get((s, sym))
            if t is None:
                continue
            if t not in seen:
                seen[t] = len(order)
                order.append(t)
                q.append(t)
    return order

def enumerate_dfa_tables(max_states):
    """Yield every complete DFA transition table over states 0..n-1 (n = 1..max_states),
    in BFS-canonical order.  State 0 is the blank state and loops on 0 by convention."""
    for n in range(1, max_states+1):
        # product of (n)^(2*n) possibilities is too large beyond n=3; we restrict
        # ourselves to tables where state 0 loops on 0 (as required).
        # Enumerate lazily but bounded; this decider only handles tiny n.
        if n > 3:
            return
        import itertools
        for combo in itertools.product(range(n), repeat=2*n):
            table = {}
            for i in range(n):
                for sym in (0, 1):
                    table[(i, sym)] = combo[2*i+sym]
            # state 0 loops on symbol 0
            if table[(0, 0)] != 0:
                continue
            # BFS-canonical: BFS from 0 must visit states in order 0,1,2,...
            order = canon_states(table, n)
            if order != list(range(n)):
                continue
            yield n, table

# ---- halting transitions ---------------------------------------------------
def halting_pairs(tm):
    rows = tm.split('_')
    out = []
    for i, row in enumerate(rows):
        for sym in (0, 1):
            c = row[3*sym:3*sym+3]
            if c == '---' or len(c) < 3:
                out.append((i, sym))
    return out

# ---- main search -----------------------------------------------------------
def decider_core(tm):
    T = transitions(tm)
    states = sorted({s for (s, _) in T} | {q for (_, _, q) in T for q in [q] if q != 'A'} | {0})
    # convert state letters
    def sid(ch):
        return state_index(ch)
    machine = {}
    for (s, sym), (w, mv, ns) in T.items():
        machine[(sid(s), sym)] = (w, mv, sid(ns))
    halt = {(sid(s), sym) for (s, sym) in halting_pairs(tm)}

    # Try small left DFAs, build context closure.
    for n, table in enumerate_dfa_tables(3):
        # Build the right automaton by reverse-determinization of the complement:
        # the right automaton must accept exactly the right half-tapes that can
        # lead to a halt.  We approximate by using the same table and mirroring.
        # For a concrete certificate we need a real automaton; here we first test
        # whether the left DFA already gives a closed context set with itself
        # mirrored (this is the common case for bouncers).
        right_table = {}
        for (i, sym), v in table.items():
            right_table[(i, sym)] = v
        # Check whether [0,0,0,0] closure is finite and halt-free.
        contexts = {(0, 0, 0, 0)}
        frontier = [(0, 0, 0, 0)]
        ok = True
        while frontier:
            l, q, s, r = frontier.pop()
            if (q, s) not in machine:
                # halting context -> reject this DFA
                ok = False
                break
            w, mv, q2 = machine[(q, s)]
            if mv == +1:
                l2 = table.get((l, w))
                if l2 is None:
                    ok = False
                    break
                # right automaton pops s2 for every (r2, s2) with right[r2][s2] == r
                for r2 in range(n):
                    for s2 in (0, 1):
                        if right_table.get((r2, s2)) == r:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                contexts.add(ctx)
                                frontier.append(ctx)
            else:
                r2 = right_table.get((r, w))
                if r2 is None:
                    ok = False
                    break
                for l2 in range(n):
                    for s2 in (0, 1):
                        if table.get((l2, s2)) == l:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                contexts.add(ctx)
                                frontier.append(ctx)
        if ok and len(contexts) <= 200000:
            # emit certificate
            left = [[table.get((i, 0)), table.get((i, 1))] for i in range(n)]
            right = [[right_table.get((i, 0)), right_table.get((i, 1))] for i in range(n)]
            ctx_list = [[l, q, s, r] for (l, q, s, r) in sorted(contexts)]
            return {"kind": "cps", "left": left, "right": right, "contexts": ctx_list}
    return None

try:
    from neverhalt.kernel import check, Reject
    _ = check
except Exception:
    pass

NAME = "search-half-automata"

def decide(tm):
    try:
        return decider_core(tm)
    except Exception:
        return None


if __name__ == "__main__":
    import sys
    for line in sys.stdin:
        tm = line.strip()
        if not tm:
            continue
        c = decide(tm)
        print(tm, "->", "CERT" if c else "none")
