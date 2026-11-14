#!/usr/bin/env python3
"""
Automated decider for the remaining Busy Beaver (3) holdouts.

Strategy: search for small half-tape automata (DFAs) that close the
context set without ever reaching a halting context.

For each surviving machine we:
  1. enumerate DFAs for the left half-tape in BFS-canonical order
     (states are numbered 0..k-1 in BFS discovery order from state 0),
     growing k from 1 to MAX_STATES, keeping only DFAs whose transition
     table is fully defined on the symbols the closure can ever read,
     and pruning any partial table as soon as a tape that can lead to a
     halt is forced to be the blank tape (state 0).
  2. build the corresponding right half-tape automaton by reversing and
     determinizing the NFA that accepts exactly the tapes which can
     reach a halting transition while reading right-to-head,
  3. close the context set [l, q, s, r] under the kernel's rules and
     emit a certificate if no halting context is forced.

Every returned certificate is re-checked with the trusted kernel before
being handed back, so a wrong construction is simply rejected.
"""

import sys
from collections import deque

from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


MAX_STATES = 9


# ---------------------------------------------------------------------
# DFA helpers
# ---------------------------------------------------------------------

def dfa_closure_steps(dfa, symbols=(0, 1)):
    """Yield (state, symbol, next_state, write) transitions of the DFA."""
    for q, row in enumerate(dfa):
        for x in symbols:
            if row[x] is not None:
                yield q, x, row[x]


def dfa_accepts_blank_path(dfa, symbols=(0, 1)):
    """True if the DFA can read a tape that is all blanks (state 0 forever)."""
    if dfa[0][0] != 0:
        return False
    return True


def enumerate_dfas(max_states, symbols=(0, 1)):
    """Enumerate DFAs in BFS-canonical order, smallest first.

    A DFA is a tuple of rows; row[q][x] is None if the transition is not
    used, else the target state.  State 0 is the blank half-tape and must
    satisfy row[0][0] == 0.
    """
    for k in range(1, max_states + 1):
        # enumerate assignments of transitions, but only those reachable
        # from state 0 in BFS order: state i may only target states < i
        # or itself.
        # We generate all functions f: [0,k) x {0,1} -> {0..k-1} with
        # f(0,0)=0 and f(i,x) <= i (BFS-canonical: targets of state i
        # are among states 0..i).
        def rec(i, rows):
            if i == k:
                yield tuple(rows)
                return
            if i == 0:
                # row 0: [0][0] must be 0; [0][1] can be 0 or 1
                for t1 in (0, 1):
                    rows0 = [0, t1]
                    yield from rec(1, rows + [rows0])
            else:
                # targets in 0..i
                for t0 in range(0, i + 1):
                    for t1 in range(0, i + 1):
                        yield from rec(i + 1, rows + [[t0, t1]])
        yield from rec(0, [])


# ---------------------------------------------------------------------
# Reverse NFA -> DFA (right half-tape)
# ---------------------------------------------------------------------

def build_right_nfa(table, n_states, n_symbols):
    """NFA over tapes read right-to-head.

    States are machine states.  A tape string s (read from far right
    towards the head) is accepted if starting from the head and moving
    left through that tape eventually reaches a halting transition.
    """
    # delta[q] = list of (symbol, q2) pairs for transitions in state q
    delta = {q: [] for q in range(n_states)}
    for q in range(n_states):
        for x in range(n_symbols):
            tr = table.get((q, x))
            if tr is None:
                # halting transition: accept immediately
                delta[q].append(("HALT", None))
            else:
                w, move, q2 = tr
                if move == -1:
                    delta[q].append((w, q2))
    return delta


def reverse_determinize(delta, n_states):
    """Build a DFA that accepts the reverse language (far-to-head)."""
    # Start states of the reverse NFA: states from which HALT is
    # reachable by reading a finite tape.
    # We compute the set of NFA states that can reach HALT via the
    # reversed transition relation.
    rev = {q: [] for q in range(n_states)}
    for q in range(n_states):
        for sym, q2 in delta[q]:
            if sym == "HALT":
                continue
            rev[q2].append((sym, q))

    # reverse NFA accepts tapes that, read far-to-head, drive the
    # machine from some state to a halting transition.  Start states are
    # those with a HALT transition on some symbol (any symbol).
    starts = set()
    for q in range(n_states):
        for sym, q2 in delta[q]:
            if sym == "HALT":
                starts.add(q)

    # subset construction
    def move(S, x):
        T = set()
        for q in S:
            for sym, q2 in rev.get(q, ()):
                if sym == x:
                    T.add(q2)
        return frozenset(T)

    start_set = frozenset(starts) if starts else frozenset()
    dfa = {}
    order = []
    idx = {start_set: 0}
    order.append(start_set)
    dfa[0] = [None, None]
    i = 0
    while i < len(order):
        S = order[i]
        for x in (0, 1):
            T = move(S, x)
            if not T:
                dfa[i][x] = None
            else:
                if T not in idx:
                    idx[T] = len(order)
                    order.append(T)
                    dfa[idx[T]] = [None, None]
                dfa[i][x] = idx[T]
        i += 1
    return dfa, len(order)


# ---------------------------------------------------------------------
# Context closure
# ---------------------------------------------------------------------

def close_contexts(table, n_states, left, right):
    """Close the context set.  Returns (contexts, halting_forced)."""
    contexts = set()
    contexts.add((0, 0, 0, 0))
    frontier = deque([(0, 0, 0, 0)])
    while frontier:
        l, q, s, r = frontier.popleft()
        tr = table.get((q, s))
        if tr is None:
            # halting context: cannot be used
            return contexts, True
        w, move, q2 = tr
        if move == 1:
            l2 = left[l][w]
            if l2 is None:
                return contexts, True
            for r2 in range(len(right)):
                for s2 in (0, 1):
                    if right[r2][s2] == r:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in contexts:
                            contexts.add(ctx)
                            frontier.append(ctx)
        else:
            r2 = right[r][w]
            if r2 is None:
                return contexts, True
            for l2 in range(len(left)):
                for s2 in (0, 1):
                    if left[l2][s2] == l:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in contexts:
                            contexts.add(ctx)
                            frontier.append(ctx)
    return contexts, False


# ---------------------------------------------------------------------
# Main decider
# ---------------------------------------------------------------------

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None

    delta = build_right_nfa(table, n_states, n_symbols)
    right_nfa, n_rnfa = reverse_determinize(delta, n_states)
    # right automaton is read far-to-head; the kernel's `right` table is
    # read far-to-head as well, so it can be used directly.
    right = right_nfa

    for left in enumerate_dfas(MAX_STATES):
        if len(left) > 200:
            continue
        # quick prune: state 0 must loop on 0
        if left[0][0] != 0:
            continue
        # no halting context should be forced
        contexts, halting = close_contexts(table, n_states, left, right)
        if halting:
            continue
        # emit certificate
        cert_contexts = [[list(c) for c in contexts]]
        cert = {
            "kind": "cps",
            "left": [list(row) for row in left],
            "right": [list(row) for row in right],
            "contexts": [list(c) for c in contexts],
        }
        try:
            check(tm, cert)
            return cert
        except Reject:
            continue
        except Exception:
            continue
    return None


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(decide(sys.argv[1]))