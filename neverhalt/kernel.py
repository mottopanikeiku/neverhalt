"""THE TRUSTED KERNEL. Everything else in this repository (model, deciders, UI) is untrusted.

check(tm, cert) returns the verified certificate kind or raises Reject. A certificate is
accepted only if it proves that `tm` never halts from the blank tape. Two kinds:

cycle  {"kind": "cycle", "t": T, "p": P}
    Simulate T steps, then P more ("the lap"). Let d be the head displacement over the lap and
    [lo, hi] the head positions seen during it. Accept iff the machine does not halt, the state
    at T and T+P is the same, tape_{T+P}[y + d] == tape_T[y] for every y in [lo, hi], and, when
    d > 0 (d < 0), every cell right of hi (left of lo) is blank at T+P.
    Proof: by induction the lap repeats forever, shifted by d each time. The window content is
    reproduced d cells over; the cells entering the window on the far side are blank and were
    required to match blank cells of the pattern; nothing outside the window is ever read.
    d = 0 is a plain cycle (reported as kind "cycle"), d != 0 a translated cycle ("tcycle").

cps    {"kind": "cps", "left": [[a, b], ...], "right": [[a, b], ...], "contexts": [[l, q, s, r], ...]}
    A closed set of abstract configurations. "left" and "right" are the transition tables of two
    deterministic automata: left[i][x] is the state reached from state i on symbol x, or null if
    that never happens. State 0 is the all-blank half-tape, so left[0][0] == right[0][0] == 0.
    The left automaton reads the cells left of the head, from far away towards the head; the
    right automaton reads the cells right of the head, also from far away towards the head.
    A context [l, q, s, r] means: left half-tape in automaton state l, machine state q (A = 0),
    symbol s under the head, right half-tape in automaton state r.
    Accept iff [0, 0, 0, 0] is a context and every context [l, q, s, r] satisfies: the transition
    (q, s) -> (w, move, q2) exists (a halting context is rejected); for a right move, l2 =
    left[l][w] is not null and [l2, q2, s2, r2] is a context for EVERY pair (r2, s2) with
    right[r2][s2] == r; for a left move the mirror image: r2 = right[r][w] is not null and
    [l2, q2, s2, r2] is a context for EVERY pair (l2, s2) with left[l2][s2] == l.
    Proof: "the automaton states of the two half-tapes, with q and s, form a context" is an
    inductive invariant. Stepping right pushes the written symbol onto the left half-tape (one
    automaton step) and pops the nearest cell s2 off the right half-tape, whose remainder is in
    some state r2 with right[r2][s2] == r; all of those are covered. No context halts.
    Automata that remember the last n cells of each half-tape are one choice (n-gram CPS);
    counters and bouncers need automata that remember something else.
"""
from __future__ import annotations

from .tm import parse

MAX_STEPS = 100_000
MAX_CONTEXTS = 200_000
MAX_STATES = 5_000


class Reject(Exception):
    pass


def check(tm: str, cert) -> str:
    try:
        if not isinstance(cert, dict):
            raise Reject("certificate is not an object")
        kind = cert.get("kind")
        if kind == "cycle":
            return _cycle(tm, cert)
        if kind == "cps":
            return _cps(tm, cert)
        raise Reject(f"unknown certificate kind {kind!r}")
    except Reject:
        raise
    except Exception as e:  # malformed certificate data
        raise Reject(f"malformed certificate: {type(e).__name__}: {e}") from None


def _cycle(tm: str, cert: dict) -> str:
    table, _, _ = parse(tm)
    t, p = cert["t"], cert["p"]
    if type(t) is not int or type(p) is not int or t < 0 or p < 1:
        raise Reject("need integers t >= 0 and p >= 1")
    if t + p > MAX_STEPS:
        raise Reject(f"t + p exceeds the kernel budget of {MAX_STEPS} steps")
    tape, q, pos = {}, 0, 0
    snap = None
    lo = hi = 0
    for step in range(t + p):
        if step == t:
            snap = (q, pos, dict(tape))
            lo = hi = pos
        tr = table.get((q, tape.get(pos, 0)))
        if tr is None:
            raise Reject(f"machine halts at step {step + 1}")
        w, d, q = tr
        if w:
            tape[pos] = w
        else:
            tape.pop(pos, None)
        pos += d
        if step >= t:
            lo, hi = min(lo, pos), max(hi, pos)
    q1, pos1, tape1 = snap
    if q != q1:
        raise Reject("state at t and t+p differs")
    shift = pos - pos1
    for y in range(lo, hi + 1):
        if tape.get(y + shift, 0) != tape1.get(y, 0):
            raise Reject(f"lap window does not reappear (cell {y - pos1:+d} relative to the head at t)")
    if shift > 0 and any(x > hi for x in tape):
        raise Reject("non-blank cell to the right of the lap window")
    if shift < 0 and any(x < lo for x in tape):
        raise Reject("non-blank cell to the left of the lap window")
    return "cycle" if shift == 0 else "tcycle"


def _automaton(name: str, rows, k: int) -> dict:
    """Validate a transition table -> predecessor index {state: [(previous state, symbol), ...]}."""
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_STATES:
        raise Reject(f"`{name}` must list between 1 and {MAX_STATES} states")
    before: dict[int, list] = {}
    for i, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != k:
            raise Reject(f"`{name}[{i}]` must have one entry per symbol")
        for x, j in enumerate(row):
            if j is None:
                continue
            if type(j) is not int or not 0 <= j < len(rows):
                raise Reject(f"`{name}[{i}][{x}]` is not a state")
            before.setdefault(j, []).append((i, x))
    if rows[0][0] != 0:
        raise Reject(f"`{name}[0][0]` must be 0: state 0 is the blank half-tape")
    return before


def _cps(tm: str, cert: dict) -> str:
    table, n, k = parse(tm)
    left, right = cert["left"], cert["right"]
    before_left, before_right = _automaton("left", left, k), _automaton("right", right, k)
    if not isinstance(cert["contexts"], list) or len(cert["contexts"]) > MAX_CONTEXTS:
        raise Reject(f"`contexts` must be a list of at most {MAX_CONTEXTS} entries")
    contexts = set()
    for c in cert["contexts"]:
        if len(c) != 4 or any(type(x) is not int for x in c):
            raise Reject("a context is four integers [l, q, s, r]")
        l, q, s, r = c
        if not (0 <= l < len(left) and 0 <= q < n and 0 <= s < k and 0 <= r < len(right)):
            raise Reject("context out of range")
        contexts.add((l, q, s, r))
    if (0, 0, 0, 0) not in contexts:
        raise Reject("the blank starting configuration [0, 0, 0, 0] is not a context")
    for l, q, s, r in contexts:
        tr = table.get((q, s))
        if tr is None:
            raise Reject(f"context in state {chr(65 + q)} reading {s} is a halting transition")
        w, d, q2 = tr
        if d > 0:
            l2 = left[l][w]
            if l2 is None:
                raise Reject("not closed: the left automaton has no transition for a written symbol")
            for r2, s2 in before_right.get(r, ()):
                if (l2, q2, s2, r2) not in contexts:
                    raise Reject("not closed: successor context missing (right move)")
        else:
            r2 = right[r][w]
            if r2 is None:
                raise Reject("not closed: the right automaton has no transition for a written symbol")
            for l2, s2 in before_left.get(l, ()):
                if (l2, q2, s2, r2) not in contexts:
                    raise Reject("not closed: successor context missing (left move)")
    return "cps"
