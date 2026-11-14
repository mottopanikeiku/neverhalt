NAME = "translated cyclers"

from neverhalt.tm import parse


def decide(tm, limit=4000):
    """Compare record-breaking moments: same state, same tape window behind the head."""
    table, _, _ = parse(tm)
    tape, q, pos = {}, 0, 0
    positions = [0]
    records = {}  # (side, state) -> [(time, pos, tape snapshot)]
    lo_all = hi_all = 0
    for step in range(limit):
        tr = table.get((q, tape.get(pos, 0)))
        if tr is None:
            return None
        w, d, q = tr
        if w:
            tape[pos] = w
        else:
            tape.pop(pos, None)
        pos += d
        positions.append(pos)
        t = step + 1
        side = 1 if pos > hi_all else -1 if pos < lo_all else 0
        hi_all, lo_all = max(hi_all, pos), min(lo_all, pos)
        if not side:
            continue
        earlier = records.setdefault((side, q), [])
        for t1, pos1, snap in reversed(earlier[-3:]):
            shift = pos - pos1
            lap = positions[t1:t + 1]
            lo, hi = min(lap), max(lap)
            if all(tape.get(y + shift, 0) == snap.get(y, 0) for y in range(lo, hi + 1)) and (
                    all(x <= hi for x in tape) if shift > 0 else all(x >= lo for x in tape)):
                return {"kind": "cycle", "t": t1, "p": t - t1}
        earlier.append((t, pos, dict(tape)))
    return None
