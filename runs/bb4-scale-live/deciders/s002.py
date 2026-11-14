from neverhalt.tm import parse, run
from neverhalt.kernel import Reject

# Decider: hunt for translated cycles (tcycle) in machines that look like
# they are sweeping a growing pattern.  We look for two times t < T where the
# window of non-blank cells has exactly the same shape shifted by d cells and
# the head state matches; the kernel then checks the full certificate.

import sys

MAX = 3000

def _snap(state, pos, tape):
    if not tape:
        return (state, 0, ())
    lo = min(tape)
    hi = max(tape)
    return (state, pos, tuple((y, tape[y]) for y in range(lo, hi + 1)))

def decide(tm: str):
    try:
        (table, nstates, nsym) = parse(tm)
    except Exception:
        return None
    # quick run to see if we halt
    halted, steps, state, pos, tape = run(tm, 400)
    if halted:
        return None

    # keep a history of (state, pos, sorted tape items) up to MAX
    hist = []
    state, pos = 0, 0
    tape = {}
    for _ in range(MAX):
        # record
        if tape:
            items = tuple(sorted(tape.items()))
        else:
            items = ()
        hist.append((state, pos, items))
        if (state, 0) in table:
            w, mv, ns = table[(state, 0)]
            if w == 0:
                tape.pop(pos, None)
            else:
                tape[pos] = w
            pos += mv
            state = ns
        else:
            # halted
            return None

    # try to find a translated cycle: same state, same tape pattern shifted by d
    # We compare the tape window shape: a tuple of (offset, symbol) relative to min key.
    def shape(items):
        if not items:
            return ()
        lo = items[0][0]
        return tuple((y - lo, v) for y, v in items)

    # build shape index
    idx = {}
    for t in range(MAX):
        st, p, items = hist[t]
        sh = shape(items)
        idx.setdefault((st, sh), []).append(t)

    # for each candidate pair, try to build a certificate for the kernel
    # We only attempt when the shapes match exactly; the kernel will verify
    # the head position relation and blank tails.
    for t in range(MAX):
        st, p, items = hist[t]
        sh = shape(items)
        # find the next occurrence of the same shape and state
        for t2 in idx.get((st, sh), [])[1:]:
            if t2 - t > 4000:
                break
            # candidate lap length
            P = t2 - t
            # head displacement over the lap
            st2, p2, items2 = hist[t2]
            d = p2 - p
            # build the certificate using the kernel's rules and let it check.
            # We need the tape contents at T and T+P over [lo, hi] of the lap.
            # The kernel simulates T steps and then P steps; we can just
            # construct the cert from our recorded history.
            # [lo, hi] of the lap: positions of head during (t, t2].
            lo = min(p for _, pp, _ in hist[t:t2]) if t2 > t else p
            hi = max(p for _, pp, _ in hist[t:t2]) if t2 > t else p
            # tape at T: dict from hist[t][2]
            tapeT = dict(hist[t][2])
            # tape at T+P: dict from hist[t2][2]
            tapeTP = dict(hist[t2][2])
            cert = {"kind": "cycle", "t": t, "p": P}
            try:
                from neverhalt.kernel import check
                check(tm, cert)
                return cert
            except Reject:
                continue
            except Exception:
                continue
    return None

if __name__ == "__main__":
    import sys
    tm = sys.argv[1]
    c = decide(tm)
    print(c if c else "None")