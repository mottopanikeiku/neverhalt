import sys
from collections import defaultdict

def search(target):
    # --- parse target into a binary grid ---
    if isinstance(target, str):
        raw = target.split('\n')
    else:
        raw = list(target)
    grid = []
    for line in raw:
        if line is None:
            continue
        line = line.rstrip('\n').rstrip('\r')
        grid.append([1 if ch == '#' else 0 for ch in line])
    H = len(grid)
    if H == 0:
        return '0RA'
    W = max(len(r) for r in grid)
    for r in grid:
        r.extend([0] * (W - len(r)))
    n_trans = H - 1
    if n_trans <= 0:
        return '0RA'

    # --- extract execution trace from consecutive-row diffs ---
    halt_at = None
    diffs = []
    for t in range(n_trans):
        d = [c for c in range(W) if grid[t][c] != grid[t + 1][c]]
        if len(d) == 0 and halt_at is None:
            halt_at = t
        diffs.append(d)
    T = halt_at if halt_at is not None else n_trans
    if T <= 0:
        return '0RA'

    pos = []
    for t in range(T):
        if len(diffs[t]) == 0:
            return '0RA'
        pos.append(diffs[t][0])

    r = [grid[t][pos[t]] for t in range(T)]
    w = [grid[t + 1][pos[t]] for t in range(T)]
    mv = [0] * T
    for t in range(T - 1):
        d = pos[t + 1] - pos[t]
        mv[t] = 1 if d > 0 else (-1 if d < 0 else -9)
    mv[T - 1] = -9  # final move unobservable

    # --- partition-refine states so each (state, symbol) is consistent ---
    n = T
    sid = [0] * n
    prev = 0
    for _ in range(n + 5):
        sig = {}
        new = [0] * n
        for t in range(n):
            key = (sid[t], r[t], w[t], mv[t], sid[t + 1] if t + 1 < n else -1)
            if key not in sig:
                sig[key] = len(sig)
            new[t] = sig[key]
        cnt = len(sig)
        if cnt == prev:
            sid = new
            break
        prev = cnt
        sid = new

    # --- collect per-state behaviour ---
    beh = {}
    for t in range(n):
        b = sid[t]
        d = beh.setdefault(b, {})
        rr, ww, mm = r[t], w[t], mv[t]
        nb = sid[t + 1] if t + 1 < n else None
        if rr in d:
            e = d[rr]
            if e[1] == -9 and mm != -9:
                e[1] = mm
            if nb is not None:
                e[2] = nb
        else:
            d[rr] = [ww, mm, nb]

    distinct = []
    for t in range(n):
        if sid[t] not in distinct:
            distinct.append(sid[t])
    letter = {sid[0]: 'A'}
    for b in distinct:
        if b not in letter:
            letter[b] = chr(ord('B') + len(letter) - 1)

    trans = {}
    for t in range(n):
        b = sid[t]
        L = letter[b]
        rr = r[t]
        e = beh[b][rr]
        ww, mm, nb = e
        Lnb = letter[nb] if nb is not None else None
        key = (L, rr)
        if key in trans:
            cur = trans[key]
            if cur[1] == -9 and mm != -9:
                cur[1] = mm
            if cur[2] is None and Lnb is not None:
                cur[2] = Lnb
        else:
            trans[key] = [ww, mm, Lnb]

    for L in letter.values():
        for rr in (0, 1):
            if (L, rr) in trans and trans[(L, rr)][1] == -9:
                trans[(L, rr)][1] = 1

    # --- serialise state rows in A,B,C... order ---
    parts = []
    for b in distinct:
        L = letter[b]
        row = ''
        for rr in (0, 1):
            key = (L, rr)
            if key in trans:
                ww, mm, Lnb = trans[key]
                if Lnb is None:
                    row += "%d%s%s" % (ww, 'R' if mm > 0 else 'L', L)
                else:
                    row += "%d%s%s" % (ww, 'R' if mm > 0 else 'L', Lnb)
            else:
                row += '---'
        parts.append(row)
    return '_'.join(parts)

