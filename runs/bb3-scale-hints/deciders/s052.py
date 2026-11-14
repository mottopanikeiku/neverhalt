import sys, itertools
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def far_dfa_from_nfa(nfa_states, nfa_start, nfa_accept, nfa_trans):
    """Determinize an NFA that reads from far away toward the head.

    nfa_trans: dict (state, symbol) -> set(states) ; None means empty set.
    The reading never stops: an infinite stream is read.  We build the DFA
    state as the frozenset of NFA states reachable after reading the prefix.
    Only states reachable by reading symbols 0/1 for some finite prefix of the
    all-blank prefix (i.e. prefixes of zeros) are relevant; we simply explore
    all reachable subset states.  Because the NFA accepts languages of finite
    prefixes of an infinite stream, we approximate: a subset is accepting if
    it contains an NFA accept state.  Non-accepting subsets are non-halting
    candidates.  We return a canonical BFS numbering where state 0 is the
    subset reached after reading only zeros from the start (all-blank).
    """
    start = frozenset([nfa_start])
    seen = {start: 0}
    order = [start]
    trans = [[None, None] for _ in range(64)]  # grown dynamically
    acc = [False] * 64
    i = 0
    while i < len(order):
        cur = order[i]
        if len(trans) <= i + 1:
            trans.extend([[None, None]] * (len(trans) + 1))
            acc.extend([False] * 1)
        if any(s in nfa_accept for s in cur):
            acc[i] = True
        for sym in (0, 1):
            nxt = set()
            for s in cur:
                for t in nfa_trans.get((s, sym), ()):
                    nxt.add(t)
            if not nxt:
                continue
            nxt = frozenset(nxt)
            if nxt not in seen:
                if len(seen) >= 4096:
                    continue
                seen[nxt] = len(order)
                order.append(nxt)
            trans[i][sym] = seen[nxt]
        i += 1
    return trans, acc


def reverse_dfa(trans, acc):
    """Return (rev_trans, rev_acc) for reading the string backwards.

    rev_acc[q] is True iff every suffix-continuation from q is accepting,
    i.e. the language read backwards is a right language; for safety we only
    need the set of states from which *some* continuation halts.  We build the
    reverse NFA from trans and determinize it.
    """
    n = len(trans)
    # Build reverse NFA transitions.
    radj = [[] for _ in range(n)]
    for q in range(n):
        for sym in (0, 1):
            p = trans[q][sym]
            if p is not None:
                radj[p].append((sym, q))
    start = frozenset([n - 1])  # accept states are "start" for the reverse
    # We only care about reachable subsets from the accepting states going
    # backwards; a stream read far-to-head corresponds to reading the tape
    # right-to-left, so a halting configuration means the *full* tape reaches
    # an accept state.  Reverse determinization from accept states gives the
    # set of suffixes that can lead to a halt.
    seen = {start: 0}
    order = [start]
    rtrans = [[None, None]]
    racc = [True]
    i = 0
    while i < len(order):
        cur = order[i]
        if len(rtrans) <= i:
            rtrans.append([None, None])
            racc.append(False)
        for sym in (0, 1):
            nxt = set()
            for s in cur:
                for (sym2, t) in radj[s]:
                    if sym2 == sym:
                        nxt.add(t)
            nxt = frozenset(nxt) if nxt else None
            if nxt is None:
                rtrans[i][sym] = None
            else:
                if nxt not in seen:
                    if len(seen) >= 4096:
                        rtrans[i][sym] = None
                        continue
                    seen[nxt] = len(order)
                    order.append(nxt)
                rtrans[i][sym] = seen[nxt]
        i += 1
    return rtrans, racc


