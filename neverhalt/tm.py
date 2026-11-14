"""Turing machines in bbchallenge notation, e.g. the BB(2) champion '1RB1LB_1LA---'.

One row per state (A, B, ...), three characters per read symbol: write, move, next state.
'---' (or a jump to a state that does not exist, e.g. Z) is an undefined transition: the
machine HALTS there, and that final transition counts as a step (bbchallenge convention).
Machines start in state A at cell 0 of an all-zero, two-way infinite tape.
"""
from __future__ import annotations


def parse(tm: str):
    """-> (table, n_states, n_symbols); table[(state, symbol)] = (write, move, next), move = +1 | -1.

    Halting transitions are simply absent from the table.
    """
    rows = tm.strip().split("_")
    n = len(rows)
    k, rem = divmod(len(rows[0]), 3)
    if k < 2 or rem or any(len(r) != 3 * k for r in rows):
        raise ValueError(f"malformed machine {tm!r}")
    table = {}
    for q, row in enumerate(rows):
        for s in range(k):
            w, d, t = row[3 * s], row[3 * s + 1], row[3 * s + 2]
            if d in "LR" and w.isdigit() and int(w) < k and 0 <= ord(t) - 65 < n:
                table[(q, s)] = (int(w), 1 if d == "R" else -1, ord(t) - 65)
    return table, n, k


def run(tm: str, max_steps: int):
    """Simulate from the blank tape -> (halted, steps, state, pos, tape).

    tape maps position -> non-zero symbol. If halted, steps includes the halting transition.
    """
    table, _, _ = parse(tm)
    tape, q, pos = {}, 0, 0
    for step in range(max_steps):
        tr = table.get((q, tape.get(pos, 0)))
        if tr is None:
            return True, step + 1, q, pos, tape
        w, d, q = tr
        if w:
            tape[pos] = w
        else:
            tape.pop(pos, None)
        pos += d
    return False, max_steps, q, pos, tape


def diagram(tm: str, steps: int = 48, max_width: int = 56) -> str:
    """ASCII space-time diagram, one line per step. '.' = 0, '#' = 1 (digits beyond that).

    The head is drawn as its state letter: lowercase over a 0, uppercase over a non-zero cell.
    """
    table, _, _ = parse(tm)
    tape, q, pos = {}, 0, 0
    rows, halted = [], False
    for _ in range(steps + 1):
        rows.append((q, pos, dict(tape)))
        tr = table.get((q, tape.get(pos, 0)))
        if tr is None:
            halted = True
            break
        w, d, q = tr
        if w:
            tape[pos] = w
        else:
            tape.pop(pos, None)
        pos += d
    lo = min(min(p for _, p, _ in rows), min((min(t) for _, _, t in rows if t), default=0))
    hi = max(max(p for _, p, _ in rows), max((max(t) for _, _, t in rows if t), default=0))
    if hi - lo + 1 > max_width:  # keep the side the head ends on
        if rows[-1][1] - lo > hi - rows[-1][1]:
            lo = hi - max_width + 1
        else:
            hi = lo + max_width - 1
    lines = []
    for i, (q, p, t) in enumerate(rows):
        cells = []
        for x in range(lo, hi + 1):
            s = t.get(x, 0)
            if x == p:
                cells.append(chr(65 + q) if s else chr(97 + q))
            else:
                cells.append("." if s == 0 else "#" if s == 1 else str(s))
        lines.append(f"{i:>4} {''.join(cells)}")
    if halted:
        lines.append("     HALT")
    return "\n".join(lines)
