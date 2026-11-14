import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def build_tables(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states, n_symbols

def step_info(table, n_states, n_symbols, q, s):
    key = (q, s)
    if key not in table:
        return None
    w, move, q2 = table[key]
    return w, move, q2

def make_dfa_remember(n_states, n_symbols):
    # 1-gram DFA: remember nothing; state 0 loops on symbol 0.
    trans = [[None] * n_symbols for _ in range(1)]
    trans[0][0] = 0
    return trans

def make_dfa_ngram(n, n_symbols):
    # states 0..2^n-1, state 0 = all blank. Transition on symbol x:
    # shift window; if n==1 state 0 loops on 0.
    size = 1 << n
    trans = [[None] * n_symbols for _ in range(size)]
    for st in range(size):
        for x in range(n_symbols):
            bit = (st >> 1) | ((x & 1) << (n - 1))
            trans[st][x] = bit
    return trans

def closure(t, transL, transR, n_states, n_symbols, max_states=200000):
    # fixed-point closed context set
    ctx = set()
    start = (0, 0, 0, 0)
    ctx.add(start)
    dq = deque([start])
    while dq and len(ctx) < max_states:
        l, q, s, r = dq.popleft()
        info = step_info(t, n_states, n_symbols, q, s)
        if info is None:
            return None
        w, move, q2 = info
        if move > 0:
            l2 = transL[l][w]
            if l2 is None:
                return None
            r2s = {}
            for r2 in range(len(transR)):
                for s2 in range(n_symbols):
                    if transR[r2][s2] == r:
                        r2s.setdefault((l2, q2, s2, r2), None)
            for nxt in r2s:
                if nxt not in ctx:
                    ctx.add(nxt)
                    dq.append(nxt)
        else:
            r2 = transR[r][w]
            if r2 is None:
                return None
            l2s = {}
            for l2 in range(len(transL)):
                for s2 in range(n_symbols):
                    if transL[l2][s2] == l:
                        l2s.setdefault((l2, q2, s2, r2), None)
            for nxt in l2s:
                if nxt not in ctx:
                    ctx.add(nxt)
                    dq.append(nxt)
    return ctx

def cert_from_ctx(tm, ctx, transL, transR):
    left = [[None] * len(transL[0]) for _ in range(len(transL))]
    for i in range(len(transL)):
        for j in range(len(transL[i])):
            if transL[i][j] is not None:
                left[i][j] = int(transL[i][j])
    right = [[None] * len(transR[0]) for _ in range(len(transR))]
    for i in range(len(transR)):
        for j in range(len(transR[i])):
            if transR[i][j] is not None:
                right[i][j] = int(transR[i][j])
    contexts = []
    for (l, q, s, r) in ctx:
        contexts.append([int(l), int(q), int(s), int(r)])
    return {"kind": "cps", "left": left, "right": right, "contexts": contexts}

def cps_search(tm, max_ngram=8):
    try:
        t, n_states, n_symbols = build_tables(tm)
    except Exception:
        return None
    # try 1-gram then ngram up to max_ngram on both sides
    for n in range(1, max_ngram + 1):
        L = make_dfa_ngram(n, n_symbols)
        R = make_dfa_ngram(n, n_symbols)
        ctx = closure(t, L, R, n_states, n_symbols)
        if ctx is not None:
            cert = cert_from_ctx(tm, ctx, L, R)
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
    return None

def decide(tm: str):
    cert = cps_search(tm, max_ngram=8)
    return cert

if __name__ == "__main__":
    tm = sys.argv[1] if len(sys.argv) > 1 else "1RB0LC_0LC1RA_---1LA"
    c = decide(tm)
    if c:
        try:
            print(check(tm, c))
        except Reject:
            print("REJECT")
    else:
        print("NONE")
