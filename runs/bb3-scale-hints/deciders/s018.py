import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import Reject

sys.setrecursionlimit(100000)

# ---------- helpers ----------

def table_of(tm):
    tbl, ns, nsym = parse(tm)
    return tbl, ns, nsym

def step(tbl, q, s):
    t = tbl.get((q, s))
    if t is None:
        return None
    w, m, q2 = t
    return (w, m, q2)

# ---------- 1. ngram CPS with 1..3 states per side ----------

def ngram_left(n):
    # states 0..n-1: 0 = all blank so far. state i>0 = last i blanks seen? 
    # build automaton over symbols read far->head: state = number of consecutive
    # blanks at the far end (capped).  We just need SOME automaton; the closure
    # will tell us if it is enough.  Simplest candidate: remember last k symbols
    # as a counter of trailing blanks.
    # state 0 loops on 0.  On symbol 1 go to state 1.  On 0 from state i>0 go to i-1? 
    # For a *half tape* read far->head, trailing blanks at the far end are the
    # only thing these survivors care about.  Use counter of trailing blanks.
    L = [[0] * 2 for _ in range(n)]
    L[0][0] = 0
    L[0][1] = 1 if n > 1 else 0
    for i in range(1, n):
        L[i][0] = i - 1
        L[i][1] = 1
    return L

def ngram_right(n):
    # same shape (states count trailing blanks from far side)
    R = [[0] * 2 for _ in range(n)]
    R[0][0] = 0
    R[0][1] = 1 if n > 1 else 0
    for i in range(1, n):
        R[i][0] = i - 1
        R[i][1] = 1
    return R

def closure(tbl, ns, L, R, maxctx=200000):
    # BFS over contexts [l,q,s,r]
    start = (0, 0, 0, 0)
    seen = {start}
    frontier = [start]
    while frontier:
        if len(seen) > maxctx:
            return None
        nxt = []
        for (l, q, s, r) in frontier:
            st = step(tbl, q, s)
            if st is None:
                # halting context -> not a proof
                return None
            w, m, q2 = st
            if m > 0:  # move right
                l2 = L[l][w]
                if l2 is None:
                    return None
                for (r2, s2) in pairs_where(R, r):
                    c = (l2, q2, s2, r2)
                    if c not in seen:
                        seen.add(c)
                        nxt.append(c)
            else:
                r2 = R[r][w]
                if r2 is None:
                    return None
                for (l2, s2) in pairs_where(L, l):
                    c = (l2, q2, s2, r2)
                    if c not in seen:
                        seen.add(c)
                        nxt.append(c)
        frontier = nxt
    return seen

def pairs_where(A, target):
    out = []
    for st in range(len(A)):
        for sym in (0, 1):
            if A[st][sym] == target:
                out.append((st, sym))
    return out

def cps_cert(seen):
    left = []
    right = []
    mx = max(max(c[0] for c in seen), max(c[3] for c in seen))
    # we will emit automata of size (mx+1) with nulls elsewhere
    # find actual sizes: max index used in l and r
    nl = 1
    nr = 1
    for (l, q, s, r) in seen:
        nl = max(nl, l + 1)
        nr = max(nr, r + 1)
    left = [[None, None] for _ in range(nl)]
    right = [[None, None] for _ in range(nr)]
    for (l, q, s, r) in seen:
        pass
    return None

# ---------- 2. search: enumerate DFAs for one half-tape, find one whose
# complement language is accepted by a right DFA built by reverse-determinization
# ----------

def build_left_from_table(L):
    # L[st][sym] -> st or None
    return L

