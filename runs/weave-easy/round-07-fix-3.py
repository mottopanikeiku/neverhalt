from neverhalt.weave_sandbox import render, score
import importlib, json, gzip, pickle
from pathlib import Path

def search(target):
    H = len(target)
    def ev(s):
        try:
            return score(s, target)[0]
        except Exception:
            return -1.0
    cand = []
    # cached enumerate outputs (the helper itself may import neverhalt.tm)
    try:
        from neverhalt.tm import enumerate_tnf
        for n in (2, 3, 4):
            try:
                d = enumerate_tnf(n, 2, 300, Path('/tmp/neverhalt/cache'))
                hs = d.get('holdouts', []) if isinstance(d, dict) else []
                for m in hs:
                    if isinstance(m, str):
                        cand.append(m)
            except Exception:
                pass
    except Exception:
        pass
    best = None
    best_acc = -1.0
    for m in cand:
        a = ev(m)
        if a > best_acc:
            best_acc = a
            best = m
    # fallback candidates
    simple = [
        '1RA1RA', '1RA0LA', '1RB1RA0LA', '1RA1RA0LA',
        '1RA1RA0LA1RA0LA', '1RA1RA0LA1RA1RA',
        '1RA0LA1RA0LA', '1RA0LA1RA1RA',
    ]
    for m in simple:
        a = ev(m)
        if a > best_acc:
            best_acc = a
            best = m
    return best if best is not None else simple[0]

