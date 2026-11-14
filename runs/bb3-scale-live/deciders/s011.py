import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import Reject

sys.setrecursionlimit(10000)


def _run_guarded(tm, limit):
    return run(tm, limit)


def _get_trans(tm, state, sym):
    try:
        return parse(tm)[0][(state, sym)]
    except KeyError:
        return None


def _search_cycle(tm, max_steps=100000):
    """Try to find a translated or plain cycle certificate.

    Returns a certificate dict, or None.
    """
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None

    # Run and record full configuration (state, pos, tape snapshot) for a
    # bounded number of steps, then look for a repeated configuration.
    limit = min(max_steps, 100000)
    try:
        ok = [None]

        def simulate(steps):
            # We re-simulate with recording using the run helper is not
            # sufficient for snapshot matching; implement a lightweight
            # deterministic simulation that records (state, pos, tape dict).
            tape = {}
            pos = 0
            st = 0
            snaps = {}
            for t in range(steps + 1):
                key = (st, pos, tuple(sorted(tape.items())))
                if key in snaps:
                    return snaps[key], t, st, pos, tape
                snaps[key] = t
                tr = table.get((st, tape.get(pos, 0)))
                if tr is None:
                    return None, t, st, pos, tape
                w, mv, nxt = tr
                if w != 0:
                    tape[pos] = w
                elif w == 0:
                    tape.pop(pos, None)
                pos += mv
                st = nxt
            return None, steps, st, pos, tape

        prev_t, T, stT, posT, tapeT = simulate(limit)
        if prev_t is None:
            return None

        # Found a repeated configuration at time T with previous occurrence
        # at time prev_t.  The lap is [prev_t, T].
        # Re-simulate to capture the tape at prev_t and at T, plus the
        # head positions seen during the lap.
        P = T - prev_t
        if T + P > 100000:
            return None

        # Re-run to record head positions and final tapes.
        def record(steps):
            tape = {}
            pos = 0
            st = 0
            positions = []
            for t in range(steps + 1):
                positions.append(pos)
                if t == steps:
                    break
                tr = table.get((st, tape.get(pos, 0)))
                if tr is None:
                    break
                w, mv, nxt = tr
                if w != 0:
                    tape[pos] = w
                elif w == 0:
                    tape.pop(pos, None)
                pos += mv
                st = nxt
            return tape, positions

        tape_prev, positions_prev = record(prev_t)
        tape_T, positions_T = record(T)

        if tape_prev != tape_T:
            # plain repeat of tape not guaranteed; fall back to cycle check
            # with kernel's own verification path below.
            return None

        # For a true cycle certificate we need state and tape to repeat.
        # Here the full configuration repeated, so d = 0.
        d = 0
        lo = min(positions_prev[prev_t:]) if prev_t < T else 0
        hi = max(positions_prev[prev_t:]) if prev_t < T else 0
        cert = {"kind": "cycle", "t": T, "p": P}
        return cert

    except Exception:
        return None


