import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---- helpers shared by every decider -------------------------------------

def _halt_pairs(t, ns, nt):
    """Pairs (q,s) that have a defined transition, and the set of pairs (q,s)
    from which some halting transition is reachable in <= 40 steps.  Used to
    prune automaton tables: any tape language that can reach a halt must not
    contain the all-blank tape."""
    def step(q, s):
        t2 = t.get((q, s))
        if t2 is None:
            return None
        w, mv, q2 = t2
        return q2
    reach = set()
    frontier = set()
    for q in range(ns):
        for s in range(nt):
            if (q, s) in t:
                if t2 := t.get((q, s)):
                    # one step of the machine from (q,s): we need the *next*
                    # symbol under the head, which is unknown; approximate by
                    # "exists a symbol" reachability.
                    frontier.add(q)
    # The useful notion here is: from state q, can a halting transition be
    # taken eventually, regardless of symbols?  If not, tape content can never
    # force a halt from q in one step; use this only as a coarse prune.
    for q in range(ns):
        for s in range(nt):
            if (q, s) in t:
                reach.add((q, s))
    return reach

def _can_reach_halt(t, ns, nt, q, limit=60):
    """From state q, can the machine possibly reach a halting transition
    ignoring the tape (i.e. is any (q,s) reachable through defined
    transitions, with s chosen adversarially)?  Coarse, used for pruning."""
    seen = {q}
    dq = deque([q])
    while dq:
        x = dq.popleft()
        for s in range(nt):
            if (x, s) in t:
                nxt = t[(x, s)][2]
                if nxt not in seen:
                    seen.add(nxt)
                    dq.append(nxt)
    return True

# ---- DFA enumeration for one half-tape -----------------------------------

def enumerate_dfa_tables(nsym, nstates, max_states):
    """Yield transition tables (list of lists, index=state, value=next state
    or None) with states 1..nstates-1 reachable on some symbol, state 0 loops
    on symbol 0 -> 0.  BFS-canonical: a table is only emitted if its state
    numbering is the BFS order from 0 on symbols 0,1,...,nsym-1."""
    for n in range(1, max_states + 1):
        # enumerate all functions state -> sym -> next state (or None) with
        # n states, then canonicalize by BFS renaming.
        total = (n + 1) ** (n * nsym)
        if total > 8_000_000:
            continue
        for code in range(total):
            tab = [[None] * nsym for _ in range(n)]
            c = code
            for st in range(n):
                for sy in range(nsym):
                    v = c % (n + 1)
                    c //= (n + 1)
                    if v != n:
                        tab[st][sy] = v
            # state 0 must loop on symbol 0
            if tab[0][0] != 0:
                continue
            # BFS canonical renaming from state 0
            name = {0: 0}
            order = [0]
            dq = deque([0])
            while dq:
                x = dq.popleft()
                for sy in range(nsym):
                    y = tab[x][sy]
                    if y is None:
                        continue
                    if y not in name:
                        name[y] = len(name)
                        order.append(y)
                        dq.append(y)
            if len(order) != n:
                continue  # unreachable states: skip (they would be pruned)
            # canonical code: BFS order must equal 0,1,2,...
            if order != list(range(n)):
                continue
            # determinism: build final table
            final = [[None] * nsym for _ in range(n)]
            for x in range(n):
                for sy in range(nsym):
                    y = tab[x][sy]
                    final[x][sy] = name[y] if y is not None else None
            yield final

# ---- reverse determinization of an NFA -----------------------------------

def reverse_determinize(nfa, nsym):
    """nfa: dict state -> list of (symbol, next_state).  Build a DFA for the
    reverse language, reading far-to-head (i.e. the reverse of the language
    read head-to-far).  States are frozensets of NFA states; start = epsilon
    closure of the accepting states of the NFA.  The DFA state 0 must be the
    all-blank half-tape: we require the empty word to be accepted, so the
    empty set (or {accepting}) must be the start.  We return the DFA table
    with state 0 looping on symbol 0 to state 0 if the empty word is accepted."""
    # We treat the NFA as reading head-to-far; reverse determinize: read
    # far-to-head, so transitions are reversed and we start from the NFA's
    # accepting states.
    acc = [st for st in nfa if nfa[st] is None]  # accepting = no outgoing
    # epsilon closure = identity here (no epsilon transitions)
    start = frozenset(acc)
    table = {}
    dq = deque([start])
    seen = {start: 0}
    while dq:
        cur = dq.popleft()
        i = seen[cur]
        row = []
        for sym in range(nsym):
            nxt = set()
            for st in cur:
                for (s, t2) in (nfa[st] or []):
                    if s == sym:
                        nxt.add(t2)
            nxt = frozenset(nxt)
            if not nxt:
                row.append(None)
            else:
                if nxt not in seen:
                    seen[nxt] = len(seen)
                    dq.append(nxt)
                row.append(seen[nxt])
        table[i] = row
    # require state 0 to loop on 0
    if table[0][0] != 0:
        return None
    return [table[i] for i in range(len(table))]

# ---- context closure ------------------------------------------------------

def close_contexts(left, right, t, ns, q0=0, s0=0):
    """Fixpoint over contexts [l,q,s,r].  Returns the set of contexts or None
    if a halting context is forced (meaning the certificate fails)."""
    ctx = set()
    if (q0, s0) not in t:
        return None
    ctx.add((0, q0, s0, 0))
    changed = True
    while changed:
        changed = False
        for (l, q, s, r) in list(ctx):
            tr = t.get((q, s))
            if tr is None:
                return None  # halting context
            w, mv, q2 = tr
            if mv == 1:  # right move
                l2 = left[l][w]
                if l2 is None:
                    return None
                for (r2, s2) in right:
                    if right[r2][s2] == r and (l2, q2, s2, r2) not in ctx:
                        ctx.add((l2, q2, s2, r2))
                        changed = True
            else:  # left move
                r2 = right[r][w]
                if r2 is None:
                    return None
                for (l2, s2) in left:
                    if left[l2][s2] == l and (l2, q2, s2, r2) not in ctx:
                        ctx.add((l2, q2, s2, r2))
                        changed = True
    return ctx

# ---- main decider ---------------------------------------------------------

def decide(tm):
    try:
        t, ns, nt = parse(tm)
    except Exception:
        return None
    # 1) quick cycle check (cheap, sometimes enough)
    try:
        halted, steps, state, pos, tape = run(tm, 20000)
        if halted:
            return None
    except Exception:
        pass

    # 2) enumerate small left DFAs and try to close contexts
    for nstates in range(1, 6):
        for left in enumerate_dfa_tables(nt, 2, nstates):
            # prune: if the language of the left DFA contains the all-blank
            # tape and the machine can reach a halt from state 0 with a blank
            # cell under the head, the certificate fails (there is a halting
            # context).  Cheap necessary check: state 0 must loop on 0.
            if left[0][0] != 0:
                continue
            # build the right automaton by brute force over small DFAs too
            for right in enumerate_dfa_tables(nt, 2, nstates):
                if right[0][0] != 0:
                    continue
                ctx = close_contexts(left, right, t, ns)
                if ctx is not None:
                    # build certificate
                    cert = {
                        "kind": "cps",
                        "left": left,
                        "right": right,
                        "contexts": [list(c) for c in ctx],
                    }
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
    return None

if __name__ == "__main__":
    print(decide(sys.argv[1]))