def complement_NFA_from_L(L):
    # language of L (read far->head).  complement NFA: guess a mismatching prefix
    # and then accept anything.  Build NFA states: 0 = "still matching", 1 = "mismatched"
    # transitions: from 0 on sym: if L[0][sym] is None -> to 1 ; else stay 0 and also go to 1
    # from 1: stay 1 on both symbols.
    # Accepting: state 1.
    # Then subset-construct to DFA reading far->head; reverse it to read head->far.
    n = len(L)
    # NFA over symbols
    # state list: we track (0, actual L-state) plus dead state 1
    # epsilon-free
    start = (0, 0)
    # subset construction
    def eps_move(state):
        # state = (mode, lst) where mode 0 = matching, 1 = mismatched
        return state
    subsets = {}
    init = frozenset([start, (1, None)])
    subsets[init] = 0
    order = [init]
    trans = []
    while order:
        cur = order.pop(0)
        row = []
        for sym in (0, 1):
            nxt = set()
            for (mode, lst) in cur:
                if mode == 1:
                    nxt.add((1, None))
                else:
                    t = L[lst][sym] if lst is not None else None
                    if t is None:
                        nxt.add((1, None))
                    else:
                        nxt.add((0, t))
                        nxt.add((1, None))
            fs = frozenset(nxt)
            if fs not in subsets:
                subsets[fs] = len(order) + len(trans)
                order.append(fs)
            row.append(subsets[fs])
        trans.append(row)
    # accepting: subset containing (1,None)
    acc = set()
    for i, s in enumerate(subsets):
        if (1, None) in s:
            acc.add(i)
    # DFA reading far->head.  Reverse to read head->far: reverse all transitions,
    # start states = accepting states, accept = {0}
    nst = len(subsets)
    rev = [[None, None] for _ in range(nst)]
    for i in range(nst):
        for sym in (0, 1):
            j = trans[i][sym]
            if rev[j][sym] is None:
                rev[j][sym] = i
    # multiple start states -> need determinization again on the reversed NFA
    # do subset construction on rev with start set = acc
    startset = frozenset(acc)
    dfa = {}
    dorder = [startset]
    dfa[startset] = 0
    dtrans = []
    while dorder:
        cur = dorder.pop(0)
        row = []
        for sym in (0, 1):
            nxt = set()
            for st in cur:
                j = rev[st][sym]
                if j is not None:
                    nxt.add(j)
            fs = frozenset(nxt)
            if fs not in dfa:
                dfa[fs] = len(dorder) + len(dtrans)
                dorder.append(fs)
            row.append(dfa[fs])
        dtrans.append(row)
    # start state 0 ; accepting = states whose subset contains 0
    n2 = len(dfa)
    R = [[0, 0] for _ in range(n2)]
    for i, s in enumerate(dfa):
        for sym in (0, 1):
            R[i][sym] = dtrans[i][sym]
    return R, n2

# ---------- 3. forward search for a DFA for one half tape ----------

def enumerate_tables(max_states, max_tables=200000):
    # enumerate all complete DFAs with states 0..n-1, state 0 loops on 0
    # canonical: BFS over transition choices, dedupe by (n, table)
    seen = set()
    out = []
    # iterative deepening on number of states
    for n in range(1, max_states + 1):
        # enumerate all tables: (2n)^(n-1) possibilities for states 1..n-1 on sym 0,1
        # and state 0: [0, t01]
        # to keep it manageable, we enumerate with pruning: state 0 on 1 goes to some state
        # (including itself); states 1..n-1 map to any state.
        # We generate lazily via recursion.
        stack = [(0, [None]*2, {})]
        # simpler: recursive generation with limit
        def rec(idx, table):
            if len(out) > max_tables:
                return
            if idx == n:
                # canonical check: reachable from 0
                reach = {0}
                st = [0]
                while st:
                    x = st.pop()
                    for sym in (0, 1):
                        y = table[x][sym]
                        if y not in reach:
                            reach.add(y)
                            st.append(y)
                if len(reach) < n:
                    return
                key = tuple(tuple(r) for r in table)
                if key in seen:
                    return
                seen.add(key)
                out.append(table)
                return
            for a in range(n):
                for b in range(n):
                    table[idx][0] = a
                    table[idx][1] = b
                    rec(idx + 1, table)
                    if len(out) > max_tables:
                        return
        table = [[0, 0] for _ in range(n)]
        table[0][0] = 0
        # choose table[0][1]
        for t01 in range(n):
            table[0][1] = t01
            rec(1, table)
            if len(out) > max_tables:
                break
        if len(out) > max_tables:
            break
    return out

