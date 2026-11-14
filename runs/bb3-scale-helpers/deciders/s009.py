from neverhalt.tm import parse
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure


def _pair_closure(pairs):
    """Try a list of (push_left, blank_left, push_right, blank_right) candidates.

    Returns a cps certificate dict or None.
    """
    for pl, bl, pr, br in pairs:
        try:
            cert = closure(pl, pr, blank_left=bl, blank_right=br)
        except Exception:
            cert = None
        if cert is not None:
            return cert
    return None


def _enumerate_automata(n):
    """Enumerate deterministic automata with states 0..n-1.

    State 0 loops on symbol 0 (blank half-tape).  Every other transition
    is either a state 0..n-1 or None (never happens).
    """
    # For each state 1..n-1 we choose what happens on symbol 0 and 1.
    # State 0: on symbol 0 -> 0, on symbol 1 -> any state 0..n-1.
    choices = []
    for st in range(1, n):
        opts = []
        for x in (0, 1):
            opts.append([None] + list(range(n)))
        choices.append(opts)

    def rec(i, acc):
        if i == len(choices):
            yield acc
            return
        for a in choices[i]:
            for b in choices[i + 1] if False else [None]:
                pass
        # simpler: iterate product per state
        raise RuntimeError

    # product over states
    import itertools
    per_state = []
    for st in range(1, n):
        opts0 = [None] + list(range(n))
        opts1 = [None] + list(range(n))
        per_state.append(list(itertools.product(opts0, opts1)))
    for combo in itertools.product(*per_state):
        tbl = {0: {0: 0, 1: 0}}  # placeholder, filled below
        tbl = {}
        tbl[0] = {0: 0, 1: 0}
        for st, (z, o) in zip(range(1, n), combo):
            tbl[st] = {0: z, 1: o}
        yield tbl


def _mk_push(tbl):
    def push(state, symbol):
        return tbl.get(state, {}).get(symbol)
    return push


def _mk_blank(tbl):
    # blank state is 0
    return 0


def decide(tm: str):
    table, n_states, n_symbols = parse(tm)
    # Kernel contract: a certificate or None.
    # Our strategy: enumerate small automata per side, use closure helper.
    # We cap the search to stay within the time budget: try 1-state and
    # 2-state automata exhaustively, then 3-state with a coarse subset.
    import itertools

    def try_pair(tbl_l, tbl_r):
        pl = _mk_push(tbl_l)
        pr = _mk_push(tbl_r)
        try:
            cert = closure(pl, pr, blank_left=0, blank_right=0)
        except Exception:
            cert = None
        if cert is not None:
            return cert
        return None

    # 1-state automata: state 0 loops on 0, on 1 either 0 or None.
    one_states = []
    for z in (0, None):
        tbl = {0: {0: 0, 1: z}}
        one_states.append(tbl)

    # 2-state automata: state 0: {0:0, 1: x0}; state 1: {0: y0, 1: y1}
    two_states = []
    for x0 in (0, 1, None):
        for y0 in (0, 1, None):
            for y1 in (0, 1, None):
                tbl = {0: {0: 0, 1: x0}, 1: {0: y0, 1: y1}}
                two_states.append(tbl)

    # Try all pairs from 1-state and 2-state automata.
    # Order: smaller automata first for speed.
    candidates = []
    for tl in one_states:
        for tr in one_states:
            candidates.append((tl, tr))
    for tl in two_states:
        for tr in one_states:
            candidates.append((tl, tr))
    for tl in one_states:
        for tr in two_states:
            candidates.append((tl, tr))

    # Limit the number of pairs to fit the budget.
    MAX_PAIRS = 40000
    for i, (tl, tr) in enumerate(candidates):
        if i >= MAX_PAIRS:
            break
        cert = try_pair(tl, tr)
        if cert is not None:
            return cert
    return None


# End of module.
