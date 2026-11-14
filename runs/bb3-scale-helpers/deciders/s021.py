import sys
sys.setrecursionlimit(1000000)

# Helper: build automata as dict-based transition tables.
# Each automaton: dict state -> dict symbol -> state or None (never happens).
# state 0 is blank half-tape; push(0, 0) must return 0.


def _mk_push(spec):
    # spec: dict state -> (sym0_state, sym1_state)
    tbl = {}
    for st, (s0, s1) in spec.items():
        tbl[st] = {0: s0, 1: s1}
    return tbl


def _push(tbl, st, sym):
    return tbl[st][sym]


def _make_machine(spec):
    """spec: dict state -> (sym0_state, sym1_state). Returns push function."""
    tbl = _mk_push(spec)
    def push(state, symbol):
        if state not in tbl:
            return None
        if symbol not in tbl[state]:
            return None
        return tbl[state][symbol]
    return push


def _enumerate_automata(max_states):
    """Enumerate all automaton transition specs with up to max_states.
    State 0 loops on symbol 0 (blank stays blank). Return list of push functions."""
    results = []
    # states used: 0..n-1
    for n in range(1, max_states + 1):
        states = list(range(n))
        # each state has 2 possible next states; but state 0 on symbol 0 must be 0.
        # enumerate all combinations for symbols 1 and for states 1..n-1 both symbols
        choices = []
        for st in states:
            if st == 0:
                # symbol 0 -> 0; symbol 1 -> any state
                choices.append([0] + states)
            else:
                choices.append(states + states)
        import itertools
        for combo in itertools.product(*choices):
            spec = {}
            for st in range(n):
                s0, s1 = combo[st][0], combo[st][1]
                spec[st] = (s0, s1)
            push = _make_machine(spec)
            results.append(push)
    return results


def _closure(left, right, blank_left, blank_right, cap=200000):
    """Compute smallest closed context set. Returns (contexts, automata_used) or None.
    contexts: set of (l, q, s, r). Returns None if a halting context is reached or too many contexts."""
    # We need the machine transition table. We'll pass it in via closure.
    raise NotImplementedError


def _build_cps(tm):
    """Try to find a CPS certificate for tm. Returns cert dict or None."""
    from neverhalt.tm import parse
    from neverhalt.helpers import closure

    table, n_states, n_symbols = parse(tm)

    # Enumerate automata pairs (1,2,3 states each).
    for n in (1, 2, 3):
        autos = _enumerate_automata(n)
        # To limit runtime, cap number of pairs. But pairs grow fast: for n=3,
        # number of automata is huge. We need to limit enumeration smartly.
        # Actually, each automaton with n states: state 0 loops on 0,
        # state 0 on 1 -> any of n, states 1..n-1 each have 2n choices.
        # n=1: 1 automaton. n=2: 1 * 2 * 4 = 8. n=3: 1 * 3 * 6 * 6 = 108.
        # Pairs: 1, 64, 11664. 11664 pairs * closure cost may be too much
        # for 5s budget. We'll order pairs and try, with a time check.

        import time
        start = time.time()
        # sort automata: prefer simpler ones? Just iterate.
        for a in autos:
            for b in autos:
                # quick check: blank automata
                if a(0, 0) != 0 or b(0, 0) != 0:
                    continue
                # build cert via closure helper
                # closure needs push functions and blank states
                # We'll call helper's closure. Signature per docstring:
                # closure(push_left, push_right, blank_left, blank_right, cap=...)
                # It returns a cps certificate or None.
                # We need to pass the machine's transitions too? The helper
                # presumably knows about the machine? Actually the helper is
                # generic: "Smallest closed context set for two automata given
                # as push functions -> a `cps` certificate, or None."
                # It must incorporate the machine transitions internally somehow.
                # We'll assume it takes the machine's table implicitly? Wait,
                # it says "given as push functions" - maybe it uses a global
                # or the machine is fixed in the sandbox per call.
                # Since we can't be sure, we implement our own closure using
                # the machine's transition table.
                pass
    return None


def _closure_own(table, n_states, left, right, blank_left, blank_right, cap=200000):
    """Own closure computation. Returns (contexts, used_left, used_right) or None."""
    # contexts: set of (l, q, s, r)
    # Start with (blank_left, 0, 0, blank_right)  [state A = 0, symbol 0]
    start = (blank_left, 0, 0, blank_right)
    contexts = set([start])
    stack = [start]
    # Track used transitions: left_used[(l, sym)] = l2 ; right_used[(r, sym)] = r2
    left_used = {}
    right_used = {}

    while stack:
        (l, q, s, r) = stack.pop()
        # transition (q, s) must exist
        key = (q, s)
        if key not in table:
            return None  # halting context
        (w, move, q2) = table[key]
        if move == 1:
            # right move
            l2 = left(l, w)
            if l2 is None:
                return None
            # for every (r2, s2) with right[r2][s2] == r:
            # need context (l2, q2, s2, r2)
            # We need to look at the right automaton's transitions.
            # Build reverse index: for each r, list of (r2, s2) such that right(r2, s2) == r
            # We'll compute on the fly.
            for r2 in range(0, 1000):  # bound? automaton states may be arbitrary hashable
                pass
        else:
            # left move
            r2 = right(r, w)
            if r2 is None:
                return None
            # mirror

    return None


def decide(tm: str):
    # Placeholder: implement real search.
    # For now, return None.
    return None
