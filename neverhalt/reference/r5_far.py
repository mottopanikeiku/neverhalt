"""Finite Automata Reduction, compiled into the kernel's two-sided CPS format.

Fix a far-to-head DFA on one half-tape. A saturated NFA then recognizes
configurations that can reach a halt in this abstraction. Reverse-subset
construction gives the other far-to-head DFA. The complement is an inductive
invariant; r3's forward closure retains only its reachable contexts and edges.

Search uses BFS-canonical DFA names and prunes partial DFAs as soon as their
already-known edges admit the blank configuration into the halting language.
See Justin Blanchard's FAR: https://discuss.bbchallenge.org/t/123 .
"""

import time

from neverhalt.helpers import closure
from neverhalt.tm import parse

NAME = "finite automata reduction"


def _saturate(dfa, transitions, n, previous=None):
    """Return the backward halting NFA, or None if blank is already unsafe."""
    size = n * len(dfa) + 1
    if previous is None:
        edges = [[0] * size for _ in range(2)]
        edges[0][0] = edges[1][0] = 1
        for l in range(len(dfa)):
            for q in range(n):
                for s in range(2):
                    if transitions[q * 2 + s] is None:
                        edges[s][1 + l * n + q] = 1
    else:
        edges = [previous[0][:], previous[1][:]]
    rules = []
    for l, row in enumerate(dfa):
        for qs, tr in enumerate(transitions):
            if tr is None:
                continue
            q, s = divmod(qs, 2)
            w, d, q2 = tr
            if d > 0:
                if row[w] >= 0:
                    edges[s][1 + l * n + q] |= 1 << (1 + row[w] * n + q2)
            else:
                for b, dst in enumerate(row):
                    if dst >= 0:
                        rules.append((s, 1 + dst * n + q, b, 1 + l * n + q2, w))
    while True:
        # Does the NFA accept the all-zero initial tape? Sink 0 loops on zero.
        reached = 2
        pending = 2
        while pending:
            bit = pending & -pending
            pending ^= bit
            new = edges[0][bit.bit_length() - 1] & ~reached
            if new & 1:
                return None
            reached |= new
            pending |= new
        changed = False
        for s, src, b, middle, w in rules:
            targets = edges[b][middle]
            value = edges[s][src]
            while targets:
                bit = targets & -targets
                targets ^= bit
                value |= edges[w][bit.bit_length() - 1]
            if value != edges[s][src]:
                edges[s][src] = value
                changed = True
        if not changed:
            return edges


def _certificate(table, dfa, edges, mirrored):
    """Reverse the unsafe NFA; its subset states read the far end first."""
    def push(subset, symbol):
        result = 0
        for i, targets in enumerate(edges[symbol]):
            if targets & subset:
                result |= 1 << i
        return result

    blank = 1
    while True:
        expanded = push(blank, 0)
        if expanded == blank:
            break
        blank = expanded
    push_dfa = lambda state, symbol: dfa[state][symbol]
    if mirrored:
        return closure(table, 2, push, push_dfa, blank, 0, cap=100000)
    return closure(table, 2, push_dfa, push, 0, blank, cap=100000)


def _search(table, transitions, n, m, mirrored, deadline):
    dfa = [[-1, -1] for _ in range(m)]
    dfa[0][0] = 0
    initial = _saturate(dfa, transitions, n)
    if initial is None:
        return None

    def visit(position, used, edges):
        if time.monotonic() >= deadline:
            return None
        if position == 2 * m:
            if used != m:
                return None
            return _certificate(table, dfa, edges, mirrored)
        if position >= 2 * used:
            return None
        l, symbol = divmod(position, 2)
        for dst in range(min(used + 1, m)):
            dfa[l][symbol] = dst
            saturated = _saturate(dfa, transitions, n, edges)
            if saturated is not None:
                cert = visit(position + 1, max(used, dst + 1), saturated)
                if cert is not None:
                    return cert
        dfa[l][symbol] = -1
        return None

    return visit(1, 1, initial)


def decide(tm: str) -> dict | None:
    table, n, k = parse(tm)
    if k != 2:
        return None
    deadline = time.monotonic() + 18.0
    transitions = [table.get((q, s)) for q in range(n) for s in range(2)]
    mirror = [None if tr is None else (tr[0], -tr[1], tr[2]) for tr in transitions]
    for m in range(1, 11):
        for mirrored, rules in ((False, transitions), (True, mirror)):
            if time.monotonic() >= deadline:
                return None
            cert = _search(table, rules, n, m, mirrored, deadline)
            if cert is not None:
                return cert
    return None
