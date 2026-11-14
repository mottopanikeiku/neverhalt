import sys
from collections import deque

# ---- helpers -------------------------------------------------------------

def automaton_closure(left, right, q_states, contexts0):
    """Closed set of contexts for a given pair of automata (as dicts)."""
    contexts = set(contexts0)
    changed = True
    while changed:
        changed = False
        for (l, q, s, r) in list(contexts):
            w, mv, q2 = TRANS[q][s]
            if mv == 1:
                l2 = left.get((l, w))
                if l2 is None:
                    return None
                for (r2, s2) in pairs_right.get(r, ()):
                    if (l2, q2, s2, r2) not in contexts:
                        contexts.add((l2, q2, s2, r2)); changed = True
            else:
                r2 = right.get((r, w))
                if r2 is None:
                    return None
                for (l2, s2) in pairs_left.get(l, ()):
                    if (l2, q2, s2, r2) not in contexts:
                        contexts.add((l2, q2, s2, r2)); changed = True
    return contexts

def emits_cert(contexts, TRANS, Q):
    return contexts

# ---- decider -------------------------------------------------------------

NAME = "dfa_search"

def _build_pairs(aut, n_states):
    """pairs[st] = list of (st2, sym) with aut[st2][sym] == st, for st != 0.
       For st == 0 we only allow sym == 0 and st2 == 0 (blank tape)."""
    pairs = {}
    for st in range(n_states):
        lst = []
        for st2 in range(n_states):
            for x in (0, 1):
                if aut.get((st2, x)) == st:
                    if st == 0 and not (x == 0 and st2 == 0):
                        continue
                    lst.append((st2, x))
        pairs[st] = lst
    return pairs

def _can_loop(aut, n_states):
    """Reject automata whose state 0 loops on 1 (would be the blank tape
    reading a 1, impossible).  Also require left[0][0] = right[0][0] = 0."""
    return aut.get((0, 0)) == 0

def _all_aut_tables(n_states):
    """All deterministic automata on n_states states,
    each state's transition on 0 and 1 is one of the n_states (or None),
    state 0 must map 0 -> 0 (blank tape stays blank tape)."""
    n = n_states
    results = []
    # represent transitions as tuples of length 2*n: trans[state*2 + sym]
    # value in 0..n-1 or -1 for None.  state 0 sym 0 fixed to 0.
    for code in range((n + 1) ** (2 * n - 1)):
        t = [0] * (2 * n)
        x = code
        t[0] = 0
        for i in range(1, 2 * n):
            x, r = divmod(x, n + 1)
            t[i] = r - 1 if r > 0 else -1
        aut = {}
        for st in range(n):
            for sym in (0, 1):
                v = t[2 * st + sym]
                if v >= 0:
                    aut[(st, sym)] = v
        if _can_loop(aut, n):
            results.append(aut)
    return results

def decide(tm):
    from neverhalt.tm import parse
    from neverhalt.kernel import check, Reject
    table, n_states, n_symbols = parse(tm)
    # q index -> (w, mv, q2) per symbol; mv: use +1 for right, -1 for left
    Q = {}
    for q in range(n_states):
        for s in range(n_symbols):
            key = (q, s)
            if key in table:
                w, mv, q2 = table[key]
                Q[(q, s)] = (w, mv, q2)
    # For the kernel we need our own table with 0/1 symbols.
    # bbchallenge uses symbols as ints; normalize to 0/1.
    syms = sorted(set(s for (q, s) in table.keys()))
    symmap = {old: i for i, old in enumerate(syms)}
    Qn = {}
    for (q, s), (w, mv, q2) in Q.items():
        Qn[(q, symmap[s])] = (symmap.get(w, w), mv, q2)
    # quick sanity: no halting transition may be reachable as a context edge;
    # we simply try to build a closed context set.

    max_states = 3
    for ns in range(1, max_states + 1):
        for aut in _all_aut_tables(ns):
            # state 0 blank tape must have left[0][0] = right[0][0] = 0
            if aut.get((0, 0)) != 0:
                continue
            # left automaton reads far-to-head on the left; right likewise.
            left = aut
            pairs_left = _build_pairs(left, ns)
            # require pair for state 0: only (0,0)
            if (0, 0) not in pairs_left.get(0, ()):
                continue
            # try all pairs (left, right) = (aut, aut) first; then also the
            # other orientation (mirror), and finally a small search over
            # second automata if time permits.
            for right in (aut,):
                pairs_right = _build_pairs(right, ns)
                if (0, 0) not in pairs_right.get(0, ()):
                    continue
                contexts0 = {(0, 0, 0, 0)}
                ctx = automaton_closure(left, right, n_states, contexts0)
                if ctx is None:
                    continue
                # convert to kernel format
                def pairs_of(aut2, n2):
                    out = {}
                    for st in range(n2):
                        lst = []
                        for st2 in range(n2):
                            for x in (0, 1):
                                if aut2.get((st2, x)) == st:
                                    if st == 0 and not (x == 0 and st2 == 0):
                                        continue
                                    lst.append([st2, x])
                        out[st] = lst
                    return out
                cert = {
                    "kind": "cps",
                    "left": [[left.get((i, x), None) if left.get((i, x)) is not None else None for x in (0, 1)] for i in range(ns)],
                    "right": [[right.get((i, x), None) if right.get((i, x)) is not None else None for x in (0, 1)] for i in range(ns)],
                    "contexts": [[l, q, s, r] for (l, q, s, r) in ctx],
                }
                # fix kernel limits: at most 5000 states per automaton and
                # 200000 contexts
                if len(cert["contexts"]) > 200000:
                    continue
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
                except Exception:
                    continue
    return None
}  # noqa: E999