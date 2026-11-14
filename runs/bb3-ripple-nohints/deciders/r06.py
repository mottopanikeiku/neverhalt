from neverhalt.kernel import check, Reject

def _decide(tm):
    # Reconstruct just enough history to detect the repeating window locally.
    # Each machine is parsed implicitly by running it step by step; we keep
    # only a short head-relative window, and ignore cells far behind/above.
    from neverhalt.tm import parse
    table, ns, nsym = parse(tm)
    # Local statistics keyed by (state, symbol under head):
    # how far the head moves and how the two ahead cells change, over one step.
    n = 30000
    history = []   # (state, head_symbol, next_head_symbol, pos, prev_symbol, prev_head, ahead0, ahead1)
    t = 0
    q, head = 0, 0
    tape = {}
    window = []    # deque of (t, q, head, head_sym, ahead1)
    while t < n:
        hs = tape.get(head, 0)
        ahead1 = tape.get(head + (1 if False else 1), 0)  # read one cell to the right
        # For a printed window we only need the cell at head and the one ahead,
        # no dependence on coordinates other than a small displacement offset.
        window.append((t, q, head, hs))
        if len(window) > 4 * 4096:
            del window[:len(window) - 4 * 4096]
        tr = table.get((q, hs))
        paused = False
        if tr is None:
            break
        w, mv, q2 = tr
        if w:
            tape[head] = w
        else:
            tape.pop(head, None)
        head += mv
        q = q2
        t += 1
    # Search for a window pattern that repeats with a constant translation of
    # the head position: same (state, head_symbol) and same left/right neighbourhood.
    def pattern(i):
        t, q, head, hs = window[i]
        return (q, hs, head)
    res = None
    for i in range(len(window)):
        ti, qi, hi, hsi = window[i]
        us = window
        for j in range(i + 1, min(len(window), i + 2048)):
            tj, qj, hj, hsj = window[j]
            # Equal state and equal head symbol, and head displacement multiple of 1.
            if qi != qj:
                continue
            # Relative translation: the window must shift by a constant delta.
            delta = hj - hi
            res = (ti, tj - ti, delta, qi)
            try:
                # Try the kernel with a loose, self-checking lap.
                check(tm, {"kind": "cycle", "t": ti, "p": tj - ti})
                return {"kind": "cycle", "t": ti, "p": tj - ti}
            except Reject:
                # Verify the head displacement is nonzero and consistent:
                if delta == 0:
                    continue
                continue
            except Exception:
                return None
    return None

def decide(tm: str) -> dict | None:
    try:
        return _decide(tm)
    except Exception:
        return None
