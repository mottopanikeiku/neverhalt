NAME = "small automata search"

from itertools import product

from neverhalt.helpers import closure
from neverhalt.tm import parse


def automata(m, k):
    """Every transition table with m states over k symbols in which the blank state 0 loops on 0."""
    for rest in product(range(m), repeat=m * k - 1):
        flat = (0,) + rest
        yield [flat[i * k:(i + 1) * k] for i in range(m)]


def decide(tm, max_states=3):
    """Try every pair of small automata; the kernel only needs one closed set."""
    table, _, k = parse(tm)
    for m in range(1, max_states + 1):
        tables = list(automata(m, k))
        for dl in tables:
            push_left = lambda st, x, dl=dl: dl[st][x]
            for dr in tables:
                cert = closure(table, k, push_left, lambda st, x, dr=dr: dr[st][x], 0, 0, cap=400)
                if cert:
                    return cert
    return None
