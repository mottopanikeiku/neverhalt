import time
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

LIMIT_MS = 500

def _tables(k):
    # enumerate deterministic automata with k states; state 0 loops on 0
    # left[i][x]: next state or None; we enumerate as tuples of length k*2
    out = []
    import itertools
    choices = [0, 1, None]
    for tup in itertools.product(choices, repeat=k * 2):
        t = [[None, None] for _ in range(k)]
        ok = True
        for i in range(k):
            for x in range(2):
                t[i][x] = tup[i * 2 + x]
        # state 0 loops on 0
        if t[0][0] != 0:
            continue
        out.append(t)
    return out

def _closure(left, right, n_states, n_syms):
    # contexts: set of (l, q, s, r)
    ctx = set()
    ctx.add((0, 0, 0, 0))
    changed = True
    while changed:
        changed = False
        for (l, q, s, r) in list(ctx):
            if (q, s) not in table:
                return None
            w, mv, q2 = table[(q, s)]
            if mv == 1:
                l2 = left[l][w]
                if l2 is None:
                    return None
                for (r2, s2) in right_pairs(right):
                    if r2 is None:
                        continue
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        ctx.add(c)
                        changed = True
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                for (l2, s2) in left_pairs(left):
                    if l2 is None:
                        continue
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        ctx.add(c)
                        changed = True
    return ctx

def _pairs(tab):
    out = []
    for i in range(len(tab)):
        for x in range(2):
            v = tab[i][x]
            if v is not None:
                out.append((v, x))
    return out

def _pairs_all(tab):
    return [(i, x, tab[i][x]) for i in range(len(tab)) for x in range(2)]

def decide(tm):
    t0 = time.time()
    deadline = t0 + LIMIT_MS / 1000.0 - 0.05
    try:
        table, n_states, n_syms = parse(tm)
    except Exception:
        return None
    if (0, 0) not in table:
        # trivial: halts immediately? then we cannot prove non-halting
        return None
    # first: try a plain window cycle quickly (cheap)
    try:
        cert = _try_cycle(table, n_states)
        if cert is not None:
            return cert
    except Exception:
        pass
    ks = [1, 2, 3]
    for k in ks:
        if time.time() > deadline:
            return None
        tabs = _tables(k)
        # dedupe by tuple
        seen = set()
        uniq = []
        for t in tabs:
            key = tuple(x for row in t for x in row)
            if key not in seen:
                seen.add(key)
                uniq.append(t)
        for L in uniq:
            if time.time() > deadline:
                return None
            # left pairs for this L
            for R in uniq:
                if time.time() > deadline:
                    return None
                left_pairs = _pairs(L)
                right_pairs = _pairs(R)
                # quick reject: left[0][0] must be 0
                if L[0][0] != 0 or R[0][0] != 0:
                    continue
                # compute closure with early abort on halting
                ctx = {(0, 0, 0, 0)}
                stack = [(0, 0, 0, 0)]
                ok = True
                while stack:
                    l, q, s, r = stack.pop()
                    if (q, s) not in table:
                        ok = False
                        break
                    w, mv, q2 = table[(q, s)]
                    if mv == 1:
                        l2 = L[l][w]
                        if l2 is None:
                            ok = False
                            break
                        for (r2, s2) in right_pairs:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                stack.append(c)
                    else:
                        r2 = R[r][w]
                        if r2 is None:
                            ok = False
                            break
                        for (l2, s2) in left_pairs:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                stack.append(c)
                if not ok:
                    continue
                # check size limits
                if len(ctx) > 200000:
                    continue
                # ensure no halting context: all (q,s) in table by construction
                # build certificate
                left_t = [[L[i][x] for x in range(2)] for i in range(len(L))]
                right_t = [[R[i][x] for x in range(2)] for i in range(len(R))]
                contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
                cert = {"kind": "cps", "left": left_t, "right": right_t, "contexts": contexts}
                # validate locally
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
                except Exception:
                    continue
    return None

def _try_cycle(table, n_states):
    # cheap plain cycle search: simulate up to 400 steps and look for a state+position repeat
    # with identical tape window (small)
    from neverhalt.tm import run
    for maxs in (100, 200, 300, 400):
        try:
            halted, steps, state, pos, tape = run(tm, maxs)
        except Exception:
            return None
        if halted:
            return None
        # need a repeat of (state,pos) with same tape content in a window
        # collect history
        # (re-simulate to get history; small cost)
        try:
            halted, steps, state, pos, tape = run(tm, maxs)
        except Exception:
            return None
        # re-run capturing history
        try:
            hist = []
            from neverhalt.tm import parse as _p
            tab, ns, nsm = _p(tm)
            tape = {}
            st = 0
            p = 0
            for i in range(maxs):
                if (st, tape.get(p, 0)) not in tab:
                    return None
                w, mv, q2 = tab[(st, tape.get(p, 0))]
                tape[p] = w
                p += mv
                st = q2
                hist.append((st, p, dict(tape)))
        except Exception:
            return None
        for i in range(len(hist)):
            for j in range(i + 1, len(hist)):
                si, pi, ti = hist[i]
                sj, pj, tj = hist[j]
                if si == sj and pi == pj and ti == tj:
                    return {"kind": "cycle", "t": i + 1, "p": j - i}
    return None

# guard against missing import of table variable inside decide
def _decide_guarded(tm):
    global table
    return decide(tm)

# expose decide
def _setup():
    pass

# The module-level `table` used above is a bug; rewrite decide cleanly:
def decide2(tm):
    t0 = time.time()
    deadline = t0 + LIMIT_MS / 1000.0 - 0.05
    try:
        table, n_states, n_syms = parse(tm)
    except Exception:
        return None
    # quick cycle attempt
    try:
        cert = _try_cycle(table, n_states)
        if cert is not None:
            return cert
    except Exception:
        pass
    ks = [1, 2, 3]
    for k in ks:
        if time.time() > deadline:
            return None
        # generate unique tables for this k
        import itertools
        seen = set()
        uniq = []
        choices = [0, 1, None]
        for tup in itertools.product(choices, repeat=k * 2):
            if tup[0] != 0:
                continue
            t = [[tup[i * 2 + x] for x in range(2)] for i in range(k)]
            key = tuple(x for row in t for x in row)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(t)
        for L in uniq:
            if time.time() > deadline:
                return None
            lp = _pairs(L)
            for R in uniq:
                if time.time() > deadline:
                    return None
                if R[0][0] != 0:
                    continue
                rp = _pairs(R)
                ctx = {(0, 0, 0, 0)}
                stack = [(0, 0, 0, 0)]
                ok = True
                while stack:
                    l, q, s, r = stack.pop()
                    if (q, s) not in table:
                        ok = False
                        break
                    w, mv, q2 = table[(q, s)]
                    if mv == 1:
                        l2 = L[l][w]
                        if l2 is None:
                            ok = False
                            break
                        for (r2, s2) in rp:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                stack.append(c)
                    else:
                        r2 = R[r][w]
                        if r2 is None:
                            ok = False
                            break
                        for (l2, s2) in lp:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                stack.append(c)
                if not ok or len(ctx) > 200000:
                    continue
                left_t = [[L[i][x] for x in range(2)] for i in range(len(L))]
                right_t = [[R[i][x] for x in range(2)] for i in range(len(R))]
                contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
                cert = {"kind": "cps", "left": left_t, "right": right_t, "contexts": contexts}
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
                except Exception:
                    continue
    return None

# final: alias decide to the clean version
decide = decide2
