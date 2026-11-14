from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Enumerate small automata for the two half-tape sides and use the closure
# helper to build a cps certificate. We enumerate every transition table of
# size 1..3 states per side, with state 0 looping on symbol 0 (so blank tape
# is fixed), and allow any symbol on the other state(s).  For each pair we
# ask the closure helper for the smallest closed context set, and if one is
# returned (no halting context reachable) we emit the certificate.

def enumerate_automata(max_states, cap):
    # returns list of (trans_table, blank_state)
    # trans_table: dict (state, symbol) -> next_state (or None meaning dead)
    # state 0 is the blank state, loops on symbol 0.
    out = []
    for n in range(1, max_states + 1):
        for codes in range((2 ** (2 * n)) ** 2 if n == 1 else 0):
            pass
        # brute force: each of the 2*n transitions (n states x 2 symbols)
        # except state0/0 which is fixed to 0, gets a target in range(n) or None
        # We limit branching: use itertools.product
        import itertools
        trans_list = [(s, x) for s in range(n) for x in range(2)]
        # fix (0,0) -> 0, others vary over {None} U range(n)
        idxs = [i for i, (s, x) in enumerate(trans_list) if not (s == 0 and x == 0)]
        choices = [None] + list(range(n))
        for combo in itertools.product(choices, repeat=len(idxs)):
            tbl = {}
            tbl[(0, 0)] = 0
            for i, j in zip(idxs, combo):
                tbl[trans_list[i]] = j
            out.append((tbl, 0))
    return out

def make_push(tbl, blank):
    # push(state, symbol) -> next state or None (null)
    def push(state, symbol):
        # symbol is 0 or 1
        return tbl.get((state, symbol), None)
    return push

def decide(tm):
    from neverhalt.helpers import closure
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # try increasing sizes; state 0 must loop on 0
    for max_states, cap in ((1, 200000), (2, 200000), (3, 200000)):
        autos = enumerate_automata(max_states, cap)
        for lt, lb in autos:
            lp = make_push(lt, lb)
            for rt, rb in autos:
                rp = make_push(rt, rb)
                # blank states must loop on 0
                if lp(lb, 0) != lb or rp(rb, 0) != rb:
                    continue
                try:
                    cert = closure(lp, lp(0, 0), rp, rp(0, 0), cap)
                except Exception:
                    cert = None
                if cert is None:
                    continue
                # verify with kernel before returning
                try:
                    check(tm, cert)
                except Reject:
                    continue
                except Exception:
                    continue
                return cert
    return None
