NAME = "cyclers"

from neverhalt.tm import parse


def decide(tm, limit=1000):
    """Exact repetition of a whole configuration, found with a checkpoint that doubles its distance (Brent)."""
    table, _, _ = parse(tm)
    tape, q, pos = {}, 0, 0
    mark, mark_step, next_mark = (0, 0, {}), 0, 1
    for step in range(1, limit + 1):
        tr = table.get((q, tape.get(pos, 0)))
        if tr is None:
            return None
        w, d, q = tr
        if w:
            tape[pos] = w
        else:
            tape.pop(pos, None)
        pos += d
        if q == mark[0] and pos == mark[1] and tape == mark[2]:
            return {"kind": "cycle", "t": mark_step, "p": step - mark_step}
        if step == next_mark:
            mark, mark_step, next_mark = (q, pos, dict(tape)), step, next_mark * 2
    return None
