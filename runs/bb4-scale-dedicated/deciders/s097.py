import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import Reject

MAXT = 100000
NS = 6

def build(tm):
    table, n_states, n_symbols = parse(tm)
    trans = {}
    for st in range(n_states):
        for sym in range(n_symbols):
            v = table.get((st, sym))
            if v is not None:
                w, mv, nxt = v
                trans[(st, sym)] = (w, mv, nxt)
    return trans, n_states, n_symbols

def canon_step(tab, st, sym):
    return tab.get((st, sym))

def enumerate_tables(size, sym_count=2):
    # enumerate all deterministic tables on `size` states over sym_count symbols
    # state 0 loops on symbol 0
    import itertools
    for idx in itertools.product(range(-1, size), repeat=size * sym_count):
        tab = {}
        for st in range(size):
            for sym in range(sym_count):
                v = idx[st * sym_count + sym]
                if v >= 0:
                    tab[(st, sym)] = v
        yield tab

def bfs_tables(size, sym_count=2):
    seen = set()
    out = []
    for t in enumerate_tables(size, sym_count):
        key = tuple(sorted(t.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out

def reverse_complement_dfa(tab, start=0):
    # language = set of tapes that lead to halt; complement
    # build NFA for complement by subset construction over symbols 0,1
    # start state of complement is the set of states from which no halting path exists
    # We'll compute halting states: states from which some string reaches a missing transition.
    states = sorted({s for (s, _) in tab} | {t for t in tab.values()})
    # compute for each state whether some string leads to a missing transition
    halting = set()
    changed = True
    while changed:
        changed = False
        for st in states:
            for sym in range(2):
                if (st, sym) not in tab:
                    if st not in halting:
                        halting.add(st); changed = True; break
                else:
                    nxt = tab[(st, sym)]
                    if nxt in halting:
                        if st not in halting:
                            halting.add(st); changed = True; break
    # non-halting states
    non = [s for s in states if s not in halting]
    # reverse determinize: DFA whose states are sets of original states; from set S, on symbol x
    # the predecessors under x are those states p with tab[(p,x)] in S
    pred = {s: [] for s in states}
    for p in states:
        for x in range(2):
            if (p, x) in tab:
                pred[tab[(p, x)]].append((p, x))
    start_set = frozenset(non)
    dfa = {}
    canon = {}
    q = deque([start_set])
    canon[start_set] = 0
    while q:
        S = q.popleft()
        for x in range(2):
            T = frozenset(p for (p, xx) in pred_flat(pred, S, x))
            if T and T not in canon:
                canon[T] = len(canon)
                q.append(T)
            dfa[(canon[S], x)] = canon.get(T)
    return dfa, canon, start_set, halting

def pred_flat(pred, S, x):
    out = []
    for s in S:
        for (p, xx) in pred.get(s, []):
            if xx == x:
                out.append(p)
    return out

def fixpoint(tab, n_states, n_symbols):
    # closed context set: list of (l, q, s, r)
    contexts = set()
    contexts.add((0, 0, 0, 0))
    frontier = deque([(0, 0, 0, 0)])
    while frontier:
        l, q, s, r = frontier.popleft()
        tr = tab.get((q, s))
        if tr is None:
            return None  # halting context would be in closure
        w, mv, q2 = tr
        if mv == 1:  # right move
            l2 = None
            # need left[l][w]
            if (l, w) in tab:
                l2 = tab[(l, w)]
            if l2 is None:
                return None
            for (r2, s2) in tab:
                if tab.get((r2, s2)) == r and (r2, s2) in tab:
                    # right[r2][s2] == r
                    c = (l2, q2, s2, r2)
                    if c not in contexts:
                        contexts.add(c); frontier.append(c)
        else:
            r2 = None
            if (r, w) in tab:
                r2 = tab[(r, w)]
            if r2 is None:
                return None
            for (l2, s2) in tab:
                if tab.get((l2, s2)) == l and (l2, s2) in tab:
                    c = (l2, q2, s2, r2)
                    if c not in contexts:
                        contexts.add(c); frontier.append(c)
    # check for halting context
    for c in contexts:
        if (c[1], c[2]) not in tab:
            return None
    return contexts

def decide(tm):
    tab, n_states, n_symbols = build(tm)
    # Try small left automata
    for size in range(1, NS + 1):
        for lt in bfs_tables(min(size, 4), 2):
            # reverse-determinize complement of halting language of lt
            rtab, canon, start_set, halting = reverse_complement_dfa(lt)
            # normalize rtab states to 0..len-1
            # left automaton state 0 must be blank loop on 0
            # skip if left[0][0] != 0
            if lt.get((0, 0)) != 0:
                continue
            if rtab.get((0, 0)) != 0:
                continue
            ctx = fixpoint(tab, n_states, n_symbols, lt, rtab)
            if ctx is not None:
                # build certificate
                left = []
                right = []
                maxl = max([s for (s, _) in lt] + [t for t in lt.values()] + [0]) + 1
                maxr = max([s for (s, _) in rtab] + [t for t in rtab.values()] + [0]) + 1
                for i in range(maxl):
                    row = [None, None]
                    for x in range(2):
                        row[x] = lt.get((i, x))
                    left.append(row)
                for i in range(maxr):
                    row = [None, None]
                    for x in range(2):
                        row[x] = rtab.get((i, x))
                    right.append(row)
                contexts = []
                for (l, q, s, r) in ctx:
                    contexts.append([l, q, s, r])
                cert = {"kind": "cps", "left": left, "right": right, "contexts": contexts}
                try:
                    from neverhalt.kernel import check
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
    return None

def decide(tm):
    tab, n_states, n_symbols = build(tm)
    for size in range(1, NS + 1):
        for lt in bfs_tables(min(size, 4), 2):
            if lt.get((0, 0)) != 0:
                continue
            rtab, canon, start_set, halting = reverse_complement_dfa(lt)
            if rtab.get((0, 0)) != 0:
                continue
            ctx = fixpoint(tab, n_states, n_symbols, lt, rtab)
            if ctx is not None:
                left = []
                right = []
                maxl = max([s for (s, _) in lt] + [t for t in lt.values()] + [0]) + 1
                maxr = max([s for (s, _) in rtab] + [t for t in rtab.values()] + [0]) + 1
                for i in range(maxl):
                    left.append([lt.get((i, 0)), lt.get((i, 1))])
                for i in range(maxr):
                    right.append([rtab.get((i, 0)), rtab.get((i, 1))])
                contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
                cert = {"kind": "cps", "left": left, "right": right, "contexts": contexts}
                try:
                    from neverhalt.kernel import check
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
    return None

if __name__ == "__main__":
    tm = sys.argv[1] if len(sys.argv) > 1 else "0RB1RC_1LC0LA_1RD1LC_---1RB"
    c = decide(tm)
    print(c is not None, len(c["contexts"]) if c else 0)