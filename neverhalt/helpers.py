"""Untrusted helpers deciders may import. Nothing here is trusted: the kernel re-checks every certificate."""
from __future__ import annotations


def closure(table, k, push_left, push_right, blank_left, blank_right, cap=20000):
    """Smallest closed context set for two automata given as push functions -> a `cps` certificate, or None.

    table: from neverhalt.tm.parse. push_left(state, symbol) / push_right(state, symbol): the automaton state after
    the half-tape grows by one cell next to the head; states are any hashable values; blank_left / blank_right: the
    states of an all-blank half-tape (push(blank, 0) must return blank). Returns None if a halting context is
    reachable or more than `cap` contexts appear. Only transitions the closure uses become part of the certificate.
    """
    edges = [{(blank_left, 0): blank_left}, {(blank_right, 0): blank_right}]
    before = [{blank_left: {(blank_left, 0)}}, {blank_right: {(blank_right, 0)}}]
    start = (blank_left, 0, 0, blank_right)
    contexts = {start}
    on_side = [{blank_left: [start]}, {blank_right: [start]}]
    todo = [start]
    while todo:
        ctx = todo.pop()
        l, q, s, r = ctx
        tr = table.get((q, s))
        if tr is None:
            return None
        w, d, q2 = tr
        side = 0 if d > 0 else 1  # the side that receives the written symbol
        src = l if d > 0 else r
        dst = (push_left if d > 0 else push_right)(src, w)
        if (src, w) not in edges[side]:
            edges[side][(src, w)] = dst
            before[side].setdefault(dst, set()).add((src, w))
            todo.extend(on_side[side].get(dst, ()))  # contexts popping from dst have a new predecessor
        for prev, s2 in list(before[1 - side].get(r if d > 0 else l, ())):
            new = (dst, q2, s2, prev) if d > 0 else (prev, q2, s2, dst)
            if new not in contexts:
                contexts.add(new)
                on_side[0].setdefault(new[0], []).append(new)
                on_side[1].setdefault(new[3], []).append(new)
                todo.append(new)
        if len(contexts) > cap:
            return None
    ids = [{blank_left: 0}, {blank_right: 0}]
    tables = []
    for side in (0, 1):
        for (src, _), dst in edges[side].items():
            ids[side].setdefault(src, len(ids[side]))
            ids[side].setdefault(dst, len(ids[side]))
        rows = [[None] * k for _ in ids[side]]
        for (src, x), dst in edges[side].items():
            rows[ids[side][src]][x] = ids[side][dst]
        tables.append(rows)
    return {"kind": "cps", "left": tables[0], "right": tables[1],
            "contexts": [[ids[0][l], q, s, ids[1][r]] for l, q, s, r in contexts]}
