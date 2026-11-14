from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

import heapq
import json

# We build a CPS certificate by searching for a pair of half-tape DFAs
# (left / right readings towards the head).  The search is:
#   * enumerate small right DFAs in canonical BFS order (language-based),
#   * for each surviving one compute its reverse-determinisation as the
#     left half-tape DFA,
#   * run the closed-context fixpoint to build the context set,
#   * accept when the closure contains no halting context.
# Halting contexts are generated directly from the machine's halting
# transitions, which prunes the search aggressively.


def _canonical_dfa_size(n_states, table):
    # BFS canonical order: from state 0, explore transitions in
    # (symbol, state) order; assign canonical ids.  Rows not reachable
    # from 0 are dropped.  We build a fresh canonical table.
    # table: list of rows, row[sym] = next state or None
    order = []
    seen = set([0])
    q = [0]
    while q:
        st = q.pop(0)
        order.append(st)
        row = table[st] if st < len(table) else None
        if row is None:
            continue
        for sym in range(2):
            nx = row[sym]
            if nx is not None and nx not in seen:
                seen.add(nx)
                q.append(nx)
    if len(order) != len(set(order)):
        return None
    remap = {}
    for i, st in enumerate(order):
        remap[st] = i
    newtab = []
    for st in order:
        old = table[st] if st < len(table) else None
        row = []
        if old is None:
            row = [None, None]
        else:
            row = [remap.get(old[0]), remap.get(old[1])]
        newtab.append(row)
    return newtab


def _normalise_dfa(table):
    table = _canonical_dfa_size(len(table), table)
    if table is None:
        return None
    return table


def _dfa_key(table):
    return json.dumps(table, separators=(',', ':'))


def _reverse_determinise(table):
    # Given a DFA reading far-to-head (i.e. a right half-tape automaton),
    # produce the mirror automaton used for the left half-tape: reverse
    # every transition and determinise.
    # Represent states by frozensets of subset states.
    n = len(table)
    # reverse adjacency
    rev = [[] for _ in range(n)]
    for a in range(n):
        for sym in range(2):
            b = table[a][sym]
            if b is not None:
                rev[b].append((sym, a))
    # start states: all states (the far end is blank, so start = {0})
    start = {0}
    seen = set([frozenset(start)])
    dq = [frozenset(start)]
    out = []
    idx = {}
    while dq:
        cur = dq.pop(0)
        if cur in idx:
            continue
        idx[cur] = len(out)
        out.append(sorted(cur))
        row = [None, None]
        for sym in range(2):
            nxt = set()
            for st in cur:
                for s2, p in rev[st]:
                    if s2 == sym:
                        nxt.add(p)
            if nxt:
                fs = frozenset(nxt)
                if fs not in idx:
                    dq.append(fs)
                row[sym] = idx.get(fs)
        # careful: row may reference a state not yet assigned; re-draw later
        # (we handle by re-scanning below)
    # rebuild table with final indices
    final = [None] * len(out)
    for i, cur in enumerate(out):
        row = [None, None]
        for sym in range(2):
            nxt = set()
            for st in cur:
                for s2, p in rev[st]:
                    if s2 == sym:
                        nxt.add(p)
            if nxt:
                fs = frozenset(nxt)
                # find index
                for j in range(len(out)):
                    if frozenset(out[j]) == fs:
                        row[sym] = j
                        break
        final[i] = row
    return final


