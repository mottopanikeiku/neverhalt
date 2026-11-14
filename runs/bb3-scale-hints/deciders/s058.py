import sys
from itertools import product

# ---------------- helpers ----------------

def parse_mach(tm):
    """Return (trans, nstate) with trans[(state,sym)] = (write, move, nextstate) or None."""
    rows = tm.split('_')
    trans = {}
    for st, row in enumerate(rows):
        for sym in range(2):
            c = row[3*sym:3*sym+3]
            if c == '---' or len(c) < 3:
                trans[(st, sym)] = None
                continue
            w, m, ns = c[0], c[1], c[2]
            if ns in 'AZ':
                nxt = None if ns == 'Z' else ord(ns) - ord('A')
                if nxt >= len(rows):
                    nxt = None
            else:
                raise ValueError('bad state')
            wm = 1 if m == 'R' else -1
            ws = 1 if w == '1' else 0
            trans[(st, sym)] = (ws, wm, nxt)
    return trans, len(rows)


# ---------------- closure / certificate ----------------

def build_cps(cert_l, cert_r, mach):
    """Given left table (list of rows) and right table, plus current machine,
       compute the smallest closed context set starting from [0,0,0,0].
       Returns list of contexts or None if a halting context is forced.
       Context = (l, q, s, r)."
    trans, nstate = mach
    left = [list(r) for r in cert_l]   # left[i][x] -> j or None
    right = [list(r) for r in cert_r]
    nl = len(left)
    nr = len(right)
    start = (0, 0, 0, 0)
    seen = {start}
    stack = [start]
    while stack:
        l, q, s, r = stack.pop()
        t = trans.get((q, s))
        if t is None:
            return None
        w, mv, q2 = t
        if mv == 1:
            l2 = left[l][w] if l < nl else None
            if l2 is None:
                return None
            # pop nearest right cell s2 with right[r2][s2] == r
            for r2 in range(nr):
                for s2 in range(2):
                    if right[r2][s2] == r:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
        else:
            r2 = right[r][w] if r < nr else None
            if r2 is None:
                return None
            for l2 in range(nl):
                for s2 in range(2):
                    if left[l2][s2] == l:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
    return [list(c) for c in seen]


def cps_certificate(mach, left, right, contexts):
    return {
        "kind": "cps",
        "left": [list(row) for row in left],
        "right": [list(row) for row in right],
        "contexts": [list(c) for c in contexts],
    }


# ---------------- DFA enumeration for a half-tape ----------------

def dfa_rows(n):
    """All deterministic transition tables with n states, entries in {0..n-1}->0..n-1.
       State 0 on symbol 0 must go to 0 (all-blank half-tape loops)."""
    for entries in product(range(n), repeat=2*n):
        ok = True
        row = []
        for i in range(n):
            a, b = entries[2*i], entries[2*i+1]
            row.append([a, b])
        if row[0][0] != 0:
            ok = False
        if ok:
            yield row


def has_halt_from_blank(mach, table):
    """Does the machine halt if the half-tape DFA starts in state 0 and reads 0 forever?
       We only care about whether a halting transition is reachable in the closed
       context closure. But the search prunes by 'blank tape can lead to halt'.
       Here we do a quick check of the pair: if context [0,0,0,0] forces halt,
       the closure returns None. We just enumerate and test."""
    return None


def load_machine(tm):
    trans, nstate = parse_mach(tm)
    return trans, nstate


# ---------------- main decider ----------------

NAME = "dfa_search"

def decide(tm):
    mach = parse_mach(tm)
    trans, nstate = mach

    # Precompute halting info for pruning (very coarse).
    halting_states = set()
    for (q, s), t in trans.items():
        if t is None:
            halting_states.add((q, s))

    # Enumerate half-tape DFAs of size 1..4 (state 0 loops on 0).
    max_states = 4
    for n in range(1, max_states + 1):
        for left in dfa_rows(n):
            # right automaton: we try the same DFA first (symmetric machines),
            # then also enumerate a distinct one for asymmetric machines.
            for right in dfa_rows(n):
                # quick prune: if state 0 in left on 1 leads to a state whose
                # transitions eventually force a halting context with right's blank state,
                # the closure will return None anyway; skip to save time.
                ctxs = build_cps(left, right, mach)
                if ctxs is None:
                    continue
                # Verify no halting transition is reachable by construction of closure:
                # closure returns None iff a halting context is forced. So if we get here,
                # we have a certificate.
                cert = cps_certificate(mach, left, right, ctxs)
                return cert
    return None


def module_init():
    pass


if __name__ == 'main':
    import sys
    tm = sys.argv[1]
    print(decide(tm))
