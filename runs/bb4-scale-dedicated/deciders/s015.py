import sys
from collections import deque
from neverhalt.tm import parse, run

# ---------- helpers ----------

def load(tm):
    table, ns, nsym = parse(tm)
    return table, ns

def step_state(table, q, s):
    """Return (w, move, q2) or None if halting."""
    return table.get((q, s))

def simulate_steps(table, q, pos, tape, n):
    """Run n steps; return (halted, q, pos, tape) where tape is dict pos->sym."""
    for _ in range(n):
        s = tape.get(pos, 0)
        t = table.get((q, s))
        if t is None:
            return True, q, pos, tape
        w, mv, q2 = t
        if tape.get(pos, 0) == w:
            pass
        else:
            tape[pos] = w
        pos += mv
        q = q2
    return False, q, pos, tape

def tape_snapshot(tape, lo, hi):
    return [tape.get(y, 0) for y in range(lo, hi + 1)]

def tape_has_content(tape, lo, hi):
    return any(tape.get(y, 0) != 0 for y in range(lo, hi + 1))

def find_tcycle(tm, table, ns):
    """Search for translated cycle of the form: state at T and T+P same,
    tape shifted by d, window reproduced, far side blank."""
    # run a base of steps then look for laps
    # We simulate up to a base limit, then try increasing lap lengths.
    base = 200
    for T in (base, 300, 500, 800, 1200):
        halted, q, pos, tape = simulate_steps(table, 0, 0, {}, T)
        if halted:
            continue
        # collect positions visited in a lap
        for P in range(1, 400):
            # run lap
            halted2, q2, pos2, tape2 = step_state_wrap(table, q, pos, tape.copy())
            # easier: re-simulate from T to T+P
            # (we already have state at T)
            tape_lap = dict(tape)
            qq, pp = q, pos
            positions = []
            ok = True
            for i in range(P):
                s = tape_lap.get(pp, 0)
                t = table.get((qq, s))
                if t is None:
                    ok = False
                    break
                w, mv, qq2 = t
                if tape_lap.get(pp, 0) != w:
                    tape_lap[pp] = w
                pp += mv
                qq = qq2
                positions.append(pp)
            if not ok:
                continue
            # condition: state same
            if qq != q:
                continue
            d = pp - pos
            lo = min([pos] + positions)
            hi = max([pos] + positions)
            # tape shifted comparison: tape2[y+d] == tape[y] for y in [lo,hi]
            good = True
            for y in range(lo, hi + 1):
                if tape.get(y, 0) != tape_lap.get(y + d, 0):
                    good = False
                    break
            if not good:
                continue
            # far-side blank conditions
            if d > 0:
                # every cell right of hi is blank at T+P
                for y in range(hi + 1, hi + 1 + abs(d) + 200):
                    if tape_lap.get(y, 0) != 0:
                        good = False
                        break
                if not good:
                    continue
            elif d < 0:
                for y in range(lo - 1 - abs(d) - 200, lo):
                    if tape_lap.get(y, 0) != 0:
                        good = False
                        break
                if not good:
                    continue
            # d == 0 plain cycle
            if d == 0:
                return {"kind": "cycle", "t": T, "p": P}
            return {"kind": "cycle", "t": T, "p": P}
    return None

def step_state_wrap(table, q, pos, tape):
    s = tape.get(pos, 0)
    t = table.get((q, s))
    return t

# ---------- cps search ----------

def build_automaton_from_table(n, trans):
    """trans: list of rows, each row list of length 2 or None.
    Returns left/right table as list of lists (or None entries)."""
    return [list(row) for row in trans]

def is_valid_automaton(trans, n):
    # state 0 loops on 0
    if trans[0][0] != 0:
        return False
    return True

def enumerate_dfa_tables(nstates, nsym=2, maxlen=None):
    """Enumerate all transition tables for nstates states, symbols 0..nsym-1.
    Yield list of rows: row[q][s] = next state (int) or None (dead)."""
    # total transitions: nstates*nsym, each can be 0..nstates-1 or None
    # We generate in a canonical order: for state 0 symbol 0 must be 0.
    # Use product generation.
    choices = []
    for q in range(nstates):
        for s in range(nsym):
            if q == 0 and s == 0:
                choices.append([0])
            else:
                choices.append(list(range(nstates)) + [None])
    # recursive product
    def rec(idx, cur):
        if idx == len(choices):
            yield [cur[q*nsym:(q+1)*nsym] for q in range(nstates)]
            return
        for v in choices[idx]:
            cur.append(v)
            yield from rec(idx + 1, cur)
            cur.pop()
    yield from rec(0, [])

def closure_contexts(tm, table, left, right, max_states=200000):
    """Compute smallest closed context set. Returns (contexts, closed) or None."""
    ns = len(left)
    # contexts: set of (l, q, s, r)
    start = (0, 0, 0, 0)
    seen = set([start])
    stack = [start]
    contexts = set()
    while stack:
        (l, q, s, r) = stack.pop()
        contexts.add((l, q, s, r))
        t = table.get((q, s))
        if t is None:
            return None  # halting context
        w, mv, q2 = t
        if mv > 0:
            # right move: l2 = left[l][w]; r2,s2 with right[r2][s2] == r
            l2 = left[l][w]
            if l2 is None:
                return None
            for r2 in range(len(right)):
                for s2 in range(2):
                    if right[r2][s2] == r:
                        nxt = (l2, q2, s2, r2)
                        if nxt not in seen:
                            seen.add(nxt)
                            stack.append(nxt)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(len(left)):
                for s2 in range(2):
                    if left[l2][s2] == l:
                        nxt = (l2, q2, s2, r2)
                        if nxt not in seen:
                            seen.add(nxt)
                            stack.append(nxt)
        if len(contexts) > max_states:
            return None
    return contexts

def make_cps_certificate(tm, table, left, right, contexts):
    left_out = [[left[i][s] for s in range(2)] for i in range(len(left))]
    right_out = [[right[i][s] for s in range(2)] for i in range(len(right))]
    ctx_out = [[l, q, s, r] for (l, q, s, r) in contexts]
    return {"kind": "cps", "left": left_out, "right": right_out, "contexts": ctx_out}

def decide(tm):
    try:
        table, ns = load(tm)
    except Exception:
        return None
    # 1) translated cycle attempt
    c = find_tcycle(tm, table, ns)
    if c is not None:
        return c
    # 2) half-tape DFA search: enumerate left automata with up to 3 states
    #    and try to close contexts. This is expensive; limit work.
    import time
    t0 = time.time()
    for nstates in (1, 2, 3):
        count = 0
        for left in enumerate_dfa_tables(nstates):
            # quick validity: state 0 loops on 0
            if not is_valid_automaton(left, nstates):
                continue
            # try right automata with same size (or up to nstates)
            for nstates_r in (nstates,):
                for right in enumerate_dfa_tables(nstates_r):
                    if not is_valid_automaton(right, nstates_r):
                        continue
                    ctx = closure_contexts(tm, table, left, right)
                    if ctx is not None:
                        # check no halting context (closure_contexts already rejects halting)
                        return make_cps_certificate(tm, table, left, right, ctx)
                    count += 1
                    if time.time() - t0 > 0.35:
                        return None
    return None

if __name__ == "__main__":
    import sys
    for line in sys.stdin:
        tm = line.strip()
        if not tm:
            continue
        cert = decide(tm)
        print(tm, cert)