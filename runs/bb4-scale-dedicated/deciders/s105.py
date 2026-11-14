import sys
from collections import deque
from neverhalt.tm import parse

sys.setrecursionlimit(100000)

NULL = None


def _bits(text):
    out = []
    for row in text.split("_"):
        for i in range(0, len(row), 3):
            out.append(row[i:i + 3])
    return out


def _table_of(tm):
    text = tm
    if text.endswith("\n"):
        text = text.strip()
    return parse(tm)


def _normalize(tm):
    return tm


def _run_steps(tm, steps):
    from neverhalt.tm import run
    halted, n, state, pos, tape = run(tm, steps)
    return halted, n, state, pos, tape


def _halt_pairs(tm):
    table, ns, nsym = parse(tm)
    hp = []
    for q in range(ns):
        for s in (0, 1):
            t = table.get((q, s))
            if t is None:
                hp.append((q, s))
    return hp


def _dfa_trans(base, trans, nstates, sym):
    if trans is None:
        return NULL
    return (base << 1) | sym


def _rev_comp(nstates, delta):
    # language of delta is a DFA over {0,1}; return reverse-determinized DFA
    # for the complement, reading far-to-head.
    # delta: list indexed by state, entries None or (write, move, next)??
    # We only use delta as a transition table: entry None means no transition.
    # Represent delta as dict: (state, sym) -> next state or None.
    # We build NFA for complement of L(delta) reading the tape from far to
    # near: reverse the language of delta.
    # Simpler: build NFA whose states are (state, flag) where flag 1 means
    # "we have seen the end of the word so far"; but complement of a DFA is a
    # DFA already.  Reverse of a DFA is an NFA.  We do subset construction on
    # the reversed NFA and then determinize again.
    # delta is dict (state, sym) -> next state (or None for dead).
    union = {}
    for st in range(nstates):
        for sym in (0, 1):
            nxt = delta.get((st, sym))
            if nxt is not None:
                key = (st, sym)
                if key not in union:
                    union[key] = set()
                union[key].add(nxt)
    # NFA for reverse: states are original states plus a new start = the
    # accepting sink of delta (we use a special accept state 0 if delta[0]
    # is the all-blank state and is accepting).  For our use we treat the
    # half-tape language as: the DFA accepts if it reaches state 0.
    # Reverse the language: NFA with start state = {0} (accepting state of
    # delta) and transitions reversed.  Accepting states = {q | q can reach 0}.
    # Compute reverse adjacency.
    rev = {}
    for (st, sym), nxts in union.items():
        for nx in nxts:
            rev.setdefault(nx, []).append((st, sym))
    # NFA states: original states; start = {0}; accepting = states that can
    # reach 0 in delta.
    can_reach_0 = [False] * nstates
    can_reach_0[0] = True
    stack = [0]
    while stack:
        u = stack.pop()
        for (st, sym), nxts in union.items():
            if st == u:
                for nx in nxts:
                    if not can_reach_0[nx]:
                        can_reach_0[nx] = True
                        stack.append(nx)
    # determinize the reversed NFA
    start = frozenset([0])
    dfa = {}
    dfa_states = {}
    order = []
    dq = deque([start])
    dfa_states[start] = 0
    order.append(start)
    while dq:
        cur = dq.popleft()
        for sym in (0, 1):
            nxt = set()
            ok = True
            for st in cur:
                for (a, b), ns in union.items():
                    if a == st and b == sym:
                        nxt.update(ns)
            if not nxt:
                continue
            nxt = frozenset(nxt)
            if nxt not in dfa_states:
                dfa_states[nxt] = len(dfa_states)
                order.append(nxt)
                dq.append(nxt)
            dfa[(dfa_states[cur], sym)] = dfa_states[nxt]
    acc = set()
    for st, idx in dfa_states.items():
        for q in st:
            if can_reach_0[q]:
                acc.add(idx)
                break
    return len(dfa_states), dfa, acc


