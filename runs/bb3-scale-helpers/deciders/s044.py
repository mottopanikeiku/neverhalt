import sys
from neverhalt.tm import parse, run

# Fast step function: simulate a machine and record (state, pos, tape) at each step.
def sim_states(tm):
    table, ns, nsym = parse(tm)
    tape = {}
    pos = 0
    state = 0
    out = []
    for _ in range(200):
        out.append((state, pos, dict(tape)))
        if (state, tape.get(pos, 0)) not in table:
            return out, True
        w, mv, nxt = table[(state, tape.get(pos, 0))]
        tape[pos] = w
        pos += mv
        state = nxt
    return out, False

def find_cycle(tm):
    seq, halted = sim_states(tm)
    if halted:
        return None
    for i in range(len(seq)):
        for j in range(i + 1, len(seq)):
            si, pi, ti = seq[i]
            sj, pj, tj = seq[j]
            if si != sj:
                continue
            d = pj - pi
            # check translation of tape over window
            ok = True
            for y in range(min(pi, pj), max(pi, pj) + 1):
                if ti.get(y, 0) != tj.get(y + d, 0):
                    ok = False
                    break
            if not ok:
                continue
            # also verify state at i and j same (already) and no halt between
            # build certificate
            return {"kind": "cycle", "t": i, "p": j - i}
    return None

def build_automaton(n_states, n_symbols, rules):
    # rules: dict (state, symbol) -> next state or None
    table = []
    for s in range(n_states):
        row = []
        for x in range(n_symbols):
            nxt = rules.get((s, x), None)
            row.append(nxt)
        table.append(row)
    return table

def push_from_table(table, blank=0):
    def push(state, symbol):
        nxt = table[state][symbol]
        return nxt
    return push

def try_cps(tm, max_states=3, cap=200000):
    from neverhalt.helpers import closure
    table, ns, nsym = parse(tm)
    # Automaton states: 0 = all blank, 1..max_states are "remember last k cells"
    # Simple n-gram: state encodes last k symbols read (only cells written before head matter).
    # We'll try all transition tables with n_states states where state 0 loops on 0.
    # Enumerate all functions for states 1..n_states-1 on symbol 0 and 1.
    import itertools
    # To keep it fast, restrict to small state counts.
    for nstates in range(1, max_states + 1):
        # state 0 must map to 0 on symbol 0
        # enumerate transitions for states 1..nstates-1 (each 2 choices) and state 0 on symbol 1
        others = list(range(1, nstates))
        choices = []
        for s in others:
            for x in (0, 1):
                choices.append((s, x))
        # state 0 on symbol 1 also variable
        choices.append((0, 1))
        total = len(choices)
        if total > 20:
            continue
        for bits in itertools.product(range(nstates), repeat=total):
            rules = {}
            for (s, x), v in zip(choices, bits):
                rules[(s, x)] = v
            # state 0 on 0 is 0
            rules[(0, 0)] = 0
            # ensure all transitions defined
            lut = build_automaton(nstates, 2, rules)
            push = push_from_table(lut, blank=0)
            blank = 0
            # closure expects push_left, push_right, blank_left, blank_right
            try:
                cert = closure(push, push, blank, blank, cap=cap)
            except Exception:
                cert = None
            if cert is not None:
                return cert
    return None

def decide(tm):
    # First try simple cycle detection (covers some survivors)
    c = find_cycle(tm)
    if c is not None:
        return c
    # Then try CPS with small automata
    cert = try_cps(tm, max_states=3, cap=200000)
    if cert is not None:
        return cert
    return None