def decide(tm: str):
    tbl, ns, nsym = table_of(tm)
    # 1) try ngram pairs 1..3
    for nl in (1, 2, 3):
        for nr in (1, 2, 3):
            L = ngram_left(nl)
            R = ngram_right(nr)
            if max(c[0] for c in [(0,0,0,0)]) >= len(L):
                continue
            seen = closure(tbl, ns, L, R)
            if seen is not None:
                return emit_cps(seen)
    # 2) enumerate small DFAs for left half tape; for each, build right half tape
    #    as complement language reversed-determinized, then close.
    for L in enumerate_tables(3, max_tables=3000):
        try:
            R, n2 = complement_NFA_from_L(L)
        except Exception:
            continue
        if n2 > 5000:
            continue
        seen = closure(tbl, ns, L, R, maxctx=200000)
        if seen is not None:
            return emit_cps(seen)
    return None

def emit_cps(seen):
    # rebuild automata from the closure: for each l index, find transitions
    # actually used, else null
    nl = max(c[0] for c in seen) + 1
    nr = max(c[3] for c in seen) + 1
    left = [[None, None] for _ in range(nl)]
    right = [[None, None] for _ in range(nr)]
    for (l, q, s, r) in seen:
        st = step(None, q, s) if False else None
    # we need the tables; recompute by scanning transitions that were applied
    # Simpler: caller passes tables.  Here we recompute via closure's tables.
    return None

# The decider above is a sketch; the real one below is self-contained.

# =====================================================================
# REAL DECIDER
# =====================================================================

def _step(tbl, q, s):
    t = tbl.get((q, s))
    if t is None:
        return None
    return t

def _pairs(A, target):
    out = []
    for st in range(len(A)):
        for sym in (0, 1):
            if A[st][sym] == target:
                out.append((st, sym))
    return out

def _close(tbl, L, R, maxctx=200000):
    start = (0, 0, 0, 0)
    seen = {start}
    frontier = [start]
    while frontier:
        if len(seen) > maxctx:
            return None
        nxt = []
        for (l, q, s, r) in frontier:
            t = _step(tbl, q, s)
            if t is None:
                return None
            w, m, q2 = t
            if m > 0:
                l2 = L[l][w]
                if l2 is None:
                    return None
                for (r2, s2) in _pairs(R, r):
                    c = (l2, q2, s2, r2)
                    if c not in seen:
                        seen.add(c)
                        nxt.append(c)
            else:
                r2 = R[r][w]
                if r2 is None:
                    return None
                for (l2, s2) in _pairs(L, l):
                    c = (l2, q2, s2, r2)
                    if c not in seen:
                        seen.add(c)
                        nxt.append(c)
        frontier = nxt
    return seen

def _cert_from(seen, L, R):
    nl = max(c[0] for c in seen) + 1
    nr = max(c[3] for c in seen) + 1
    # keep only transitions used by closure: rebuild via reachability from 0 in L,R
    def trim(A, limit):
        n = len(A)
        reach = {0}
        st = [0]
        while st:
            x = st.pop()
            for sym in (0, 1):
                y = A[x][sym]
                if y is not None and y not in reach:
                    reach.add(y)
                    st.append(y)
        out = [[None, None] for _ in range(limit)]
        for i in range(min(n, limit)):
            for sym in (0, 1):
                y = A[i][sym]
                if y is not None and y < limit and i in reach:
                    out[i][sym] = y
        return out
    left = trim(L, nl)
    right = trim(R, nr)
    if left[0][0] != 0 or right[0][0] != 0:
        return None
    return {
        "kind": "cps",
        "left": left,
        "right": right,
        "contexts": [list(c) for c in seen],
    }