def _context_closure(tm, left_tab, right_tab, nsl, nsr, nctx_limit):
    table, ns, nsym = parse(tm)
    # contexts: (l, q, s, r)
    start = (0, 0, 0, 0)
    ctx = {start}
    # left[0][0] == 0 and right[0][0] == 0 must hold
    if left_tab.get((0, 0)) != 0 or right_tab.get((0, 0)) != 0:
        return None
    while True:
        new = set()
        for (l, q, s, r) in ctx:
            t = table.get((q, s))
            if t is None:
                return None  # halting context -> no certificate
            w, mv, q2 = t
            if mv == 1:
                l2 = left_tab.get((l, w))
                if l2 is None:
                    return None
                for (r2, s2) in right_tab:
                    if right_tab[(r2, s2)] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            new.add(c)
            else:
                r2 = right_tab.get((r, w))
                if r2 is None:
                    return None
                for (l2, s2) in left_tab:
                    if left_tab[(l2, s2)] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            new.add(c)
        if not new:
            break
        ctx |= new
        if len(ctx) > nctx_limit:
            return None
    # check no halting context
    for (l, q, s, r) in ctx:
        if table.get((q, s)) is None:
            return None
    # shrink tables to used transitions
    used_l = set()
    used_r = set()
    for (l, q, s, r) in ctx:
        for (a, b) in left_tab:
            if a == l:
                used_l.add((a, b))
        for (a, b) in right_tab:
            if a == r:
                used_r.add((a, b))
    lt = [[None, None] for _ in range(nsl)]
    for (a, b) in used_l:
        lt[a][b] = left_tab[(a, b)]
    rt = [[None, None] for _ in range(nsr)]
    for (a, b) in used_r:
        rt[a][b] = right_tab[(a, b)]
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    return {"kind": "cps", "left": lt, "right": rt, "contexts": contexts}


def _enum_dfa(nstates, max_states, prune):
    # enumerate DFAs over {0,1} with states 0..nstates-1, state 0 all-blank
    # (0 loops on 0), BFS-canonical: we enumerate all transition tables
    # delta[state][sym] in 0..nstates-1; prune partial tables whose language
    # already contains the all-blank tape (accepted by reaching state 0).
    # Here "language contains blank tape" means state 0 is reachable from
    # start on the blank word 0* -- but the blank tape is the empty word in
    # the far-to-head reading, so the DFA must NOT accept it: i.e. from the
    # start state 0 reading symbol 0 it must not stay at 0 forever.  Actually
    # the all-blank half-tape has no cells, so the DFA start state must be
    # non-accepting in the language of "reaches 0"?  Our convention: the
    # automaton state 0 means all-blank remainder.  If the DFA reaches state
    # 0 on input, the half-tape is blank.  We must avoid states that accept
    # the empty word: state 0 on input 0 must not lead back to 0?  The hint
    # says prune as soon as the tapes that can lead to a halt are forced to
    # include the blank tape.  For simplicity we enumerate all tables and
    # let the closure check reject halting contexts.
    results = []
    for code in range((nstates) ** (2 * nstates)):
        delta = {}
        x = code
        for st in range(nstates):
            for sym in (0, 1):
                delta[(st, sym)] = x % nstates
                x //= nstates
        # state 0 must loop on 0 (all-blank half-tape)
        if delta[(0, 0)] != 0:
            continue
        results.append((nstates, delta))
    return results


def decide(tm: str):
    from neverhalt.kernel import check, Reject
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    # try small DFAs for the right half-tape first
    for nst in (1, 2, 3, 4):
        # build DFA table: list of lists
        for code in range(nst ** (2 * nst)):
            x = code
            delta_tab = [[0, 0] for _ in range(nst)]
            for st in range(nst):
                for sym in (0, 1):
                    delta_tab[st][sym] = x % nst
                    x //= nst
            if delta_tab[0][0] != 0:
                continue
            delta = {(st, sym): delta_tab[st][sym] for st in range(nst) for sym in (0, 1)}
            # build the left half-tape DFA as reverse-determinized complement
            try:
                nls, ldfa, lacc = _rev_comp(nst, delta)
            except Exception:
                continue
            if nls > 8:
                continue
            ltab = {k: v for k, v in ldfa.items()}
            # left automaton: index states 0..nls-1, but state 0 must be the
            # all-blank start.  Our construction uses state indices; ensure
            # ltab[(0,0)] == 0.
            if ltab.get((0, 0)) != 0:
                continue
            cert = _context_closure(tm, ltab, delta, nls, nst, 200000)
            if cert is not None:
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
    return None


if __name__ == "__main__":
    import sys
    tm = sys.argv[1]
    print(decide(tm))
