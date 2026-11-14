import sys
from collections import deque

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(100000)


def _pair_closure(left, right, table, n_states, contexts_cap=200000):
    """Closed context set for automata pair (left, right) and the machine table.

    left:  list of rows, left[i][x] -> state or None
    right: list of rows, right[i][x] -> state or None
    table: dict (state, symbol) -> (write, move, next_state)
    Returns (contexts, ok) where ok is False if a halting context is forced.
    """
    start = (0, 0, 0, 0)
    seen = {start}
    queue = deque([start])
    contexts = [start]
    while queue:
        l, q, s, r = queue.popleft()
        tr = table.get((q, s))
        if tr is None:
            return contexts, False
        w, move, q2 = tr
        if move == 1:
            l2 = left[l][w]
            if l2 is None:
                return contexts, False
            for r2 in range(len(right)):
                row = right[r2]
                if row[s] == r:
                    ctx = (l2, q2, s, r2)
                    if ctx not in seen:
                        seen.add(ctx)
                        contexts.append(ctx)
                        queue.append(ctx)
        else:
            r2 = right[r][w]
            if r2 is None:
                return contexts, False
            for l2 in range(len(left)):
                row = left[l2]
                if row[s] == l:
                    ctx = (l2, q2, s, r2)
                    if ctx not in seen:
                        seen.add(ctx)
                        contexts.append(ctx)
                        queue.append(ctx)
        if len(contexts) > contexts_cap:
            return contexts, False
    return contexts, True


def _reverse_dfa(rows, n_states):
    """Reverse of a DFA over symbols {0,1}; returns rows over reversed reads
    (far-to-head becomes head-to-far when the input is read backwards).
    """
    rev = [[None, None] for _ in range(n_states)]
    for i in range(n_states):
        for x in (0, 1):
            j = rows[i][x]
            if j is not None:
                rev[j][x] = i
    return rev


def _can_reach_halt(table, n_states):
    """Set of (state, symbol) pairs from which some halting transition is
    reachable via a finite number of steps in the table."""
    reach = set()
    changed = True
    while changed:
        changed = False
        for (q, s), (w, move, q2) in list(table.items()):
            if (q, s) in reach:
                continue
            nxt = (q2, w)
            if nxt not in reach and nxt in table:
                reach.add((q, s))
                changed = True
    # also pairs whose immediate successor is a halting transition
    for (q, s), (w, move, q2) in list(table.items()):
        nxt = (q2, w)
        if nxt not in table:
            reach.add((q, s))
    return reach


def _enumerate_dfa(max_states, max_rows=3):
    """Yield DFA row tables (list of [a0, a1]) with up to max_states reachable
    states, canonical BFS order, symbol 0 self-loop at state 0 per hint."""
    out = []
    # state 0 loops on 0
    def rec(rows, n):
        if n >= 2:
            out.append([list(r) for r in rows])
        if n >= max_states:
            return
        # add a new state
        new_rows = [list(r) for r in rows] + [[None, None]]
        # canonical: transitions of new state to existing states or itself
        n2 = n + 1
        for a in range(n2 + 1):
            for b in range(n2 + 1):
                nr = [list(r) for r in new_rows]
                nr[n][0] = a
                nr[n][1] = b
                # canonical BFS check: reachable set from 0
                reach = {0}
                q = deque([0])
                while q:
                    i = q.popleft()
                    for x in (0, 1):
                        j = nr[i][x]
                        if j is not None and j not in reach:
                            reach.add(j)
                            q.append(j)
                if len(reach) == n2:
                    rec(nr, n2)
    # start from a 1-state DFA that loops on 0 and may go anywhere on 1
    for b in range(2):
        rec([[0, b]], 1)
    return out


def _dfa_from_rows(rows, n_states):
    """Keep only transitions used in the closure; null elsewhere.
    """
    used = [[None, None] for _ in range(n_states)]
    for i in range(n_states):
        for x in (0, 1):
            j = rows[i][x]
            if j is not None:
                used[i][x] = j
    return used


def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # quick reject: machine halts within budget -> not our job
    try:
        halted, steps, state, pos, tape = run(tm, 20000)
        if halted:
            return None
    except Exception:
        return None

    halting_pairs = _can_reach_halt(table, n_states)

    # 1) try n-gram automata directly (small window) first
    for n in range(1, 4):
        rows = [[None, None] for _ in range(n)]
        # n-gram: state = last n-1 cells read so far; simplest: state 0 all blank
        # build the standard n-gram DFA: state i means last i cells were all 0
        # We approximate with a DFA that counts leading zeros up to n-1.
        r = []
        r.append([0, 1])
        for i in range(1, n):
            r.append([i, 1])
        if n == 1:
            r = [[0, 1]]
        left = r
        right = r
        contexts, ok = _pair_closure(left, right, table, n_states)
        if ok and len(contexts) <= 200000 and contexts and contexts[0] == (0, 0, 0, 0):
            cert = {"kind": "cps", "left": [list(x) for x in left],
                    "right": [list(x) for x in right],
                    "contexts": [list(c) for c in contexts]}
            try:
                from neverhalt.kernel import check
                check(tm, cert)
                return cert
            except Reject:
                pass
            except Exception:
                pass

    # 2) search over DFAs, growing state count, canonical order
    # limit total work
    deadline_ops = 3000000
    ops = 0
    max_states = 6
    for size in range(1, max_states + 1):
        dfa_list = _enumerate_dfa(size)
        # sort by number of used transitions then by rows
        dfa_list.sort(key=lambda rs: (sum(1 for r in rs for x in r if x is not None), rs))
        for dl in dfa_list:
            if ops > deadline_ops:
                return None
            ops += 1
            left = dl
            # right: same DFA reversed (far-to-head), i.e. reverse rows
            # A cheap family: right = reverse of left (palindrome search)
            right = _reverse_dfa(left, len(left))
            if right[0][0] != 0:
                continue
            # prune: if the blank tape context (0,0,0,0) forces a halt, skip
            contexts, ok = _pair_closure(left, right, table, n_states)
            if not ok:
                continue
            if len(contexts) > 200000:
                continue
            if not contexts or contexts[0] != (0, 0, 0, 0):
                continue
            cert = {"kind": "cps", "left": [list(x) for x in left],
                    "right": [list(x) for x in right],
                    "contexts": [list(c) for c in contexts]}
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
            except Exception:
                pass

    # 3) reverse-determinize attempt: build right DFA as reverse of left
    #    and try all pairs of small DFAs up to 4 states
    small = []
    for size in range(1, 5):
        small.extend(_enumerate_dfa(size))
    seen_pairs = set()
    for dl in small:
        if ops > deadline_ops:
            return None
        ops += 1
        for dr in small:
            key = (tuple(map(tuple, dl)), tuple(map(tuple, dr)))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            if dr[0][0] != 0 or dl[0][0] != 0:
                continue
            contexts, ok = _pair_closure(dl, dr, table, n_states)
            if not ok or len(contexts) > 200000:
                continue
            if not contexts or contexts[0] != (0, 0, 0, 0):
                continue
            cert = {"kind": "cps", "left": [list(x) for x in dl],
                    "right": [list(x) for x in dr],
                    "contexts": [list(c) for c in contexts]}
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
            except Exception:
                pass

    return None


if __name__ == "__main__":
    import json
    tm = sys.argv[1] if len(sys.argv) > 1 else ""
    r = decide(tm)
    print(json.dumps(r) if r else None)
