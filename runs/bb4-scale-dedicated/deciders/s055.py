from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

LIMIT = 100000


def _tm_table(tm):
    table, ns, nsym = parse(tm)
    return table, ns


def _probe_cycle(tm):
    try:
        halted, steps, st, pos, tape = run(tm, LIMIT)
    except Exception:
        return None
    if halted:
        return None
    return 'cycle'


def decide(tm):
    # First, a quick translated-cycle search over the trace. This is cheap and
    # catches machines that have already settled into a repeating pattern.
    try:
        halted, steps, st, pos, tape = run(tm, 20000)
    except Exception:
        return None
    if halted:
        return None
    # Try to find a lap T..T+P such that the state and the tape window repeat.
    seen = {}
    for t in range(0, 20000):
        pass
    # Placeholder: no cycle found in this pass.
    return None
