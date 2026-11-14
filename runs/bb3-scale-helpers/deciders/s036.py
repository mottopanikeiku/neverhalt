import sys
sys.path.insert(0, '/app')
from neverhalt.tm import parse
from neverhalt.helpers import closure


def decide(tm):
    table, ns, nsym = parse(tm)
    # Determine the maximum n-gram window size we can afford.
    # Enumerate automata with 1, 2, 3 states per side.
    for n in (1, 2, 3):
        # Build push functions for n-gram automata.
        # Automaton states are tuples of the last n symbols read.
        def mk_push(n):
            def push(state, symbol):
                if state is None:
                    state = ()
                return ((state + (symbol,)) % n)
            return push
        # Actually we need to enumerate ALL transition tables of size n states,
        # not just the n-gram one. The hint says enumerate every transition table
        # with 1, 2, 3 states per side (state 0 loops on symbol 0).
        # We'll enumerate all tables for a given number of states.
        for n in (1, 2, 3):
            # Enumerate all transition tables left[i][x] for i in range(n), x in {0,1}
            # where left[0][0] == 0.
            # Total possibilities: for each state i (n states), each symbol x (2),
            # target in range(n) or None. But None means "never happens" - but
            # actually the push function must return a valid state; None is for
            # transitions that never occur. Since we are enumerating push
            # functions, we define push(state, symbol) -> next_state or None.
            # The kernel's closure helper expects push functions that return
            # a state (any hashable) or None if that transition never happens.
            # We'll enumerate all functions from (state, symbol) -> state or None.
            import itertools
            # state space: 0..n-1, plus None means halting/never
            # We build all possible tables.
            # For a given n, number of possible transitions per (state,symbol) is n+1 (n states or None).
            # Total tables: (n+1)^(2n). For n=1: 2^2=4, n=2: 3^4=81, n=3: 4^6=4096.
            # That's manageable. For each table, build push functions and try closure.
            # To reduce, we can first try the n-gram automaton (state = last n symbols),
            # which is likely to work for counters/bouncers.
            # But the hint says enumerate every transition table. Let's do that.
            # But we also need blank_left / blank_right: the state of an all-blank
            # half-tape. Typically state 0. We'll set blank_left = 0, blank_right = 0,
            # and require push(0, 0) == 0.
            # We enumerate tables and call closure with push_left, push_right, blank_left, blank_right.
            # To keep runtime low, we first try the n-gram automata.
            # n-gram: state is tuple of last n symbols (or a rolling hash).
            # We'll represent state as an integer 0..2^n-1.
            # But the hint says enumerate every transition table with 1,2,3 states per side.
            # Let's do full enumeration for n=1,2,3.
            # We'll precompute all tables.
            # Actually the closure helper might be slow if there are many contexts.
            # We'll try the n-gram first, then full enumeration.
            # Let's implement n-gram push.
            # For n-gram, the state after reading a new symbol is the last n symbols.
            # The automaton reads from far away towards the head. So the state
            # represents the n cells already read (from far away). When a new cell
            # is pushed next to the head, it becomes the new nearest cell, so the
            # state becomes (new_symbol, old_state_without_last).
            # Wait: the automaton reads cells from far away towards the head.
            # So the first cell read is the farthest. The state accumulates the
            # cells read so far. When a new cell is added next to the head, that
            # cell is read next (it's closer to the head). So the sequence of
            # symbols read is: farthest, ..., nearest. The new cell is the nearest
            # so far, so it should be appended to the end of the sequence.
            # Actually: the automaton reads from far away towards the head. So the
            # order of reading is far -> near. The state should remember the last
            # n symbols read, i.e., the n cells closest to the head. When a new
            # cell is pushed next to the head, it becomes the new closest cell.
            # So the new state is (old_state + (new_symbol,)) truncated to n.
            # That is: push(state, symbol) = ((state << 1) | symbol) & ((1<<n)-1)
            # with state 0 being all blanks (all zeros). But we need to ensure
            # that the all-blank state is 0 and push(0,0)=0. With the above,
            # push(0,0)=0. Good.
            # Let's try this n-gram for n=1,2,3 for both sides.
            # But the hint says enumerate every transition table. Let's first
            # try n-gram, then if that fails, try full enumeration.
            # Given time budget 5000 ms, full enumeration for n=3 is 4096 tables
            # per side pair? Actually we need pairs of tables (left, right).
            # That's 4096^2 = 16 million pairs, too many. So we need to be smart.
            # The hint says: "enumerate every transition table with 1, 2, then 3 states per side
            # (state 0 loops on symbol 0), compute the smallest closed context set for each pair,
            # and stop at the first pair whose closure has no halting context."
            # That suggests we try all pairs. But 16M pairs is too many for 5 seconds.
            # Maybe the number of states is small and closure is fast, but still.
            # Perhaps we can use symmetry: many tables are equivalent. Or we can
            # first try the n-gram, which is likely to work for counters/bouncers.
            # Let's try n-gram first.
            for n in (1, 2, 3):
                # n-gram push
                mask = (1 << n) - 1
                def make_push(n):
                    mask = (1 << n) - 1
                    def push(state, symbol):
                        return ((state << 1) | symbol) & mask
                    return push
                pl = make_push(n)
                pr = make_push(n)
                # blank state is 0
                try:
                    cert = closure(pl, pr, 0, 0)
                    if cert is not None:
                        return cert
                except Exception:
                    pass
            # If n-gram fails, try full enumeration for n=1,2.
            # For n=1: 4 tables per side, 16 pairs. For n=2: 81 tables, 6561 pairs.
            # That's feasible. For n=3: 4096 tables, 16M pairs - too many.
            # We'll do full enumeration for n=1 and n=2, and if time permits,
            # try a limited set for n=3 (e.g., only tables that are "reasonable").
            # But the hint says 3 states per side, so maybe the search space is small
            # because we can prune early. Let's implement full enumeration for n=1,2
            # and then try n=3 with a time check.
            import itertools, time
            start = time.time()
            for n in (1, 2):
                # Enumerate all push functions: for each state 0..n-1 and symbol 0/1,
                # target in 0..n-1 or None.
                # But we require state 0 loops on symbol 0: push(0,0) == 0.
                # We'll generate all tables as dicts or as tuples.
                # Represent push function as a tuple of length 2n: for state i, symbol j,
                # the value is target (0..n-1) or None (represented as -1).
                # Total possibilities: (n+1)^(2n-1) because push(0,0)=0 fixed.
                # For n=1: (2)^1 = 2 tables. For n=2: 3^3 = 27 tables. Wait, 2n-1 = 1 for n=1, 3 for n=2. That's small!
                # Actually, we need to consider all (state, symbol) pairs except (0,0) which is fixed to 0.
                # Number of free pairs: 2n - 1. For n=1: 1 free pair (state 0, symbol 1). For n=2: 3 free pairs (state 0 sym1, state 1 sym0, state 1 sym1). For n=3: 5 free pairs.
                # So total tables for n=3: (3+1)^5 = 4^5 = 1024. That's tiny!
                # Wait, targets can be any of n states or None: n+1 choices. So for n=3, 4^5 = 1024 tables.
                # Pairs: 1024^2 = 1,048,576. That's still a lot but maybe manageable if closure is fast.
                # But closure might be expensive. We can try to prune: only try pairs where both automata are "deterministic" and maybe use symmetry.
                # Let's first do full enumeration for n=1 and n=2, then n=3.
                # We'll generate all tables as tuples of length 2n (index = state*2 + symbol).
                # For n=1: index 0: (0,0) fixed to 0; index 1: (0,1) can be 0 or None -> 2 tables.
                # For n=2: indices: 0:(0,0)=0 fixed; 1:(0,1); 2:(1,0); 3:(1,1). Each of 1,2,3 can be 0,1,None -> 3^3=27 tables.
                # For n=3: indices 0..5: 0:(0,0)=0 fixed; 1:(0,1); 2:(1,0); 3:(1,1); 4:(2,0); 5:(2,1). Each of 1..5 can be 0,1,2,None -> 4^5=1024 tables.
                # Let's do n=1,2 first.
                for n in (1, 2):
                    # Generate all tables
                    free_indices = [i for i in range(2*n) if i != 0]
                    tables = []
                    for combo in itertools.product(range(n+1), repeat=len(free_indices)):
                        # combo values: 0..n-1 for state, n for None
                        table = [None] * (2*n)
                        table[0] = 0  # state 0, symbol 0 -> 0
                        for idx, val in zip(free_indices, combo):
                            table[idx] = None if val == n else val
                        tables.append(tuple(table))
                    # Try all pairs
                    for lt in tables:
                        # Build push_left from table
                        def make_push(t):
                            def push(state, symbol):
                                return t[state*2 + symbol]
                            return push
                        pl = make_push(lt)
                        for rt in tables:
                            pr = make_push(rt)
                            # blank states: 0
                            # But we must ensure push(0,0)==0 for both, which is true.
                            try:
                                cert = closure(pl, pr, 0, 0)
                                if cert is not None:
                                    return cert
                            except Exception:
                                pass
                            if time.time() - start > 4.5:
                                return None
            # If we get here, try n=3 with a limited search.
            # For n=3, 1024 tables per side, 1M pairs. Too many for 5 seconds.
            # We can try to use the n-gram automata first (already done above).
            # Maybe we can try a smarter approach: use the n-gram but with different
            # window sizes or different blank states. Or try to use the kernel's
            # closure with a timeout? The helper might not support timeout.
            # For now, return None.
            return None


