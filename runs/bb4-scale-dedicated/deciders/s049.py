import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(100000)


def _parse_table(tm):
    table, n_states, _ = parse(tm)
    return table, n_states


def _mov_str(move):
    return "+" if move == 1 else "-"


def _build_contexts(table, n_states, left, right, ctxs, halting):
    """Closed-context fixpoint for a candidate automaton pair.
    left, right: transition tables with None for unused transitions.
    ctxs: set of (l, q, s, r). Returns (contexts, ok) where ok is False if
    any context is halting (rejected) or the closure fails to close within
    the kernel's limits.
    """
    if (0, 0, 0, 0) not in ctxs:
        return set(), False
    work = list(ctxs)
    seen = set(ctxs)
    while work:
        l, q, s, r = work.pop()
        if q in halting:
            return set(), False
        tr = None
        for sym in (0, 1):
            if (q, sym) in table:
                tr = (sym, table[(q, sym)])
                break
        if tr is None:
            return set(), False
        w, (w2, mv, q2) = tr
        if mv == 1:
            l2 = left[l][w]
            if l2 is None:
                return set(), False
            for r2 in range(len(right)):
                for s2 in (0, 1):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if seen.__contains__(c):
                            continue
                        seen.add(c)
                        work.append(c)
        else:
            r2 = right[r][w]
            if r2 is None:
                return set(), False
            for l2 in range(len(left)):
                for s2 in (0, 1):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if seen.__contains__(c):
                            continue
                        seen.add(c)
                        work.append(c)
    return seen, True


def _emit(tm, left, right, contexts):
    cert = {
        "kind": "cps",
        "left": [[(row[i] if row[i] is not None else None) for i in range(len(row))] for row in left],
        "right": [[(row[i] if row[i] is not None else None) for i in range(len(row))] for row in right],
        "contexts": [[l, q, s, r] for (l, q, s, r) in contexts],
    }
    try:
        check(tm, cert)
    except Reject:
        return None
    return cert


def _iter_tables(n_states, symbols=2):
    """All transition tables for n_states states, 2 symbols, no halting, with
    state 0 looping on symbol 0 (blank tape state) as in the hint."""
    states = list(range(n_states))
    # We enumerate per (state, symbol) target choices lazily via recursion.
    total = n_states * symbols
    ranges = [states for _ in range(total)]
    for combo in _product(ranges):
        table = [[None, None] for _ in range(n_states)]
        for idx, tgt in enumerate(combo):
            st = idx // symbols
            sym = idx % symbols
            table[st][sym] = tgt
        table[0][0] = 0  # state 0 loops on blank
        yield table


def _product(ranges):
    if not ranges:
        yield []
        return
    for head in ranges[0]:
        for tail in _product(ranges[1:]):
            yield [head] + tail


def _prune_tables(tm, table, halting):
    """Prune a candidate automaton pair immediately if the blank tape (state 0)
    is forced to reach a halting context. Returns True if the pair is still
    plausible."""
    return True


def _try_pair(tm, table, n_states, halting):
    # Candidate: left = table, right = table (same structure, mirror roles).
    # First try same automaton on both sides; then a fresh small right one.
    for right_size in range(1, min(4, n_states + 2) + 1):
        for right in _iter_tables(right_size):
            # require state 0 loops on 0
            if right[0][0] != 0:
                continue
            ctxs, ok = _build_contexts(table, n_states, table, right, {(0, 0, 0, 0)}, halting)
            if ok:
                cert = _emit(tm, table, right, ctxs)
                if cert is not None:
                    return cert
    return None


def _search_left(tm, table, n_states, halting, deadline):
    for right_size in range(1, 5):
        for right in _iter_tables(right_size):
            if right[0][0] != 0:
                continue
            ctxs, ok = _build_contexts(table, n_states, table, right, {(0, 0, 0, 0)}, halting)
            if ok:
                cert = _emit(tm, table, right, ctxs)
                if cert is not None:
                    return cert
    return None


def _search_right(tm, table, n_states, halting, deadline):
    # Mirror: same enumeration, roles swapped.
    for left_size in range(1, 5):
        for left in _iter_tables(left_size):
            if left[0][0] != 0:
                continue
            ctxs, ok = _build_contexts(table, n_states, left, table, {(0, 0, 0, 0)}, halting)
            if ok:
                cert = _emit(tm, left, table, ctxs)
                if cert is not None:
                    return cert
    return None


def decide(tm):
    import time

    deadline = time.time() + 0.45
    table, n_states = _parse_table(tm)
    halting = set()
    for (q, s), tr in table.items():
        pass
    # halting: any transition absent from the table for a state/symbol pair
    # In parse(), halting transitions are absent. Find states and symbols.
    max_state = max(table.keys())
    halting_states = set(range(max_state + 1))
    # A state q is a halting candidate if (q, 0) or (q, 1) is absent.
    halting = set()
    for q in halting_states:
        for s in (0, 1):
            if (q, s) not in table:
                halting.add(q)
    # Search small automata, growing state count.
    for n in range(1, 4):
        if time.time() > deadline:
            return None
        for cand in _iter_tables(n):
            if time.time() > deadline:
                return None
            cert = _search_left(tm, cand, n, halting, deadline)
            if cert is not None:
                return cert
            cert = _search_right(tm, cand, n, halting, deadline)
            if cert is not None:
                return cert
    return None


if __name__ == "__main__":
    import json
    tm = "1RB0LB_1LC0RD_---1LA_1RA1LD"
    print(json.dumps(decide(tm)))
