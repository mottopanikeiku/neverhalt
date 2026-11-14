import itertools, json
from neverhalt.tm import parse
from neverhalt.helpers import closure

# --- small helpers ---------------------------------------------------------

def transitions(tm):
    tbl, ns, nsym = parse(tm)
    out = {}
    for q in range(ns):
        for s in range(nsym):
            out[(q, s)] = tbl.get((q, s))
    return out, ns, nsym

def pushers_for(tm):
    """Candidate push functions for the two half-tape automata.

    The half-tape automaton reads cells of one half-tape from far away
    towards the head.  push(state, symbol) tells us the state after the
    half-tape grew by one cell next to the head (the newly written cell).
    We enumerate small deterministic automata as transition tables
    delta[state][symbol] = next_state, with state 0 looping on 0 (all
    blank half-tape must stay in state 0).  Some cells simply never occur
    in that half-tape, so 'no transition' is allowed too.
    """
    tbl, ns, nsym = parse(tm)
    syms = [s for s in range(nsym)]
    cands = []
    # sizes 1..3 states per side; state 0 must loop on symbol 0
    for n in (1, 2, 3):
        for combo in itertools.product(range(n), repeat=(n * len(syms))):
            # build delta
            delta = {}
            ok = True
            for st in range(n):
                for si, s in enumerate(syms):
                    delta[(st, s)] = combo[st * len(syms) + si]
            if delta[(0, 0)] != 0:
                continue
            # push function: state -> state, but 'no transition' means we
            # cannot extend the half-tape that way.  closure() wants a
            # function, so we model that as a distinct terminal state.
            NULL = ('null',)
            def mk(delta, n, NULL):
                def push(state, symbol):
                    if state is NULL:
                        return NULL
                    v = delta.get((state, symbol))
                    return NULL if v is None else v
                return push
            cands.append(mk(delta, n, NULL))
    return cands, ns, nsym

def try_pair(tm, pl, pr, cap=200000):
    """closure expects blank_left/blank_right as states with push(blank,0)==blank."""
    return closure(pl, pr, cap=cap)

def decide(tm):
    if not isinstance(tm, str):
        return None
    tbl, ns, nsym = parse(tm)

    # Fast reject: if the machine has any state that cannot reach a halt,
    # the decider will fail anyway; just try anyway.

    pl_cands, ns, nsym = pushers_for(tm)
    pr_cands, ns, nsym = pushers_for(tm)

    # both sides share the same candidate set; try all pairs smallest first.
    # To keep the search inside the time budget we order by (size_l, size_r).
    def size_of(push):
        # count reachable states by probing
        seen = set()
        stack = [push(0, 0)]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            for s in range(nsym):
                y = push(x, s)
                if y not in seen:
                    stack.append(y)
        return len(seen)

    ordered = sorted(pl_cands, key=size_of)
    for pl in ordered:
        for pr in ordered:
            try:
                cert = try_pair(tm, pl, pr)
            except Exception:
                cert = None
            if cert is not None:
                # validate before returning (the kernel is the real judge)
                from neverhalt.kernel import check, Reject
                try:
                    check(tm, cert)
                except Reject:
                    continue
                except Exception:
                    continue
                return cert
    return None