# The above is a placeholder. Let's write a proper decider.
# We need to actually implement the full enumeration for n=1,2,3.
# Given the time budget, we can try n=1,2 fully, and for n=3 we can try
# a subset: maybe only tables that are "reasonable" (e.g., no None transitions
# unless necessary). Or we can use the n-gram which is a specific table.
# The hint says: "enumerate every transition table with 1, 2, then 3 states per side
# (state 0 loops on symbol 0), compute the smallest closed context set for each pair,
# and stop at the first pair whose closure has no halting context."
# So we should do full enumeration for n=1,2,3. But 1M pairs for n=3 might be too slow.
# However, the closure helper is likely fast (it's a BFS over contexts). For small
# automata, the number of contexts might be small. Let's test: for n=3, the number
# of contexts is at most (n^2) * 2 * 2 = 4 * 4 = 16? Actually contexts are (l, q, s, r).
# l and r are automaton states (n possibilities each), q is machine state (ns), s is symbol (2).
# So max contexts = n * ns * 2 * n = 2 * n^2 * ns. For n=3 and ns=3, that's 2*9*3 = 54.
# The closure BFS will be very fast. So 1M pairs * 54 contexts = 54M operations, might be
# feasible in 5 seconds if optimized. But Python overhead might be high.
# We can optimize by precomputing transitions and using the kernel's closure.
# Let's implement full enumeration for n=1,2,3 with early exit.
# We'll also try the n-gram first as a quick win.
# Let's write the final decider.

