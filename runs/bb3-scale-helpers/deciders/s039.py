import itertools
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure

# Enumerate small push automata: state 0 loops on symbol 0 and maps 1 -> some state,
# but also allow richer tables (state 0 may map 1 to itself). We build tables of size 1..3
# states; left[i][x] = next state or None.
def enum_tables(n):
    # states 0..n-1; state 0 must satisfy push(0,0)=0 (blank stays blank on 0).
    # Each state has two entries (for symbol 0 and 1), each entry is None or a state.
    if n == 1:
        # only state 0; must map 0->0; 1->0 is forced to avoid null on symbol 1
        # (closure requires a state to exist after pushing any cell we read).
        # We allow None for symbol 1 only if the closure never pushes 1 through it.
        return [[[0, None]], [[0, 0]]]
    out = []
    choices = [None] + list(range(n))
    for entries in itertools.product(choices, repeat=2 * n):
        # state 0 on symbol 0 must be 0
        if entries[0] != 0:
            continue
        # build table
        table = []
        ok = True
        for i in range(n):
            row = [entries[2 * i], entries[2 * i + 1]]
            table.append(row)
        out.append(table)
    return out


def build_push(table):
    def push(state, symbol):
        if state is None:
            return None
        return table[state][symbol]
    return push


def try_closure(tm, left_table, right_table, cap=200000):
    t, ns, nsym = parse(tm)
    # blank states must stay blank on symbol 0
    if left_table[0][0] != 0 or right_table[0][0] != 0:
        return None
    lp = build_push(left_table)
    rp = build_push(right_table)
    try:
        cert = closure(lp, rp, blank_left=0, blank_right=0, cap=cap)
    except Exception:
        return None
    if cert is None:
        return None
    try:
        check(tm, cert)
    except Reject:
        return None
    return cert


def decide(tm):
    t, ns, nsym = parse(tm)
    # quick check: does the machine halt quickly?
    halted, steps, st, pos, tape = run(tm, 2)
    if halted:
        return None
    sizes = [1, 2, 3]
    cnt = 0
    for n in sizes:
        tables = enum_tables(n)
        for lt in tables:
            for rt in tables:
                # skip identical trivial pairs early? No, just try.
                cnt += 1
                cert = try_closure(tm, lt, rt, cap=200000)
                if cert is not None:
                    return cert
    # If enumeration was too big for 3 states, we may have exhausted time; return None.
    return None
