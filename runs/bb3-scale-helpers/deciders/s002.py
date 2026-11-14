import sys
from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

def decide(tm):
    try:
        table, ns, nsy = parse(tm)
    except Exception:
        return None
    # halting transitions absent; treat as halting
    try:
        from neverhalt.helpers import closure
    except Exception:
        return None

    n_states = ns
    syms = [0, 1]

    # enumerate automata with k states per side
    def all_autos(k):
        # state 0 loops on symbol 0
        # states: 0..k-1; transitions: for s != 0, left[s][x] in 0..k-1 or None
        # (blank state 0 loops on 0, may go anywhere on 1? require blank_left loops on 0)
        results = []
        # each state s != 0 has two entries: (left transition, right transition)
        # left[s][x] and right[s][x] independent? In closure, push_left and push_right
        # are separate functions. So enumerate separately for left and right.
        def gen():
            # for each state s in 1..k-1, left[s][0], left[s][1] each in 0..k-1 or None
            # right similarly
            import itertools
            choices = list(range(k)) + [None]
            for s in range(1, k):
                # 4 choices per state for left, 4 for right -> enumerate all combos
                pass
            # iterate over all pairs
            for ls in itertools.product(choices, repeat=2*(k-1)):
                # build left
                L = {0: {0: 0, 1: None}}
                for i in range(1, k):
                    L[i] = {0: ls[2*(i-1)], 1: ls[2*(i-1)+1]}
                yield L
        def gen_both():
            # generate all left and right automata separately
            import itertools
            choices = list(range(k)) + [None]
            for ls in itertools.product(choices, repeat=2*(k-1)):
                L = {0: {0: 0, 1: None}}
                for i in range(1, k):
                    L[i] = {0: ls[2*(i-1)], 1: ls[2*(i-1)+1]}
                yield L
        for L in gen_both():
            for R in gen_both():
                yield L, R

    for k in (1, 2, 3):
        # cap contexts to fit kernel limit
        for L, R in all_autos(k):
            # build push functions
            def blank_left(): return 0
            def blank_right(): return 0
            def push_left(s, x):
                if s == 0:
                    return 0 if x == 0 else None
                return L.get(s, {}).get(x)
            def push_right(s, x):
                if s == 0:
                    return 0 if x == 0 else None
                return R.get(s, {}).get(x)
            try:
                cert = closure(blank_left, blank_right, push_left, push_right, tm)
            except Exception:
                continue
            if cert is None:
                continue
            try:
                check(tm, cert)
            except Reject:
                continue
            except Exception:
                continue
            return cert
    return None