def _enumerate(max_states, max_tables):
    out = []
    seen = set()
    for n in range(1, max_states + 1):
        # recursive enumeration
        table = [[0, 0] for _ in range(n)]
        table[0][0] = 0
        def rec(idx):
            if len(out) > max_tables:
                return
            if idx == n:
                # reachability
                reach = {0}
                st = [0]
                while st:
                    x = st.pop()
                    for sym in (0, 1):
                        y = table[x][sym]
                        if y not in reach:
                            reach.add(y)
                            st.append(y)
                if len(reach) < n:
                    return
                key = tuple(tuple(r) for r in table)
                if key in seen:
                    return
                seen.add(key)
                out.append([row[:] for row in table])
                return
            for a in range(n):
                for b in range(n):
                    table[idx][0] = a
                    table[idx][1] = b
                    rec(idx + 1)
                    if len(out) > max_tables:
                        return
        for t01 in range(n):
            table[0][1] = t01
            rec(1)
            if len(out) > max_tables:
                break
        if len(out) > max_tables:
            break
    return out

def _rev_det(L):
    # language of L over {0,1}* read far->head; complement, then reverse -> DFA
    # complement NFA: state 0 = still matching, state 1 = mismatched (sink)
    # subset construction
    n = len(L)
    start = frozenset([(0, 0), (1, None)])
    subsets = {start: 0}
    order = [start]
    trans = []
    while order:
        cur = order.pop(0)
        row = []
        for sym in (0, 1):
            nxt = set()
            for (mode, lst) in cur:
                if mode == 1:
                    nxt.add((1, None))
                else:
                    t = L[lst][sym] if lst is not None else None
                    if t is None:
                        nxt.add((1, None))
                    else:
                        nxt.add((0, t))
                        nxt.add((1, None))
            fs = frozenset(nxt)
            if fs not in subsets:
                subsets[fs] = len(order) + len(trans)
                order.append(fs)
            row.append(subsets[fs])
        trans.append(row)
    acc = set(i for i, s in enumerate(subsets) if (1, None) in s)
    nst = len(subsets)
    rev = [[None, None] for _ in range(nst)]
    for i in range(nst):
        for sym in (0, 1):
            j = trans[i][sym]
            if rev[j][sym] is None:
                rev[j][sym] = i
    # determinize rev with start set = acc
    startset = frozenset(acc)
    dfa = {startset: 0}
    dorder = [startset]
    dtrans = []
    while dorder:
        cur = dorder.pop(0)
        row = []
        for sym in (0, 1):
            nxt = set()
            for st in cur:
                j = rev[st][sym]
                if j is not None:
                    nxt.add(j)
            fs = frozenset(nxt)
            if fs not in dfa:
                dfa[fs] = len(dorder) + len(dtrans)
                dorder.append(fs)
            row.append(dfa[fs])
        dtrans.append(row)
    n2 = len(dfa)
    R = [[dtrans[i][sym] for sym in (0, 1)] for i in range(n2)]
    return R

def decide(tm: str):
    tbl, ns, nsym = parse(tm)
    # quick ngram attempts
    for nl in (1, 2, 3):
        for nr in (1, 2, 3):
            L = [[0, 0] for _ in range(nl)]
            L[0][0] = 0
            L[0][1] = 1 if nl > 1 else 0
            for i in range(1, nl):
                L[i][0] = i - 1
                L[i][1] = 1
            R = [[0, 0] for _ in range(nr)]
            R[0][0] = 0
            R[0][1] = 1 if nr > 1 else 0
            for i in range(1, nr):
                R[i][0] = i - 1
                R[i][1] = 1
            seen = _close(tbl, L, R)
            if seen is not None:
                c = _cert_from(seen, L, R)
                if c is not None:
                    return c
    # enumerate left DFAs up to 4 states, build right DFA from complement
    for L in _enumerate(4, 4000):
        try:
            R = _rev_det(L)
        except Exception:
            continue
        if len(R) > 5000:
            continue
        seen = _close(tbl, L, R)
        if seen is not None:
            c = _cert_from(seen, L, R)
            if c is not None:
                return c
    # enumerate right DFAs too (symmetric attempt)
    for R in _enumerate(4, 4000):
        for L in _enumerate(3, 2000):
            try:
                pass
            except Exception:
                continue
            seen = _close(tbl, L, R)
            if seen is not None:
                c = _cert_from(seen, L, R)
                if c is not None:
                    return c
    return None
};