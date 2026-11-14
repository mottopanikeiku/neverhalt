import sys
from collections import deque
from neverhalt.tm import parse

sys.setrecursionlimit(1000000)

# ---------- helpers to build certificates ----------

def make_cert_contexts(tm):
    """Try to build a cps certificate by enumerating small DFAs for the
    left half-tape.  Returns a dict certificate or None."""
    table, n_states, n_symbols = parse(tm)
    # table[(state, symbol)] = (write, move, next_state)
    # symbol 0 and 1.  Writes are 0/1, moves +1/-1.

    # For a DFA A with states 0..k-1 for one half-tape, and B for the other,
    # state 0 is the blank tape: A[0][0] == 0 and B[0][0] == 0.
    # Context (l, q, s, r): l is state of left automaton, q machine state,
    # s symbol under head, r state of right automaton.

    # First, enumerate DFA transition tables for the left automaton.
    # A DFA here has n states, each with a transition on symbol 0 and 1.
    # We enumerate in BFS order by n: 1, 2, 3, ... up to MAXLEFT.
    # State 0 is the blank tape: dfa[0][0] == 0.

    def enumerate_dfas(max_states):
        # yield transition tables as list of [t0, t1] pairs.
        # BFS by number of states.
        # canonical: state 0 has t0 == 0 (blank loop).  We enumerate all
        # tables with states 0..n-1, and then try to merge equivalent states
        # in BFS order.  Simplest: enumerate all n^n*2^n tables for n<=3,
        # then for n=4..max_states enumerate in a smarter way?  That's too
        # many.  Instead we enumerate DFAs reachable by adding one state
        # at a time in BFS order (language-based canonical order).
        # For simplicity here: enumerate all tables for n<=3 exhaustively,
        # and for larger n build them by extending smaller tables with one
        # new state that is reachable, canonicalised by min-state BFS.
        for n in range(1, max_states + 1):
            if n == 1:
                # states: 0.  t0 must be 0.  t1 in {0} (only state).
                yield [[0, 0]]
            elif n <= 3:
                # exhaustive over t0,t1 in range(n)
                import itertools
                for t0s in itertools.product(range(n), repeat=n):
                    for t1s in itertools.product(range(n), repeat=n):
                        tabs = [[t0s[i], t1s[i]] for i in range(n)]
                        # require state 0 loops on 0 (blank half-tape)
                        if tabs[0][0] != 0:
                            continue
                        # BFS canonical: renumber states in order of first
                        # reachability from 0 using transitions.
                        seen = {0}
                        order = [0]
                        dq = deque([0])
                        while dq:
                            u = dq.popleft()
                            for v in (tabs[u][0], tabs[u][1]):
                                if v not in seen:
                                    seen.add(v)
                                    order.append(v)
                                    dq.append(v)
                        if len(order) != n:
                            continue  # unreachable states: skip
                        remap = {old: i for i, old in enumerate(order)}
                        newtabs = [[remap[tabs[st][0]], remap[tabs[st][1]]] for st in order]
                        # skip duplicates
                        yield newtabs
            else:
                # build by extending n-1 tables: add state n-1 with arbitrary
                # transitions, require reachability and canonical BFS.
                for base in enumerate_dfas(n - 1):
                    # add new state n-1
                    for a in range(n):
                        for b in range(n):
                            tabs = [list(x) for x in base]
                            tabs.append([a, b])
                            # reachability
                            seen = {0}
                            order = [0]
                            dq = deque([0])
                            while dq:
                                u = dq.popleft()
                                for v in (tabs[u][0], tabs[u][1]):
                                    if v not in seen:
                                        seen.add(v)
                                        order.append(v)
                                        dq.append(v)
                            if len(order) != n:
                                continue
                            remap = {old: i for i, old in enumerate(order)}
                            newtabs = [[remap[tabs[st][0]], remap[tabs[st][1]]] for st in order]
                            yield newtabs

    MAXLEFT = 4  # keep runtime small for 500ms budget

    # Forward simulation of the machine from blank tape to warm up.
    def simulate(tm, steps):
        table2, _, _ = parse(tm)
        tape = {}
        state = 0
        pos = 0
        for _ in range(steps):
            if (state, tape.get(pos, 0)) not in table2:
                return None
            w, mv, ns = table2[(state, tape.get(pos, 0))]
            tape[pos] = w
            pos += mv
            state = ns
        return state, pos, tape

    # Check whether a given left DFA yields a closed context set.
    def try_left(dfa):
        n = len(dfa)
        # left[0][0] must be 0.  Also left[0][1] can be anything.
        if dfa[0][0] != 0:
            return None
        # Build contexts fixpoint.
        # Context = (l, q, s, r) with r in range(1<<16) as a placeholder for
        # the right automaton state; we will first try to see if a right
        # automaton with 1 state (only blank) works, then build one.
        # Strategy: guess right DFA too by symmetry of search.  Instead,
        # we do a joint enumeration: for each left DFA, we try to build the
        # right DFA by reverse-determinization later.  Here, for speed, we
        # try a fixed family of right DFAs: 1 state, or n-gram memory.
        # The hint suggests reverse-determinizing the other side's language.
        # For this decider we enumerate both left and right DFAs over small
        # state counts with pruning: we only keep pairs whose closure has no
        # halting context.
        return None

    # Simpler approach for this round: enumerate pairs of small DFAs
    # (left, right) with 1..3 states each, compute the closure, and emit.
    def closure_has_no_halt(left, right):
        nl = len(left)
        nr = len(right)
        # context set as a set of (l,q,s,r)
        start = (0, 0, 0, 0)
        cur = {start}
        seen = {start}
        # worklist
        dq = deque([start])
        # Precompute transitions.
        # For each context, we need:
        #   (q,s) in table -> (w, mv, q2)
        #   if mv == +1: for every (r2, s2) with right[r2][s2] == r:
        #       l2 = left[l][w]; if l2 is None -> fail (not closed)
        #       (l2, q2, s2, r2) must be in contexts
        #   if mv == -1: for every (l2, s2) with left[l2][s2] == l:
        #       r2 = right[r][w]; if r2 is None -> fail
        #       (l2, q2, s2, r2) must be in contexts
        # We compute the closure and check every context has a valid
        # transition (no halt) and the resulting contexts are all present.
        # Since we grow the set, we can iterate until fixpoint.
        while dq:
            l, q, s, r = dq.popleft()
            key = (q, s)
            if key not in table:
                return None  # halting context -> reject
            w, mv, q2 = table[key]
            if mv == 1:
                # l2 = left[l][w]
                l2 = left[l][w]
                if l2 is None:
                    return None
                # For every (r2, s2) with right[r2][s2] == r:
                #   need (l2, q2, s2, r2) in cur
                for r2 in range(nr):
                    for s2 in range(2):
                        if right[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in seen:
                                seen.add(c)
                                cur.add(c)
                                dq.append(c)
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                for l2 in range(nl):
                    for s2 in range(2):
                        if left[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in seen:
                                seen.add(c)
                                cur.add(c)
                                dq.append(c)
        # check no halting context: all contexts processed, and each had a
        # transition (checked above).  But we must ensure the fixpoint is
        # closed: every produced context was added to seen and processed.
        # Since we processed all, closure is closed.
        return cur

    def try_pair(left, right):
        cur = closure_has_no_halt(left, right)
        if cur is None:
            return None
        # Build certificate.
        # left and right as lists of [t0, t1].  Convert to kernel format:
        # left[i][x] = state reached, or null.  Our DFA tables already use
        # ints; None for null is not needed since we only have defined
        # transitions.  But the kernel wants null where "never happens".
        # Our enumeration only produced total DFAs (every (state,symbol)
        # defined).  That's fine: no nulls.
        L = [[int(left[i][0]), int(left[i][1])] for i in range(len(left))]
        R = [[int(right[i][0]), int(right[i][1])] for i in range(len(right))]
        contexts = [[int(c[0]), int(c[1]), int(c[2]), int(c[3])] for c in cur]
        return {"kind": "cps", "left": L, "right": R, "contexts": contexts}

    # Enumerate left and right DFAs with small sizes.
    def all_dfas(maxn):
        for n in range(1, maxn + 1):
            for t in enumerate_dfas(n):
                yield t

    # Try pairs.
    MAXN = 3
    lefts = list(all_dfas(MAXN))
    rights = list(all_dfas(MAXN))
    # dedupe by tuple
    def key(t):
        return tuple(tuple(x) for x in t)
    lefts = list({key(t): t for t in lefts}.values())
    rights = list({key(t): t for t in rights}.values())
    for L in lefts:
        for R in rights:
            cert = try_pair(L, R)
            if cert is not None:
                return cert
    return None


def decide(tm: str):
    try:
        cert = make_cert_contexts(tm)
        if cert is not None:
            from neverhalt.kernel import check, Reject
            try:
                check(tm, cert)
                return cert
            except Reject:
                return None
        return None
    except Exception:
        return None


NAME = "small-dfa-pair-search"