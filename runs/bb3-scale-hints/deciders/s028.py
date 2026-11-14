from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def decide(tm):
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    # Try to emit a cycle/tcycle certificate first (cheap, sometimes enough).
    try:
        cert = _try_cycle(tm)
        if cert:
            return cert
    except Exception:
        pass
    try:
        return _try_cps_search(tm)
    except Exception:
        return None


def _try_cycle(tm):
    # Simulate a bounded number of steps; look for a translated cycle.
    try:
        halted, steps, state, pos, tape = run(tm, 4000)
    except Exception:
        return None
    if halted:
        return None
    # Re-simulate capturing full history of (state, pos, tape snapshot around window).
    hist = []
    st, p, tp = state, pos, dict(tape)
    # We cannot easily reconstruct history from run(), so re-simulate manually.
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    states = ns
    hist = []
    cur_state, cur_pos = 0, 0
    tp = {}
    for _ in range(4000):
        s = table.get((cur_state, tp.get(cur_pos, 0)))
        if s is None:
            break
        w, mv, nx = s
        if tp.get(cur_pos, 0) != w:
            tp[cur_pos] = w
        else:
            tp.pop(cur_pos, None)
        cur_state = nx
        cur_pos += mv
        hist.append((cur_state, cur_pos, dict(tp)))
        if len(hist) >= 4000:
            break
    n = len(hist)
    # Look for repeated (state, pos) with matching tape in a window.
    seen = {}
    for i in range(n):
        sti, pi, _ = hist[i]
        key = (sti, pi)
        if key in seen:
            j = seen[key]
            d = pi - hist[j][1]
            # Check translated-cycle condition.
            t = j
            p = i - j
            if t + p > 100000:
                return None
            try:
                cert = {"kind": "cycle", "t": t, "p": p}
                check(tm, cert)
                return cert
            except Reject:
                pass
        seen[key] = i
    return None


def _try_cps_search(tm):
    table, ns, nsym = parse(tm)
    # halting transitions: (state, symbol) not in table
    # Build backward set of (state, symbol) that can reach a halt.
    # We will search automata for the left half-tape (states 0..k-1), with state 0 = blank loop.
    # For each candidate automaton A_left, compute the set of contexts that must be closed.
    # If closure has no halting context, we need the right automaton to witness the certificate.
    # Simplification: search for a left DFA, then pick right DFA as the same search over the mirror
    # but we only need ONE pair with a closed context set.
    # We'll do a bounded search over left DFAs with 1..3 states and right DFAs 1..3 states.

    def build_automaton(nstates):
        # enumerate all transition tables: for each state, for symbols 0 and 1, a target in 0..nstates-1
        # state 0 must have trans[0][0] = 0 (blank loop).
        # Represent as list: trans[state][sym] = next state
        tables = []
        # generate all assignments for nstates*2 transitions, with trans[0][0]=0 fixed.
        import itertools
        fixed = 0
        # We'll enumerate all tuples of length nstates*2 for symbols (0,1) per state.
        choices = []
        for st in range(nstates):
            for sym in range(2):
                if st == 0 and sym == 0:
                    choices.append([0])
                else:
                    choices.append(list(range(nstates)))
        for combo in itertools.product(*choices):
            trans = [[0]*2 for _ in range(nstates)]
            idx = 0
            for st in range(nstates):
                for sym in range(2):
                    trans[st][sym] = combo[idx]
                    idx += 1
            tables.append(trans)
        return tables

    for nl in range(1, 4):
        left_tables = build_automaton(nl)
        for nr in range(1, 4):
            right_tables = build_automaton(nr)
            for L in left_tables:
                for R in right_tables:
                    # Build contexts and close.
                    contexts = set()
                    contexts.add((0, 0, 0, 0))  # l=0, q=0, s=0, r=0
                    changed = True
                    while changed:
                        changed = False
                        new = set()
                        for (l, q, s, r) in contexts:
                            tr = table.get((q, s))
                            if tr is None:
                                # halting context -> reject this pair
                                break
                            w, mv, q2 = tr
                            if mv == 1:  # right move
                                l2 = L[l][w]
                                if l2 is None:
                                    break
                                # for every (r2, s2) with R[r2][s2] == r
                                for r2 in range(nr):
                                    for s2 in range(2):
                                        if R[r2][s2] == r:
                                            ctx = (l2, q2, s2, r2)
                                            if ctx not in contexts:
                                                new.add(ctx)
                                            else:
                                                contexts.add(ctx)
                            else:  # left move
                                r2 = R[r][w]
                                if r2 is None:
                                    break
                                for l2 in range(nl):
                                    for s2 in range(2):
                                        if L[l2][s2] == l:
                                            ctx = (l2, q2, s2, r2)
                                            if ctx not in contexts:
                                                new.add(ctx)
                                            else:
                                                contexts.add(ctx)
                        if new:
                            contexts.update(new)
                            changed = True
                    else:
                        # closure succeeded without halting context
                        # Emit certificate.
                        contexts_list = [list(c) for c in contexts]
                        cert = {
                            "kind": "cps",
                            "left": L,
                            "right": R,
                            "contexts": contexts_list,
                        }
                        try:
                            check(tm, cert)
                            return cert
                        except Reject:
                            pass
        # next nl
    return None
}'}