def _search_cps_ngram(tm, n=3):
    """n-gram context-sensitive proof search, small n.

    Builds left and right automata remembering the last n cells on each
    side, then closes the set of contexts starting from [0,0,0,0].
    """
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None

    # left automaton: reads cells left of head from far away towards head.
    # state = last n cells seen (as a tuple, padded with 0 at the far end)
    # left[i][x] -> next state after reading x, or None.
    # We index states by integer ids.

    def build_automata(n):
        left = []
        right = []

        def encode(cells):
            # cells: tuple of length n, oldest first (far away first)
            return cells

        def extend(cells, x, side):
            # side=0: left side, new cell x is closer to head (appended at end)
            # side=1: right side, same convention from far away towards head
            if len(cells) < n:
                newc = cells + (x,)
            else:
                newc = cells[1:] + (x,)
            return newc

        # Build reachable states lazily.
        def get_id(cells, table_, base):
            if cells not in table_:
                table_[cells] = len(table_) + base
            return table_[cells]

        lmap = {}
        rmap = {}
        lid = {}
        rid = {}

        def left_step(cid, x):
            cells = lmap[cid]
            newc = extend(cells, x, 0)
            if newc not in lid:
                lid[newc] = len(lmap) + 1
                lmap[lid[newc]] = newc
            return lid[newc]

        def right_step(cid, x):
            cells = rmap[cid]
            newc = extend(cells, x, 1)
            if newc not in rid:
                rid[newc] = len(rmap) + 1
                rmap[rid[newc]] = newc
            return rid[newc]

        # We'll represent automaton transition tables as lists of lists.
        # State 0 = all blank: cells = (0,)*n.
        blank = tuple([0] * n)
        lmap[0] = blank
        rmap[0] = blank
        # Ensure id 0 maps to blank.
        lid[blank] = 0
        rid[blank] = 0

        def ensure_left(cid):
            return cid

        # We'll build tables on the fly during closure.
        return lmap, rmap, lid, rid

    lmap, rmap, lid, rid = build_automata(n)

    # Context representation: (l, q, s, r)
    contexts = set()
    contexts.add((0, 0, 0, 0))
    frontier = [(0, 0, 0, 0)]

    # Helper to get left automaton transitions.
    def left_trans(cid, x):
        cells = lmap[cid]
        newc = cells[1:] + (x,)
        if newc in lid:
            return lid[newc]
        lid[newc] = len(lmap)
        lmap[lid[newc]] = newc
        return lid[newc]

    def right_trans(cid, x):
        cells = rmap[cid]
        newc = cells[1:] + (x,)
        if newc in rid:
            return rid[newc]
        rid[newc] = len(rmap)
        rmap[rid[newc]] = newc
        return rid[newc]

    # We need actual transition tables for the kernel.
    # Build them after closure using the maps.
    left_tab = None
    right_tab = None

    processed = 0
    while frontier:
        ctx = frontier.pop()
        processed += 1
        if processed > 200000:
            return None
        l, q, s, r = ctx
        tr = table.get((q, s))
        if tr is None:
            return None  # halting context found
        w, mv, q2 = tr

        if mv == 1:
            # right move: l2 = left[l][w]
            l2 = left_trans(l, w)
            # For every (r2, s2) with right[r2][s2] == r, need context (l2, q2, s2, r2)
            # We must enumerate all pairs.  Since automata are n-gram, enumerate
            # all states r2 in rmap and check if reading s2 leads to r.
            # To be exhaustive, for each r2 and each s2 in symbols, check.
            for r2 in list(rmap.keys()):
                cells = rmap[r2]
                for s2 in (0, 1):
                    newc = cells[1:] + (s2,)
                    # Is r the state reached from r2 reading s2?
                    # We need right[r2][s2] == r, i.e. the transition from r2
                    # on s2 yields state r.  That means newc corresponds to r.
                    if newc in rid and rid[newc] == r:
                        nctx = (l2, q2, s2, r2)
                        if nctx not in contexts:
                            contexts.add(nctx)
                            frontier.append(nctx)
        else:
            r2 = right_trans(r, w)
            for l2 in list(lmap.keys()):
                cells = lmap[l2]
                for s2 in (0, 1):
                    newc = cells[1:] + (s2,)
                    if newc in lid and lid[newc] == l:
                        nctx = (l2, q2, s2, r2)
                        if nctx not in contexts:
                            contexts.add(nctx)
                            frontier.append(nctx)

    if not contexts:
        return None

    # Build automaton transition tables.
    def build_table(m):
        size = max(m.values()) + 1 if m else 1
        tab = [[None, None] for _ in range(size)]
        for cid, cells in m.items():
            for x in (0, 1):
                newc = cells[1:] + (x,)
                if newc in m:
                    tab[cid][x] = m[newc]
        return tab

    # Ensure state 0 maps to blank.
    left_tab = build_table(lmap)
    right_tab = build_table(rmap)

    # Ensure left_tab[0][0] == 0 and right_tab[0][0] == 0
    # (blank state on blank cell stays blank)
    if left_tab[0][0] != 0 or right_tab[0][0] != 0:
        return None

    ctx_list = [[list(c) for c in ctx] for ctx in contexts]
    cert = {
        "kind": "cps",
        "left": left_tab,
        "right": right_tab,
        "contexts": ctx_list,
    }
    return cert


def decide(tm: str):
    # First try a quick cycle search (helps with machines that loop simply).
    try:
        cert = _search_cycle(tm, 20000)
        if cert is not None:
            from neverhalt.kernel import check
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
    except Exception:
        pass

    # Then try n-gram CPS with increasing n.
    for n in (1, 2, 3, 4):
        try:
            cert = _search_cps_ngram(tm, n)
            if cert is not None:
                from neverhalt.kernel import check
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
        except Exception:
            continue
    return None