def _contexts_closure(tm, table, n_states):
    # table: (n_states, 2) rows of next-state or None.
    # Returns (contexts, ok) where ok is False if a halting context
    # is forced.
    # context = (l, q, s, r)
    # We start from the blank context [0, 0, 0, 0].
    tab, nq, ns = parse(tm)
    # halting transitions: table entries missing in tab (or target absent)
    # parse() already excludes halting transitions.
    contexts = set()
    contexts.add((0, 0, 0, 0))
    # For each context, enumerate successors.
    # We need to know for the left automaton which (l2, s2) pairs map to l.
    # Build reverse maps.
    left_rev = {}  # l -> list of (l2, s2) with table[l2][s2] == l
    for l2 in range(n_states):
        for sym in range(2):
            l = table[l2][sym]
            if l is not None:
                left_rev.setdefault(l, []).append((l2, sym))
    # right automaton is the same machine reading from the other side
    # (we use the same table; contexts treat r as reading far-to-head).
    right_rev = left_rev
    frontier = [contexts.pop()]
    contexts.add((0, 0, 0, 0))
    frontier = [(0, 0, 0, 0)]
    while frontier:
        l, q, s, r = frontier.pop()
        if (l, q, s, r) in contexts:
            continue
        contexts.add((l, q, s, r))
        entry = tab.get((q, s))
        if entry is None:
            # halting context -> certificate impossible with this table
            return None, False
        w, move, q2 = entry
        if move == 1:
            # right move: l2 = table[l][w] must exist, and for every
            # (r2, s2) with right[r2][s2] == r the context (l2, q2, s2, r2)
            # must be present.
            l2 = table[l][w]
            if l2 is None:
                return None, False
            for (r2, s2) in right_rev.get(r, []):
                nxt = (l2, q2, s2, r2)
                if nxt not in contexts:
                    frontier.append(nxt)
        else:
            r2 = table[r][w]
            if r2 is None:
                return None, False
            for (l2, s2) in left_rev.get(l, []):
                nxt = (l2, q2, s2, r2)
                if nxt not in contexts:
                    frontier.append(nxt)
    return contexts, True


def _try_pair(tm, table):
    contexts, ok = _contexts_closure(tm, table, len(table))
    if not ok:
        return None
    # build certificate
    left = [[None if x is None else int(x) for x in row] for row in table]
    right = [[None if x is None else int(x) for x in row] for row in table]
    # verify state 0 loops on symbol 0
    if left[0][0] != 0 or right[0][0] != 0:
        return None
    ctx = [[int(l), int(q), int(s), int(r)] for (l, q, s, r) in contexts]
    cert = {"kind": "cps", "left": left, "right": right, "contexts": ctx}
    try:
        from neverhalt.kernel import check
        kind = check(tm, cert)
        if kind:
            return cert
    except Reject:
        pass
    except Exception:
        pass
    return None


def _enumerate_tables(max_states):
    # Enumerate DFA transition tables with n states, state 0 loops on 0.
    # Only reachable states matter; we enumerate all and canonicalise.
    # Yield canonical tables in increasing state count.
    for n in range(1, max_states + 1):
        # transitions: for each (state, sym) either None or a target state
        # To limit, require state 0 -> 0 on sym 0.
        # Enumerate via recursion but prune: only states reachable from 0.
        # We'll do iterative deepening by number of transitions present.
        # Since n <= 10, brute force over (n^2 + 2n) choices is too big;
        # instead enumerate canonical structures greedily.
        # Simpler: enumerate all functions from n states x 2 symbols to
        # {None} U [0,n) with 0->0 on sym0.  For n up to 4 this is 5^8
        # = 390625, for n=5 6^10 = 60M too big.  We cap enumeration at 4
        # and rely on the reverse-determinisation for larger half-tapes.
        if n > 4:
            break
        cells = n * 2
        # enumerate in lexicographic order of a compact encoding
        import itertools
        # values: 0..n-1 for states, n for None
        # state 0 sym 0 forced to 0
        total = (n + 1) ** (cells - 1)
        for enc in range(total):
            vals = []
            e = enc
            for i in range(cells - 1):
                vals.append(e % (n + 1))
                e //= (n + 1)
            flat = [0] + vals  # first cell (0,0) = 0
            table = []
            for st in range(n):
                row = []
                for sym in range(2):
                    v = flat[st * 2 + sym]
                    row.append(None if v == n else v)
                table.append(row)
            table = _normalise_dfa(table)
            if table is None:
                continue
            # skip duplicates via canonical key
            key = _dfa_key(table)
            if key in getattr(_enumerate_tables, "_seen", set()):
                continue
            _enumerate_tables._seen.add(key)
            yield table


def decide(tm: str):
    _enumerate_tables._seen = set()
    # First try small direct pairs (n-gram style) for cheap wins.
    for table in _enumerate_tables(4):
        cert = _try_pair(tm, table)
        if cert is not None:
            return cert
    # Then try reverse-determinised mirrors of surviving right tables.
    for table in _enumerate_tables(4):
        rev = _reverse_determinise(table)
        if rev is None:
            continue
        cert = _try_pair(tm, rev)
        if cert is not None:
            return cert
    return None
