from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure

# Enumerate every transition table of 1..3 states per side (state 0 loops on 0),
# deduplicate up to isomorphism, and test the smallest closed context set.
import itertools

def _tables(max_states):
    for n in range(1, max_states + 1):
        # states: 0..n-1 ; blank state 0 has to loop on 0
        for rows in itertools.product(range(n + 1), repeat=n):  # row per state, entries 0..n
            for syms in itertools.product(range(n + 1), repeat=n):  # symbol per state's 0-row
                t = {}
                ok = True
                for st in range(n):
                    for s in range(2):
                        if s == 0 and st == 0:
                            t[(st, s)] = st
                        else:
                            if s == 0:
                                t[(st, s)] = syms[st]
                            else:
                                t[(st, s)] = rows[st]
                # canonicalize: relabel states in order of first appearance starting from 0
                seen = {}
                canon = []
                for st in range(n):
                    for s in range(2):
                        if s == 0 and st == 0:
                            nxt = 0
                        else:
                            nxt = t[(st, s)]
                        if nxt not in seen:
                            seen[nxt] = len(canon)
                            canon.append(nxt)
                used = sorted(seen.keys())
                if len(used) != n:
                    continue
                remap = {old: new for new, old in enumerate(used)}
                out = {}
                for st in range(n):
                    for s in range(2):
                        out[(st, s)] = remap[t[(st, s)]]
                yield out

def _build_push(t, blank):
    def push(state, symbol):
        nxt = t.get((state, symbol))
        return nxt
    return push

def _try_pair(tl, tr, blank_l, blank_r):
    pl = _build_push(tl, blank_l)
    pr = _build_push(tr, blank_r)
    try:
        cert = closure(pl, pr, blank_l, blank_r)
    except Exception:
        return None
    if cert is None:
        return None
    return cert

_cache = []

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # Build push tables for the machine's per-state transitions:
    # for the left half-tape automaton, reading cells far away towards head.
    # We approximate the machine's own state-dependent writes by enumerating
    # small automata instead (per the hint), then verify with the kernel.
    # First, try the direct n-gram closures for n = 1, 2, 3 by construction
    # using the helper with machine-derived push functions.
    for n in (1, 2, 3):
        def mpush_left(state, symbol, n=n):
            # state is a tuple of the last n symbols (or fewer); symbol is new cell
            if isinstance(state, tuple):
                return (state + (symbol,))[-n:]
            return (symbol,)
        def mpush_right(state, symbol, n=n):
            if isinstance(state, tuple):
                return (state + (symbol,))[-n:]
            return (symbol,)
        blank = ()
        cert = None
        try:
            cert = closure(mpush_left, mpush_right, blank, blank)
        except Exception:
            cert = None
        if cert is not None:
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
    # Now search over small automata explicitly.
    for tl in _tables(3):
        for tr in _tables(3):
            if tl == tr:
                pass
            cert = _try_pair(tl, tr, 0, 0)
            if cert is not None:
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
    return None
}