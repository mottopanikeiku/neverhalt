import sys
from collections import deque


def _parse_machine(tm):
    rows = tm.split("_")
    states = rows[0].split("?")
    n_states = 0
    name2idx = {}
    for row in rows:
        for i, s in enumerate(row):
            if s != "-":
                if s not in name2idx:
                    name2idx[s] = n_states
                    n_states += 1
    table = {}
    for si, row in enumerate(rows):
        for col in range(3):
            cell = row[col]
            if cell == "-":
                continue
            nxt = cell
            if nxt == "Z" or nxt == "z":
                continue
            if nxt not in name2idx:
                continue
            w = 1 if cell == "1" else 0
            q = int(cell)
            m = 1 if q == 1 else -1
            table[(si, col)] = (w, m, name2idx[nxt])
    return table, n_states


def _machines_states(tm):
    rows = tm.split("_")
    seen = set()
    order = []
    for row in rows:
        for ch in row:
            if ch not in seen:
                seen.add(ch)
                order.append(ch)
    return order


def _halting_states(tm):
    rows = tm.split("_")
    names = _machines_states(tm)
    idx = {ch: i for i, ch in enumerate(names)}
    halting = set()
    for si, row in enumerate(rows):
        for col in range(3):
            if row[col] == "-":
                halting.add((si, col))
                continue
            ch = row[col]
            if ch == "Z" or ch == "z":
                halting.add((si, col))
    return halting


def _determinize_half(tm, side, max_states):
    """Enumerate far-to-head DFAs for one half-tape.

    side=0 left half-tape: machine reads cells left of the head, far away
    towards the head.  A DFA state is reached from state 0 by reading a
    sequence of symbols far-to-head.  left[i][x] is the state after reading x.
    Returns a list of (transitions, n) where transitions is a list of lists
    (or list of None) and left[0][0] == 0 is enforced.
    """
    rows = tm.split("_")
    states = _machines_states(tm)
    idx = {ch: i for i, ch in enumerate(states)}
    n_m = len(states)

    def mtrans(q, x):
        for si, name in enumerate(states):
            if idx[name] != q:
                continue
            cell = rows[si][x]
            if cell == "-":
                return None
            if cell == "Z":
                return None
            w = 1 if cell == "1" else 0
            q2 = int(cell)
            nxt = cell
            # cell is one of '0','1','z'? bbchallenge symbol is char; for '0'/'1' the char is the symbol
            return (w, q2, nxt)

    # We do not need the machine's transitions here: the DFA is over symbols
    # written on the tape.  The language of the half-tape is "what symbol
    # sequences can appear"; the fixpoint below only uses the automaton's own
    # transitions to close contexts, so any DFA can be tried.
    return _enumerate_dfas(side, max_states)


def _enumerate_dfas(side, max_states):
    out = []
    # DFA over symbols {0,1}, state 0 loops on symbol 0 (blank tape).
    for n in range(1, max_states + 1):
        # enumerate all transition tables with n states, canonical-ish:
        # state 0 fixed to loop on 0; other entries arbitrary.
        entries = n * 2
        # Limit enumeration; for n>2 this is huge, so only n<=2 full here.
        if n > 2:
            break
        idxs = [(i, x) for i in range(n) for x in range(2)]
        # fix (0,0) = 0
        idxs = [e for e in idxs if e != (0, 0)]
        total = n ** len(idxs)
        if total > 20000:
            total = 20000
        for code in range(total):
            c = code
            trans = [[None, None] for _ in range(n)]
            trans[0][0] = 0
            for (i, x) in idxs:
                trans[i][x] = c % n
                c //= n
            out.append(trans)
    return out


def _close_contexts(tm, left, right, max_ctx=200000):
    rows = tm.split("_")
    states = _machines_states(tm)
    idx = {ch: i for i, ch in enumerate(states)}
    n_m = len(states)
    table = {}
    halting = set()
    for si, row in enumerate(states):
        for col in range(3):
            cell = row[col]
            if cell == "-" or cell == "Z" or cell == "z":
                halting.add((si, col))
                continue
            w = 1 if cell == "1" else 0
            q2 = int(cell)
            nxt = cell
            if nxt not in idx:
                halting.add((si, col))
                continue
            table[(si, col)] = (w, q2, idx[nxt])

    n_left = len(left)
    n_right = len(right)

    # context key (l, q, s, r)
    start = (0, 0, 0, 0)
    seen = {start}
    dq = deque([start])
    while dq:
        (l, q, s, r) = dq.popleft()
        if (q, s) in halting or (q, s) not in table:
            return None
        w, q2, _ = table[(q, s)]
        if w == 1:
            l2 = left[l][w]
            if l2 is None:
                return None
            new = []
            for r2 in range(n_right):
                for s2 in range(2):
                    if right[r2][s2] == r:
                        key = (l2, q2, s2, r2)
                        if key not in seen:
                            seen.add(key)
                            new.append(key)
                            if len(seen) > max_ctx:
                                return None
            for key in new:
                dq.append(key)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            new = []
            for l2 in range(n_left):
                for s2 in range(2):
                    if left[l2][s2] == l:
                        key = (l2, q2, s2, r2)
                        if key not in seen:
                            seen.add(key)
                            new.append(key)
                            if len(seen) > max_ctx:
                                return None
            for key in new:
                dq.append(key)
    return seen


def decide(tm: str):
    try:
        table, n_states = _parse_machine(tm)
    except Exception:
        return None

    # 1) tiny DFA pairs first
    for n in (1, 2, 3):
        try:
            lefts = _enumerate_dfas(0, n)
        except Exception:
            lefts = []
        try:
            rights = _enumerate_dfas(1, n)
        except Exception:
            rights = []
        if not lefts or not rights:
            continue
        for left in lefts[:400]:
            for right in rights[:400]:
                ctx = _close_contexts(tm, left, right)
                if ctx is None:
                    continue
                # emit certificate
                left_t = [[None if v is None else v for v in row] for row in left]
                right_t = [[None if v is None else v for v in row] for row in right]
                contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
                return {"kind": "cps", "left": left_t, "right": right_t, "contexts": contexts}
    return None


if __name__ == "__main__":
    pass
