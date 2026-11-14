import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: "dense-segment CPS"
# Idea: many surviving holdouts are machines whose tape keeps growing on both sides
# while the head walks monotonically.  We build a CPS certificate with a *dense*
# left automaton (it remembers the last few cells to the left of the head) and a
# matching dense right automaton, but we only demand that the certificate be closed
# over contexts reachable from the initial blank context.  We iterate: start from
# [(0,0,0,0)], expand under the transition rules, and stop when the context set is
# closed.  If closure succeeds the kernel accepts it; otherwise we return None.

MAX_CTX = 200000
MAX_STATES = 5000
MAX_LAP = 100000

def _dense_automaton(table, n_states, n_symbols, depth):
    # Build an automaton that remembers the last `depth` symbols read (far to near).
    # State = tuple of the last up to `depth` symbols, encoded as an integer.
    # left[0][0] must be 0.
    # We return (trans, n_states) where trans is a list indexed by state.
    # Encoding: state 0 = all-blank empty history.  Otherwise, encode the history
    # (oldest..newest) as base-n_symbols integer, shifted by 1.
    def enc(hist):
        v = 0
        for x in hist:
            v = v * n_symbols + x
        return v + 1
    trans = [[None, None] for _ in range(MAX_STATES)]
    # state 0 = empty history
    trans[0][0] = 0
    # For a non-empty history we would need to enumerate; instead we lazily create
    # states on demand.  Return a factory closure.
    store = {}
    def step(state, sym):
        if state == 0:
            if sym == 0:
                return 0
            key = (state, sym)
            ns = enc([sym])
            if ns >= MAX_STATES:
                raise ValueError
            store[(ns, sym)] = ns
            return ns
        key = (state, sym)
        if key in store:
            return store[key]
        hist = decode(state, depth, n_symbols)
        newhist = (hist + [sym])[-depth:]
        ns = enc(newhist)
        if ns >= MAX_STATES:
            raise ValueError
        store[key] = ns
        return ns
    return step, store

def decode(state, depth, n_symbols):
    if state == 0:
        return []
    v = state - 1
    out = []
    for _ in range(depth):
        out.append(v % n_symbols)
        v //= n_symbols
    out.reverse()
    return out

def _closed_cps(tm, depth):
    table, n_states, n_symbols = parse(tm)
    left_step, _ = _dense_automaton(table, n_states, n_symbols, depth)
    right_step, _ = _dense_automaton(table, n_states, n_symbols, depth)
    # We cannot know the state count in advance; build lazily with a dict.
    # Rebuild with dynamic state allocation.
    left = {}
    right = {}
    left[0] = [0, None]
    right[0] = [0, None]
    def lstep(s, x):
        if s in left and left[s][x] is not None:
            return left[s][x]
        # allocate
        ns = len(left)
        left[s][x] = ns
        left[ns] = [None, None]
        return ns
    def rstep(s, x):
        if s in right and right[s][x] is not None:
            return right[s][x]
        ns = len(right)
        right[s][x] = ns
        right[ns] = [None, None]
        return ns
    # We need left[0][0] == right[0][0] == 0 (satisfied).
    # Build the context closure.
    ctx = set()
    ctx.add((0, 0, 0, 0))
    changed = True
    while changed:
        changed = False
        for (l, q, s, r) in list(ctx):
            if len(ctx) > MAX_CTX:
                return None
            # transition must exist
            key = (q, s)
            if key not in table:
                return None
            w, move, q2 = table[key]
            if move > 0:
                # right move: l2 = left[l][w]; context for every (r2, s2) with right[r2][s2] == r
                l2 = left.get(l, [None, None])[w]
                if l2 is None:
                    # allocate
                    if l not in left:
                        left[l] = [None, None]
                    left[l][w] = l2 = len(left)
                    left[l2] = [None, None]
                # find all (r2, s2) with right[r2][s2] == r
                pairs = []
                for r2 in list(right.keys()):
                    row = right.get(r2, [None, None])
                    for s2 in range(n_symbols):
                        if row[s2] == r:
                            pairs.append((r2, s2))
                for (r2, s2) in pairs:
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        ctx.add(c)
                        changed = True
            else:
                # left move: r2 = right[r][w]; context for every (l2, s2) with left[l2][s2] == l
                r2 = right.get(r, [None, None])[w]
                if r2 is None:
                    if r not in right:
                        right[r] = [None, None]
                    right[r][w] = r2 = len(right)
                    right[r2] = [None, None]
                pairs = []
                for l2 in list(left.keys()):
                    row = left.get(l2, [None, None])
                    for s2 in range(n_symbols):
                        if row[s2] == l:
                            pairs.append((l2, s2))
                for (l2, s2) in pairs:
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        ctx.add(c)
                        changed = True
    # Build certificate
    left_list = []
    for i in range(len(left)):
        row = left.get(i, [None, None])
        left_list.append([row[0], row[1]])
    right_list = []
    for i in range(len(right)):
        row = right.get(i, [None, None])
        right_list.append([row[0], row[1]])
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    cert = {"kind": "cps", "left": left_list, "right": right_list, "contexts": contexts}
    return cert

def decide(tm: str):
    for depth in (1, 2, 3, 4, 6, 8, 12):
        try:
            cert = _closed_cps(tm, depth)
        except Exception:
            cert = None
        if cert is not None:
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
    return None
