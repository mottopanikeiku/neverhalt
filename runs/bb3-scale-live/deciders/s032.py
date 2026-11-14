import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: "cps_ngram_big"
# Generalized n-gram CPS with a larger window, plus a bounded search over
# a few window sizes and both automaton constructions (last-n and full-window).
# We try several window sizes n, build the left/right automata as "last n cells
# of the half-tape" automata, compute the reachable context closure, and hand
# the resulting certificate to the kernel. We also try a smaller n first so the
# closure stays small, then larger n for machines that need more memory.

def _build_automaton(n, alphabet=(0, 1)):
    # states 0..2**n-1, state encodes the last n cells (most recent first).
    # state 0 = all blank.
    size = 1 << n
    trans = [[None] * len(alphabet) for _ in range(size)]
    for st in range(size):
        for ai, sym in enumerate(alphabet):
            # new most-recent cell = sym; shift out oldest bit
            new = ((st << 1) | sym) & (size - 1)
            trans[st][ai] = new
    return trans

def _contexts_closure(tm):
    table, n_states, n_symbols = parse(tm)
    # n_symbols is 2; alphabet {0,1}
    alphabet = (0, 1)
    # try several window sizes
    for n in (2, 3, 4, 5):
        left = _build_automaton(n)
        right = _build_automaton(n)
        # context: (l, q, s, r)
        start = (0, 0, 0, 0)
        seen = {start}
        stack = [start]
        ok = True
        while stack:
            (l, q, s, r) = stack.pop()
            if q >= n_states:
                ok = False
                break
            key = (q, s)
            if key not in table:
                ok = False
                break
            w, move, q2 = table[key]
            if move > 0:
                # right move: push w onto left half-tape
                l2 = left[l][w]
                if l2 is None:
                    ok = False
                    break
                # pop any symbol from right half-tape
                for r2 in range(len(right)):
                    for s2 in alphabet:
                        if right[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in seen:
                                seen.add(c)
                                stack.append(c)
            else:
                r2 = right[r][w]
                if r2 is None:
                    ok = False
                    break
                for l2 in range(len(left)):
                    for s2 in alphabet:
                        if left[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in seen:
                                seen.add(c)
                                stack.append(c)
        if ok:
            # build certificate
            left_out = [row[:] for row in left]
            right_out = [row[:] for row in right]
            contexts = [[l, q, s, r] for (l, q, s, r) in seen]
            cert = {
                "kind": "cps",
                "left": left_out,
                "right": right_out,
                "contexts": contexts,
            }
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    return None

def decide(tm):
    return _contexts_closure(tm)
