import sys
from neverhalt.tm import parse, run

def build_dfa(n, max_states, allowed_syms=None):
    # enumerate deterministic automata tables: list of rows, row[x] = next state or None
    # state 0 loops on 0; we allow rows to be partial (None = dead)
    rows = []
    # first row: state 0: on 0 -> 0, on 1 -> some state (we enumerate)
    # Represent a table as tuple of rows, each row a tuple of length n (0..max_states-1 or -1 for dead)
    # We enumerate in order of increasing number of distinct live states reachable, BFS-canonical.
    # For simplicity: enumerate all tables with at most max_states live states, ordered by (num states, lexicographic canonical BFS).
    def canon(table):
        # table: list of rows, row[sym] = next state index (0..max_states-1) or -1
        # BFS from 0, assign canonical ids; unreachable states dropped.
        start = 0
        order = []
        seen = {start}
        stack = [start]
        while stack:
            st = stack.pop()
            order.append(st)
            row = table[st]
            for nxt in row:
                if nxt != -1 and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        mapping = {st: i for i, st in enumerate(order)}
        new_table = []
        for i, st in enumerate(order):
            new_table.append(tuple(mapping.get(x, -1) for x in table[st]))
        return tuple(new_table)
    results = []
    # enumerate row choices for up to max_states states
    import itertools
    choices = list(range(max_states)) + [-1]
    # enumerate tables of size max_states x n
    for flat in itertools.product(choices, repeat=max_states * n):
        table = [tuple(flat[i*n:(i+1)*n]) for i in range(max_states)]
        # prune: state 0 must loop on symbol 0
        if table[0][0] != 0:
            continue
        c = canon(table)
        if c not in results:
            results.append(c)
    # sort by number of reachable states then lexicographic
    results.sort(key=lambda t: (len(t), t))
    return results

def closure_contexts(tm, table, n_states, n_symbols):
    # compute transitions
    # tm table: dict (state, sym) -> (write, move, next_state)
    # contexts: (l, q, s, r) where l is automaton state of left half-tape reading far->head,
    # r likewise for right half-tape. We use the given DFA table for one side and build the other side.
    # Here we implement the kernel's cps check logic as a closure computation for a fixed pair of automata.
    # Returns None if a halting context appears, else the context list.
    # Automaton row[x]: next state or None (dead). Symbol 0 must go to 0 from 0.
    # For kernel: left[i][x] is state reached from i on symbol x, or null.
    # We'll represent None as -1 internally but convert later.
    pass

def decide(tm: str):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # For each state/symbol, get transition or None
    def trans(q, s):
        t = table.get((q, s))
        if t is None:
            return None
        w, mv, q2 = t
        return w, mv, q2
    # We implement the fixpoint for a given pair of automata (left_table, right_table)
    def close(left_rows, right_rows):
        # left_rows: list of rows, row[x] = next state or -1
        # right_rows similarly
        # contexts: set of (l, q, s, r)
        # start with (0, 0, 0, 0)
        ctx = set()
        ctx.add((0, 0, 0, 0))
        changed = True
        while changed:
            changed = False
            new = set()
            for (l, q, s, r) in list(ctx):
                tr = trans(q, s)
                if tr is None:
                    # halting context: reject
                    return None
                w, mv, q2 = tr
                if mv > 0:
                    # right move: l2 = left_rows[l][w]
                    if w >= n_symbols or left_rows[l][w] == -1:
                        return None
                    l2 = left_rows[l][w]
                    # for every pair (r2, s2) with right_rows[r2][s2] == r
                    for r2 in range(len(right_rows)):
                        for s2 in range(n_symbols):
                            if right_rows[r2][s2] == r:
                                c = (l2, q2, s2, r2)
                                if c not in ctx:
                                    ctx.add(c)
                                    changed = True
                else:
                    # left move: r2 = right_rows[r][w]
                    if w >= n_symbols or right_rows[r][w] == -1:
                        return None
                    r2 = right_rows[r][w]
                    for l2 in range(len(left_rows)):
                        for s2 in range(n_symbols):
                            if left_rows[l2][s2] == l:
                                c = (l2, q2, s2, r2)
                                if c not in ctx:
                                    ctx.add(c)
                                    changed = True
            new = ctx
        # check all contexts non-halting already ensured by trans check
        return ctx
    # We need to search over pairs of automata. To keep time, start with small ones.
    # Build candidate automata sets
    import itertools
    def enum_automata(max_states, max_syms=2):
        # only symbols 0 and 1
        n = 2
        results = []
        def canon(table):
            start = 0
            order = []
            seen = {start}
            stack = [start]
            while stack:
                st = stack.pop()
                order.append(st)
                row = table[st]
                for nxt in row:
                    if nxt != -1 and nxt not in seen:
                        seen.add(nxt)
                        stack.append(nxt)
            mapping = {st: i for i, st in enumerate(order)}
            new_table = []
            for i, st in enumerate(order):
                new_table.append(tuple(mapping.get(x, -1) for x in table[st]))
            return tuple(new_table)
        choices = list(range(max_states)) + [-1]
        for flat in itertools.product(choices, repeat=max_states * n):
            table = [tuple(flat[i*n:(i+1)*n]) for i in range(max_states)]
            if table[0][0] != 0:
                continue
            c = canon(table)
            if c not in results:
                results.append(c)
        results.sort(key=lambda t: (len(t), t))
        return results
    for ms in (1, 2, 3):
        automata = enum_automata(ms)
        for left_rows in automata:
            for right_rows in automata:
                ctx = close([list(r) for r in left_rows], [list(r) for r in right_rows])
                if ctx is None:
                    continue
                # found a certificate: convert to kernel format
                # left/right: transition tables with null for dead
                def to_kernel(rows):
                    out = []
                    for row in rows:
                        out.append([None if x == -1 else x for x in row])
                    return out
                left_k = to_kernel(left_rows)
                right_k = to_kernel(right_rows)
                contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
                # ensure [0,0,0,0] present
                if [0, 0, 0, 0] not in contexts:
                    continue
                return {"kind": "cps", "left": left_k, "right": right_k, "contexts": contexts}
    return None


if __name__ == "__main__":
    import sys
    from neverhalt.kernel import check, Reject
    tm = sys.argv[1]
    cert = decide(tm)
    print(cert)
    if cert:
        try:
            print(check(tm, cert))
        except Reject as e:
            print("REJECT", e)
