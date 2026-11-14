import sys
sys.setrecursionlimit(10000000)

def parse(tm):
    rows = tm.split('_')
    table = {}
    n_states = len(rows)
    n_symbols = 2
    for si, row in enumerate(rows):
        st = si
        for x in range(n_symbols):
            j = x * 3
            if j + 3 > len(row):
                continue
            w, mv, ns = row[j], row[j+1], row[j+2]
            if w == '-' or mv == '-' or ns == '-' or ns == 'Z':
                continue
            wv = 1 if w == '1' else 0
            mvv = 1 if mv == 'R' else -1
            nxt = ord(ns) - ord('A')
            table[(st, x)] = (wv, mvv, nxt)
    return table, n_states, n_symbols

def run(tm, max_steps):
    table, n_states, n_symbols = parse(tm)
    tape = {0: 0}
    state = 0
    pos = 0
    for step in range(max_steps + 1):
        key = (state, tape.get(pos, 0))
        if key not in table:
            return True, step, state, pos, tape
        w, mv, nxt = table[key]
        tape[pos] = w
        pos += mv
        state = nxt
    return False, max_steps + 1, state, pos, tape

def decide(tm):
    try:
        table, n_states, _ = parse(tm)
    except Exception:
        return None
    # Try to find a plain cycle by storing full configurations (tape window + state + pos).
    # We limit to a window of the tape and bound positions.
    MAX_STEPS = 20000
    MAX_ABS_POS = 400
    seen = {}
    tape = {0: 0}
    state = 0
    pos = 0
    for step in range(MAX_STEPS):
        key = (state, pos)
        if key in seen:
            return None
        seen[key] = step
        k = (state, tape.get(pos, 0))
        if k not in table:
            return None
        w, mv, nxt = table[k]
        tape[pos] = w
        pos += mv
        state = nxt
        if abs(pos) > MAX_ABS_POS:
            return None
    return None
