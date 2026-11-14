import sys
from itertools import product
from collections import deque

# CPS decider via small-automaton search.

# ---- helpers -------------------------------------------------------------

def build_table(tm):
    """Return halt_set: (state, symbol) pairs that halt, plus a run helper."""
    # parse via the provided helper
    from neverhalt.tm import parse
    table, n_states, n_symbols = parse(tm)
    return table, n_states, n_symbols


def step(tm, state, symbol):
    """Return (write, move, next_state) or ('HALT',) if the transition halts."""
    table, n_states, n_symbols = tm
    key = (state, symbol)
    tr = table.get(key)
    if tr is None:
        return ('HALT',)
    return tr  # (write, move, next_state)


def one_step_context(tm, ctx):
    """
    ctx = (l, q, s, r).  Return list of successor contexts (as tuples) that
    the machine could reach in one step, or None if it halts.
    """
    table, n_states, n_symbols = tm
    l, q, s, r = ctx
    tr = table.get((q, s))
    if tr is None:
        return None
    w, move, q2 = tr
    succ = []
    if move == +1:
        # head moves right: written symbol w is pushed onto the left tape
        l2 = LEFT_AUTO[l].get(w) if LEFT_AUTO else None
        if l2 is None:
            return []
        # pop the nearest cell s2 from the right tape; its remainder state r2
        # must satisfy right[r2][s2] == r
        for r2, s2 in RIGHT_POP_R.get(r, ()):
            succ.append((l2, q2, s2, r2))
    else:
        # head moves left: mirror
        r2 = RIGHT_AUTO[r].get(w)
        if r2 is None:
            return []
        for l2, s2 in LEFT_POP_R.get(r, ()):
            # careful: for a left move the popped cell comes off the left
            # tape; remainder state l2 must satisfy left[l2][s2] == l
            for l3, s3 in LEFT_POP_R.get(l, ()):
                succ.append((l3, q2, s3, r2))
    return succ


# globals filled per machine
LEFT_AUTO = {}
RIGHT_AUTO = {}
LEFT_POP_R = {}
RIGHT_POP_R = {}


# ---- DFA enumeration -----------------------------------------------------

def enumerate_dfa_states(max_states, alphabet):
    """Yield DFA transition tables as dicts: (state, sym) -> state or None."""
    for n in range(1, max_states + 1):
        # state 0 loops on symbol 0
        for body in product(range(n), repeat=2 * n):
            trans = {}
            trans[(0, 0)] = 0
            ok = True
            idx = 0
            for st in range(n):
                for sym in alphabet:
                    if st == 0 and sym == 0:
                        continue
                    trans[(st, sym)] = body[idx]
                    idx += 1
            yield trans


def complete_dfa(trans, n, alphabet):
    """Fill missing transitions with None (dead)."""
    for st in range(n):
        for sym in alphabet:
            trans.setdefault((st, sym), None)
    return trans


def dfa_accept_from(trans, start, target_states):
    """Simple reachability: can we reach any target state?"""
    seen = {start}
    stack = [start]
    while stack:
        st = stack.pop()
        for sym in (0, 1):
            nxt = trans.get((st, sym))
            if nxt is not None and nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return bool(seen & set(target_states))


# ---- fixpoint closure ----------------------------------------------------

def close_contexts(tm, left_auto, right_auto, max_ctx=200000):
    """
    Compute the smallest closed context set containing (0,0,0,0), given the
    two automata as tables (state, sym) -> state or None.
    Returns the set of contexts or None if a halting context is forced.
    """
    table, n_states, n_symbols = tm
    alphabet = (0, 1)

    # precompute pop relations: for each automaton state a and symbol s, the
    # set of (remainder_state, popped_symbol) such that
    # auto[remainder][popped] == a
    def pop_rel(auto):
        rel = {}
        n = max(k[0] for k in auto) + 1 if auto else 1
        for st in range(n):
            rel[st] = []
        for (st, sym), nxt in auto.items():
            if nxt is not None:
                rel[nxt].append((st, sym))
        return rel

    left_pop = pop_rel(left_auto)
    right_pop = pop_rel(right_auto)

    init = (0, 0, 0, 0)
    contexts = {init}
    frontier = deque([init])
    while frontier:
        l, q, s, r = frontier.popleft()
        tr = table.get((q, s))
        if tr is None:
            return None  # a halting context is in the set -> not a proof
        w, move, q2 = tr
        if move == +1:
            l2 = left_auto.get((l, w))
            if l2 is None:
                continue
            for r2, s2 in right_pop.get(r, ()):
                c = (l2, q2, s2, r2)
                if c not in contexts:
                    contexts.add(c)
                    frontier.append(c)
        else:
            r2 = right_auto.get((r, w))
            if r2 is None:
                continue
            for l2, s2 in left_pop.get(l, ()):
                c = (l2, q2, s2, r2)
                if c not in contexts:
                    contexts.add(c)
                    frontier.append(c)
        if len(contexts) > max_ctx:
            return None
    return contexts


def emit_certificate(tm, contexts):
    """Turn a closed context set into the kernel's cps format."""
    # We must recover the automata.  Reconstruct minimal tables from the
    # context set itself: derive transitions from observed contexts.
    # Simpler: the caller passes the automata used; we rebuild here from the
    # closure by inferring edges.
    # Instead, we record them in a global set by the search routine.
    return None


# ---- per-machine search --------------------------------------------------

def decide(tm):
    try:
        from neverhalt.kernel import check, Reject
    except Exception:
        return None

    table, n_states, n_symbols = build_table(tm)
    alphabet = (0, 1)

    # Try the cheap hint first: 1- and 2-state automata on each side.
    for n_left in range(1, 4):
        for left_auto in enumerate_dfa_states(n_left, alphabet):
            left_auto = complete_dfa(dict(left_auto), n_left, alphabet)
            # quick sanity: state 0 loops on 0
            if left_auto.get((0, 0)) != 0:
                continue
            for n_right in range(1, 4):
                for right_auto in enumerate_dfa_states(n_right, alphabet):
                    right_auto = complete_dfa(dict(right_auto), n_right, alphabet)
                    if right_auto.get((0, 0)) != 0:
                        continue
                    global LEFT_AUTO, RIGHT_AUTO
                    LEFT_AUTO = left_auto
                    RIGHT_AUTO = right_auto
                    contexts = close_contexts(tm, left_auto, right_auto)
                    if contexts is not None and (0, 0, 0, 0) in contexts:
                        cert = build_cert(tm, contexts, left_auto, right_auto)
                        if cert is not None:
                            try:
                                check(tm, cert)
                                return cert
                            except Reject:
                                pass
    return None


def build_cert(tm, contexts, left_auto, right_auto):
    """Build the cps certificate dict from a closed context set."""
    # left/right transition tables as lists-of-lists with None for dead
    def to_list(auto):
        n = max(k[0] for k in auto) + 1 if auto else 1
        out = []
        for st in range(n):
            row = []
            for sym in (0, 1):
                row.append(auto.get((st, sym)))
            out.append(row)
        return out

    left = to_list(left_auto)
    right = to_list(right_auto)
    ctxs = [[l, q, s, r] for (l, q, s, r) in contexts]
    cert = {"kind": "cps", "left": left, "right": right, "contexts": ctxs}
    return cert


# entry point required by the contract
NAME = "cps_search"


def decide(tm):
    return _decide(tm)


def _decide(tm):
    return decide(tm)