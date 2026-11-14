import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---- machine tables ----
def get_tables(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states

# ---- candidate DFA enumeration (canonical BFS order) ----
def enum_dfa_tables(max_states, sym=2):
    """Yield DFA transition tables as dicts {state: {sym: next}} with states 0..k-1,
    canonical: state 0 is the blank state and loops on symbol 0.
    We enumerate reachable tables of size <= max_states by BFS over partial tables
    completed deterministically.  To keep it finite we enumerate tables as tuples
    of transitions for states 0..k-1 and require the whole table closed."""
    # iterate number of states k = 1..max_states
    for k in range(1, max_states + 1):
        # enumerate all functions for states 1..k-1 (state 0 fixed: on 0 -> 0),
        # plus state 0 on symbol 1 free.
        # Represent a table as tuple of length k*sym giving next state or -1.
        # Use recursive enumeration with early canonical pruning.
        # For k up to 3 this is small; for larger we cap transitions per state.
        # Generate all tables where state 0 on 0 -> 0.
        # We'll generate via itertools.product over allowed next states.
        import itertools
        allowed = list(range(k))
        # positions: state 0 sym 0 fixed 0; others free
        free_positions = []
        for st in range(k):
            for sx in range(sym):
                if st == 0 and sx == 0:
                    continue
                free_positions.append((st, sx))
        if len(free_positions) > 12:
            # too many; skip large k in this simple enumerator
            continue
        for combo in itertools.product(allowed, repeat=len(free_positions)):
            tab = {}
            for st in range(k):
                tab[st] = {}
                if st == 0:
                    tab[0][0] = 0
            for (st, sx), nx in zip(free_positions, combo):
                tab[st][sx] = nx
            yield tab

# ---- helpers ----
def step_ctx(machine, ctx):
    """Given context [l, q, s, r] and machine transition for (q,s),
    return list of possible next contexts (or None if halting)."""
    table, n_states = machine
    w, move, q2 = table[(q, s)]
    nxt = []
    if move > 0:
        # right move: push w onto left half-tape
        # left automaton reads cells left of head from far away towards head;
        # stepping right: the written symbol w is pushed onto the LEFT half-tape.
        # l2 = left[l][w]
        for r2 in range(10000):
            # we need all r2 with right[r2][s2] == r; handled by caller
            pass
        return ('right', w, q2, l, r)
    else:
        return ('left', w, q2, l, r)

def close_contexts(machine, left, right, init, max_ctx=200000, max_iter=50):
    """Fixpoint closure of contexts [l, q, s, r]."""
    table, n_states = machine
    ctxs = set([init])
    if init[1] >= n_states:
        return None
    # precompute right inverse: for each (r, s2) list r2 with right[r2][s2] == r
    # and left inverse similarly.
    def inv_right(r, s2):
        out = []
        for r2 in range(len(right)):
            row = right[r2]
            if s2 in row and row[s2] == r:
                out.append(r2)
        return out
    def inv_left(l2, s2):
        out = []
        for l in range(len(left)):
            row = left[l]
            if s2 in row and row[s2] == l2:
                out.append(l)
        return out
    changed = True
    it = 0
    while changed and it < max_iter:
        changed = False
        it += 1
        cur = list(ctxs)
        for (l, q, s, r) in cur:
            if (q, s) not in table:
                return None  # halting context
            w, move, q2 = table[(q, s)]
            if move > 0:
                # right move: l2 = left[l][w]; for every (r2, s2) with right[r2][s2] == r
                if w not in left[l]:
                    return None
                l2 = left[l][w]
                for (r2, s2) in [(r2, s2) for r2 in range(len(right)) for s2 in range(2)]:
                    if s2 in right[r2] and right[r2][s2] == r:
                        nxt = (l2, q2, s2, r2)
                        if nxt not in ctxs:
                            ctxs.add(nxt); changed = True
            else:
                if w not in right[r]:
                    return None
                r2 = right[r][w]
                for (l2, s2) in [(l2, s2) for l2 in range(len(left)) for s2 in range(2)]:
                    if s2 in left[l2] and left[l2][s2] == l:
                        nxt = (l2, q2, s2, r2)
                        if nxt not in ctxs:
                            ctxs.add(nxt); changed = True
            if len(ctxs) > max_ctx:
                return None
    return ctxs if ctxs else None

# ---- NFA determinization helper (subset construction) ----
def determinize_nfa(nfa, n_states):
    """nfa: dict state -> dict sym -> set of next states.  Reverse-determinize:
    far-to-head DFA states are subsets of NFA states; blank tape is empty set."""
    from collections import deque
    start = frozenset()
    dfa = {}
    dfa[frozenset()] = 0
    idx = [frozenset()]
    q = deque([frozenset()])
    while q:
        cur = q.popleft()
        row = {}
        for sx in (0, 1):
            nxt = set()
            for st in cur:
                if st in nfa and sx in nfa[st]:
                    nxt |= nfa[st][sx]
            fs = frozenset(nxt)
            if fs not in dfa:
                dfa[fs] = len(idx); idx.append(fs); q.append(fs)
            row[sx] = dfa[fs]
        dfa_row = {}
        for sx in (0, 1):
            dfa_row[sx] = row[sx]
        # store by state id
        # we'll rebuild below
    # rebuild clean
    table = {}
    for fs, sid in dfa.items():
        table[sid] = {}
    for fs, sid in dfa.items():
        for sx in (0, 1):
            table[sid][sx] = dfa.get(frozenset().union(*[nfa.get(st, {}).get(sx, set()) for st in fs]) if fs else set(), -1)
    return table, len(idx)

# ---- main decider ----
def decide(tm: str):
    machine = get_tables(tm)
    table, n_states = machine
    # 1) try small DFA tables for the left half-tape
    for left in enum_dfa_tables(3):
        # require blank state loops on 0 (already) and is reachable/closed
        # build right automaton as identity-ish tracker of last n cells
        # simplest: right automaton as a chain remembering up to 2 recent cells
        # we will try the other side too later; first try symmetric small tables
        for right in enum_dfa_tables(3):
            # context closure
            ctxs = close_contexts(machine, left, right, (0, 0, 0, 0), max_ctx=200000)
            if ctxs is None:
                continue
            # build certificate: contexts as lists
            contexts = [[l, q, s, r] for (l, q, s, r) in ctxs]
            # normalize tables: keep only used transitions
            def slim(tab, used_states):
                out = []
                for st in range(len(tab)):
                    row = []
                    for sx in (0, 1):
                        row.append(tab[st].get(sx))
                    out.append(row)
                return out
            cert = {
                "kind": "cps",
                "left": slim(left, None),
                "right": slim(right, None),
                "contexts": contexts,
            }
            # verify with kernel before returning
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    # 2) fallback: longer simulation to detect plain cycles
    try:
        halted, steps, state, pos, tape = run(tm, 100000)
        if halted:
            return None
    except Exception:
        return None
    return None

# ensure no top-level execution issues
if __name__ == "__main__":
    pass
