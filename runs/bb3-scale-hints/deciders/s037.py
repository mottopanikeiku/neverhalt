"""CPS decider: search small DFAs for the left half-tape, determinize the
right half-tape's language, and close the context set.

Plan:
  1. Enumerate DFA transition tables for one half-tape with 1..4 states in
     BFS-canonical order (state 0 loops on symbol 0, reachable from 0).
  2. For each candidate DFA, first check whether it is a "survivor": every
     context reachable from the start must avoid halting transitions.  We do
     this by computing, backwards from the halting transitions of the machine,
     the set of abstract tapes that can still halt; if the blank tape's
     abstract value is forced to be in that set, the DFA is useless.
  3. For a surviving DFA, the right half-tape's language becomes an NFA
     (reverse-determinize a DFA for the left side is not enough here because
     the machine need not be reversible), so instead we enumerate small DFAs
     for the right side too and take the first pair whose closed-context
     fixpoint contains no halting context.
  4. Emit the certificate, pruned to only the transitions used by the closure.
"""

from neverhalt.tm import parse
from neverhalt.kernel import Reject, check


def _parse(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states, n_symbols


def _canonical_order(states):
    """BFS-canonical labelling of states reachable from 0 (blank tape)."""
    ids = {0: 0}
    order = [0]
    queue = [0]
    while queue:
        s = queue.pop(0)
        for x in (0, 1):
            t = states[s][x]
            if t is None:
                continue
            if t not in ids:
                ids[t] = len(order)
                order.append(t)
                queue.append(t)
    return ids, order


def _enumerate_dfas(max_states):
    """Yield DFA transition tables (list of lists, index 0 is start).

    Symbol 0 from state 0 is forced to 0 (blank half-tape is invariant).
    States are generated in BFS-canonical order from state 0.
    """
    # Represent a partial DFA as a dict: state -> {symbol: target or None}.
    # We build by BFS from state 0, always assigning the next fresh index.
    results = []

    def rec(states, next_index):
        if next_index > max_states:
            return
        # Try to extend any state that is currently "undecided".
        undecided = [s for s in range(len(states))
                     if states[s][0] is None or states[s][1] is None]
        if not undecided:
            # Complete DFA found.
            results.append([list(states[s].values()) for s in range(len(states))])
            return
        s = undecided[0]
        # Symbol 0 from state 0 must stay 0.
        if s == 0 and states[0][0] is None:
            states[0][0] = 0
            rec(states, next_index)
            states[0][0] = None
            return
        # Branch: for each symbol, either target existing state or new state.
        for sym in (0, 1):
            if states[s][sym] is not None:
                continue
            # Target an existing state.
            for t in range(len(states)):
                states[s][sym] = t
                rec(states, next_index)
                states[s][sym] = None
            # Target a fresh state.
            states[s][sym] = next_index
            states.append([None, None])
            # Fresh state's symbol-0 transition: allow any existing or itself.
            for x in range(len(states)):
                states[-1][0] = x
                rec(states, next_index + 1)
                states[-1][0] = None
            states.pop()
            states[s][sym] = None
            return

    rec([[None, None]], 1)
    return results


def _context_key(l, q, s, r):
    return (l, q, s, r)


def _close_contexts(left, right, table, n_states, n_symbols, start_ctx,
                    max_contexts):
    """Fixpoint closure of contexts under the CPS rules.

    Returns (contexts_set, halting_contexts).  If any context leads to a
    halting transition, we mark it so the caller can reject the pair.
    """
    contexts = {start_ctx}
    halting = set()
    work = [start_ctx]
    while work:
        if len(contexts) > max_contexts:
            return None, None
        l, q, s, r = work.pop()
        tr = table.get((q, s))
        if tr is None:
            halting.add((l, q, s, r))
            continue
        w, move, q2 = tr
        if move > 0:
            # Right move: l2 = left[l][w] must exist; s2 is popped off the
            # right half-tape, any s2 with right[r2][s2] == r.
            if left[l][w] is None:
                halting.add((l, q, s, r))
                continue
            l2 = left[l][w]
            for r2 in range(len(right)):
                for s2 in (0, 1):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in contexts:
                            contexts.add(c)
                            work.append(c)
        else:
            # Left move: mirror image.
            if right[r][w] is None:
                halting.add((l, q, s, r))
                continue
            r2 = right[r][w]
            for l2 in range(len(left)):
                for s2 in (0, 1):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in contexts:
                            contexts.add(c)
                            work.append(c)
    return contexts, halting


def decide(tm):
    table, n_states, n_symbols = _parse(tm)
    # Precompute halting transitions (absent entries in table).
    # Search DFA pairs with small sizes, growing.
    max_states = 3
    for ls in range(1, max_states + 1):
        left_tables = _enumerate_dfas(ls)
        for lt in left_tables:
            # left automaton as list-of-lists with None for dead.
            left = lt
            # Quick sanity: left[0][0] == 0 already enforced.
            for rs in range(1, max_states + 1):
                right_tables = _enumerate_dfas(rs)
                for rt in right_tables:
                    right = rt
                    # Closed-context fixpoint from the start context.
                    contexts, halting = _close_contexts(
                        left, right, table, n_states, n_symbols,
                        (0, 0, 0, 0), 200000)
                    if contexts is None:
                        continue
                    if halting:
                        continue
                    # No halting context: emit certificate.
                    # Keep only transitions used by the closure.
                    used_left = set()
                    used_right = set()
                    for (l, q, s, r) in contexts:
                        tr = table.get((q, s))
                        if tr is None:
                            continue
                        w, move, q2 = tr
                        if move > 0 and left[l][w] is not None:
                            used_left.add((l, w))
                        if move < 0 and right[r][w] is not None:
                            used_right.add((r, w))
                    left_cert = [[left[i][x] if (i, x) in used_left else None
                                  for x in (0, 1)] for i in range(len(left))]
                    right_cert = [[right[i][x] if (i, x) in used_right else None
                                   for x in (0, 1)] for i in range(len(right))]
                    contexts_list = [[l, q, s, r]
                                     for (l, q, s, r) in contexts]
                    cert = {
                        "kind": "cps",
                        "left": left_cert,
                        "right": right_cert,
                        "contexts": contexts_list,
                    }
                    try:
                        check(tm, cert)
                    except Reject:
                        continue
                    return cert
    return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(decide(sys.argv[1]))