def build_context_closure(tm, left, right, n_states, n_syms, max_ctx=200000):
    """Closed-context fixpoint.

    left/right: trans tables (lists of lists with None).  left[0][0] and
    right[0][0] must be 0.
    Returns list of contexts [l, q, s, r] or None if a halting context is
    forced.
    """
    table, ns, nsm = parse(tm)
    nq = ns
    # contexts as a set of tuples
    ctx = {(0, 0, 0, 0)}
    frontier = list(ctx)
    while frontier:
        if len(ctx) > max_ctx:
            return None
        new = []
        for (l, q, s, r) in frontier:
            # halting transition?
            key = (q, s)
            if key not in table:
                return None  # halting context reached
            w, move, q2 = table[key]
            if move > 0:  # right move: consume from right half-tape
                l2 = left[l][w]
                if l2 is None:
                    return None
                # r2, s2 with right[r2][s2] == r
                for r2 in range(len(right)):
                    for s2 in range(nsm):
                        if right[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                new.append(c)
            else:  # left move: consume from left half-tape
                r2 = right[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(left)):
                    for s2 in range(nsm):
                        if left[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                new.append(c)
        frontier = new
    return [[l, q, s, r] for (l, q, s, r) in ctx]


def emit_cps(tm, left, right, contexts):
    # strip automata to used states only, renumber so 0 is blank
    used_l = set(c[0] for c in contexts)
    used_r = set(c[3] for c in contexts)
    used_q = set(c[1] for c in contexts)
    used_s = set(c[2] for c in contexts)
    def strip(tab, used):
        idx = {s: i for i, s in enumerate(sorted(used))}
        n = len(idx)
        out = []
        for i in range(n):
            src = idx[i]
            row = []
            for sym in range(2):
                p = tab[src][sym]
                row.append(idx[p] if p is not None and p in idx else None)
            out.append(row)
        return out
    # ensure state 0 is blank loop
    L = strip(left, used_l)
    R = strip(right, used_r)
    # force 0 to loop on 0
    if L[0][0] != 0:
        L[0][0] = 0
    if R[0][0] != 0:
        R[0][0] = 0
    # remap contexts
    li = {i: i for i in range(len(used_l))}
    # build mapping from old to new index
    old_l = sorted(used_l); old_r = sorted(used_r)
    lm = {old: i for i, old in enumerate(old_l)}
    rm = {old: i for i, old in enumerate(old_r)}
    qm = {old: i for i, old in enumerate(sorted(used_q))}
    sm = {old: i for i, old in enumerate(sorted(used_s))}
    new_ctx = [[lm[c[0]], qm[c[1]], sm[c[2]], rm[c[3]]] for c in contexts]
    # blank state must be 0 in both automata
    # find index of blank subset (state 0 originally) in stripped
    if 0 not in lm:
        # shouldn't happen for valid certificates (blank start must be present)
        return None
    # reorder so that blank is index 0
    def reorder(tab, idx, blank_old):
        bi = idx.get(blank_old)
        if bi == 0:
            return tab
        n = len(tab)
        nt = [None] * n
        for i in range(n):
            nt[i] = [None, None]
        for i in range(n):
            for sym in range(2):
                p = tab[i][sym]
                if p is not None:
                    if p == bi:
                        nt[0][sym] = 0
                    else:
                        j = tab.index(p) if False else None
                        # find original index of p
                        for k in range(n):
                            if k == bi:
                                continue
                        # simpler: build map
        # do it properly
        pos = {}
        pos[bi] = 0
        for i in range(n):
            if i != bi:
                pos[i] = len(pos)
        for i in range(n):
            for sym in range(2):
                p = tab[i][sym]
                if p is not None:
                    nt[pos[i]][sym] = pos[p]
        return nt
    L = reorder(L, lm, old_l[0] if old_l[0] in lm else None) if False else L
    # Actually blank state corresponds to old index 0
    L = reorder(L, None, 0) if 0 in old_l else L
    R = reorder(R, None, 0) if 0 in old_r else R
    # remap contexts again after reorder
    def newmap(old, blank):
        m = {}
        m[blank] = 0
        for o in sorted(old):
            if o != blank:
                m[o] = len(m)
        return m
    lm2 = newmap(old_l, 0) if 0 in old_l else {o: i for i, o in enumerate(old_l)}
    rm2 = newmap(old_r, 0) if 0 in old_r else {o: i for i, o in enumerate(old_r)}
    ctx2 = [[lm2[c[0]], c[1], c[2], rm2[c[3]]] for c in new_ctx]
    cert = {"kind": "cps", "left": L, "right": R, "contexts": ctx2}
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None


# ---------------------------------------------------------------------------
# Decider strategies
# ---------------------------------------------------------------------------

def decide(tm):
    # ---- Strategy 1: enumerate tiny DFAs (1..3 states) for both half-tapes
    table, ns, nsm = parse(tm)
    nq = ns
    best = None
    for nl in (1, 2, 3):
        for nr in (1, 2, 3):
            # enumerate all deterministic transition tables, state 0 loops on 0
            for ltab in enumerate_tables(nl):
                for rtab in enumerate_tables(nr):
                    if ltab is None or rtab is None:
                        continue
                    # quick sanity: blank loop
                    if ltab[0][0] != 0 or rtab[0][0] != 0:
                        continue
                    ctx = build_context_closure(tm, ltab, rtab, nl, nr)
                    if ctx is None:
                        continue
                    cert = emit_cps(tm, ltab, rtab, ctx)
                    if cert is not None:
                        return cert
    # ---- Strategy 2: CPS with n-gram automata (memory of last n cells)
    # left automaton reads cells left of head far-to-head, remembers last n
    for n in (1, 2, 3, 4, 5, 6):
        ltab = ngram_table(n, nsm)
        rtab = ngram_table(n, nsm)
        ctx = build_context_closure(tm, ltab, rtab, None, None)
        if ctx is None:
            continue
        cert = emit_cps(tm, ltab, rtab, ctx)
        if cert is not None:
            return cert
    # ---- Strategy 3: run a short cycle search as fallback
    cert = find_cycle(tm)
    if cert is not None:
        return cert
    return None


def enumerate_tables(n):
    """Yield all deterministic 2-symbol tables for n states with state 0
    looping on symbol 0.  Returns None entries are not generated here; we
    generate full deterministic tables only (null entries handled by
    stripping later).  """
    syms = 2
    for bits in range((n * syms) ** 2):
        tab = []
        b = bits
        ok = True
        for i in range(n):
            row = []
            for sym in range(syms):
                v = b % n
                b //= n
                row.append(v)
            tab.append(row)
        if n == 0:
            continue
        if tab[0][0] != 0:
            continue
        yield tab


def ngram_table(n, nsm):
    """Automaton remembering the last n symbols.  States are n-grams
    encoded as integers base nsm."""
    if n == 0:
        return [[0, 0]]
    total = nsm ** n
    # state 0 encodes all-zero n-gram (blank)
    trans = [[None, None] for _ in range(total)]
    for i in range(total):
        for sym in range(nsm):
            # shift: new state = (i * nsm + sym) mod nsm^n
            trans[i][sym] = (i * nsm + sym) % total
    return trans


def find_cycle(tm, max_steps=5000):
    table, ns, nsm = parse(tm)
    # simulate and look for exact state+window repeat
    try:
        halted, steps, state, pos, tape = run(tm, max_steps)
    except Exception:
        return None
    # We don't have the full history from run; re-simulate manually.
    hist = []
    state = 0
    pos = 0
    tape = {}
    for t in range(max_steps):
        key = (state, pos)
        if key not in tape:
            s = 0
        else:
            s = tape[key]
        if (state, s) not in table:
            return None
        w, move, q2 = table[(state, s)]
        tape[key] = w
        hist.append((state, pos, s, dict(tape)))
        pos += move
        state = q2
        # bound tape size
        if len(tape) > 400:
            return None
    # look for a repeat of (state, pos) with matching window content
    seen = {}
    for t, (st, p, s, tp) in enumerate(hist):
        if (st, p) in seen:
            t0 = seen[(st, p)]
            # check tape matches on the window
            lo = min(min(tp.keys(), default=0), min(hist[t0][3].keys(), default=0))
            hi = max(max(tp.keys(), default=0), max(hist[t0][3].keys(), default=0))
            if tp == hist[t0][3]:
                P = t - t0
                return {"kind": "cycle", "t": t0, "p": P}
        else:
            seen[(st, p)] = t
    return None


# ---------------------------------------------------------------------------
# Time budget guard: bail out early if we have spent too long
# ---------------------------------------------------------------------------

import time as _time

_START = _time.time()


def decide(tm):
    t0 = _time.time()
    try:
        table, ns, nsm = parse(tm)
    except Exception:
        return None
    # Strategy 1: tiny DFAs
    for nl in (1, 2, 3):
        if _time.time() - t0 > 1.2:
            break
        for nr in (1, 2, 3):
            if _time.time() - t0 > 1.2:
                break
            for ltab in enumerate_tables(nl):
                if _time.time() - t0 > 1.2:
                    break
                for rtab in enumerate_tables(nr):
                    if _time.time() - t0 > 1.2:
                        break
                    if ltab[0][0] != 0 or rtab[0][0] != 0:
                        continue
                    ctx = build_context_closure(tm, ltab, rtab, nl, nr)
                    if ctx is None:
                        continue
                    cert = emit_cps(tm, ltab, rtab, ctx)
                    if cert is not None:
                        return cert
    # Strategy 2: n-gram
    for n in (1, 2, 3, 4, 5, 6, 7, 8):
        if _time.time() - t0 > 2.0:
            break
        ltab = ngram_table(n, nsm)
        rtab = ngram_table(n, nsm)
        ctx = build_context_closure(tm, ltab, rtab, None, None)
        if ctx is None:
            continue
        cert = emit_cps(tm, ltab, rtab, ctx)
        if cert is not None:
            return cert
    # Strategy 3: cycle search
    if _time.time() - t0 < 4.0:
        cert = find_cycle(tm)
        if cert is not None:
            return cert
    return None