from neverhalt.tm import parse
from neverhalt.helpers import closure
import itertools, time

def decide(tm):
    table, ns, nsym = parse(tm)
    start = time.time()
    # Quick try: n-gram automata for n=1,2,3
    for n in (1, 2, 3):
        mask = (1 << n) - 1
        def make_push(n):
            mask = (1 << n) - 1
            def push(state, symbol):
                return ((state << 1) | symbol) & mask
            return push
        pl = make_push(n)
        pr = make_push(n)
        try:
            cert = closure(pl, pr, 0, 0)
            if cert is not None:
                return cert
        except Exception:
            pass
    # Full enumeration for n=1,2
    for n in (1, 2):
        free_indices = [i for i in range(2*n) if i != 0]
        tables = []
        for combo in itertools.product(range(n+1), repeat=len(free_indices)):
            t = [None] * (2*n)
            t[0] = 0
            for idx, val in zip(free_indices, combo):
                t[idx] = None if val == n else val
            tables.append(tuple(t))
        for lt in tables:
            def make_push(t):
                def push(state, symbol):
                    return t[state*2 + symbol]
                return push
            pl = make_push(lt)
            for rt in tables:
                pr = make_push(rt)
                try:
                    cert = closure(pl, pr, 0, 0)
                    if cert is not None:
                        return cert
                except Exception:
                    pass
                if time.time() - start > 4.0:
                    return None
    # Full enumeration for n=3, but we may need to limit.
    # For n=3, there are 1024 tables per side. 1024^2 = 1,048,576 pairs.
    # We can try to reduce by symmetry: left and right automata can be swapped?
    # Not necessarily, because the machine is not symmetric. But we can try
    # all pairs. Let's optimize the inner loop.
    # We'll precompute push functions for each table.
    n = 3
    free_indices = [i for i in range(2*n) if i != 0]
    tables = []
    for combo in itertools.product(range(n+1), repeat=len(free_indices)):
        t = [None] * (2*n)
        t[0] = 0
        for idx, val in zip(free_indices, combo):
            t[idx] = None if val == n else val
        tables.append(tuple(t))
    # Precompute push functions as lists for speed
    push_funcs = []
    for t in tables:
        # push(state, symbol) = t[state*2 + symbol]
        # We can represent as a list of length 2n
        push_funcs.append(t)
    # Try all pairs, but with a time limit
    count = 0
    for lt in push_funcs:
        for rt in push_funcs:
            # Define push functions inline for speed
            def pl(state, symbol, lt=lt):
                return lt[state*2 + symbol]
            def pr(state, symbol, rt=rt):
                return rt[state*2 + symbol]
            try:
                cert = closure(pl, pr, 0, 0)
                if cert is not None:
                    return cert
            except Exception:
                pass
            count += 1
            if count % 10000 == 0:
                if time.time() - start > 4.5:
                    return None
    return None
}]