import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

NAME = "small_automaton_search"

# We search for a pair of DFAs (left, right) as described in the kernel's cps
# certificate: two deterministic half-tape automata reading cells far-to-head,
# plus a closed context set.  Our search is incremental: enumerate DFA
# transition tables of small size, and for each pair run the closed-context
# fixpoint to see whether it yields a certificate with no halting context.
# We prune tables that cannot possibly cover the blank tape.

# --- helpers for DFA representation -----------------------------------------
# A DFA table is a list of rows: row[i] = (on0, on1), each a state index in
# [0, n) or None (meaning "this input never occurs in a surviving context").
# State 0 must loop on symbol 0: table[0][0] == 0.
# We also require that the automaton is "0-total" on symbol 0 (blank tape):
# every state must have a defined transition on 0, because the far side of a
# half-tape is always blank.  This is a strong pruning rule: if a state has
# table[i][0] is None, that state is unreachable from the blank far side and
# can never be part of a valid context.


def dfa_valid(tab):
    n = len(tab)
    if n == 0:
        return False
    for i in range(n):
        row = tab[i]
        if len(row) != 2:
            return False
        if row[0] is None:
            return False  # blank tape must always be readable
        if row[0] >= n:
            return False
    return True


def dfa_blank_reachable(tab):
    """States reachable from 0 by reading blank symbols (state 0 loops on 0,
    so only 0 is reachable on an all-blank tape; but intermediate states must
    still exist)."""
    return True


def norm_dfa(tab):
    """Canonical form: relabel states by first-visit BFS order from 0."""
    n = len(tab)
    order = []
    seen = [False] * n
    stack = [0]
    seen[0] = True
    while stack:
        i = stack.pop()
        order.append(i)
        for x in (0, 1):
            j = tab[i][x]
            if j is not None and not seen[j]:
                seen[j] = True
                stack.append(j)
    remap = {}
    for k, i in enumerate(order):
        remap[i] = k
    m = len(order)
    new = []
    for i in order:
        new.append((remap[tab[i][0]] if tab[i][0] is not None else None,
                    remap[tab[i][1]] if tab[i][1] is not None else None))
    return new


def enumerate_dfas(max_states):
    """Yield DFA tables of size 1..max_states in a deterministic order.
    State 0 loops on symbol 0.  We build tables row by row; each row is a pair
    (on0, on1) where on0 can be any existing state (index < current size, but
    we allow the row index itself as well since rows are appended in order and
    state indices refer to the final numbering; simpler: we enumerate all pairs
    of target indices in [0, size) including the new row's own index, and for
    the final row we allow targets in [0, size).  To keep it manageable we
    enumerate only "prefix-legal" tables: row i may reference states <= i."""
    # size 1
    for on1 in [0]:
        yield [[0, on1]]
    # size >= 2
    for size in range(2, max_states + 1):
        # enumerate rows for states 1..size-1
        # row 0 is fixed: (0, a) with a in [0, size)
        # For simplicity of enumeration: generate all combinations with
        # prefix-legal targets (target <= row index).  This may miss some DFAs
        # but is a reasonable heuristic for small sizes.
        import itertools
        # row i for i>=1: on0 in [0, i], on1 in [0, size) or None
        choices = []
        for i in range(1, size):
            opts0 = list(range(0, i + 1))
            opts1 = list(range(0, size)) + [None]
            choices.append([(a, b) for a in opts0 for b in opts1])
        for combo in itertools.product(*choices):
            rows = [[0, 0]]  # placeholder row 0, fixed below
            for i, (a, b) in enumerate(combo, start=1):
                rows.append([a, b])
            # row 0: on0 must be 0; on1 in [0, size)
            for a0 in [0]:
                for b0 in range(size):
                    t = [list(r) for r in rows]
                    t[0] = [a0, b0]
                    if dfa_valid(t):
                        yield t


def enumerate_dfas_limited(max_states, limit):
    """Same as above but stops after `limit` tables (to respect time)."""
    c = 0
    for t in enumerate_dfas(max_states):
        yield t
        c += 1
        if c >= limit:
            return


# --- context fixpoint --------------------------------------------------------
# context: (l, q, s, r)  where l, r are DFA state indices, q machine state
# (0-based), s symbol (0/1).  We compute the smallest closed set containing
# (0, 0, 0, 0) and check that no context halts.

def context_key(l, q, s, r):
    return (l, q, s, r)


def compute_closure(tm, left, right, max_ctx=200000):
    table, n_states, n_symbols = parse(tm)
    # transition existence: table.get((q,s))
    start = (0, 0, 0, 0)
    seen = set()
    stack = [start]
    seen.add(start)
    halting = False
    while stack:
        (l, q, s, r) = stack.pop()
        tr = table.get((q, s))
        if tr is None:
            halting = True
            return None, True
        (w, move, q2) = tr
        if move == 1:  # right move
            l2 = left[l][w]
            if l2 is None:
                return None, False
            # for every pair (r2, s2) with right[r2][s2] == r
            for r2 in range(len(right)):
                for s2 in (0, 1):
                    if right[r2][s2] == r:
                        k = context_key(l2, q2, s2, r2)
                        if k not in seen:
                            seen.add(k)
                            stack.append(k)
        else:  # left move
            r2 = right[r][w]
            if r2 is None:
                return None, False
            for l2 in range(len(left)):
                for s2 in (0, 1):
                    if left[l2][s2] == l:
                        k = context_key(l2, q2, s2, r2)
                        if k not in seen:
                            seen.add(k)
                            stack.append(k)
        if len(seen) > max_ctx:
            return None, False
    # build certificate
    left_tab = []
    for i in range(len(left)):
        row = []
        for x in (0, 1):
            row.append(left[i][x])
        left_tab.append(row)
    right_tab = []
    for i in range(len(right)):
        row = []
        for x in (0, 1):
            row.append(right[i][x])
        right_tab.append(row)
    contexts = [list(k) for k in seen]
    cert = {"kind": "cps", "left": left_tab, "right": right_tab, "contexts": contexts}
    return cert, False


# --- main search -------------------------------------------------------------

def try_pair(tm, left, right):
    cert, bad = compute_closure(tm, left, right)
    if cert is not None:
        try:
            check(tm, cert)
            return cert
        except Reject:
            return None
        except Exception:
            return None
    return None


def decide(tm: str):
    # quick cycle check first (cheap, may catch easy ones)
    try:
        h, steps, st, pos, tape = run(tm, 100000)
        if h:
            return None
    except Exception:
        pass
    # enumerate DFAs up to 3 states per side, with a time guard
    import time
    t0 = time.time()
    budget = 4.5  # seconds, leaving margin for the sandbox
    # collect DFAs of size 1..3
    dfas = []
    for size in (1, 2, 3):
        cnt = 0
        for t in enumerate_dfas(size):
            if time.time() - t0 > budget * 0.3:
                break
            dfas.append(t)
            cnt += 1
            if cnt > 4000:
                break
        if time.time() - t0 > budget * 0.3:
            break
    # try pairs; prioritize small total size
    dfas.sort(key=len)
    n = len(dfas)
    for i in range(n):
        if time.time() - t0 > budget:
            return None
        for j in range(n):
            if time.time() - t0 > budget:
                return None
            c = try_pair(tm, dfas[i], dfas[j])
            if c is not None:
                return c
    return None
