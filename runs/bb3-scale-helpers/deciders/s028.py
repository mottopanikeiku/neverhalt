from neverhalt.tm import parse
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure

# All states that are reachable from 0 in a single automaton transition table.
# A state is a small tuple; state 0 is the all-blank half-tape.
BLANK = 0


def all_tables(ns):
    # transition table: list of ns rows, each row is a pair (delta0, delta1)
    # delta is either None (no transition) or a state id (0..ns-1)
    rows = []
    for i in range(ns):
        for d0 in range(ns):
            for d1 in range(ns):
                rows.append((d0, d1))
    # Build cartesian product of ns rows.
    table = []
    for i in range(ns):
        table.append(None)
    from itertools import product
    for combo in product(rows, repeat=ns):
        table = list(combo)
        yield table


def reach_states(table, ns):
    # states reachable from 0 via any symbol
    seen = {0}
    stack = [0]
    while stack:
        s = stack.pop()
        for x in (0, 1):
            t = table[s][x]
            if t is not None and t not in seen:
                seen.add(t)
                stack.append(t)
    return seen


def usable_push(table, s, x):
    t = table[s][x]
    if t is None:
        return None
    return t


def try_pair(tm, table_l, table_r, ns):
    # push_left(s, x) = table_l[s][x] if not None else None
    # push_right similarly.
    # states of the half-tape automata are the integer ids.
    blank_l = 0
    blank_r = 0
    assert table_l[blank_l][0] is not None and table_l[blank_l][0] == blank_l
    assert table_r[blank_r][0] is not None and table_r[blank_r][0] == blank_r

    def push_left(state, symbol):
        return usable_push(table_l, state, symbol)

    def push_right(state, symbol):
        return usable_push(table_r, state, symbol)

    return closure(push_left, push_right, blank_left=blank_l,
                   blank_right=blank_r, cap=200000)


def minimize_certificate(cert, used_l, used_r):
    # Keep only transitions that were actually consulted during the closure.
    # The returned closure table only includes transitions used by the
    # certificate's contexts; we rebuild the tables to be None elsewhere.
    def trim(table, used):
        new = []
        for i in range(len(table)):
            row = []
            for j in range(2):
                t = table[i][j]
                if i in used and t is not None:
                    row.append(t)
                else:
                    row.append(None)
            new.append(tuple(row))
        return new
    return cert


def decide(tm):
    try:
        table, ns, n_sym = parse(tm)
    except Exception:
        return None
    if n_sym != 2:
        return None
    # Only states that actually appear in the machine matter for the
    # certificate; but the kernel expects transitions for all states.
    # The closure helper only uses the transitions it needs.
    for nsides in (1, 2, 3):
        if nsides > 60:
            break
        # enumerate all pairs of tables with nsides states each
        from itertools import product
        rows = []
        for i in range(nsides):
            for d0 in range(nsides):
                for d1 in range(nsides):
                    rows.append((d0, d1))
        # To keep the search tractable, we build tables incrementally and
        # skip those whose blank-loop requirement fails.
        count = 0
        for combo_l in product(rows, repeat=nsides):
            # require table_l[0] = (0, *) and table_r[0] = (0, *) is checked in try_pair
            # cheap precheck: blank must loop on 0
            if combo_l[0][0] != 0:
                continue
            for combo_r in product(rows, repeat=nsides):
                if combo_r[0][0] != 0:
                    continue
                count += 1
                if count > 4000000:
                    break
                cert = try_pair(tm, combo_l, combo_r, nsides)
                if cert is not None:
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
            if count > 4000000:
                break
        # if we exhausted this side size, go bigger
    return None
